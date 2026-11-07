"""Free people steps (ported from VFX evidence.py and pool_match.py): read Impressum / team / project pages, and find 2nd/3rd contacts among
already-paid leads for sheet companies that have fewer than the per-company cap."""
from __future__ import annotations

import collections
import glob
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from .. import fields as F, web
from ..textnorm import norm, ntoks
from .base import Step, StepContext, StepResult, register
from .harvest import _need_pipeline

AI_BROAD = re.compile(r"generative|gen[\s-]?ai\b|\bgenai\b|midjourney|\brunway\b|\bsora\b|\bveo\b|kling|seedance|nano banana|comfyui|stable diffusion|higgsfield|"
                      r"\bAI[- ](generated|film|spot|campaign|commercial|video|animation|production|powered|assisted|driven)|\bKI\b|\bIA\b|künstliche[nr]? Intelligenz|"
                      r"inteligencia artificial|intelligenza artificiale|intelligence artificielle|inteligência artificial|生成AI|생성형", re.I)
LEAD = re.compile(r"(gesch[äa]ftsf[üu]hr\w*|vertreten durch|founder|co-?founder|gr[üu]nder\w*|fondat\w+|fundador\w*|ceo|managing director|inhaber\w*|owner|"
                  r"creative director|executive producer|directeur|direttore|director general|socio|partner|代表取締役|대표)", re.I)
PAGE_KEYS = re.compile(r"ai|ki|ia|genai|work|works|projekt|project|referenz|reference|case|portfolio|showreel|arbeiten|trabajos|proyectos|lavori|about|ueber|uber|team|"
                       r"impressum|imprint|nosotros|quienes|chi-siamo|qui-sommes|equipe|company|studio|clients|kunden|事例|実績", re.I)
PRESS = re.compile(r"linkedin|lbbonline|shots|vimeo|youtube|instagram|adsoftheworld|campaign|muse|stash|adweek|adage|creativepool|press|news|variety|deadline|"
                   r"hollywood|theorg|facebook|x\.com|twitter|tiktok|medium|behance|apple|google|higgsfield|runway|wikipedia|engage|bizcommunity|horizont|wuv|kress|"
                   r"dwdl|quotenmeter|markt-kom|clios|crunchbase|rocketreach|zoominfo|imdb|screendaily|thedrum|mumbrella|bandt|adnews|stoppress|cartoonbrew|fxguide")


class EvidenceParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["extract", "grep"] = "extract"
    tag: str = Field("ev", pattern=r"^[a-z0-9_]{1,30}$")
    domains: list[str] = []          # extract: company domains
    urls: list[str] = []             # grep: pages (Impressum, team, project pages)
    pattern: str = r"vertreten durch|gesch[äa]ftsf[üu]hr|founder"     # grep: regex
    threads: int = Field(12, ge=1, le=32)


def extract_domain(dom: str, extra_ai: re.Pattern | None = None) -> str:
    out = [f"######## {dom}"]
    u, h = web.fetch("https://" + dom)
    if not h:
        u, h = web.fetch("http://" + dom)
    if not h:
        return "\n".join(out + ["  UNREACHABLE"])
    links = web.internal_links(u, h, lambda p: bool(PAGE_KEYS.search(p.strip("/").split("/")[-1])) if p.strip("/") else False, 10)
    ai_rx = re.compile(AI_BROAD.pattern + (("|" + extra_ai.pattern) if extra_ai else ""), re.I)
    seen: set = set()
    for pu, ph in [(u, h)] + [web.fetch(link) for link in links]:
        t = web.text(ph)
        if not t:
            continue
        ai = [t[max(0, m.start() - 130):m.end() + 170] for m in ai_rx.finditer(t)]
        ld = [t[max(0, m.start() - 70):m.end() + 70] for m in LEAD.finditer(t)]
        a2 = [s for s in ai if s[:60] not in seen][:4]
        l2 = [s for s in ld if s[:50] not in seen][:3]
        seen |= {s[:60] for s in a2} | {s[:50] for s in l2}
        if a2 or l2:
            out.append(f"  [{pu}] ai={len(ai)}")
            out += ["    AI: " + s for s in a2] + ["    LEAD: " + s for s in l2]
    return "\n".join(out)


