"""Free company discovery: RevenueBase category lists and association / directory member pages (ported from VFX rb_harvest.py, dir_harvest.py).
Both write <tag>_domains.json = {domain: [{organization_name, desc, loc, cat}]} into the cycle workdir; deep_crawl reads it."""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from .. import known, web
from ..textnorm import clean_domain, domain_is_known, squash
from .base import Step, StepContext, StepResult, register

RB_BASE = "https://revenuebase.ai/companies/"
DEFAULT_CATEGORIES = ("video-production-companies animation-studios vfx-studios visual-effects-companies post-production-companies "
                      "post-production-studios motion-graphics-studios 3d-animation-studios branded-content-production-companies "
                      "music-video-production-companies product-video-production-companies animation-companies motion-design-companies "
                      "film-studios animated-explainer-video-companies documentary-production-companies").split()
# pipeline country names -> RevenueBase URL slugs
COUNTRY_SLUG = {"us": "united-states", "usa": "united-states", "united states": "united-states", "canada": "canada", "uk": "united-kingdom",
                "united kingdom": "united-kingdom", "ireland": "ireland", "australia": "australia", "new zealand": "new-zealand", "france": "france",
                "germany": "germany", "netherlands": "netherlands", "belgium": "belgium", "switzerland": "switzerland", "austria": "austria",
                "italy": "italy", "spain": "spain", "portugal": "portugal", "sweden": "sweden", "norway": "norway", "denmark": "denmark",
                "finland": "finland", "uae": "united-arab-emirates", "united arab emirates": "united-arab-emirates", "singapore": "singapore",
                "japan": "japan", "south korea": "south-korea", "korea": "south-korea", "israel": "israel", "hong kong": "hong-kong",
                "poland": "poland", "czech republic": "czechia", "czechia": "czechia", "south africa": "south-africa", "malaysia": "malaysia",
                "argentina": "argentina", "brazil": "brazil", "mexico": "mexico"}
CITIES = {"united-states": "new-york los-angeles chicago houston phoenix philadelphia san-antonio san-diego dallas austin san-francisco seattle denver boston "
                           "nashville portland las-vegas atlanta miami minneapolis detroit charlotte salt-lake-city brooklyn santa-monica burbank",
          "canada": "toronto vancouver montreal calgary ottawa", "united-kingdom": "london manchester bristol birmingham leeds glasgow edinburgh brighton liverpool",
          "ireland": "dublin cork", "australia": "sydney melbourne brisbane perth adelaide", "new-zealand": "auckland wellington",
          "germany": "berlin hamburg munich cologne frankfurt stuttgart dusseldorf leipzig", "austria": "vienna graz salzburg linz",
          "switzerland": "zurich geneva basel bern lausanne", "france": "paris lyon marseille toulouse bordeaux lille nantes",
          "netherlands": "amsterdam rotterdam utrecht eindhoven the-hague", "belgium": "brussels antwerp ghent", "spain": "madrid barcelona valencia seville malaga bilbao",
          "portugal": "lisbon porto", "italy": "milan rome turin bologna florence", "sweden": "stockholm gothenburg malmo", "norway": "oslo bergen",
          "denmark": "copenhagen aarhus", "finland": "helsinki tampere", "poland": "warsaw krakow wroclaw", "czechia": "prague",
          "united-arab-emirates": "dubai abu-dhabi", "israel": "tel-aviv", "south-africa": "cape-town johannesburg", "brazil": "sao-paulo rio-de-janeiro",
          "mexico": "mexico-city guadalajara", "argentina": "buenos-aires", "singapore": "singapore", "japan": "tokyo osaka", "south-korea": "seoul", "hong-kong": "hong-kong"}
ORG = re.compile(r'"@type": "Organization", "name": "(.*?)", "url": "(.*?)", "description": "(.*?)"')
NOISE = re.compile(r"linkedin|facebook|instagram|twitter|x\.com|youtube|vimeo|tiktok|pinterest|google|apple|microsoft|wordpress|wix|squarespace|gstatic|cloudflare|"
                   r"gravatar|w3\.org|schema\.org|adobe|amazonaws|gumlet|shgstatic|jsdelivr|unpkg|bootstrap|fonts|cookie|hubspot|mailchimp|typeform|"
                   r"wikipedia|imdb|spotify|soundcloud|behance|dribbble|medium|substack|issuu|calendly|zoom\.us|eventbrite|paypal|stripe|"
                   r"lbbonline|shots\.net|campaign|adforum|adweek|adage|variety|deadline|screendaily|clutch|designrush|sortlist|productionparadise|lebook")


def _need_pipeline(ctx: StepContext) -> None:
    if ctx.cfg is None or ctx.db is None:
        raise RuntimeError("this step needs a pipeline: start it from Run Cycle (or pass a pipeline)")


def _excluded(domain: str, ctx: StepContext) -> bool:
    return any(re.search(p, domain, re.I) for p in ctx.cfg.countries.excluded_patterns)


def _write_domains(ctx: StepContext, tag: str, new: dict) -> str:
    name = f"{tag}_domains.json"
    (ctx.workdir / name).write_text(json.dumps(new, ensure_ascii=False), encoding="utf-8")
    return name


class RBParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag: str = Field("rb", pattern=r"^[a-z0-9_]{1,30}$")
    categories: list[str] = []                       # empty = the productive VFX categories
    skip_prefixes: list[str] = ["generative-ai-", "ai-"]
    cities: bool = False                             # also try ~150 unlisted big-city pages per category (finds few new companies)
    limit_pages: int | None = Field(None, ge=1)      # for pilots and demos
    threads: int = Field(10, ge=1, le=32)


