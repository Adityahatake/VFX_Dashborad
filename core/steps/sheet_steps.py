"""Steps that touch the sheet or mark review gates.
  sheet_snapshot  (free)   read-only: writes sheet_snapshot.json for pool_match and adds the sheet's companies to the known set
  verify_companies / verify_people / build_rows  (free)  manual gates: they only point to the review on Home
  append_sheet    (write)  the safe append of an approved review CSV; runs as a worker job with a log, and is never auto-resumed after a write error"""
from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from .. import append as ap, known, review
from ..dedupe import pad
from .base import NoParams, Step, StepContext, StepResult, register
from .harvest import _need_pipeline


@register
class SheetSnapshot(Step):
    id = "sheet_snapshot"
    kind = "free"
    title = "Read the sheet (read-only snapshot + known companies)"
    params_model = NoParams

    def run(self, ctx: StepContext, p: NoParams) -> StepResult:
        _need_pipeline(ctx)
        cfg, tabs = ctx.cfg, {}
        for t in cfg.output.tabs:
            ctx.check_cancel()
            v = ctx.sheet.get_values(t.range)
            tabs[t.name] = {"header": v[0] if v else [], "rows": v[1:] if v else []}
        (ctx.pipeline_dir / "sheet_snapshot.json").write_text(json.dumps({"tabs": tabs}, ensure_ascii=False), encoding="utf-8")
        n = 0
        for name, t in tabs.items():
            h = t["header"]
            if cfg.output.dedupe.company_field in h:
                ci = h.index(cfg.output.dedupe.company_field)
                for r in t["rows"]:
                    if len(r) > ci and r[ci].strip():
                        known.add_name(ctx.db, cfg.name, r[ci], "sheet")
                        n += 1
        rows = sum(len(t["rows"]) for t in tabs.values())
        ctx.log(f"snapshot of {len(tabs)} tabs, {rows} rows; {n} company names added to the known set")
        return StepResult(counts={"tabs": len(tabs), "rows": rows}, artifacts=[], message=f"{rows} rows read")


class _Gate(Step):
    kind = "free"
    where = ""

    def run(self, ctx: StepContext, p: NoParams) -> StepResult:
        ctx.log(f"Manual gate: {self.where} Nothing is written to the sheet from here.")
        return StepResult(message="review on Home")


@register
class VerifyCompanies(_Gate):
    id = "verify_companies"
    title = "Review gate: approve or reject crawl hits"
    where = "on Home > Latest companies, approve or reject each crawl hit."


@register
class VerifyPeople(_Gate):
    id = "verify_people"
    title = "Review gate: approve or reject people"
    where = "on Home > Latest people, edit fields, and approve or reject."


@register
class BuildRows(_Gate):
    id = "build_rows"
    title = "Review gate: build the review CSV"
    where = "on Home > Sheet & append, build the review CSV, then run the dry run."


class AppendParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    csv_name: str = Field("review.csv", pattern=r"^[A-Za-z0-9_.-]{1,80}\.csv$")      # file inside the cycle folder
    tag: str = Field("batch", pattern=r"^[A-Za-z0-9_]{1,30}$")
    expected_rows: int = Field(..., ge=1)       # the count the user typed to confirm; the CSV must contain exactly this many rows


@register
class AppendSheet(Step):
    id = "append_sheet"
    kind = "write"
    title = "Append approved rows to the sheet (safe append)"
    params_model = AppendParams

    def run(self, ctx: StepContext, p: AppendParams) -> StepResult:
        _need_pipeline(ctx)
        if ctx.cycle_id is None:
            raise RuntimeError("append_sheet needs a cycle")
        cfg, con = ctx.cfg, ctx.db
        if con.execute("SELECT 1 FROM stop_events WHERE cycle_id=? AND rule='append_recovery' AND acknowledged_at IS NULL", (ctx.cycle_id,)).fetchone():
            raise RuntimeError("a previous append failed with an unknown outcome: run recovery in Home > Sheet & append first (never retry a write blindly)")
        path = ctx.workdir / p.csv_name
        header, rows = ap.read_review_csv(path)
        if header != cfg.output.columns:
            raise ValueError("the CSV header does not match the configured columns; rebuild it in Home > Sheet & append")
        if len(rows) != p.expected_rows:
            raise ValueError(f"the CSV has {len(rows)} rows but you confirmed {p.expected_rows}; nothing was written")
        ctx.log(f"appending {len(rows)} rows from {p.csv_name} (target: {type(getattr(ctx.sheet, '_inner', ctx.sheet)).__name__})")
        try:
            rep = ap.append_rows(ctx.sheet, cfg, rows, log=ctx.log, check_cancel=ctx.check_cancel,
                                 on_landed=lambda a, rr: review.record_append(con, cfg, ctx.cycle_id, a, rr))
        except ap.AppendStop as s:
            rep = getattr(s, "report", ap.Report())
            ap.write_logs(ctx.workdir, p.tag, rep)
            if s.unknown:                                    # outcome unknown: block everything until the user runs recovery
                ap.write_review_csv(ctx.workdir / f"unknown_outcome_{p.tag}.csv", cfg.output.columns, s.unknown)
                con.execute("INSERT OR REPLACE INTO stop_events (cycle_id, rule, reason) VALUES (?, 'append_recovery', ?)",
                            (ctx.cycle_id, f"write outcome unknown for {len(s.unknown)} rows ({p.tag})"))
            ctx.log("STOPPED: " + str(s))
            raise
        logs = ap.write_logs(ctx.workdir, p.tag, rep)
        for w in rep.warnings:
            ctx.log("warning: " + w)
        ctx.log(f"added {len(rep.added)} | skipped {len(rep.skipped)} | rows {rep.rows}")
        for c, n, why in rep.skipped:
            ctx.log(f"  skip: {n} | {c} | {why}")
        return StepResult(counts={"added": len(rep.added), "skipped": len(rep.skipped)}, artifacts=logs, message=f"added {len(rep.added)}, skipped {len(rep.skipped)}")
