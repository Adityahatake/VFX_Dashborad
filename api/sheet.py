"""Sheet & append, recovery, the cycle report, settings and source yield (the parts of the old Review / Settings / History pages
that the new dashboard needs). The rules are unchanged and enforced HERE, not in the browser:
  - show before write: a dry run of exactly this CSV (same content hash) must exist and have no stop before an append can start;
  - the user types the row count; the append itself is the gated `append_sheet` worker job (never retried);
  - an unknown write outcome blocks appending until recovery has read the sheet tail;
  - switching to the REAL sheet with writes needs the words REAL SHEET."""
from __future__ import annotations

import hashlib
import json
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from core import append as ap, gate, jobs, keys, metrics, paths, review, sheets, spend
from core.config import PipelineConfig
from core.db import get_setting, set_setting
from core.logmask import prefix

from .deps import PIPELINE, active_cycle, cfg, db

router = APIRouter(prefix="/api")
CSV = "review.csv"
TARGET_LABELS = {"sandbox": "Sandbox sheet (writes allowed)", "real_readonly": "Real sheet, read-only", "real": "Real sheet (writes allowed)"}


def _cycle(con):
    c = active_cycle(con)
    if c is None:
        raise HTTPException(409, "start a cycle first")
    return c


def _workdir(cid: int):
    d = jobs.workdir_for(cid, 0)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _client(con, c: PipelineConfig):
    try:
        return sheets.get_client(con, c)
    except Exception as e:                                   # no credentials, no sheet id, no network
        raise HTTPException(503, f"the sheet is not reachable: {type(e).__name__}: {e}")


def _csv_state(cid: int):
    p = _workdir(cid) / CSV
    if not p.exists():
        return None, None, None
    raw = p.read_bytes()
    header, rows = ap.read_review_csv(p)
    return header, rows, hashlib.sha256(raw).hexdigest()


def _dry_path(cid: int):
    return _workdir(cid) / "dry_run.json"