@register
class HarvestRevenueBase(Step):
    id = "harvest_revenuebase"
    kind = "free"
    title = "RevenueBase category lists (free)"
    params_model = RBParams

    def run(self, ctx: StepContext, p: RBParams) -> StepResult:
        _need_pipeline(ctx)
        cats = [c for c in (p.categories or DEFAULT_CATEGORIES) if not any(c.startswith(s) for s in p.skip_prefixes)]
        slugs = {COUNTRY_SLUG[c.casefold()] for c in ctx.cfg.countries.approved if c.casefold() in COUNTRY_SLUG}
        allowed = re.compile(r"^(" + "|".join(re.escape(s) for s in sorted(slugs)) + r")(/|$)")
        ctx.log(f"{len(cats)} categories, {len(slugs)} approved countries")

        def locations(cat):
            t = web.fetch(f"{RB_BASE}browse/{cat}")[1]
            return sorted(set(re.findall(r"/companies/" + re.escape(cat) + r"/([a-z0-9-]+(?:/[a-z0-9-]+)?)", t)))

        def page(cl):
            cat, loc = cl
            t = web.fetch(f"{RB_BASE}{cat}/{loc}")[1]
            return [(clean_domain(m.group(2)), m.group(1), m.group(3), loc, cat) for m in ORG.finditer(t)]

        with ThreadPoolExecutor(p.threads) as ex:
            pages = {(c, loc) for c, locs in zip(cats, ex.map(locations, cats)) for loc in locs if allowed.match(loc)}
            if p.cities:
                pages |= {(c, f"{k}/{city}") for c in cats for k, v in CITIES.items() if k in slugs for city in v.split()}
            pages = sorted(pages)
            if p.limit_pages:
                pages = pages[: p.limit_pages]
            ctx.log(f"{len(pages)} location pages to read")
            cos: dict = {}
            for i in range(0, len(pages), p.threads * 4):
                ctx.check_cancel()
                for res in ex.map(page, pages[i:i + p.threads * 4]):
                    for d, n, desc, loc, cat in res:
                        cos.setdefault(d, {"organization_name": n, "desc": desc, "loc": loc, "cat": cat})
        names, seen = known.known_names(ctx.db, ctx.cfg.name), known.seen_domains(ctx.db, ctx.cfg.name)
        new = {d: [v] for d, v in cos.items() if d and d not in seen and not _excluded(d, ctx) and not domain_is_known(d, names)
               and squash(v["organization_name"]) not in names}
        out = _write_domains(ctx, p.tag, new)
        ctx.log(f"{len(cos)} companies on {len(pages)} pages, {len(new)} new (not known, not excluded)")
        return StepResult(counts={"pages": len(pages), "companies": len(cos), "new": len(new)}, artifacts=[out], message=f"{len(new)} new domains")


class DirParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag: str = Field("dir", pattern=r"^[a-z0-9_]{1,30}$")
    urls: list[str] = Field(default_factory=list)
    min_domains_ok: int = Field(30, ge=0)            # fewer outbound domains than this and the page is reported as blocked / JavaScript-rendered


def page_domains(page_url: str, content: str) -> set[str]:
    host = urlparse(page_url).netloc.lower().removeprefix("www.")
    found = {urlparse(link).netloc for link in re.findall(r"(?:href=[\"']|\]\()(https?://[^\"')\s]+)", content)}
    found |= set(re.findall(r"(?<![\w./@-])www\.([a-z0-9-]+(?:\.[a-z0-9-]+)+)", content, re.I))
    out = set()
    for d in found:
        d = clean_domain(d)
        if d and "." in d and host not in d and d not in host and not NOISE.search(d) and not d.endswith(".in"):
            out.add(d)
    return out


@register
class HarvestDirectory(Step):
    id = "harvest_directory"
    kind = "free"
    title = "Association / directory member pages (free)"
    params_model = DirParams

    def run(self, ctx: StepContext, p: DirParams) -> StepResult:
        _need_pipeline(ctx)
        urls = [u for u in p.urls if u.strip()]
        if not urls:
            raise ValueError("give at least one member-list URL in 'urls'")
        bad = [u for u in urls if not web.is_public_url(u)]
        if bad:
            raise ValueError(f"not public http(s) URLs: {bad[:3]}")
        with ThreadPoolExecutor(8) as ex:
            pages = dict(zip(urls, (h for _, h in ex.map(web.fetch, urls))))
        found: dict = {}
        blocked = []
        for u, html in pages.items():
            ctx.check_cancel()
            ds = page_domains(u, html)
            ctx.log(f"{len(ds):4} domains  {u}")
            if len(html) < 2000 or len(ds) < p.min_domains_ok:
                blocked.append(u)
            for d in ds:
                found.setdefault(d, [{"organization_name": d, "loc": "", "cat": urlparse(u).netloc}])
        if blocked:
            ctx.log(f"{len(blocked)} page(s) look blocked or JavaScript-rendered (the Tavily extract fallback is not available in this build): " + ", ".join(blocked))
        names, seen = known.known_names(ctx.db, ctx.cfg.name), known.seen_domains(ctx.db, ctx.cfg.name)
        new = {d: v for d, v in found.items() if d not in seen and not _excluded(d, ctx) and not domain_is_known(d, names)}
        out = _write_domains(ctx, p.tag, new)
        ctx.log(f"{len(found)} domains, {len(new)} new")
        return StepResult(counts={"pages": len(urls), "blocked_pages": len(blocked), "domains": len(found), "new": len(new)}, artifacts=[out], message=f"{len(new)} new domains")
