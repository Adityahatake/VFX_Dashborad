"""FastAPI app for the VFX dashboard. One pipeline only (vfx_genai). Every rule stays in core/:
  - free steps start directly; paid / llm / write steps go through core.gate (cap, key, pilot, stop rules) and need the
    cost and key the user confirmed, exactly like the Streamlit page;
  - responses carry short key ids only (core.keys.key_id), never secrets;
  - nothing here writes to a sheet except by starting the gated append_sheet step.
Run:  .venv\\Scripts\\python -m uvicorn api.main:app --host 127.0.0.1 --port 8000"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core import gate, jobs, keys, paths, spend
from core.config import PipelineConfig, effective_cap
from core.db import connect, get_setting, open_db
from core.registry import get_config
from core.steps import get_step, steps_for

PIPELINE = "vfx_genai"
HIDDEN_STEPS = {"demo_slow", "demo_paid"}           # test helpers: never offered in the production UI


def db() -> Iterator[sqlite3.Connection]:
    con = connect()
    try:
        yield con
    finally:
        con.close()


def cfg() -> PipelineConfig:
    c = get_config(PIPELINE)
    if c is None:
        raise HTTPException(500, f"pipelines/{PIPELINE}/pipeline.yaml is missing or invalid")
    return c


def row(r) -> dict | None:
    return dict(r) if r is not None else None


def active_cycle(con) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM cycles WHERE pipeline=? AND status='active' ORDER BY id DESC LIMIT 1", (PIPELINE,)).fetchone()


def job_view(j) -> dict:
    d = dict(j)
    d["stuck"] = jobs.is_stuck(j)
    d["heartbeat_age_s"] = jobs.age_seconds(j["heartbeat_at"]) if j["status"] in jobs.LIVE else None
    d["params"] = json.loads(d.pop("params_json") or "{}")
    for k in ("log_path", "checkpoint_path", "pid"):
        d.pop(k, None)                                   # local paths and pids are not the UI's business
    return d


def _startup() -> None:
    paths.load_env()
    paths.ensure_dirs()
    con = open_db()                                      # runs migrations once
    con.execute("INSERT OR IGNORE INTO pipelines (name, yaml_path) VALUES (?, ?)", (PIPELINE, str(paths.PIPELINES_DIR / PIPELINE / "pipeline.yaml")))
    jobs.reconcile(con)                                  # dead workers become 'interrupted' and free their key leases
    con.close()


@asynccontextmanager
async def lifespan(_app):
    _startup()
    yield


app = FastAPI(title="VFX Lead Dashboard API", version="0.1.0", lifespan=lifespan)


# ------------------------------------------------------------------ health
@app.get("/api/health")
def health(con=Depends(db)):
    jobs.reconcile(con)
    cyc = active_cycle(con)
    running = con.execute("SELECT * FROM jobs WHERE status IN ('queued','running')").fetchall()
    return {
        "ok": True, "pipeline": PIPELINE, "demo": keys.is_demo(con),
        "sheet_target": get_setting(con, "sheet_target", "sandbox"),
        "active_cycle": row(cyc),
        "running_jobs": len(running), "stuck_jobs": [j["id"] for j in running if jobs.is_stuck(j)],
        "interrupted_jobs": con.execute("SELECT COUNT(*) FROM jobs WHERE status='interrupted'").fetchone()[0],
        "pending_review": {"companies": con.execute("SELECT COUNT(*) FROM companies WHERE decision='pending'").fetchone()[0],
                           "people": con.execute("SELECT COUNT(*) FROM people WHERE decision='pending'").fetchone()[0]},
    }


# ------------------------------------------------------------------ keys (ids and balances only, never secrets)
def _key_rows(con) -> list[dict]:
    leased = keys.leased_ids(con)
    out = []
    for r in keys.statuses(con):
        d = dict(r)
        d["in_use"] = d["key_prefix"] in leased
        d["age_s"] = keys.age_s(d["checked_at"])
        out.append(d)
    return out


def _usage(con, kind: str) -> dict:
    r = con.execute("SELECT COUNT(*) n, COALESCE(SUM(actual_usd),0) usd, COALESCE(SUM(results),0) results, MAX(ts) last FROM spend_ledger WHERE kind=?",
                    (kind,)).fetchone()
    r30 = con.execute("SELECT COALESCE(SUM(actual_usd),0) FROM spend_ledger WHERE kind=? AND ts >= datetime('now','-30 days')", (kind,)).fetchone()[0]
    return {"calls": r["n"], "spent_usd": round(r["usd"], 4), "spent_30d_usd": round(r30, 4), "results": r["results"], "last_used": r["last"]}


@app.get("/api/keys")
def list_keys(con=Depends(db)):
    """Everything the API & Keys section shows, per provider. Key ids only; the secrets never leave .env."""
    demo, rows, warns = keys.is_demo(con), _key_rows(con), keys.warnings(con)
    out = {}
    for p in keys.PROVIDERS:
        configured = {keys.key_id(k) for k in keys.load_keys(p, demo)}
        mine = [r for r in rows if r["provider"] == p and r["key_prefix"] in configured]
        known = [r["remaining"] for r in mine if r["remaining"] is not None]
        mine += [{"key_prefix": k, "provider": p, "state": "unchecked", "remaining": None, "cap": None, "resets": "", "checked_at": None,
                  "in_use": False, "age_s": None} for k in sorted(configured - {r["key_prefix"] for r in mine})]
        out[p] = {"label": keys.LABELS[p], "unit": keys.UNITS[p], "env_var": keys.PROVIDERS[p][1], "prefix": keys.PROVIDERS[p][0],
                  "configured": len(configured), "usable": sum(r["state"] == "usable" for r in mine), "dead": sum(r["state"] == "dead" for r in mine),
                  "total_remaining": round(sum(known), 2) if known else None, "keys": mine,
                  "usage": _usage(con, "llm" if p == "groq" else p), "warnings": [w for w in warns if w["provider"] == p]}
    return {"providers": out, "low_credit_threshold": keys.low_credit_threshold(con), "usable_apify_credit": keys.usable_credit(con), "demo": demo}


class CheckReq(BaseModel):
    live_tavily: bool = False                            # one real search per key (1 credit each)
    live_groq: bool = False                              # one 1-token completion per key (counts against the daily quota)


@app.post("/api/keys/check")
def check_keys(body: CheckReq | None = None, con=Depends(db)):
    b = body or CheckReq()
    keys.check_all(con, live_tavily=b.live_tavily, live_groq=b.live_groq)
    return list_keys(con)


def _provider(p: str) -> str:
    if p not in keys.PROVIDERS:
        raise HTTPException(404, f"unknown provider '{p}'")
    return p


class AddKeys(BaseModel):
    keys: list[str] = Field(..., min_length=1, max_length=200)


@app.post("/api/keys/{provider}")
def add_keys(provider: str, body: AddKeys, con=Depends(db)):
    """Add keys to .env (backed up outside the repo first). The response names how many were added, never the keys."""
    p = _provider(provider)
    try:
        n, _ = keys.add_keys(p, body.keys)
    except ValueError as e:
        raise HTTPException(422, str(e))
    keys.check_all(con)                                  # free checks, so the new keys show a status straight away
    return {"added": n, **list_keys(con)}


class ReplaceKey(BaseModel):
    key: str = Field(..., min_length=8)


@app.put("/api/keys/{provider}/{kid}")
def replace_key(provider: str, kid: str, body: ReplaceKey, con=Depends(db)):
    p = _provider(provider)
    try:
        keys.replace_key(con, p, kid, body.key)
    except ValueError as e:
        raise HTTPException(409, str(e))
    keys.check_all(con)
    return list_keys(con)


@app.delete("/api/keys/{provider}/{kid}")
def remove_key(provider: str, kid: str, con=Depends(db)):
    p = _provider(provider)
    try:
        keys.remove_key(con, p, kid)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return list_keys(con)


class Threshold(BaseModel):
    threshold: float = Field(..., ge=0, le=100000)


@app.put("/api/settings/low-credit")
def set_low_credit(body: Threshold, con=Depends(db)):
    from core.db import set_setting
    set_setting(con, "low_credit_threshold", str(body.threshold))
    return {"low_credit_threshold": body.threshold}


# ------------------------------------------------------------------ cycle
class NewCycle(BaseModel):
    goal_rows: int = Field(..., ge=1, le=1000)
    cap_usd: float | None = Field(None, gt=0)


@app.get("/api/cycle")
def get_cycle(con=Depends(db), c: PipelineConfig = Depends(cfg)):
    cyc = active_cycle(con)
    if cyc is None:
        return {"active": None, "default_cap_usd": min(float(get_setting(con, "default_cap_usd", str(c.budget.default_cycle_cap_usd))),
                                                       c.budget.hard_max_cycle_cap_usd), "hard_max_cap_usd": c.budget.hard_max_cycle_cap_usd}
    cid = cyc["id"]
    return {"active": dict(cyc), "spent_usd": spend.cycle_spend(con, cid), "remaining_usd": spend.remaining_cap(con, cid),
            "rows_approved": spend.rows_approved(con, cid), "rows_appended": spend.rows_appended(con, cid),
            "stop_events": [dict(e) for e in spend.sync_stop_events(con, c, cid)], "hard_max_cap_usd": c.budget.hard_max_cycle_cap_usd}


@app.post("/api/cycle")
def start_cycle(body: NewCycle, con=Depends(db), c: PipelineConfig = Depends(cfg)):
    if active_cycle(con) is not None:
        raise HTTPException(409, "a cycle is already active: end it first")
    cid = spend.create_cycle(con, c, body.goal_rows, body.cap_usd)
    return {"id": cid, "cap_usd": effective_cap(c, body.cap_usd)}


@app.post("/api/cycle/end")
def end_cycle(con=Depends(db)):
    cyc = active_cycle(con)
    if cyc is None:
        raise HTTPException(404, "no active cycle")
    con.execute("UPDATE cycles SET status='ended', ended_at=CURRENT_TIMESTAMP WHERE id=?", (cyc["id"],))
    return {"ended": cyc["id"]}


# ------------------------------------------------------------------ steps and the gate
@app.get("/api/steps")
def list_steps(c: PipelineConfig = Depends(cfg)):
    in_yaml = {s.step: s for s in c.steps}
    out = []
    for sid, st in steps_for(PIPELINE).items():
        if sid in HIDDEN_STEPS:
            continue
        try:
            default = st.params_model().model_dump()
        except Exception:
            default = {}                                 # required params (e.g. salesnav companies): the user must fill them
        ref = in_yaml.get(sid)
        if ref and ref.params:
            default = {**default, **ref.params}
        out.append({"id": sid, "kind": st.kind, "title": st.title, "stage": ref.stage if ref else None, "default_params": default,
                    "in_pipeline": ref is not None})
    order = ["sheet_snapshot"] + [s.step for s in c.steps]        # the read-only snapshot always runs first in a cycle
    return sorted(out, key=lambda s: order.index(s["id"]) if s["id"] in order else 999)


class GateReq(BaseModel):
    params: dict = {}


def _gate_view(g: gate.Gate) -> dict:
    d = dataclasses.asdict(g)
    d["ok"] = g.ok
    return d


@app.post("/api/steps/{step_id}/gate")
def evaluate_gate(step_id: str, body: GateReq, con=Depends(db), c: PipelineConfig = Depends(cfg)):
    _known_step(step_id)
    cyc = active_cycle(con)
    try:
        g = gate.evaluate(con, c, cyc["id"] if cyc else None, step_id, body.params)
    except Exception as e:                               # bad params: pydantic message back to the form
        raise HTTPException(422, f"parameters are not valid: {e}")
    from core import metrics
    v = _gate_view(g)
    v["exhausted"] = [dataclasses.asdict(x) if dataclasses.is_dataclass(x) else x.model_dump() for x in metrics.matching_exhausted(c, step_id, body.params)]
    return v


def _known_step(step_id: str):
    if step_id in HIDDEN_STEPS or step_id not in steps_for(PIPELINE):
        raise HTTPException(404, f"unknown step '{step_id}'")
    return get_step(step_id)


# ------------------------------------------------------------------ jobs
class StartJob(BaseModel):
    step_id: str
    params: dict = {}
    confirmed_max_usd: float | None = None               # required for paid / llm / write: what the user saw on the gate
    confirmed_key_id: str | None = None


@app.post("/api/jobs")
def start(body: StartJob, con=Depends(db), c: PipelineConfig = Depends(cfg)):
    st = _known_step(body.step_id)
    cyc = active_cycle(con)
    try:
        st.params_model(**body.params)
    except Exception as e:
        raise HTTPException(422, f"parameters are not valid: {e}")
    if st.kind == "free":
        return {"job_id": jobs.start_job(con, body.step_id, body.params, cyc["id"] if cyc else None, pipeline=PIPELINE)}
    if body.confirmed_max_usd is None:
        raise HTTPException(400, f"'{body.step_id}' is a {st.kind} step: evaluate the gate and confirm its cost and key first")
    try:
        jid = gate.confirm_and_start(con, c, cyc["id"] if cyc else None, body.step_id, body.params, body.confirmed_max_usd, body.confirmed_key_id)
    except gate.Blocked as e:
        raise HTTPException(409, {"blockers": e.blockers})
    return {"job_id": jid}


@app.get("/api/jobs")
def list_jobs(limit: int = Query(30, ge=1, le=200), con=Depends(db)):
    jobs.reconcile(con)
    return [job_view(j) for j in jobs.list_jobs(con, limit)]


def _job(con, job_id: int):
    j = jobs.get_job(con, job_id)
    if j is None:
        raise HTTPException(404, "no such job")
    return j


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int, con=Depends(db)):
    return job_view(_job(con, job_id))


@app.get("/api/jobs/{job_id}/log")
def job_log(job_id: int, lines: int = Query(200, ge=1, le=5000), con=Depends(db)):
    _job(con, job_id)
    return {"log": jobs.tail_log(job_id, lines)}           # worker logs are already key-masked (core.logmask)


@app.post("/api/jobs/{job_id}/cancel")
def cancel(job_id: int, con=Depends(db)):
    j = _job(con, job_id)
    if j["status"] not in jobs.LIVE:
        raise HTTPException(409, f"job {job_id} is {j['status']}, not running")
    jobs.request_cancel(con, job_id)
    return {"cancel_requested": job_id}


class ResumeReq(BaseModel):
    confirmed_max_usd: float | None = None
    confirmed_key_id: str | None = None


@app.post("/api/jobs/{job_id}/resume")
def resume(job_id: int, body: ResumeReq, con=Depends(db), c: PipelineConfig = Depends(cfg)):
    j = _job(con, job_id)
    if j["status"] not in jobs.RESUMABLE:
        raise HTTPException(409, f"job {job_id} is {j['status']} and cannot be resumed")
    if j["kind"] in ("paid", "llm", "write"):
        if body.confirmed_max_usd is None:
            raise HTTPException(400, "a paid job is re-checked by the gate before it resumes: confirm its cost and key")
        try:
            return {"job_id": gate.confirm_and_resume(con, c, job_id, body.confirmed_max_usd, body.confirmed_key_id)}
        except gate.Blocked as e:
            raise HTTPException(409, {"blockers": e.blockers})
    return {"job_id": jobs.resume_job(con, job_id)}


@app.get("/api/jobs/{job_id}/resume-gate")
def resume_gate(job_id: int, con=Depends(db), c: PipelineConfig = Depends(cfg)):
    j = _job(con, job_id)
    return _gate_view(gate.evaluate(con, c, j["cycle_id"], j["step_id"], json.loads(j["params_json"] or "{}")))


# ------------------------------------------------------------------ latest records
@app.get("/api/companies")
def companies(limit: int = Query(20, ge=1, le=500), decision: str | None = None, con=Depends(db)):
    q, a = "SELECT id, cycle_id, domain, name, country, source, decision, reason_code, decided_at, evidence_json FROM companies", []
    if decision:
        q, a = q + " WHERE decision=?", [decision]
    out = []
    for r in con.execute(q + " ORDER BY id DESC LIMIT ?", (*a, limit)):
        d = dict(r)
        ev = json.loads(d.pop("evidence_json") or "{}")
        d["score"], d["evidence"] = ev.get("score"), ev.get("ev", [])[:3]
        out.append(d)
    return out


@app.get("/api/people")
def people(limit: int = Query(20, ge=1, le=500), decision: str | None = None, con=Depends(db)):
    q, a = "SELECT id, cycle_id, domain, fields_json, confidence, flags_json, decision, reason_code, decided_at FROM people", []
    if decision:
        q, a = q + " WHERE decision=?", [decision]
    out = []
    for r in con.execute(q + " ORDER BY id DESC LIMIT ?", (*a, limit)):
        d = dict(r)
        d["fields"], d["flags"] = json.loads(d.pop("fields_json") or "{}"), json.loads(d.pop("flags_json") or "[]")
        out.append(d)
    return out


# ------------------------------------------------------------------ live updates (Server-Sent Events)
def snapshot(con) -> dict:
    jobs.reconcile(con)
    jl = []
    for j in jobs.list_jobs(con, 15):
        v = job_view(j)
        if j["status"] in jobs.LIVE:
            tail = jobs.tail_log(j["id"], 1).strip()
            v["last_line"] = tail.splitlines()[-1] if tail else ""
        jl.append(v)
    cyc = active_cycle(con)
    return {"jobs": jl, "cycle": ({"id": cyc["id"], "spent_usd": spend.cycle_spend(con, cyc["id"]), "cap_usd": cyc["cap_usd"]} if cyc else None)}


@app.get("/api/events")
async def events(request: Request, interval: float = Query(1.0, ge=0.2, le=10), once: bool = False):
    """One `snapshot` event whenever jobs or spend change, and a comment line every 15 s to keep proxies from closing the stream.
    `once=1` sends a single event and closes (tests, debugging)."""
    def take() -> dict:
        con = connect()
        try:
            return snapshot(con)
        finally:
            con.close()

    async def gen():
        last, idle = None, 0.0
        while True:
            if await request.is_disconnected():
                break
            snap = await asyncio.to_thread(take)
            body = json.dumps(snap, default=str)
            if body != last:
                last, idle = body, 0.0
                yield f"event: snapshot\ndata: {body}\n\n"
                if once:
                    break
            elif idle >= 15:
                idle = 0.0
                yield ": keep-alive\n\n"
            await asyncio.sleep(interval)
            idle += interval

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