@register
class Evidence(Step):
    id = "evidence"
    kind = "free"
    title = "Impressum / team / project page evidence (free)"
    params_model = EvidenceParams

    def run(self, ctx: StepContext, p: EvidenceParams) -> StepResult:
        if p.mode == "extract":
            if not p.domains:
                raise ValueError("extract mode needs 'domains'")
            with ThreadPoolExecutor(p.threads) as ex:
                res = []
                for i in range(0, len(p.domains), p.threads * 2):
                    ctx.check_cancel()
                    res += list(ex.map(extract_domain, p.domains[i:i + p.threads * 2]))
            name = f"evid_{p.tag}.txt"
            (ctx.workdir / name).write_text("\n".join(res), encoding="utf-8")
            unreachable = sum("UNREACHABLE" in r for r in res)
            ctx.log(f"{len(res)} domains -> {name} ({unreachable} unreachable)")
            return StepResult(counts={"domains": len(res), "unreachable": unreachable}, artifacts=[name], message=f"{len(res)} domains")
        if not p.urls:
            raise ValueError("grep mode needs 'urls'")
        rx = re.compile(p.pattern, re.I)
        lines, hits = [], 0
        for u in p.urls:
            ctx.check_cancel()
            fu, h = web.fetch(u)
            t = web.text(h)
            lines.append(f"===== {u} -> {fu} ({len(t)} chars)")
            for m in list(rx.finditer(t))[:6]:
                hits += 1
                lines.append("    " + t[max(0, m.start() - 160):m.end() + 200])
        name = f"grep_{p.tag}.txt"
        (ctx.workdir / name).write_text("\n".join(lines), encoding="utf-8")
        ctx.log(f"{len(p.urls)} pages, {hits} matches -> {name}")
        return StepResult(counts={"pages": len(p.urls), "matches": hits}, artifacts=[name], message=f"{hits} matches")


# ---------------------------------------------------------------- pool_match
class PoolMatchParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag: str = Field("pm", pattern=r"^[a-z0-9_]{1,30}$")
    pool_files: list[str] = []       # paths relative to data/<pipeline>/pools/ ; empty = every pool_*.json
    snapshot: str = "sheet_snapshot.json"     # {"tabs": {name: {"header": [...], "rows": [[...]]}}}, written by the Sheets client (phase 5)


def _family(title: str, families: dict[str, list[str]]) -> str:
    t = title.casefold()
    for fam, terms in families.items():
        if any(re.search(rf"(?<![a-z]){re.escape(x.casefold())}(?![a-z])", t) for x in terms):
            return fam
    return "other"


def _company_domain(evidence: str) -> str:
    for u in re.findall(r"https?://[^\s;,]+", evidence or ""):
        d = urlparse(u).netloc.lower().removeprefix("www.")
        if d and not PRESS.search(d):
            return d
    return ""


def _url_key(u: str) -> str:
    return (u or "").lower().rstrip("/").split("?")[0].replace("http://", "https://")


def find_snapshot(ctx: StepContext, name: str) -> Path:
    for base in (ctx.workdir, ctx.pipeline_dir):
        if base and (base / name).exists():
            return base / name
    raise FileNotFoundError(f"{name} not found: the Sheets client (phase 5) writes it; until then place a sheet snapshot in {ctx.pipeline_dir}")


