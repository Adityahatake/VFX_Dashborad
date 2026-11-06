"""Deep crawl (ported from VFX deep_crawl.py): homepage + up to N work/case/AI pages per company, keeping sentences where strong AI wording
sits next to a client cue. Resumable (JSONL append, done domains are skipped). Hits become pending rows for the Review page."""
from __future__ import annotations

import glob
import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .. import known, patterns, web
from ..textnorm import domain_is_known, norm, squash
from .base import Step, StepContext, StepResult, register
from .harvest import _need_pipeline

INNER_KEYWORDS = r"\b(ai|ki|ia|genai|work|works|projects?|projekte|referenzen|references|cases?|case-studies|portfolio|arbeiten|trabajos|proyectos|lavori|clients|news|blog)\b"


class CrawlParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag: str = Field("rb", pattern=r"^[a-z0-9_]{1,30}$")      # reads <tag>_domains.json, writes <tag>_crawl.jsonl
    source: Literal["domains", "pools"] = "domains"            # "pools": first build <tag>_domains.json from already-paid pool_*.json leads
    threads: int = Field(40, ge=1, le=64)
    max_inner_pages: int = Field(6, ge=0, le=20)
    limit: int | None = Field(None, ge=1)                      # crawl at most this many domains (pilots, demos)
    inner_page_keywords: str = INNER_KEYWORDS


def crawl_one(domain: str, pat: patterns.Patterns, max_inner: int, keyp: re.Pattern) -> dict:
    u, h = web.fetch("https://" + domain)
    if not h:
        u, h = web.fetch("http://" + domain)
    if not h:
        return {"domain": domain, "score": -1}

    def keep(path: str) -> bool:
        seg = [s for s in path.lower().split("/") if s]
        return bool(seg) and len(seg) <= 3 and any(keyp.search(s.replace("-", " ")) for s in seg)

    sents, seen = [], set()
    for pu, ph in [(u, h)] + [web.fetch(link) for link in web.internal_links(u, h, keep, max_inner)]:
        for s in patterns.evidence_hits(web.text(ph), pat, seen=seen):
            sents.append((pu, s))
    return {"domain": domain, "score": len(sents), "ev": sents[:5]}


def build_pool_domains(ctx: StepContext, tag: str) -> int:
    """VFX `deep_crawl pools`: re-screen companies from paid pools that were never verified (homepage-only checks missed qualifying studios)."""
    cfg = ctx.cfg
    ok = re.compile("|".join(re.escape(t) for t in cfg.people.decision_titles), re.I)
    bad = re.compile("|".join(rf"\b{re.escape(t)}\b" for t in cfg.people.reject_titles), re.I) if cfg.people.reject_titles else None
    india = re.compile("|".join(cfg.countries.excluded_patterns), re.I) if cfg.countries.excluded_patterns else None
    names, by = known.known_names(ctx.db, cfg.name), {}
    for f in glob.glob(str(ctx.pipeline_dir / "pools" / "pool_*.json")):
        try:
            items = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for it in items:
            d = (it.get("organization_primary_domain") or "").lower().removeprefix("www.")
            t, li = it.get("title") or "", it.get("linkedin_url") or ""
            if not d or "linkedin.com/in/" not in li or not ok.search(t) or (bad and bad.search(t)):
                continue
            if india and (india.search(d) or india.search(" ".join(str(it.get(k) or "") for k in ("city", "state", "country", "headline")))):
                continue
            if domain_is_known(d, names) or squash(it.get("organization_name") or "") in names:
                continue
            by.setdefault(d, {})[li.rstrip("/").lower()] = {k: it.get(k) for k in ("first_name", "last_name", "title", "organization_name", "linkedin_url", "headline", "city", "country")}
    (ctx.workdir / f"{tag}_domains.json").write_text(json.dumps({d: list(v.values()) for d, v in by.items()}, ensure_ascii=False), encoding="utf-8")
    return len(by)


@register
class DeepCrawl(Step):
    id = "deep_crawl"
    kind = "free"
    title = "Deep crawl of company sites (free, resumable)"
    params_model = CrawlParams

    def run(self, ctx: StepContext, p: CrawlParams) -> StepResult:
        _need_pipeline(ctx)
        return self._go(ctx, p)

    resume = run          # the JSONL is the checkpoint: finished domains are skipped on the next call

    def _go(self, ctx: StepContext, p: CrawlParams) -> StepResult:
        if p.source == "pools":
            n = build_pool_domains(ctx, p.tag)
            ctx.log(f"{n} unverified pool companies with a decision-owner")
        src = ctx.workdir / f"{p.tag}_domains.json"
        if not src.exists():
            raise FileNotFoundError(f"{src.name} not found in this cycle's folder: run a harvest step with tag '{p.tag}' first")
        meta = json.loads(src.read_text(encoding="utf-8"))
        out = ctx.workdir / f"{p.tag}_crawl.jsonl"
        done = set()
        if out.exists():
            for line in out.read_text(encoding="utf-8").splitlines():
                try:
                    done.add(json.loads(line)["domain"])
                except Exception:
                    pass
        todo = [d for d in meta if d not in done]
        if p.limit:
            todo = todo[: max(0, p.limit - len(done))]
        pat, keyp = patterns.build(ctx.cfg.evidence), re.compile(p.inner_page_keywords, re.I)
        ctx.log(f"{len(todo)} to crawl ({len(done)} already done)")
        hits = unreachable = 0
        batch = p.threads * 2
        with ThreadPoolExecutor(p.threads) as ex, open(out, "a", encoding="utf-8") as f:
            for i in range(0, len(todo), batch):
                ctx.check_cancel()                                  # between batches: a cancel never loses finished sites
                chunk = todo[i:i + batch]
                for r in ex.map(lambda d: crawl_one(d, pat, p.max_inner_pages, keyp), chunk):
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                    unreachable += r["score"] < 0
                    if r["score"] >= 1:
                        hits += 1
                        self._to_review(ctx, p.tag, r, meta.get(r["domain"]) or [{}])
                f.flush()
                known.add_domains(ctx.db, ctx.cfg.name, chunk, "crawled", p.tag)
                ctx.log(f"{min(i + batch, len(todo))}/{len(todo)} crawled, {hits} with evidence so far")
        return StepResult(counts={"crawled": len(todo), "with_evidence": hits, "unreachable": unreachable}, artifacts=[out.name],
                          message=f"{hits} companies with AI-plus-client evidence out of {len(todo)} crawled")

    @staticmethod
    def _to_review(ctx: StepContext, tag: str, r: dict, meta: list) -> None:
        m = meta[0] if meta else {}
        name = m.get("organization_name") or m.get("organization") or r["domain"]
        ctx.db.execute("INSERT OR IGNORE INTO companies (cycle_id, domain, name, country, source, evidence_json) VALUES (?,?,?,?,?,?)",
                       (ctx.cycle_id, r["domain"], name, m.get("loc") or m.get("country") or "", f"{tag}:{m.get('cat') or ''}",
                        json.dumps({"score": r["score"], "ev": r["ev"]}, ensure_ascii=False)))


def view_hits(workdir, tag: str, min_score: int = 1) -> list[dict]:
    """Crawl results with at least `min_score` hits, best first (the Review page reads the DB; this is for inspection and tests)."""
    res = []
    p = workdir / f"{tag}_crawl.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r["score"] >= min_score:
                res.append(r)
    return sorted(res, key=lambda r: -r["score"])
