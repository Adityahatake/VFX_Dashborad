"""Paid people steps (ported from VFX leads_run.py and salesnav.py), on top of core.apify's no-relaunch run flow.
Both: one key under a lease, the key and maximum cost confirmed at the gate, spend recorded once per run, results cached so a rerun is free."""
from __future__ import annotations

import json
import re
import time

from pydantic import BaseModel, ConfigDict, Field

from .. import apify, review
from ..dedupe import country_key
from ..people import people_from_leads
from ..textnorm import clean_domain, norm
from .base import CostEstimate, Step, StepContext, StepResult, register
from .harvest import _need_pipeline

LEADS_ACTOR = "microworlds~leads-finder"
SALESNAV_ACTOR = "bestscrapers~sales-navigator-scraper-by-filters"
MAX_DOMAINS_PER_RUN = 40          # large companies swamp a batch's result cap: keep batches at about 40 websites (02_find_people.md)


def _write_json(path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------- leads finder
class LeadsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag: str = Field("leads", pattern=r"^[a-z0-9_]{1,30}$")
    domains: list[str] = []                          # empty = approved companies of this cycle that have no people yet
    max_result: int = Field(50, ge=1, le=2000)
    price_per_result: float = Field(0.003, gt=0)


@register
class LeadsFinder(Step):
    id = "leads_finder"
    kind = "paid"
    title = "Leads finder: decision-makers by company website (paid, one key)"
    params_model = LeadsParams
    pilot_source = LEADS_ACTOR

    def planned_records(self, p: LeadsParams) -> int:
        return p.max_result

    def estimate_cost(self, ctx, p: LeadsParams) -> CostEstimate:
        return CostEstimate(max_usd=round(p.max_result * p.price_per_result, 6), provider="apify", key_required=True,
                            note=f"{p.max_result} results x ${p.price_per_result}")

    def _domains(self, ctx: StepContext, p: LeadsParams) -> list[str]:
        if p.domains:
            doms = [clean_domain(d) for d in p.domains]
        else:
            have = {r[0] for r in ctx.db.execute("SELECT DISTINCT domain FROM people WHERE cycle_id=?", (ctx.cycle_id,))}
            doms = [r[0] for r in ctx.db.execute("SELECT domain FROM companies WHERE cycle_id=? AND decision='approved' ORDER BY id", (ctx.cycle_id,)) if r[0] not in have]
        doms = list(dict.fromkeys(d for d in doms if d))
        if not doms:
            raise ValueError("no domains: approve companies on the Review page first, or pass 'domains'")
        if len(doms) > MAX_DOMAINS_PER_RUN:
            ctx.log(f"{len(doms)} domains; using the first {MAX_DOMAINS_PER_RUN} (a bigger batch lets large companies swamp the result cap). Run again for the rest")
            doms = doms[:MAX_DOMAINS_PER_RUN]
        return doms

    def run(self, ctx: StepContext, p: LeadsParams) -> StepResult:
        _need_pipeline(ctx)
        cfg = ctx.cfg
        from .. import keys as keymod
        # Demo mode (synthetic leads) must never leave files where pool_match / pool rescans would read them as real leads.
        pool = (ctx.workdir if keymod.is_demo(ctx.db) else ctx.pipeline_dir / "pools") / f"pool_{p.tag}.json"
        pool.parent.mkdir(parents=True, exist_ok=True)
        cost = 0.0
        if pool.exists():                                           # cached: a rerun costs nothing
            items = json.loads(pool.read_text(encoding="utf-8"))
            ctx.log(f"cached pool_{p.tag}.json: {len(items)} leads, no new spend")
        else:
            doms = self._domains(ctx, p)
            inp = {"company_domains": doms, "contact_job_titles": [t.casefold() for t in cfg.people.decision_titles],
                   "contact_not_location": sorted({c.casefold() for c in cfg.countries.excluded}), "max_result": p.max_result}
            est = self.estimate_cost(ctx, p).max_usd
            ctx.log(f"{len(doms)} domains, max cost ${est:.3f}")
            with ctx.use_key("apify") as (kid, secret):
                client = apify.get_client(ctx.db, secret)
                status, items, run, recovered = apify.run_actor(client, ctx.db, job_id=ctx.job_id, actor=LEADS_ACTOR, inp=inp, key_id=kid, log=ctx.log, check_cancel=ctx.check_cancel)
                cost = apify.actual_cost(run, len(items), p.price_per_result)
                apify.spend_once(ctx, run["id"], source=LEADS_ACTOR, est_max_usd=est, actual_usd=cost, results=len(items), key_id=kid,
                                 note=("recovered " if recovered else "") + status)
                _write_json(pool, items)                              # saved before anything else can fail
                apify.mark_consumed(ctx.db, run["id"])
            if status != "SUCCEEDED":
                ctx.log(f"WARNING: run status {status}: results may be partial (credit ran out?). Check the key's balance before running the remaining batches")
            if len(items) >= p.max_result:
                ctx.log("WARNING: the result cap was reached; large companies may have swamped it. Filter hard and consider smaller batches")
        res = people_from_leads(ctx.db, cfg, ctx.cycle_id, items) if ctx.cycle_id else {"added": 0, "companies": 0, "skipped": {}}
        ctx.log(f"{len(items)} leads -> {res['added']} candidates for review across {res['companies']} companies; filtered out: {res['skipped'] or 'none'}")
        return StepResult(counts={"leads": len(items), "candidates": res["added"]}, artifacts=[], actual_cost=cost,
                          message=f"{len(items)} leads, {res['added']} candidates, ${cost:.3f}")


# ---------------------------------------------------------------- Sales Navigator (async gap fill)
PAGE = 100                                                           # the actor returns at most 100 rows per page
PENDING = re.compile(r"check back|in progress|processing|pending|not ready|try again", re.I)
TITLE_KEYS = ("title", "current_title", "position", "job_title", "headline")
URL_KEYS = ("profile_url", "linkedin_url", "url", "profile_link", "linkedin_profile_url")


class SalesNavParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag: str = Field("sn", pattern=r"^[a-z0-9_]{1,30}$")
    companies: list[str] = Field(..., min_length=1, max_length=10)   # one search covers at most 10 companies
    locations: dict[str, str] = {}                                    # company -> regex its people's location must match (short names return namesakes)
    limit: int = Field(40, ge=1, le=1000)
    search_price: float = Field(0.50, ge=0)
    result_price: float = Field(0.01, gt=0)                           # charged for EVERY result on EVERY fetch
    max_wait_polls: int = Field(10, ge=0, le=60)
    poll_wait_s: float = Field(60, ge=0, le=600)


def page_rows(items: list) -> list[dict]:
    rows = []
    for it in items:
        d = it.get("data") if isinstance(it, dict) else None
        rows += d if isinstance(d, list) else ([it] if isinstance(it, dict) and it.get("full_name") else [])
    return rows


def _company(r: dict) -> str:
    c = r.get("current_company") or r.get("company_name") or r.get("company") or ""
    return c.get("name", "") if isinstance(c, dict) else str(c)


def lead_from_row(r: dict) -> dict:
    """Map a Sales Navigator row to the lead shape used everywhere else. Field names are tolerant: the first pilot must confirm the mapping."""
    name = (r.get("full_name") or f"{r.get('first_name', '')} {r.get('last_name', '')}").strip()
    first, _, last = name.partition(" ")
    return {"first_name": first, "last_name": last, "title": next((str(r[k]) for k in TITLE_KEYS if r.get(k)), ""),
            "linkedin_url": next((str(r[k]) for k in URL_KEYS if r.get(k)), ""), "organization_name": _company(r), "country": "",
            "city": str(r.get("location") or ""), "headline": str(r.get("headline") or "")}


def matches(rows: list[dict], targets: dict[str, str]) -> list[dict]:
    """Keep rows whose company equals a target after normalisation AND whose location fits (VFX: 'VAIN' returned 38 of 40 namesakes)."""
    out = []
    for r in rows:
        comp = norm(_company(r)).replace(" ", "")
        for t, loc in targets.items():
            if comp == norm(t).replace(" ", "") and re.search(loc or "", str(r.get("location") or ""), re.I):
                out.append({**r, "target": t})
                break
    return out


@register
class SalesNav(Step):
    id = "salesnav"
    kind = "paid"
    title = "Sales Navigator gap fill (paid, async, last resort)"
    params_model = SalesNavParams
    pilot_source = SALESNAV_ACTOR

    def planned_records(self, p: SalesNavParams) -> int:
        return p.limit

    def estimate_cost(self, ctx, p: SalesNavParams) -> CostEstimate:
        return CostEstimate(max_usd=round(p.search_price + p.limit * p.result_price, 6), provider="apify", key_required=True,
                            note=f"${p.search_price} search + up to {p.limit} results x ${p.result_price} (charged per fetch)")

    def run(self, ctx: StepContext, p: SalesNavParams) -> StepResult:
        _need_pipeline(ctx)
        cfg, con = ctx.cfg, ctx.db
        f = ctx.workdir / f"salesnav_{p.tag}.json"
        st = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        est = self.estimate_cost(ctx, p).max_usd
        cost = 0.0
        with ctx.use_key("apify") as (kid, secret):
            if st and st.get("key_id") != kid:
                raise RuntimeError(f"this search was submitted with key {st.get('key_id')} and can only be continued with it (now {kid}); "
                                   "start the step again so the gate picks that key, or use a new tag for a new search")
            client = apify.get_client(con, secret)
            if not st.get("request_id"):                              # submit exactly once per tag
                inp = {"current_company_names": p.companies, "title_keywords": [t.casefold() for t in cfg.people.decision_titles][:20], "limit": p.limit}
                status, items, run, rec = apify.run_actor(client, con, job_id=ctx.job_id, actor=SALESNAV_ACTOR, inp=inp, key_id=kid, log=ctx.log, check_cancel=ctx.check_cancel)
                rid = next((it.get("request_id") for it in items if isinstance(it, dict) and it.get("request_id")), None)
                if not rid:
                    raise RuntimeError(f"no request_id in the search response: {json.dumps(items)[:300]}")
                c = apify.actual_cost(run, 0, 0, extra=p.search_price)
                apify.spend_once(ctx, run["id"], source=SALESNAV_ACTOR, est_max_usd=est, actual_usd=c, results=0, key_id=kid, note="search submitted")
                cost += c
                st = {"request_id": rid, "key_id": kid, "companies": p.companies, "limit": p.limit, "pages": {}}
                _write_json(f, st)                                    # request_id saved before any polling
                apify.mark_consumed(con, run["id"])
                ctx.log(f"submitted search, request_id {rid} (charged ${c:.2f})")
            page, waits = 1 + len(st["pages"]), 0
            total = sum(len(v) for v in st["pages"].values())
            while total < st["limit"]:
                ctx.check_cancel()
                status, items, run, rec = apify.run_actor(client, con, job_id=ctx.job_id, actor=SALESNAV_ACTOR, inp={"request_id": st["request_id"], "page": page},
                                                          key_id=kid, log=ctx.log, check_cancel=ctx.check_cancel)
                rows = page_rows(items)
                if not rows:                                          # an empty poll costs nothing
                    apify.mark_consumed(con, run["id"])
                    if PENDING.search(json.dumps(items)) and waits < p.max_wait_polls:
                        waits += 1
                        ctx.log(f"page {page}: not ready, waiting ({waits}/{p.max_wait_polls})")
                        time.sleep(p.poll_wait_s)
                        continue
                    ctx.log(f"page {page}: no rows; done")
                    break
                c = apify.actual_cost(run, len(rows), p.result_price)
                apify.spend_once(ctx, run["id"], source=SALESNAV_ACTOR, est_max_usd=est, actual_usd=c, results=len(rows), key_id=kid, note=f"page {page}")
                cost += c
                st["pages"][str(page)] = rows                         # each page saved ONCE, immediately: a page is never fetched twice
                _write_json(f, st)
                apify.mark_consumed(con, run["id"])
                total += len(rows)
                ctx.log(f"page {page}: {len(rows)} rows (total {total}, this run's cost so far ${cost:.2f})")
                if len(rows) < PAGE:
                    break
                page += 1
        allrows = [r for k in sorted(st["pages"], key=int) for r in st["pages"][k]]
        keep = matches(allrows, {c: p.locations.get(c, "") for c in p.companies})
        ctx.log(f"{len(allrows)} rows fetched, {len(keep)} match a target company and location")
        added = 0
        if ctx.cycle_id and keep:
            dom = {norm(r["name"]).replace(" ", ""): r["domain"] for r in con.execute("SELECT name, domain FROM companies WHERE cycle_id=? AND decision='approved'", (ctx.cycle_id,))}
            leads = []
            for r in keep:
                ld = lead_from_row(r)
                ld["organization_primary_domain"] = dom.get(norm(r["target"]).replace(" ", ""), "")
                if not ld["linkedin_url"]:
                    ctx.log(f"row without a profile URL (fields seen: {sorted(r)[:12]}): skipped; the pilot must confirm the actor's field names")
                    continue
                leads.append(ld)
            res = people_from_leads(con, cfg, ctx.cycle_id, leads)
            added = res["added"]
            ctx.log(f"{added} candidates added for review; filtered out: {res['skipped'] or 'none'} (companies must be approved in Review first)")
        return StepResult(counts={"rows": len(allrows), "matched": len(keep), "candidates": added}, artifacts=[f.name], actual_cost=cost,
                          message=f"{len(allrows)} rows, {len(keep)} matched, {added} candidates, ${cost:.2f}")