@register
class PoolMatch(Step):
    id = "pool_match"
    kind = "free"
    title = "2nd/3rd contacts from already-paid pools (free)"
    params_model = PoolMatchParams

    def run(self, ctx: StepContext, p: PoolMatchParams) -> StepResult:
        _need_pipeline(ctx)
        cfg = ctx.cfg
        snap = json.loads(find_snapshot(ctx, p.snapshot).read_text(encoding="utf-8"))["tabs"]
        wt = cfg.output.write_tab
        tab = snap[wt.name]
        h = tab["header"]
        need = [F.to_column(cfg, k) for k in ("name", "company", "title", "role", "country")] + [cfg.output.dedupe.evidence_field, cfg.output.dedupe.url_fields[0]]
        missing = [c for c in need if c not in h]
        if missing:
            raise ValueError(f"the sheet header has no column(s) {missing}; pool_match needs them")
        ix = {c: h.index(c) for c in need}
        rows = [(r + [""] * len(h))[: len(h)] for r in tab["rows"] if r and str(r[0]).strip()]
        names = set()
        for t in snap.values():
            th, nf = t["header"], cfg.output.dedupe.name_field
            if nf in th:
                names |= {" ".join(ntoks(r[th.index(nf)])) for r in t["rows"] if len(r) > th.index(nf)}
        urls = {_url_key(r[ix[cfg.output.dedupe.url_fields[0]]]) for r in rows if r[ix[cfg.output.dedupe.url_fields[0]]]}
        by = collections.defaultdict(list)
        for r in rows:
            by[norm(r[ix[F.to_column(cfg, "company")]])].append(r)
        dom = {}
        for k, v in by.items():
            for r in v:
                d = _company_domain(r[ix[cfg.output.dedupe.evidence_field]])
                if d:
                    dom.setdefault(d, k)
        ok = re.compile("|".join(re.escape(t) for t in cfg.people.decision_titles), re.I)
        bad = re.compile("|".join([rf"\b{re.escape(t)}\b" for t in cfg.people.reject_titles] + [r"(?<![a-z])ex-"]), re.I)
        india = re.compile("|".join(cfg.countries.excluded_patterns), re.I) if cfg.countries.excluded_patterns else None
        pdir = ctx.pipeline_dir / "pools"
        files = [str(pdir / f) for f in p.pool_files] or glob.glob(str(pdir / "pool_*.json"))
        if not files:
            raise FileNotFoundError(f"no pool_*.json files in {pdir}")
        out: dict = {}
        cap = cfg.people.max_per_company
        for f in files:
            ctx.check_cancel()
            try:
                items = json.load(open(f, encoding="utf-8"))
            except Exception:
                ctx.log(f"skipped unreadable pool file {Path(f).name}")
                continue
            for it in items:
                d = (it.get("organization_primary_domain") or "").lower().removeprefix("www.")
                k = dom.get(d) or (norm(it.get("organization_name") or "") if norm(it.get("organization_name") or "") in by else None)
                if not k or len(by[k]) >= cap:
                    continue
                t = it.get("title") or ""
                li = _url_key(it.get("linkedin_url") or "")
                nm = " ".join(ntoks((it.get("first_name") or "") + " " + (it.get("last_name") or "")))
                if "linkedin.com/in/" not in li or li in urls or nm in names:
                    continue
                if not ok.search(t) or (bad and bad.search(t)):
                    continue
                if india and india.search(" ".join(str(it.get(x) or "") for x in ("city", "country", "headline"))):
                    continue
                fam = _family(t, cfg.people.role_families)
                have = {_family(r[ix[F.to_column(cfg, "title")]], cfg.people.role_families) for r in by[k]}
                if fam in have and fam != "other":
                    continue
                e = by[k][0]
                out[li] = {"sheet_company": e[ix[F.to_column(cfg, "company")]], "sheet_country": e[ix[F.to_column(cfg, "country")]], "sheet_domain": _company_domain(e[ix[cfg.output.dedupe.evidence_field]]),
                           "first": it.get("first_name"), "last": it.get("last_name"), "title": t, "family": fam, "linkedin_url": it.get("linkedin_url"),
                           "headline": (it.get("headline") or "")[:110], "lead_location": f"{it.get('city')}, {it.get('country')}", "lead_domain": d,
                           "existing": [(r[ix[F.to_column(cfg, "name")]], r[ix[F.to_column(cfg, "title")]], r[ix[F.to_column(cfg, "role")]]) for r in by[k]],
                           "existing_row": F.fields_from_row(cfg, h, by[k][0])}          # the company's first sheet row: company-level fields and evidence are reused
        cands = list(out.values())
        for c in cands:      # a namesake is the main risk (VFX cycle 16): flag when the sheet's company domain differs from the lead's
            c["domain_differs"] = bool(c["sheet_domain"] and c["lead_domain"] and c["sheet_domain"] != c["lead_domain"])
        name = f"{p.tag}_pool_match.json"
        (ctx.workdir / name).write_text(json.dumps(cands, ensure_ascii=False, indent=0), encoding="utf-8")
        flagged = sum(c["domain_differs"] for c in cands)
        ctx.log(f"{len(cands)} candidates ({flagged} flagged DOMAIN DIFFERS: likely namesakes, check by hand) -> {name}")
        if ctx.cycle_id:
            from .. import review
            n = review.people_from_pool_match(ctx.db, cfg, ctx.cycle_id, cands)
            ctx.log(f"{n} added to the Review queue as pending people (nothing is written to the sheet until you approve and confirm)")
        return StepResult(counts={"candidates": len(cands), "domain_differs": flagged}, artifacts=[name], message=f"{len(cands)} candidates")
