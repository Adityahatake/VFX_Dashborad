"""Stage 1, company discovery with Tavily (paid: one credit per basic search). Step id `harvest_tavily_press` (the VFX pipeline's
planned trade-press / web search step).

SOP 01 s5: "Discovery is not qualification." Search results only nominate candidate DOMAINS; deep_crawl then reads each company's own
site for evidence, and the qualification checks decide. A result page on a press, platform or social site is never a candidate itself
(the company it mentions has to be found on its own site).

Writes <tag>_domains.json in the same shape as the free harvests ({domain: [{organization_name, desc, loc, cat, url}]}), so deep_crawl
with the same tag reads it. Resumable: every finished query is appended to <tag>_tavily.jsonl and never searched (or paid for) again."""
from __future__ import annotations

import json
import re
import urllib.error

from pydantic import BaseModel, ConfigDict, Field

from .. import http, known
from ..textnorm import clean_domain, domain_is_known, squash
from .base import CostEstimate, Step, StepContext, StepResult, register
from .harvest import _need_pipeline

TAVILY_SOURCE = "tavily~search"           # ledger source name (also the pilot-rule key)

# Built from SOP 01 s5 discovery signals and the pipeline's evidence terms: AI used in real client production work.
DEFAULT_QUERIES = [
    "VFX studio generative AI commercial for brand client case study",
    "production company AI-generated commercial brand campaign case study",
    "animation studio generative AI campaign client project",
    "post-production studio generative AI VFX client work",
    "AI film studio commercial made with Runway Midjourney for brand",
    "creative production studio AI spot TV commercial launched client",
    "virtual production studio generative AI brand film",
    "hybrid AI commercial production company our work",
    "AI music video production studio client project",
    "localization dubbing studio generative AI client production",
    "KI-generierter Werbespot Produktionsfirma Kunde",
    "KI-Film Kampagne Produktionsfirma Projekt",
    "film publicitaire IA générative société de production client",
    "spot publicitario generado con IA productora cliente",
    "spot pubblicitario intelligenza artificiale generativa casa di produzione",
    "comercial gerado por IA produtora cliente",
    "AI commercial production studio case study Kling Veo Sora",
    "generative AI advertising production studio portfolio brand",
    "AI-generated brand film studio Europe client",
    "AI animation studio commercial for client 2026",
]

# Result pages on these sites are about companies, not the company's own site: never a candidate.
NON_COMPANY_DOMAINS = {
    "linkedin.com", "youtube.com", "youtu.be", "vimeo.com", "instagram.com", "facebook.com", "x.com", "twitter.com", "tiktok.com",
    "reddit.com", "medium.com", "substack.com", "wikipedia.org", "github.com", "behance.net", "dribbble.com", "pinterest.com",
    "adage.com", "adweek.com", "campaignlive.co.uk", "campaignlive.com", "shots.net", "lbbonline.com", "creativereview.co.uk",
    "thedrum.com", "fxguide.com", "cartoonbrew.com", "variety.com", "hollywoodreporter.com", "deadline.com", "indiewire.com",
    "befores-afters.com", "vfxvoice.com", "postmagazine.com", "musebycl.io", "adsoftheworld.com", "forbes.com", "techcrunch.com",
    "theverge.com", "wired.com", "businessinsider.com", "nytimes.com", "theguardian.com", "bbc.co.uk", "bbc.com", "cnn.com",
    "pymnts.com", "c21media.net", "prnewswire.com", "businesswire.com", "globenewswire.com", "openai.com", "runwayml.com",
    "midjourney.com", "google.com", "blog.google", "adobe.com", "apple.com", "amazon.com", "news.ycombinator.com",
}
PRESS_WORDS = re.compile(r"(news|magazine|journal|times|daily|weekly|insider|review|press|report|digest|blog|wire|tribune)", re.I)


class TavilyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag: str = Field("tv", pattern=r"^[a-z0-9_]{1,30}$")
    queries: list[str] = Field(default_factory=lambda: list(DEFAULT_QUERIES), min_length=1, max_length=200)
    max_queries: int = Field(20, ge=1, le=200)          # each query costs one Tavily credit
    max_results: int = Field(10, ge=1, le=20)
    time_range: str | None = Field("month", pattern=r"^(day|week|month|year)$")   # VFX notes: trade press is mined out; rerun monthly only
    search_depth: str = Field("basic", pattern=r"^(basic|advanced)$")             # advanced costs 2 credits
    price_per_credit: float = Field(0.008, gt=0)        # pay-as-you-go price; a free-plan credit still counts as spend for the stop rules


def credits_per_query(p: TavilyParams) -> int:
    return 2 if p.search_depth == "advanced" else 1


def non_company(domain: str) -> str:
    """Why a result domain cannot be a company candidate ('' = it can)."""
    d = domain.lower()
    if any(d == x or d.endswith("." + x) for x in NON_COMPANY_DOMAINS):
        return "press / platform / social site"
    if PRESS_WORDS.search(d.split(".")[0]):
        return "looks like a publication"
    return ""


