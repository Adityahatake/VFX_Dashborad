"""The pre-run gate for paid steps. `evaluate` computes what the user is shown (max cost, key prefix, balance, remaining cap) and every
reason the run must be blocked. `confirm_and_start` re-checks at click time, so a stale screen can never start a run."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from . import jobs, keys as keymod, spend
from .config import PipelineConfig
from .steps import get_step
from .steps.base import CostEstimate


class Blocked(Exception):
    def __init__(self, blockers: list[str]):
        self.blockers = blockers
        super().__init__("; ".join(blockers))


@dataclass
class Gate:
    step_id: str
    kind: str
    estimate: CostEstimate
    cycle_id: int | None
    key_id: str | None = None
    key_balance: float | None = None
    cycle_cap: float = 0.0
    cycle_spent: float = 0.0
    reserved: float = 0.0
    remaining: float = 0.0
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.blockers


def evaluate(con: sqlite3.Connection, cfg: PipelineConfig, cycle_id: int | None, step_id: str, params: dict | None = None) -> Gate:
    step = get_step(step_id)
    p = step.params_model(**(params or {}))
    est = step.estimate_for(con, cfg, p)
    g = Gate(step_id, step.kind, est, cycle_id)
    if step.kind == "free":
        return g
    if cycle_id is None:
        g.blockers.append("no active cycle: create one on the Run Cycle page first")
        return g
    cyc = con.execute("SELECT * FROM cycles WHERE id=?", (cycle_id,)).fetchone()
    if cyc is None or cyc["status"] != "active":
        g.blockers.append("the cycle is not active")
        return g
    floor = cfg.budget.min_key_balance_usd
    if step.kind == "write":          # sheet writes have their own confirmation on the Review page; caps and stop rules are about spend
        from . import keys as _keys, sheets as _sheets
        if not _keys.is_demo(con) and _sheets.sheet_target(con) == "real_readonly":
            g.blockers.append("the sheet target is READ-ONLY (Review > Sheet and append): switch it to sandbox or real before appending")
        return g

    if step.kind == "llm":
        from . import llm
        res = llm.resolve(con, cfg, provider_factory=getattr(step, "provider_factory", None))
        if not res.on:
            g.blockers.append(res.reason)
            return g
        cap = res.cap_usd
        g.cycle_cap, g.cycle_spent = cap, spend.llm_spend(con, cycle_id)
        g.remaining = round(cap - g.cycle_spent, 4)
        if est.max_usd > g.remaining:
            g.blockers.append(f"LLM estimate ${est.max_usd:.3f} exceeds the remaining LLM cap ${g.remaining:.3f}")
        return g

    g.cycle_cap, g.cycle_spent, g.reserved = cyc["cap_usd"], spend.cycle_spend(con, cycle_id), spend.reserved(con, cycle_id)
    g.remaining = spend.remaining_cap(con, cycle_id)
    if est.max_usd > g.remaining + 1e-9:
        g.blockers.append(f"max cost ${est.max_usd:.3f} exceeds the remaining cycle cap ${g.remaining:.3f}")

    n = step.planned_records(p)
    if step.pilot_source and n is not None and n > step.pilot_records and not spend.has_run(con, step.pilot_source):
        g.blockers.append(f"pilot first: '{step.pilot_source}' has never been paid for here. Run it with at most {step.pilot_records} records, "
                          "check the cost per usable record, then run the full size")

    for ev in spend.sync_stop_events(con, cfg, cycle_id):
        g.blockers.append(f"stop rule '{ev['rule']}': {ev['reason']} (acknowledge it in the Cycle panel on Home, or on the Spend page, to continue)")

    if est.key_required and est.provider:
        k = keymod.pick_key(con, est.provider, floor)
        if k is None:
            fresh = [s for s in keymod.statuses(con, est.provider) if keymod.age_s(s["checked_at"]) <= keymod.STALE_S]
            g.blockers.append("no usable key with a fresh balance check: press 'Check balances' on the Keys page" if not fresh
                              else f"no free key at or above ${floor:.2f} (all are low, out, dead or in use by another job)")
        else:
            g.key_id, g.key_balance = k.key_id, k.remaining
            if est.provider == "apify" and est.max_usd > (k.remaining or 0) - floor:
                g.warnings.append(f"max cost ${est.max_usd:.3f} could take the key below ${floor:.2f}; the run may stop partway and return partial results")
    return g


def confirm_and_resume(con: sqlite3.Connection, cfg: PipelineConfig, job_id: int, confirmed_max_usd: float, confirmed_key_id: str | None) -> int:
    """Resume an interrupted paid/LLM job with the same checks as a fresh start (cap, key floor, stop rules)."""
    import json
    j = jobs.get_job(con, job_id)
    if j is None or j["status"] not in jobs.RESUMABLE:
        raise ValueError(f"job {job_id} cannot be resumed")
    g = evaluate(con, cfg, j["cycle_id"], j["step_id"], json.loads(j["params_json"] or "{}"))
    if g.blockers:
        raise Blocked(g.blockers)
    if abs(g.estimate.max_usd - confirmed_max_usd) > 1e-9 or g.key_id != confirmed_key_id:
        raise Blocked([f"the cost or key changed since you confirmed (now ${g.estimate.max_usd:.3f} on {g.key_id}); review and confirm again"])
    con.execute("UPDATE jobs SET key_id=?, est_max_usd=? WHERE id=?", (g.key_id, g.estimate.max_usd if g.kind != "llm" else 0.0, job_id))
    return jobs.resume_job(con, job_id, confirmed=True)


def confirm_and_start(con: sqlite3.Connection, cfg: PipelineConfig, cycle_id: int | None, step_id: str, params: dict | None,
                      confirmed_max_usd: float, confirmed_key_id: str | None) -> int:
    """Start a paid/LLM/write step. Raises Blocked if anything changed since the user saw the gate."""
    g = evaluate(con, cfg, cycle_id, step_id, params)
    if g.blockers:
        raise Blocked(g.blockers)
    if abs(g.estimate.max_usd - confirmed_max_usd) > 1e-9 or g.key_id != confirmed_key_id:
        raise Blocked([f"the cost or key changed since you confirmed (now ${g.estimate.max_usd:.3f} on {g.key_id}); review and confirm again"])
    return jobs.start_job(con, step_id, params, cycle_id, confirmed=True, key_id=g.key_id, est_max_usd=g.estimate.max_usd if g.kind != "llm" else 0.0,
                          pipeline=cfg.name)
