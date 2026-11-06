"""The safe append (VFX sheet_tools.append + docs/prompts/04_add_to_sheets.md), with the rules from CLAUDE.md:

  1. Re-read ALL checked tabs before EVERY batch (default 8 rows). Skip duplicates, companies at the cap, excluded countries, empty evidence, no profile URL.
  2. Stop if the header differs from the configured columns, or if blank rows exist in the data (an append would land mid-sheet). Never delete them.
  3. Verify each landing range and read the rows back after writing.
  4. Colour ONLY our own rows (white background, black text), one row at a time.
  5. NEVER retry a write. If an append call errors, stop: the outcome is unknown. `find_landed` then reads the tail to see what arrived,
     and `write_missing_csv` produces a new CSV with only the missing rows.
  6. Our own rows are logged (appended_rows) the moment they are confirmed, before the colouring step.
There is no delete, reorder or edit of existing rows anywhere in this module."""
from __future__ import annotations

import csv
import datetime
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import PipelineConfig
from .dedupe import SheetState, check_rows, name_key, norm, pad, read_state, url_key
from .sheets import SheetsClient, SheetsWriteError, col_letter, quote_tab


class AppendStop(Exception):
    """A safety stop. Nothing further is written. `landed` lists rows (row number, values) that DID get written before the stop."""

    def __init__(self, message: str, landed: list | None = None, unknown: list | None = None):
        super().__init__(message)
        self.landed, self.unknown = landed or [], unknown or []     # unknown: rows whose write outcome is not known


@dataclass
class Report:
    added: list[tuple[int, list[str]]] = field(default_factory=list)          # (sheet row number, row)
    skipped: list[tuple[str, str, str]] = field(default_factory=list)         # (company, name, reason)
    batches: int = 0
    warnings: list[str] = field(default_factory=list)
    unwhitened: list[int] = field(default_factory=list)
    stopped: str = ""

    @property
    def rows(self) -> str:
        return f"{self.added[0][0]}-{self.added[-1][0]}" if self.added else "none"


