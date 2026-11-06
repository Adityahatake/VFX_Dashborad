"""LLM assist steps (kind 'llm': separate spend, own cap, optional). They only PRE-FILL suggestions into companies.llm_json / people.llm_json.
Nothing here approves, rejects, appends or edits a sheet. Results are checkpointed in the database per item, so a rerun skips finished items."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from .. import keys, llm, paths, spend, web
from ..llm import checks, prompts
from ..llm.base import approx_tokens
from ..llm.schemas import COMPANY_SCHEMA, PERSON_SCHEMA
from .base import CostEstimate, Step, StepContext, StepResult, register
from .harvest import _need_pipeline

SYSTEMIC = ("rate_limited", "auth_error", "bad_request", "connection_error")      # errors that will repeat for every item: stop the batch


class VerdictParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_items: int = Field(25, ge=1, le=300)
    redo: bool = False                                  # ask again even if an up-to-date verdict (same prompt, model and rubric) exists
    max_output_tokens: int = Field(500, ge=100, le=2000)


class DraftParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_items: int = Field(25, ge=1, le=300)
    redo: bool = False
    max_output_tokens: int = Field(700, ge=100, le=2000)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def item_max_usd(prices: dict, system_tokens: int, user_tokens: int, out_tokens: int) -> float:
    """Worst case for ONE call: the system prompt read from cache, the user text uncached, the full output allowance."""
    return (system_tokens * prices["cache_read"] + user_tokens * prices["in"] + out_tokens * prices["out"]) / 1_000_000


def cache_write_usd(prices: dict, system_tokens: int) -> float:
    """What the FIRST call of a run pays to write the cached system prompt (later calls read it for a tenth of the input price)."""
    return system_tokens * prices["cache_write"] / 1_000_000


def estimate(con, cfg, n: int, system: str, user_chars: int, out_tokens: int) -> CostEstimate:
    res = llm.resolve(con, cfg)
    if not res.on:
        return CostEstimate(max_usd=0.0, provider="llm", note=res.reason)
    st = approx_tokens(system)
    worst = n * item_max_usd(res.prices, st, approx_tokens("x" * user_chars), out_tokens) + st * res.prices["cache_write"] / 1_000_000    # + one cache write
    return CostEstimate(max_usd=round(worst, 6), provider="llm", key_required=False, note=f"up to {n} calls on {res.model}, system prompt ~{st} tokens (cached)")


class _LLMStep(Step):
    kind = "llm"

    def _setup(self, ctx: StepContext):
        _need_pipeline(ctx)
        res = llm.resolve(ctx.db, ctx.cfg, provider_factory=(lambda: ctx.llm) if ctx.llm is not None else None)
        if not res.on:
            raise RuntimeError(res.reason)
        return res

    def _record(self, ctx, res, est_max, r, what: str) -> None:
        ctx.record_spend(source=res.model, est_max_usd=est_max, actual_usd=r.cost_usd or 0.0, results=1, key_id=None, kind="llm",
                         note=f"{what} in={r.input_tokens} cr={r.cache_read_tokens} cw={r.cache_write_tokens} out={r.output_tokens} {r.error or ''}".strip())


@register
class LLMVerdicts(_LLMStep):
    id = "llm_verdicts"
    title = "LLM company verdicts (optional; suggestions only)"
    params_model = VerdictParams

    def estimate_for(self, con, cfg, p: VerdictParams) -> CostEstimate:
        return estimate(con, cfg, p.max_items, prompts.company_system(cfg, paths.PIPELINES_DIR / cfg.name), cfg.llm.max_page_chars + 2500, p.max_output_tokens)

    def run(self, ctx: StepContext, p: VerdictParams) -> StepResult:
        res = self._setup(ctx)
        cfg, con = ctx.cfg, ctx.db
        system = prompts.company_system(cfg, paths.PIPELINES_DIR / cfg.name)
        rh, st = prompts.rubric_hash(system), approx_tokens(system)
        per_item = item_max_usd(res.prices, st, approx_tokens("x" * (cfg.llm.max_page_chars + 2500)), p.max_output_tokens)
        rows = con.execute("SELECT * FROM companies WHERE cycle_id=? AND decision IN ('pending','look') ORDER BY id", (ctx.cycle_id,)).fetchall()
        todo = []
        for r in rows:
            cur = json.loads(r["llm_json"]) if r["llm_json"] else None
            if cur and not p.redo and cur.get("prompt_version") == prompts.COMPANY_VERDICT_V and cur.get("model") == res.model and cur.get("rubric_hash") == rh and not cur.get("error"):
                continue
            todo.append(r)
        todo = todo[: p.max_items]
        ctx.log(f"{len(todo)} companies to ask about ({len(rows) - len(todo)} skipped: already have an up-to-date verdict or over max_items); model {res.model}, LLM cap ${res.cap_usd:.2f}")
        counts = {"yes": 0, "no": 0, "unsure": 0, "errors": 0}
        cost, stopped, first = 0.0, "", True
        for r in todo:
            ctx.check_cancel()
            if spend.llm_spend(con, ctx.cycle_id) + per_item + (cache_write_usd(res.prices, st) if first else 0.0) > res.cap_usd:     # the first call also writes the cache
                stopped = f"LLM cap ${res.cap_usd:.2f} reached"
                break
            ev = json.loads(r["evidence_json"] or "{}").get("ev") or []
            sentences = [s for _, s in ev]
            url = ev[0][0] if ev else f"https://{r['domain']}"
            page = "" if keys.is_demo(con) else web.text(web.fetch(url)[1])          # demo mode makes no network calls at all
            body = "\n".join(sentences) + "\n\n" + page                      # matched sentences first, then the page, trimmed as one block
            page_text = body[: cfg.llm.max_page_chars]
            user = prompts.company_user(url, r["country"] or "", sentences, page_text if page else "(page could not be fetched)")
            out = res.provider.complete_json(model=res.model, system=system, user=user, schema=COMPANY_SCHEMA, max_tokens=p.max_output_tokens, effort=cfg.llm.effort)
            self._record(ctx, res, per_item, out, f"company {r['domain']}")
            first = False
            cost += out.cost_usd or 0.0
            verdict = checks.finalize_company(checks.parse_company(out.parsed, out.error), [page_text] + sentences, cfg)
            verdict.update(model=res.model, prompt_version=prompts.COMPANY_VERDICT_V, rubric_hash=rh, cost_usd=out.cost_usd, error=out.error or "", at=_now(),
                           tokens={"in": out.input_tokens, "out": out.output_tokens, "cache_read": out.cache_read_tokens, "cache_write": out.cache_write_tokens})
            con.execute("UPDATE companies SET llm_json=? WHERE id=?", (json.dumps(verdict, ensure_ascii=False), r["id"]))
            counts[verdict["qualifies"]] += 1
            counts["errors"] += bool(out.error)
            ctx.log(f"{r['domain']}: {verdict['qualifies']} ({verdict.get('code') or 'ok'}) ${out.cost_usd or 0:.4f}")
            if out.error and out.error.split(":")[0] in SYSTEMIC:
                stopped = f"stopped: {out.error} (it would repeat for every item). Fix it and run again; finished items are kept"
                break
        if stopped:
            ctx.log(stopped)
        return StepResult(status="partial" if stopped and "cap" not in stopped else "done", counts=counts, actual_cost=cost,
                          message=f"{sum(counts[k] for k in ('yes', 'no', 'unsure'))} verdicts, ${cost:.3f}" + (f"; {stopped}" if stopped else ""))


@register
class LLMPersonDrafts(_LLMStep):
    id = "llm_person_drafts"
    title = "LLM person drafts (optional; suggestions only)"
    params_model = DraftParams

    def estimate_for(self, con, cfg, p: DraftParams) -> CostEstimate:
        return estimate(con, cfg, p.max_items, prompts.person_system(cfg, paths.PIPELINES_DIR / cfg.name), 2500, p.max_output_tokens)

    def run(self, ctx: StepContext, p: DraftParams) -> StepResult:
        res = self._setup(ctx)
        cfg, con = ctx.cfg, ctx.db
        system = prompts.person_system(cfg, paths.PIPELINES_DIR / cfg.name)
        rh, st = prompts.rubric_hash(system), approx_tokens(system)
        per_item = item_max_usd(res.prices, st, approx_tokens("x" * 2500), p.max_output_tokens)
        rows = con.execute("SELECT * FROM people WHERE cycle_id=? AND decision='pending' ORDER BY id", (ctx.cycle_id,)).fetchall()
        todo = []
        for r in rows:
            cur = json.loads(r["llm_json"]) if r["llm_json"] else None
            if cur and not p.redo and cur.get("prompt_version") == prompts.PERSON_DRAFT_V and cur.get("model") == res.model and cur.get("rubric_hash") == rh and not cur.get("error"):
                continue
            todo.append(r)
        todo = todo[: p.max_items]
        ctx.log(f"{len(todo)} people to draft; model {res.model}, LLM cap ${res.cap_usd:.2f}")
        done, cost, stopped, first = 0, 0.0, "", True
        for r in todo:
            ctx.check_cancel()
            if spend.llm_spend(con, ctx.cycle_id) + per_item + (cache_write_usd(res.prices, st) if first else 0.0) > res.cap_usd:
                stopped = f"LLM cap ${res.cap_usd:.2f} reached"
                break
            f = json.loads(r["fields_json"])
            same = [json.loads(x["fields_json"]) for x in con.execute("SELECT fields_json FROM people WHERE cycle_id=? AND domain=? AND id!=?", (ctx.cycle_id, r["domain"], r["id"]))]
            user = prompts.person_user(f.get("company", ""), f.get("ai_evidence", ""), f.get("title", ""), f.get("_headline", ""), f.get("_location", "") or f.get("country", ""),
                                       [f"{x.get('title', '')} ({x.get('role', '')})" for x in same])
            out = res.provider.complete_json(model=res.model, system=system, user=user, schema=PERSON_SCHEMA, max_tokens=p.max_output_tokens, effort=cfg.llm.effort)
            self._record(ctx, res, per_item, out, f"person {f.get('name', '')}")
            first = False
            cost += out.cost_usd or 0.0
            draft = checks.parse_person(out.parsed, out.error)
            meta = {"model": res.model, "prompt_version": prompts.PERSON_DRAFT_V, "rubric_hash": rh, "cost_usd": out.cost_usd, "error": out.error or "", "at": _now()}
            if draft is None:
                con.execute("UPDATE people SET llm_json=? WHERE id=?", (json.dumps({**meta, "error": out.error or "llm_parse_error"}), r["id"]))
                ctx.log(f"{f.get('name')}: no usable draft ({out.error or 'invalid output'})")
            else:
                con.execute("UPDATE people SET llm_json=? WHERE id=?", (json.dumps({**checks.finalize_person(draft, cfg), **meta}, ensure_ascii=False), r["id"]))
                done += 1
                ctx.log(f"{f.get('name')}: drafted ${out.cost_usd or 0:.4f}")
            if out.error and out.error.split(":")[0] in SYSTEMIC:
                stopped = f"stopped: {out.error} (it would repeat for every item). Fix it and run again; finished items are kept"
                break
        if stopped:
            ctx.log(stopped)
        return StepResult(status="partial" if stopped and "cap" not in stopped else "done", counts={"drafted": done}, actual_cost=cost,
                          message=f"{done} drafts, ${cost:.3f}" + (f"; {stopped}" if stopped else ""))
