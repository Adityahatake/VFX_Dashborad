"""Leads (from leads-finder / Sales Navigator pools) -> pending people rows for the Review page.
Filtering and ranking come from the pipeline config (decision titles, reject titles, role families, per-company caps, excluded countries);
nothing here approves anything."""
from __future__ import annotations

import json
import re
import sqlite3

from .config import PipelineConfig
from .dedupe import country_key, url_key
from .textnorm import clean_domain

MAX_CANDIDATES_PER_COMPANY = 2       # stage-2 rule (02_find_people.md): at most 2 candidates per company; the cap on the tab is enforced at append


def _title_rx(words: list[str]) -> re.Pattern | None:
    return re.compile("|".join(rf"(?<![a-z]){re.escape(w)}(?![a-z])" for w in words), re.I) if words else None


def title_rank(cfg: PipelineConfig, title: str) -> int:
    """Position of the first decision title found in the title (lower = better). 999 when none match."""
    t = (title or "").casefold()
    for i, d in enumerate(cfg.people.decision_titles):
        if re.search(rf"(?<![a-z]){re.escape(d.casefold())}(?![a-z])", t):
            return i
    return 999


def role_family(cfg: PipelineConfig, title: str) -> str:
    t = (title or "").casefold()
    for fam, terms in cfg.people.role_families.items():
        if any(re.search(rf"(?<![a-z]){re.escape(x.casefold())}(?![a-z])", t) for x in terms):
            return fam
    return "other"


def lead_problem(cfg: PipelineConfig, lead: dict) -> str:
    """Why a lead cannot be a candidate (empty string = fine)."""
    t, li = lead.get("title") or "", lead.get("linkedin_url") or ""
    if not any(m in li for m in cfg.output.dedupe.profile_url_markers):
        return "no personal profile URL"
    if title_rank(cfg, t) == 999:
        return "not a decision-owner title"
    bad = _title_rx(cfg.people.reject_titles + ["ex-", "former"])
    if bad and bad.search(t):
        return "rejected title"
    loc = " ".join(str(lead.get(k) or "") for k in ("city", "state", "country", "headline", "location"))
    if any(re.search(p, loc, re.I) for p in cfg.countries.excluded_patterns) or country_key(lead.get("country") or "") in {country_key(c) for c in cfg.countries.excluded}:
        return "excluded country"
    return ""


def choose(cfg: PipelineConfig, leads: list[dict], n: int = MAX_CANDIDATES_PER_COMPANY) -> list[dict]:
    """Best `n` leads of ONE company: ranked by title, each adding a different role family (SOP 02 s18)."""
    ok = sorted((ld for ld in leads if not lead_problem(cfg, ld)), key=lambda ld: title_rank(cfg, ld.get("title", "")))
    out, fams = [], set()
    for ld in ok:
        fam = role_family(cfg, ld.get("title", ""))
        if fam in fams and fam != "other":
            continue
        fams.add(fam)
        out.append(ld)
        if len(out) >= n:
            break
    return out


def people_from_leads(con: sqlite3.Connection, cfg: PipelineConfig, cycle_id: int, leads: list[dict]) -> dict:
    """Group leads by company domain, keep the best per company, add them as pending people. Returns counts and per-lead rejection reasons."""
    cols, d = cfg.output.columns, cfg.output.dedupe
    comp = {r["domain"]: r for r in con.execute("SELECT * FROM companies WHERE cycle_id=? AND decision='approved'", (cycle_id,))}
    have = set()
    for r in con.execute("SELECT fields_json FROM people WHERE cycle_id=?", (cycle_id,)):
        have.add(url_key(json.loads(r[0]).get(d.url_fields[0], "")))
    by: dict[str, list[dict]] = {}
    skipped: dict[str, int] = {}
    for ld in leads:
        dom = clean_domain(ld.get("organization_primary_domain") or "")
        why = "company not approved in Review" if dom not in comp else lead_problem(cfg, ld)
        if why:
            skipped[why] = skipped.get(why, 0) + 1
            continue
        by.setdefault(dom, []).append(ld)
    added = 0
    for dom, group in by.items():
        c = comp[dom]
        ev = json.loads(c["evidence_json"] or "{}").get("ev") or []
        ev_urls = list(dict.fromkeys(u for u, _ in ev))
        ev_text = " ".join(ev[0][1].split())[:280] if ev else ""
        for rank, ld in enumerate(choose(cfg, group)):
            url = ld["linkedin_url"]
            if url_key(url) in have:
                skipped["already queued"] = skipped.get("already queued", 0) + 1
                continue
            row = dict.fromkeys(cols, "")
            row.update(name=f"{ld.get('first_name') or ''} {ld.get('last_name') or ''}".strip(), company=c["name"] or ld.get("organization_name") or dom,
                       title=ld.get("title", ""), role=f"P{rank + 1}", country=(ld.get("country") or "").strip(), primary_classification="Production studio / agency",
                       ai_adoption_stage="Active Production", ai_evidence=ev_text, primary_commercial_problem="", why_this_person="",
                       qualification_decision="PASS-B", qa_decision="PASS", qa_confidence=cfg.people.database_title_confidence, outreach_readiness="Ready",
                       contact_or_reference=url, contact_or_reference_type="Personal LinkedIn")
            row[d.evidence_field] = "; ".join(ev_urls + [url])
            row = {k: v for k, v in row.items() if k in cols}
            flags = ["title from a lead database only: Medium confidence", "ai_evidence is the raw crawl sentence: confirm the named client and the tool, and shorten it"]
            con.execute("INSERT INTO people (cycle_id, domain, fields_json, confidence, flags_json) VALUES (?,?,?,?,?)",
                        (cycle_id, dom, json.dumps(row, ensure_ascii=False), cfg.people.database_title_confidence, json.dumps(flags)))
            have.add(url_key(url))
            added += 1
    return {"added": added, "companies": len(by), "skipped": skipped}