# ------------------------------------------------------------------ CSV (UTF-8, NO BOM)
def write_review_csv(path: Path, header: list[str], rows: list[list[str]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:           # "utf-8", not "utf-8-sig": a BOM breaks the header check
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        w.writerow(header)
        w.writerows(rows)
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")
    return path


def read_review_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with open(path, encoding="utf-8-sig", newline="") as f:               # tolerate a BOM written by other tools
        src = list(csv.reader(f))
    return (src[0], src[1:]) if src else ([], [])


# ------------------------------------------------------------------ helpers
def _rgb(name: str) -> dict:
    named = {"white": (1, 1, 1), "black": (0, 0, 0)}
    if name.lower() in named:
        r, g, b = named[name.lower()]
    else:
        m = re.fullmatch(r"#?([0-9a-fA-F]{6})", name)
        if not m:
            raise ValueError(f"colour '{name}' must be white, black or #RRGGBB")
        r, g, b = (int(m.group(1)[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return {"red": r, "green": g, "blue": b}


def whiten_requests(cfg: PipelineConfig, sheet_id: int, rownums: list[int]) -> list[dict]:
    """One repeatCell per row we appended, columns A..last only. Never a range that could hold anyone else's rows."""
    c = cfg.output.colour_own_rows
    fmt = {"backgroundColor": _rgb(c.background), "textFormat": {"foregroundColor": _rgb(c.text)}}
    width = len(cfg.output.columns)
    return [{"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": n - 1, "endRowIndex": n, "startColumnIndex": 0, "endColumnIndex": width},
                            "cell": {"userEnteredFormat": fmt}, "fields": "userEnteredFormat(backgroundColor,textFormat.foregroundColor)"}} for n in rownums]


def preflight(client: SheetsClient, cfg: PipelineConfig) -> list[list[str]]:
    """Read the write tab and enforce: header == configured columns, no blank rows inside the data. Returns the values."""
    v = client.get_values(cfg.output.write_tab.range)
    cols = cfg.output.columns
    if not v or v[0] != cols:
        raise AppendStop("the sheet's header does not match the configured columns (or the tab is empty); stopping. Nothing was written")
    blanks = [j + 1 for j, r in enumerate(v) if j and not any(str(c).strip() for c in r)]
    if blanks:
        raise AppendStop(f"blank rows at {blanks[:8]}: an append would land mid-sheet. Ask the sheet owner; this app never deletes rows. Nothing was written")
    return v


def take_baseline(client: SheetsClient, cfg: PipelineConfig) -> dict:
    v = client.get_values(cfg.output.write_tab.range)
    return {"tab": cfg.output.write_tab.name, "data_rows": max(0, len(v) - 1), "non_empty_rows": sum(1 for r in v[1:] if any(str(c).strip() for c in r)),
            "last_row": len(v), "last_row_name": (v[-1] + [""])[0] if v else "", "taken_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}


def progress(baseline: dict, own_rows: int, current_values: list[list[str]]) -> dict:
    """Progress is baseline + our own append log. Rows other people added are reported separately and never counted as ours."""
    current = max(0, len(current_values) - 1)
    return {"baseline": baseline["data_rows"], "ours": own_rows, "current": current, "added_by_others": max(0, current - baseline["data_rows"] - own_rows)}


# ------------------------------------------------------------------ dry run (read-only)
def dry_run(client: SheetsClient, cfg: PipelineConfig, rows: list[list[str]]) -> Report:
    """What would happen, with the same checks and batching as the real thing, writing nothing. Rows accepted in an earlier batch count in later ones."""
    rep = Report()
    preflight(client, cfg)
    n = cfg.output.dedupe.batch_size
    st, _ = read_state(client, cfg)
    rep.warnings += st.warnings
    for i in range(0, len(rows), n):
        ok, rej = check_rows(rows[i:i + n], cfg, st)
        rep.skipped += rej
        rep.batches += 1
        for r in ok:
            st.add(cfg.output.columns, r, cfg)
            rep.added.append((0, r))
    return rep


# ------------------------------------------------------------------ the real append
def append_rows(client: SheetsClient, cfg: PipelineConfig, rows: list[list[str]], *, log: Callable[[str], None] = lambda m: None,
                check_cancel: Callable[[], None] = lambda: None, on_landed: Callable[[int, list[list[str]]], None] = lambda a, r: None) -> Report:
    """Append `rows` in batches. Raises AppendStop on any safety stop (Report-so-far is attached as e.report)."""
    cols, wt = cfg.output.columns, cfg.output.write_tab
    width, n = len(cols), cfg.output.dedupe.batch_size
    rep = Report()
    try:
        for i in range(0, len(rows), n):
            check_cancel()                                                  # between batches only: a cancel never splits a batch
            v = preflight(client, cfg)                                      # re-read before EVERY batch; header + blank-row stops
            st, _ = read_state(client, cfg)
            rep.warnings += [w for w in st.warnings if w not in rep.warnings]
            ok, rej = check_rows(rows[i:i + n], cfg, st)
            rep.skipped += rej
            rep.batches += 1
            if not ok:
                log(f"batch {rep.batches}: nothing to add, skipped {len(rej)}")
                continue
            expected_first = len(v) + 1
            try:
                res = client.append(wt.name, ok)                            # sent ONCE. No retry, ever.
            except SheetsWriteError as e:
                raise AppendStop(f"{e}. Not retried. Run recovery: it reads the sheet tail to see which of these {len(ok)} rows landed", unknown=ok) from e
            m = re.findall(r"[A-Z]+(\d+)", res["updates"]["updatedRange"])
            a, b = int(m[0]), int(m[1])
            if b - a + 1 != len(ok):
                raise AppendStop(f"the sheet reports {b - a + 1} rows written at {a}-{b} but {len(ok)} were sent; stopping", unknown=ok)
            back = client.get_values(f"{quote_tab(wt.name)}!A{a}:{col_letter(width)}{b}")          # verify the landing range
            if [pad(r, width) for r in back] != [pad(r, width) for r in ok]:
                raise AppendStop(f"read-back of rows {a}-{b} differs from what was written; stopping (the rows are not recoloured or logged as ours)", unknown=ok)
            if a != expected_first:
                rep.warnings.append(f"rows landed at {a}-{b}, not {expected_first}: someone else wrote to the sheet in between (our rows verified by read-back)")
            landed = [(a + k, r) for k, r in enumerate(ok)]
            on_landed(a, ok)                                                # logged as ours BEFORE colouring
            rep.added += landed
            try:
                client.batch_update(whiten_requests(cfg, client.tab_ids()[wt.name], list(range(a, b + 1))))
            except (SheetsWriteError, KeyError) as e:
                rep.unwhitened += list(range(a, b + 1))
                raise AppendStop(f"rows {a}-{b} were written and logged, but recolouring failed ({e}); not retried. They may inherit the colour of the row above: recolour them by hand",
                                 landed=landed) from e
            log(f"batch {rep.batches}: added rows {a}-{b} ({len(ok)}), skipped {len(rej)}")
    except AppendStop as s:
        rep.stopped = str(s)
        s.report = rep
        raise
    return rep


# ------------------------------------------------------------------ recovery after a failed write
def find_landed(client: SheetsClient, cfg: PipelineConfig, rows: list[list[str]]) -> tuple[list[tuple[int, list[str]]], list[list[str]]]:
    """After a write error: read the sheet and split `rows` into (landed with their row numbers, missing). Matches on name + company + profile URL."""
    cols, d = cfg.output.columns, cfg.output.dedupe
    v = client.get_values(cfg.output.write_tab.range)
    ni, ci, ui = cols.index(d.name_field), cols.index(d.company_field), cols.index(d.url_fields[0])
    on_sheet = {}
    for j, r in enumerate(v[1:], start=2):
        r = pad(r, len(cols))
        on_sheet[(name_key(r[ni]), norm(r[ci]), url_key(r[ui]))] = j
    landed, missing = [], []
    for r in rows:
        r = pad(r, len(cols))
        j = on_sheet.get((name_key(r[ni]), norm(r[ci]), url_key(r[ui])))
        (landed.append((j, r)) if j else missing.append(r))
    return landed, missing


def write_missing_csv(path: Path, cfg: PipelineConfig, missing: list[list[str]]) -> Path:
    return write_review_csv(path, cfg.output.columns, missing)


def write_logs(workdir: Path, tag: str, report: Report) -> list[str]:
    """new_people_<date>_<tag>.csv (row number + row) and <tag>_rejected.csv (company, person, reason), UTF-8 without BOM, appended to."""
    out = []
    today = datetime.date.today().strftime("%Y%m%d")
    workdir.mkdir(parents=True, exist_ok=True)
    if report.added:
        p = workdir / f"new_people_{today}_{tag}.csv"
        with open(p, "a", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows([n] + r for n, r in report.added)
        out.append(p.name)
    if report.skipped:
        p = workdir / f"{tag}_rejected.csv"
        with open(p, "a", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(report.skipped)
        out.append(p.name)
    return out
