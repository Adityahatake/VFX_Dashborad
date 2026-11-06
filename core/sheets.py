"""Google Sheets access. One small interface (SheetsClient) with three implementations:
  GoogleSheets  the real API (service-account JWT). Reads retry; a write is NEVER retried.
  FakeSheet     an in-memory sheet that reproduces the API behaviours that matter for safety (used for tests, demo mode and development).
  SafeSheet     wraps either: refuses any write outside the pipeline's write tab, and has NO delete or clear operation at all.
The app has no delete feature for other people's rows: the interface simply does not contain one."""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Protocol

from . import http, paths

SCOPE = "https://www.googleapis.com/auth/spreadsheets"


def col_letter(n: int) -> str:
    """1 -> A, 26 -> Z, 27 -> AA."""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def a1_tab(rng: str) -> str:
    """Tab name of an A1 range: "Linkedin!A1:Q9" -> Linkedin, "'Stage 32'!A1:AC9" -> Stage 32."""
    t = rng.split("!")[0]
    return t[1:-1].replace("''", "'") if t.startswith("'") else t


def quote_tab(tab: str) -> str:
    return "'" + tab.replace("'", "''") + "'"


class SheetsWriteError(Exception):
    """A write call failed. The outcome is UNKNOWN (it may or may not have landed): the caller must stop and inspect the sheet."""


class SheetsClient(Protocol):
    def get_values(self, rng: str) -> list[list[str]]: ...
    def append(self, tab: str, values: list[list[str]]) -> dict: ...
    def batch_update(self, requests: list[dict]) -> dict: ...
    def tab_ids(self) -> dict[str, int]: ...