def pick_candidates(cfg, results: list[dict], names: set[str], seen: set[str], query_ix: int) -> tuple[dict, dict]:
    """Search results -> {domain: [meta]} for NEW, plausible company domains, plus counts of why the others were dropped."""
    india = re.compile("|".join(cfg.countries.excluded_patterns), re.I) if cfg.countries.excluded_patterns else None
    reject = {squash(n) for n in cfg.icp.reject_names}
    out, why = {}, {}
    for r in results:
        d = clean_domain(r.get("url") or "")
        reason = ""
        if not d:
            reason = "no domain"
        elif d in seen or d in out:
            reason = "duplicate in this run"
        elif non_company(d):
            reason = non_company(d)
        elif india and india.search(d):
            reason = "excluded country"
        elif squash(d.split(".")[0]) in reject:
            reason = "rejected company name"
        elif domain_is_known(d, names):
            reason = "already known (sheet, crawled, verified or rejected)"
        if reason:
            why[reason] = why.get(reason, 0) + 1
            continue
        out[d] = [{"organization_name": (r.get("title") or d)[:120], "desc": (r.get("content") or "")[:400], "loc": "", "cat": f"q{query_ix}",
                   "url": r.get("url") or ""}]
    return out, why


@register
class HarvestTavily(Step):
    id = "harvest_tavily_press"
    kind = "paid"
    title = "Tavily web search for VFX / production companies using GenAI (paid: Tavily credits)"
    params_model = TavilyParams
    pilot_source = TAVILY_SOURCE

    def planned_records(self, p: TavilyParams) -> int:
        return min(p.max_queries, len(p.queries))        # the pilot rule counts searches

    def estimate_cost(self, ctx, p: TavilyParams) -> CostEstimate:
        n = self.planned_records(p) * credits_per_query(p)
        return CostEstimate(max_usd=round(n * p.price_per_credit, 6), provider="tavily", key_required=True,
                            note=f"{n} Tavily credits x ${p.price_per_credit}")

    def run(self, ctx: StepContext, p: TavilyParams) -> StepResult:
        _need_pipeline(ctx)
        cfg = ctx.cfg
        done_path, dom_path = ctx.workdir / f"{p.tag}_tavily.jsonl", ctx.workdir / f"{p.tag}_domains.json"
        done: dict[int, dict] = {}
        if done_path.exists():
            for line in done_path.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                    done[r["i"]] = r
                except Exception:
                    pass
        names = known.known_names(ctx.db, cfg.name, ("crawled", "verified", "rejected"))
        domains: dict = json.loads(dom_path.read_text(encoding="utf-8")) if dom_path.exists() else {}
        todo = [(i, q) for i, q in enumerate(p.queries[: p.max_queries]) if i not in done]
        ctx.log(f"{len(todo)} Tavily searches to run ({len(done)} already done), {credits_per_query(p)} credit(s) each")
        searched = failed = 0
        dropped: dict[str, int] = {}
        stop = ""
        with ctx.use_key("tavily") as (kid, secret):
            for i, q in todo:
                ctx.check_cancel()
                body = {"query": q, "max_results": p.max_results, "search_depth": p.search_depth, "topic": "general"}
                if p.time_range:
                    body["time_range"] = p.time_range
                try:
                    res = http.post_json("https://api.tavily.com/search", body, secret)     # sent once; a search is never retried
                except urllib.error.HTTPError as e:
                    from .. import keys as keymod
                    state = keymod.mark_failed(ctx.db, kid, "tavily", e.code, str(e))
                    if state in ("dead", "out"):
                        stop = f"key {kid} is {state} (HTTP {e.code})"
                        ctx.log(f"STOP: {stop}; {len(todo) - searched - failed} searches left for another key")
                        break
                    failed += 1
                    ctx.log(f"search {i + 1} failed: HTTP {e.code}; skipped")
                    continue
                except Exception as e:                    # network trouble: we do not know if a credit was used, so we do not repeat it
                    failed += 1
                    ctx.log(f"search {i + 1} failed ({type(e).__name__}); skipped, not retried")
                    continue
                n = credits_per_query(p)
                ctx.record_spend(source=TAVILY_SOURCE, est_max_usd=n * p.price_per_credit, actual_usd=n * p.price_per_credit,
                                 results=len(res.get("results") or []), key_id=kid, note=f"credits={n}", kind="tavily")
                new, why = pick_candidates(cfg, res.get("results") or [], names, set(domains), i)
                for k, v in why.items():
                    dropped[k] = dropped.get(k, 0) + v
                domains.update(new)
                tmp = dom_path.with_suffix(".tmp")
                tmp.write_text(json.dumps(domains, ensure_ascii=False), encoding="utf-8")
                tmp.replace(dom_path)                       # domains first, then mark the query done: a crash never loses a paid result
                with open(done_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"i": i, "q": q, "results": len(res.get("results") or []), "new": sorted(new)}) + "\n")
                searched += 1
                ctx.log(f"search {i + 1}/{len(p.queries[: p.max_queries])}: {len(res.get('results') or [])} results, {len(new)} new candidate companies")
        if not dom_path.exists():
            dom_path.write_text("{}", encoding="utf-8")
        ctx.log(f"dropped results: {dropped or 'none'}")
        msg = f"{len(domains)} candidate companies from {searched} searches" + (f"; stopped: {stop}" if stop else "")
        return StepResult(status="partial" if stop and searched + failed < len(todo) else "done",
                          counts={"searches": searched, "failed": failed, "candidates": len(domains), **{f"dropped:{k}": v for k, v in dropped.items()}},
                          artifacts=[dom_path.name, done_path.name], actual_cost=searched * credits_per_query(p) * p.price_per_credit, message=msg)