# ------------------------------------------------------------------ state
@router.get("/sheet")
def sheet_state(progress: bool = False, con=Depends(db), c: PipelineConfig = Depends(cfg)):
    demo, target = keys.is_demo(con), sheets.sheet_target(con)
    out = {"target": target, "targets": TARGET_LABELS, "demo": demo, "read_only": (not demo) and target == "real_readonly",
           "batch_size": c.output.dedupe.batch_size, "write_tab": c.output.write_tab.name, "cycle": None}
    cyc = active_cycle(con)
    if cyc is None:
        return out
    cid = cyc["id"]
    header, rows, digest = _csv_state(cid)
    dry = None
    if _dry_path(cid).exists():
        d = json.loads(_dry_path(cid).read_text(encoding="utf-8"))
        dry = {**d, "current": d.get("csv_sha") == digest}
    ev = con.execute("SELECT * FROM stop_events WHERE cycle_id=? AND rule='append_recovery' AND acknowledged_at IS NULL", (cid,)).fetchone()
    last = con.execute("SELECT * FROM jobs WHERE cycle_id=? AND step_id='append_sheet' ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
    base = json.loads(cyc["baseline_json"]) if cyc["baseline_json"] else None
    out.update(cycle=cid, goal_rows=cyc["goal_rows"], baseline=base, approved=len(review.approved_rows(con, c, cid)),
               appended=spend.rows_appended(con, cid),
               csv={"rows": len(rows), "header": header, "preview": [dict(zip(header, r)) for r in rows[:200]]} if rows is not None else None,
               dry_run=dry, recovery={"reason": ev["reason"], "has_file": any(_workdir(cid).glob("unknown_outcome_*.csv"))} if ev else None,
               append_job={"id": last["id"], "status": last["status"], "error": last["error"]} if last else None)
    if progress and base:
        client, label = _client(con, c)
        out["label"] = label
        out["progress"] = ap.progress(base, spend.rows_appended(con, cid), client.get_values(c.output.write_tab.range))
    return out


class Target(BaseModel):
    target: str
    confirm: str = ""


@router.put("/sheet/target")
def set_target(body: Target, con=Depends(db)):
    if body.target not in sheets.TARGETS:
        raise HTTPException(422, f"target must be one of {list(sheets.TARGETS)}")
    if body.target == "real" and body.confirm != "REAL SHEET":
        raise HTTPException(422, "to allow writes to the REAL shared sheet, type REAL SHEET")
    set_setting(con, "sheet_target", body.target)
    return {"target": body.target}


@router.post("/sheet/baseline")
def take_baseline(con=Depends(db), c: PipelineConfig = Depends(cfg)):
    cyc = _cycle(con)
    if cyc["baseline_json"] and spend.rows_appended(con, cyc["id"]) > 0:
        raise HTTPException(409, "rows were already appended in this cycle: the baseline cannot be retaken")
    client, _ = _client(con, c)
    base = ap.take_baseline(client, c)
    con.execute("UPDATE cycles SET baseline_json=? WHERE id=?", (json.dumps(base), cyc["id"]))
    return base


# ------------------------------------------------------------------ show before write
@router.post("/sheet/csv")
def build_csv(con=Depends(db), c: PipelineConfig = Depends(cfg)):
    cid = _cycle(con)["id"]
    rows = review.approved_rows(con, c, cid)
    if not rows:
        raise HTTPException(409, "no approved people in this cycle")
    ap.write_review_csv(_workdir(cid) / CSV, c.output.columns, rows)
    _dry_path(cid).unlink(missing_ok=True)                  # a new CSV needs a new dry run
    return {"rows": len(rows)}


@router.post("/sheet/dry-run")
def dry_run(con=Depends(db), c: PipelineConfig = Depends(cfg)):
    cid = _cycle(con)["id"]
    header, rows, digest = _csv_state(cid)
    if rows is None:
        raise HTTPException(409, "build the review CSV first")
    client, label = _client(con, c)
    try:
        rep = ap.dry_run(client, c, rows)
        res = {"rows": len(rows), "add": len(rep.added), "skipped": [{"company": a, "name": b, "why": w} for a, b, w in rep.skipped],
               "warnings": rep.warnings, "stop": None}
    except ap.AppendStop as s:
        res = {"rows": len(rows), "add": 0, "skipped": [], "warnings": [], "stop": str(s)}
    res.update(csv_sha=digest, label=label)
    _dry_path(cid).write_text(json.dumps(res), encoding="utf-8")
    return {**res, "current": True}


class AppendReq(BaseModel):
    typed_rows: int = Field(..., ge=1)


@router.post("/sheet/append")
def append(body: AppendReq, con=Depends(db), c: PipelineConfig = Depends(cfg)):
    cid = _cycle(con)["id"]
    header, rows, digest = _csv_state(cid)
    if rows is None:
        raise HTTPException(409, "build the review CSV first")
    if not _dry_path(cid).exists():
        raise HTTPException(409, "run the dry run first: nothing is appended without showing what would happen")
    d = json.loads(_dry_path(cid).read_text(encoding="utf-8"))
    if d.get("csv_sha") != digest:
        raise HTTPException(409, "the CSV changed since the dry run: run the dry run again")
    if d.get("stop"):
        raise HTTPException(409, "the dry run stopped: " + d["stop"])
    if body.typed_rows != len(rows):
        raise HTTPException(422, f"you typed {body.typed_rows} but the CSV has {len(rows)} rows")
    try:
        jid = gate.confirm_and_start(con, c, cid, "append_sheet", {"csv_name": CSV, "tag": f"c{cid}", "expected_rows": len(rows)}, 0.0, None)
    except gate.Blocked as e:
        raise HTTPException(409, {"blockers": e.blockers})
    return {"job_id": jid}


@router.post("/sheet/recover")
def recover(con=Depends(db), c: PipelineConfig = Depends(cfg)):
    """After an unknown write outcome: read the sheet tail, log the rows that landed as ours, write the missing ones to a new CSV."""
    cid = _cycle(con)["id"]
    ev = con.execute("SELECT 1 FROM stop_events WHERE cycle_id=? AND rule='append_recovery' AND acknowledged_at IS NULL", (cid,)).fetchone()
    if not ev:
        raise HTTPException(409, "there is no failed write to recover")
    unk = sorted(_workdir(cid).glob("unknown_outcome_*.csv"))
    if not unk:
        raise HTTPException(409, "the unknown-outcome file is missing: check the sheet by hand")
    client, _ = _client(con, c)
    _, rows_unk = ap.read_review_csv(unk[-1])
    landed, missing = ap.find_landed(client, c, rows_unk)
    for n, r in landed:
        if not con.execute("SELECT 1 FROM appended_rows WHERE cycle_id=? AND row_number=? AND tab=?", (cid, n, c.output.write_tab.name)).fetchone():
            review.record_append(con, c, cid, n, [r])
    if missing:
        ap.write_missing_csv(_workdir(cid) / CSV, c, missing)              # becomes the next batch: it must be dry-run again
        _dry_path(cid).unlink(missing_ok=True)
    spend.resolve_append_recovery(con, cid)
    return {"landed": [n for n, _ in landed], "missing": len(missing),
            "note": "Landed rows may need recolouring by hand if the colouring step did not run."}


@router.get("/cycle/report", response_class=PlainTextResponse)
def cycle_report(con=Depends(db), c: PipelineConfig = Depends(cfg)):
    return review.cycle_report_markdown(con, c, _cycle(con)["id"])


# ------------------------------------------------------------------ settings
ENV_VARS = ["GOOGLE_SHEET_ID", "SANDBOX_SHEET_ID", "GOOGLE_APPLICATION_CREDENTIALS", "APIFY_TOKEN_POOL", "TAVILY_API_KEYS", "GROQ_API_KEYS", "ANTHROPIC_API_KEY"]


@router.get("/settings")
def get_settings(con=Depends(db), c: PipelineConfig = Depends(cfg)):
    from core import llm
    env = {}
    for name in ENV_VARS:
        v = os.environ.get(name, "")
        if name == "GOOGLE_APPLICATION_CREDENTIALS":
            env[name] = "set (file exists)" if v and os.path.exists(v) else ("set (file NOT found)" if v else "not set")
        elif name.endswith(("_POOL", "_KEYS")):
            n = len(keys.split_keys(v))
            env[name] = f"{n} key(s)" if n else "not set"
        else:
            env[name] = prefix(v) if v else "not set"
    return {"demo_mode": get_setting(con, "demo_mode", "0") == "1",
            "default_cap_usd": float(get_setting(con, "default_cap_usd", str(c.budget.default_cycle_cap_usd))), "hard_max_cap_usd": c.budget.hard_max_cycle_cap_usd,
            "llm_enabled": get_setting(con, "llm.enabled", "0") == "1", "llm_model": get_setting(con, "llm.model", c.llm.model) or c.llm.model,
            "llm_cycle_cap_usd": float(get_setting(con, "llm.cycle_cap_usd", str(c.llm.cycle_cap_usd))), "llm_prices": llm.price_table(con),
            "env": env, "paths": {"data": str(paths.DATA_DIR), "database": str(paths.DB_PATH)}}


class SettingsReq(BaseModel):
    demo_mode: bool | None = None
    default_cap_usd: float | None = Field(None, ge=0)
    llm_enabled: bool | None = None
    llm_model: str | None = Field(None, min_length=1, max_length=80)
    llm_cycle_cap_usd: float | None = Field(None, ge=0)
    llm_prices: dict[str, dict[str, float]] | None = None


@router.put("/settings")
def put_settings(body: SettingsReq, con=Depends(db), c: PipelineConfig = Depends(cfg)):
    if body.demo_mode is not None and body.demo_mode != (get_setting(con, "demo_mode", "0") == "1"):
        set_setting(con, "demo_mode", "1" if body.demo_mode else "0")
        con.execute("DELETE FROM key_status")                # never mix fake and real balances
    if body.default_cap_usd is not None:
        set_setting(con, "default_cap_usd", str(min(body.default_cap_usd, c.budget.hard_max_cycle_cap_usd)))
    if body.llm_enabled is not None:
        set_setting(con, "llm.enabled", "1" if body.llm_enabled else "0")
    if body.llm_model is not None:
        set_setting(con, "llm.model", body.llm_model)
    if body.llm_cycle_cap_usd is not None:
        set_setting(con, "llm.cycle_cap_usd", str(body.llm_cycle_cap_usd))
    if body.llm_prices is not None:
        need = {"in", "out", "cache_read", "cache_write"}
        if not all(need <= set(v) and all(x >= 0 for x in v.values()) for v in body.llm_prices.values()):
            raise HTTPException(422, "each model needs non-negative in, out, cache_read and cache_write prices (USD per 1M tokens)")
        set_setting(con, "llm.prices", json.dumps(body.llm_prices))
    return get_settings(con, c)


# ------------------------------------------------------------------ sources
@router.get("/sources")
def sources(con=Depends(db), c: PipelineConfig = Depends(cfg)):
    return {"yield": metrics.source_yield(con, PIPELINE),
            "exhausted": [x.model_dump() for x in c.exhausted_sources]}


# ------------------------------------------------------------------ cycle history and AI suggestions
@router.get("/cycles")
def cycles(con=Depends(db)):
    return metrics.cycles_overview(con, PIPELINE)


@router.post("/people/{person_id}/use-suggestion")
def use_suggestion(person_id: int, con=Depends(db)):
    """Copy the AI draft into the row (a reviewer action). The row goes back to pending and is flagged: it still needs Approve."""
    if con.execute("SELECT 1 FROM people WHERE id=?", (person_id,)).fetchone() is None:
        raise HTTPException(404, "no such person")
    try:
        review.apply_person_suggestion(con, person_id)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"id": person_id, "decision": "pending"}