# ------------------------------------------------------------------ real client
class GoogleSheets:
    def __init__(self, sheet_id: str, cred_path: str | Path):
        self.sid, self.cred = sheet_id, Path(cred_path)
        self._tok: tuple[str, float] | None = None

    def _token(self) -> str:
        if self._tok and self._tok[1] > time.time() + 60:
            return self._tok[0]
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        b = lambda v: base64.urlsafe_b64encode(v).rstrip(b"=").decode()
        c = json.loads(self.cred.read_text(encoding="utf-8"))
        now = int(time.time())
        h = b(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
        p = b(json.dumps({"iss": c["client_email"], "scope": SCOPE, "aud": c["token_uri"], "iat": now, "exp": now + 3600}, separators=(",", ":")).encode())
        sig = serialization.load_pem_private_key(c["private_key"].encode(), password=None).sign(f"{h}.{p}".encode(), padding.PKCS1v15(), hashes.SHA256())
        req = urllib.request.Request(c["token_uri"], method="POST", data=urllib.parse.urlencode(
            {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": f"{h}.{p}.{b(sig)}"}).encode())
        for attempt in range(4):                       # getting a token writes nothing, so retrying is safe
            try:
                d = json.load(urllib.request.urlopen(req, timeout=30))
                self._tok = (d["access_token"], time.time() + int(d.get("expires_in", 3600)))
                return self._tok[0]
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                if attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))
        raise RuntimeError("unreachable")

    def _url(self, path: str) -> str:
        return f"https://sheets.googleapis.com/v4/spreadsheets/{self.sid}{path}"

    def get_values(self, rng: str) -> list[list[str]]:
        return http.request_json(self._url("/values/" + urllib.parse.quote(rng)), key=self._token(), timeout=90).get("values", [])

    def append(self, tab: str, values: list[list[str]]) -> dict:
        """values:append, RAW, INSERT_ROWS. Sent exactly once: any failure raises SheetsWriteError (outcome unknown)."""
        url = self._url("/values/" + urllib.parse.quote(f"{quote_tab(tab)}!A1") + ":append?valueInputOption=RAW&insertDataOption=INSERT_ROWS")
        try:
            return http.request_json(url, key=self._token(), body={"majorDimension": "ROWS", "values": values}, timeout=90)
        except Exception as e:                         # noqa: BLE001
            raise SheetsWriteError(f"append failed ({type(e).__name__}); the rows may or may not have landed") from e

    def batch_update(self, requests: list[dict]) -> dict:
        try:
            return http.request_json(self._url(":batchUpdate"), key=self._token(), body={"requests": requests}, timeout=90)
        except Exception as e:                         # noqa: BLE001
            raise SheetsWriteError(f"batchUpdate failed ({type(e).__name__})") from e

    def tab_ids(self) -> dict[str, int]:
        d = http.request_json(self._url("?fields=sheets.properties"), key=self._token(), timeout=60)
        return {s["properties"]["title"]: s["properties"]["sheetId"] for s in d["sheets"]}


# ------------------------------------------------------------------ in-memory fake with the real API's quirks
class FakeSheet:
    """Behaves like the Sheets API where it matters for safety:
      - values.get drops trailing empty cells and trailing empty rows
      - values:append (INSERT_ROWS) lands after the first blank row of the table starting at A1, NOT after the last row of the tab
      - repeatCell formatting is recorded per row so tests can prove only our own rows were recoloured
    Test hooks: before_append (another writer sneaks in), fail_append ('before' = never applied, 'after' = applied then the connection drops),
    fail_batch_update."""

    def __init__(self, tabs: dict[str, list[list[str]]], path: Path | None = None):
        self.tabs = {k: [list(r) for r in v] for k, v in tabs.items()}
        self.bg: dict[tuple[str, int], tuple] = {}
        self.ids = {name: 100 + i for i, name in enumerate(self.tabs)}
        self.calls: list[tuple] = []
        self.before_append = None
        self.fail_append: str | None = None
        self.fail_batch_update = False
        self.path = path
        self.format_log: list[tuple[str, int, int, int]] = []     # (tab, row1, start_col, end_col) of every repeatCell applied

    # -- persistence for demo mode
    def save(self) -> None:
        if self.path:
            Path(self.path).write_text(json.dumps({"tabs": self.tabs, "bg": [[t, r, list(c)] for (t, r), c in self.bg.items()]}), encoding="utf-8")

    @classmethod
    def load(cls, path: Path, default_tabs: dict[str, list[list[str]]]) -> "FakeSheet":
        p = Path(path)
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            s = cls(d["tabs"], p)
            s.bg = {(t, r): tuple(c) for t, r, c in d.get("bg", [])}
            return s
        s = cls(default_tabs, p)
        s.save()
        return s

    # -- API
    def tab_ids(self) -> dict[str, int]:
        return dict(self.ids)

    def get_values(self, rng: str) -> list[list[str]]:
        self.calls.append(("get", rng))
        tab = a1_tab(rng)
        rows = [list(r) for r in self.tabs[tab]]
        m = re.search(r"!([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?$", rng)
        if m:
            c1, r1 = col_index(m.group(1)), int(m.group(2))
            c2, r2 = (col_index(m.group(3)), int(m.group(4))) if m.group(3) else (c1, r1)
            rows = [(r + [""] * c2)[c1 - 1:c2] for r in rows[r1 - 1:r2]]
        out = [[str(c) for c in r] for r in rows]
        out = [self._trim(r) for r in out]
        while out and not out[-1]:
            out.pop()
        return out

    @staticmethod
    def _trim(r: list[str]) -> list[str]:
        r = list(r)
        while r and r[-1] == "":
            r.pop()
        return r

    def _table_end(self, tab: str) -> int:
        """Last row (1-based) of the contiguous table that starts at row 1; a blank row ends it."""
        n = 0
        for r in self.tabs[tab]:
            if not any(str(c).strip() for c in r):
                break
            n += 1
        return n

    def append(self, tab: str, values: list[list[str]]) -> dict:
        self.calls.append(("append", tab, len(values)))
        if self.before_append:
            hook, self.before_append = self.before_append, None
            hook(self)
        if self.fail_append == "before":
            raise SheetsWriteError("append failed (ConnectionError); the rows may or may not have landed")
        at = self._table_end(tab)
        width = max(len(r) for r in values)
        self.tabs[tab][at:at] = [[str(c) for c in r] for r in values]          # INSERT_ROWS: later rows (if any) shift down
        for (t, r) in sorted([k for k in self.bg if k[0] == tab and k[1] > at], reverse=True):
            self.bg[(t, r + len(values))] = self.bg.pop((t, r))               # formatting travels with its rows
        self.save()
        if self.fail_append == "after":
            raise SheetsWriteError("append failed (ConnectionError); the rows may or may not have landed")
        return {"updates": {"updatedRange": f"{quote_tab(tab)}!A{at + 1}:{col_letter(width)}{at + len(values)}", "updatedRows": len(values)}}

    def batch_update(self, requests: list[dict]) -> dict:
        self.calls.append(("batch_update", len(requests)))
        if self.fail_batch_update:
            raise SheetsWriteError("batchUpdate failed (ConnectionError)")
        by_id = {v: k for k, v in self.ids.items()}
        for rq in requests:
            if "repeatCell" not in rq:
                raise ValueError("FakeSheet supports repeatCell only: this app never deletes or reorders")
            rc = rq["repeatCell"]
            tab = by_id[rc["range"]["sheetId"]]
            fmt = rc["cell"]["userEnteredFormat"]
            bg = fmt.get("backgroundColor", {})
            for row0 in range(rc["range"]["startRowIndex"], rc["range"]["endRowIndex"]):
                self.bg[(tab, row0 + 1)] = (bg.get("red", 0), bg.get("green", 0), bg.get("blue", 0))
                self.format_log.append((tab, row0 + 1, rc["range"]["startColumnIndex"], rc["range"]["endColumnIndex"]))
        self.save()
        return {}

    # -- test helpers
    def set_bg(self, tab: str, row: int, rgb: tuple) -> None:
        self.bg[(tab, row)] = rgb

    def write_raw(self, tab: str, row1: int, values: list[str]) -> None:
        rows = self.tabs[tab]
        while len(rows) < row1:
            rows.append([])
        rows[row1 - 1] = list(values)
        self.save()


# ------------------------------------------------------------------ safety wrapper
class SafeSheet:
    """Only the pipeline's write tab can be written; everything else is read-only. There is intentionally no delete/clear/sort method."""

    def __init__(self, inner: SheetsClient, write_tab: str):
        self._inner, self.write_tab = inner, write_tab

    def get_values(self, rng: str) -> list[list[str]]:
        return self._inner.get_values(rng)

    def tab_ids(self) -> dict[str, int]:
        return self._inner.tab_ids()

    def append(self, tab: str, values: list[list[str]]) -> dict:
        if tab != self.write_tab:
            raise PermissionError(f"refusing to write to tab '{tab}': only '{self.write_tab}' may be written")
        return self._inner.append(tab, values)

    def batch_update(self, requests: list[dict]) -> dict:
        ids = self._inner.tab_ids()
        for rq in requests:
            if set(rq) != {"repeatCell"}:
                raise PermissionError(f"refusing request type {sorted(rq)}: only repeatCell on our own rows is allowed")
            if rq["repeatCell"]["range"]["sheetId"] != ids.get(self.write_tab):
                raise PermissionError("refusing to format a tab other than the write tab")
            r = rq["repeatCell"]["range"]
            if r["endRowIndex"] - r["startRowIndex"] != 1:
                raise PermissionError("formatting must be one row at a time (never a range that could include other people's rows)")
        return self._inner.batch_update(requests)


# ------------------------------------------------------------------ choosing the sheet
DEMO_TABS_FILE = "demo_sheet.json"


def sheet_target(con) -> str:
    """'sandbox' (default) or 'real'. Demo mode overrides both with an in-memory demo sheet."""
    from .db import get_setting
    return get_setting(con, "sheet_target", "sandbox") or "sandbox"


def demo_sheet(cfg) -> FakeSheet:
    """A demo sheet shaped like the pipeline's tabs, with a few rows written by 'other people' so dedupe and caps can be shown."""
    wt = cfg.output.write_tab
    hdr = cfg.output.columns
    other_tabs = {t.name: [["name", "company", "country"], ["Known Elsewhere", "Zed Pictures", "Germany"]] for t in cfg.output.tabs if not t.write}

    def row(**k):
        d = dict.fromkeys(hdr, "")
        d.update(k)
        return [d[c] for c in hdr]
    base = dict(role="P1", country="Germany", primary_classification="Production studio", ai_adoption_stage="Active Production", qa_decision="PASS",
                qa_confidence="High", outreach_readiness="Ready", contact_or_reference_type="Personal LinkedIn", qualification_decision="PASS-A")
    rows = [list(hdr),
            row(name="Anna Beispiel", company="Neu Film", title="Founder", contact_or_reference="https://linkedin.com/in/anna-beispiel",
                evidence_source="https://neufilm.de/ai; https://neufilm.de/impressum", ai_evidence="AI-generated spot for a client.", **base),
            row(name="Full One", company="Full Co", title="CEO", contact_or_reference="https://linkedin.com/in/full-one", evidence_source="https://fullco.com", **base),
            row(name="Full Two", company="Full Co", title="Creative Director", contact_or_reference="https://linkedin.com/in/full-two", evidence_source="https://fullco.com", **base),
            row(name="Full Three", company="Full Co", title="Head of Production", contact_or_reference="https://linkedin.com/in/full-three", evidence_source="https://fullco.com", **base)]
    return FakeSheet.load(paths.DATA_DIR / DEMO_TABS_FILE, {wt.name: rows, **other_tabs})


def get_client(con, cfg) -> tuple[SafeSheet, str]:
    """(client, label). Demo mode -> demo sheet. Otherwise the sandbox sheet (default) or the real one when Settings says so."""
    from . import keys
    wt = cfg.output.write_tab.name
    if keys.is_demo(con):
        return SafeSheet(demo_sheet(cfg), wt), "DEMO sheet (in memory)"
    target = sheet_target(con)
    env = cfg.output.sheet_id_env if target == "real" else "SANDBOX_SHEET_ID"
    sid, cred = os.environ.get(env, ""), os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not sid:
        raise RuntimeError(f"{env} is not set in .env, so the {target} sheet cannot be used (turn on demo mode in Settings to try the flow without a sheet)")
    if not cred or not Path(cred).exists():
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS is not set or the file does not exist")
    return SafeSheet(GoogleSheets(sid, cred), wt), f"{target.upper()} sheet ({sid[:6]}…)"
