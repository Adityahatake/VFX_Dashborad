"""Review queue logic: company and people decisions, people rows from pool_match, review-CSV building, per-cycle report.
Nothing here writes to a sheet; the append step does, and only after the Review page's typed confirmation."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import fields as F
from .config import PipelineConfig
from .dedupe import url_key
from .textnorm import ntoks

REJECT_REASONS = {
    "service_line_only": "AI is only a service line / homepage claim",
    "self_initiated": "self-initiated or spec work",
    "ai_vendor_client": "film about an AI product (AI vendor is the client)",
    "moodboard_only": "AI used only for moodboard / exploration",
    "training": "training exercise",
    "no_named_client": "no named client",
    "excluded_country": "excluded country (e.g. India HQ)",
    "country_not_approved": "country not approved",
    "agency_marketing": "marketing / SEO / PR / web / branding agency",
    "agency_network": "agency network or brand group",
    "broadcaster": "broadcaster",
    "tool_vendor": "AI tool or SaaS vendor",
    "false_positive": "false keyword hit (Runway, Kling, ...)",
    "one_piece_only": "one experimental piece only",
    "other": "other (see note)",
}
PERSON_REASONS = {
    "namesake": "namesake / different company",
    "not_decision_owner": "not a decision-owner",
    "left_company": "has left the company",
    "junior_or_other": "junior / sales / HR / finance / engineering / coordinator",
    "no_company_tie": "LinkedIn headline does not tie them to the company",
    "company_at_cap": "company already at the per-company cap",
    "duplicate": "duplicate",
    "excluded_country": "excluded country",
    "other": "other (see note)",
}


# ---------------------------------------------------------------- companies
def decide_company(con: sqlite3.Connection, company_id: int, decision: str, reason: str | None = None) -> None:
    if decision not in ("approved", "rejected", "look", "pending"):
        raise ValueError(f"unknown decision '{decision}'")
    if decision == "rejected" and reason not in REJECT_REASONS:
        raise ValueError("a rejection needs a reason code")
    con.execute("UPDATE companies SET decision=?, reason_code=?, decided_at=CURRENT_TIMESTAMP WHERE id=?",
                (decision, reason if decision == "rejected" else None, company_id))
    if decision == "rejected":                       # rejected companies are never proposed again
        r = con.execute("SELECT c.domain, y.pipeline FROM companies c JOIN cycles y ON y.id=c.cycle_id WHERE c.id=?", (company_id,)).fetchone()
        if r:
            con.execute("INSERT OR IGNORE INTO known_domains (domain, pipeline, status, source) VALUES (?,?, 'rejected', 'review')", (r[0], r[1]))


def company_evidence(row: sqlite3.Row) -> dict:
    try:
        return json.loads(row["evidence_json"] or "{}")
    except ValueError:
        return {}


# ---------------------------------------------------------------- people
def _blank(cols: list[str]) -> dict:
    return dict.fromkeys(cols, "")


def people_from_pool_match(con: sqlite3.Connection, cfg: PipelineConfig, cycle_id: int, candidates: list[dict]) -> int:
    """Turn pool_match candidates into pending people rows. The company-level fields are copied from the person's existing row
    (VFX: 'reuse the existing row's company fields and evidence'); the person-specific `why_this_person` is a plain factual draft that is
    flagged for editing. Confidence is Medium (title from a lead database). Returns how many were added."""
    cols = F.internal_columns(cfg)
    added = 0
    for c in candidates:
        ex = c.get("existing_row") or {}
        url = c.get("linkedin_url") or ""
        have = {url_key(json.loads(r[0]).get(F.url_key_name(cfg), "")) for r in
                con.execute("SELECT fields_json FROM people WHERE cycle_id=?", (cycle_id,))}
        if url_key(url) in have:
            continue
        n_existing = len(c.get("existing") or [])
        row = _blank(cols)
        row.update({k: ex.get(k, "") for k in ("primary_classification", "ai_adoption_stage", "ai_evidence", "primary_commercial_problem",
                                                "qualification_decision", "qa_decision", "outreach_readiness", "contact_or_reference_type") if k in cols})
        company_urls = [u for u in (ex.get(F.evidence_key(cfg), "") or "").split(";") if u.strip()]
        row.update(name=f"{c.get('first') or ''} {c.get('last') or ''}".strip(), company=c["sheet_company"], title=c.get("title", ""),
                   role=f"P{min(3, n_existing + 1)}", country=c.get("sheet_country", ""), qa_confidence=cfg.people.database_title_confidence,
                   contact_or_reference=url, why_this_person=f"{c.get('title', '')} at {c['sheet_company']} ({c.get('family', 'role')} role); EDIT: say what this person owns.")
        row[F.evidence_key(cfg)] = "; ".join([u.strip() for u in company_urls] + [url])
        row = {k: v for k, v in row.items() if k in cols}
        flags = ["title from a lead database only: Medium confidence"]      # the draft warning is computed live by draft_problems() so it never goes stale
        if c.get("domain_differs"):
            flags.insert(0, "DOMAIN DIFFERS: likely namesake, check by hand")
        con.execute("INSERT INTO people (cycle_id, domain, fields_json, confidence, flags_json) VALUES (?,?,?,?,?)",
                    (cycle_id, c.get("lead_domain") or "", json.dumps(row, ensure_ascii=False), cfg.people.database_title_confidence, json.dumps(flags)))
        added += 1
    return added


def update_person_fields(con: sqlite3.Connection, person_id: int, fields: dict) -> None:
    old = json.loads(con.execute("SELECT fields_json FROM people WHERE id=?", (person_id,)).fetchone()[0] or "{}")
    merged = {**{k: v for k, v in old.items() if k.startswith("_")}, **fields}            # hidden review context (_headline, _location) survives edits
    con.execute("UPDATE people SET fields_json=?, decided_at=NULL, decision='pending' WHERE id=?", (json.dumps(merged, ensure_ascii=False), person_id))


def apply_person_suggestion(con: sqlite3.Connection, person_id: int) -> dict:
    """Copy the LLM's person draft into the row's fields. This is a REVIEWER action (a button); it resets the decision to pending, so the row still
    needs an explicit Approve, and it adds a flag so nobody mistakes model text for a human-written note."""
    r = con.execute("SELECT fields_json, llm_json, flags_json FROM people WHERE id=?", (person_id,)).fetchone()
    if not r or not r["llm_json"]:
        raise ValueError("no LLM suggestion for this person")
    d, f = json.loads(r["llm_json"]), json.loads(r["fields_json"])
    f["role"] = d["priority"]
    f["why_this_person"] = d["why_this_person"]
    route = "" if d["commercial_route"] == "UNSURE" else f"{d['commercial_route']}: "
    f["primary_commercial_problem"] = route + d["primary_commercial_problem"]
    update_person_fields(con, person_id, f)
    flags = [x for x in json.loads(r["flags_json"] or "[]") if "came from the LLM" not in x] + ["why_this_person and the commercial hypothesis came from the LLM suggestion: read and edit them"]
    con.execute("UPDATE people SET flags_json=? WHERE id=?", (json.dumps(flags), person_id))
    return f


def decide_person(con: sqlite3.Connection, person_id: int, decision: str, reason: str | None = None) -> None:
    if decision not in ("approved", "rejected", "pending"):
        raise ValueError(f"unknown decision '{decision}'")
    if decision == "rejected" and reason not in PERSON_REASONS:
        raise ValueError("a rejection needs a reason code")
    con.execute("UPDATE people SET decision=?, reason_code=?, decided_at=CURRENT_TIMESTAMP WHERE id=?", (decision, reason if decision == "rejected" else None, person_id))


def approved_rows(con: sqlite3.Connection, cfg: PipelineConfig, cycle_id: int) -> list[list[str]]:
    out = []
    for r in con.execute("SELECT fields_json FROM people WHERE cycle_id=? AND decision='approved' ORDER BY id", (cycle_id,)):
        out.append(F.row_from_fields(cfg, json.loads(r[0])))        # internal names -> the sheet's column order
    return out


def draft_problems(cfg: PipelineConfig, fields: dict) -> list[str]:
    """Things the reviewer must still fix before a row is approvable (never auto-fixed)."""
    p = []
    if "EDIT:" in str(fields.get("why_this_person", "")) or not str(fields.get("why_this_person", "")).strip():
        p.append("why_this_person is still the draft: write a sentence specific to this person")
    if not str(fields.get(F.evidence_key(cfg), "")).strip():
        p.append("evidence_source is empty")
    if "primary_commercial_problem" in F.internal_columns(cfg) and not str(fields.get("primary_commercial_problem", "")).strip():
        p.append("primary_commercial_problem is empty: write a one-sentence hypothesis from the evidence (never R2 or R4 by default)")
    if "ai_evidence" in F.internal_columns(cfg) and not str(fields.get("ai_evidence", "")).strip():
        p.append("ai_evidence is empty: name the client or project and the tool")
    return p


def record_append(con: sqlite3.Connection, cfg: PipelineConfig, cycle_id: int, first_row: int, rows: list[list[str]]) -> None:
    """Our own append log: the source of truth for 'rows we added' (baseline + this log = progress)."""
    cols, d = cfg.output.columns, cfg.output.dedupe
    ni, ci, ui = cols.index(d.name_field), cols.index(d.company_field), cols.index(d.url_fields[0])
    con.executemany("INSERT INTO appended_rows (cycle_id, tab, row_number, name, company, url) VALUES (?,?,?,?,?,?)",
                    [(cycle_id, cfg.output.write_tab.name, first_row + k, r[ni], r[ci], r[ui]) for k, r in enumerate(rows)])


def cycle_report_markdown(con: sqlite3.Connection, cfg: PipelineConfig, cycle_id: int) -> str:
    """The per-cycle report (CLAUDE.md step 7): rows by company with evidence, High/Medium counts, borderline rows, rejections, spend per source."""
    from . import spend
    cyc = con.execute("SELECT * FROM cycles WHERE id=?", (cycle_id,)).fetchone()
    cols = cfg.output.columns
    ppl = [(r["decision"], r["reason_code"], json.loads(r["fields_json"])) for r in con.execute("SELECT * FROM people WHERE cycle_id=?", (cycle_id,))]
    ok = [f for d, _, f in ppl if d == "approved"]
    by_co: dict[str, list] = {}
    for f in ok:
        by_co.setdefault(f.get("company", ""), []).append(f)
    high = sum(1 for f in ok if f.get("qa_confidence") == "High")
    L = [f"# Cycle #{cycle_id} report: {cfg.title}", "", f"- Goal: {cyc['goal_rows']} rows, spend cap ${cyc['cap_usd']:.2f}",
         f"- Rows appended: {spend.rows_appended(con, cycle_id)}; approved in review: {len(ok)} (High {high}, Medium {len(ok) - high})",
         f"- Spend (Apify/Tavily): ${spend.cycle_spend(con, cycle_id):.3f}; cost per final row: " + (f"${c:.2f}" if (c := spend.cost_per_row(con, cycle_id)) is not None else "n/a"), "",
         "## Rows by company"]
    for co, fs in sorted(by_co.items()):
        L.append(f"### {co}")
        for f in fs:
            L.append(f"- **{f.get('name')}**, {f.get('title')} ({f.get('role')}, {f.get('qa_confidence')}): {f.get('why_this_person', '')}")
            L.append(f"  - evidence: {f.get(F.evidence_key(cfg), '')}")
    border = [f for f in ok if f.get("qa_confidence") != "High"]
    L += ["", "## Borderline (Medium confidence)"] + ([f"- {f.get('name')} at {f.get('company')}: title from a lead database only" for f in border] or ["- none"])
    rej_c = con.execute("SELECT reason_code, COUNT(*) FROM companies WHERE cycle_id=? AND decision='rejected' GROUP BY reason_code", (cycle_id,)).fetchall()
    rej_p = [(rc, 1) for d, rc, _ in ppl if d == "rejected"]
    L += ["", "## Rejections"] + [f"- company: {REJECT_REASONS.get(r[0], r[0])}: {r[1]}" for r in rej_c] + [f"- person: {PERSON_REASONS.get(r[0], r[0])}" for r in rej_p]
    if not rej_c and not rej_p:
        L.append("- none")
    L += ["", "## Spend by source"] + [f"- {s['source']} ({s['kind']}): ${(s['usd'] or 0):.3f}, {s['results'] or 0} results" for s in spend.by_source(con, cycle_id)]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- LLM suggestions: plain markdown for the Review page
def llm_company_note(v: dict) -> str:
    """The LLM's company verdict as markdown, always labelled as a suggestion. Never reorders or pre-selects anything."""
    bits = [f"**{v.get('qualifies', '?')}**", f"confidence {float(v.get('confidence') or 0):.0%}"]
    if v.get("named_client"):
        bits.append(f"client: {v['named_client']}")
    if v.get("country"):
        bits.append(f"country: {v['country']}")
    parts = ["LLM suggestion (not a decision): " + " | ".join(bits)]
    if v.get("reason"):
        parts.append(v["reason"])
    if v.get("quote"):
        parts.append("> " + v["quote"])
    if v.get("code"):
        parts.append(f"_automatic check: {v['code']}_")
    if v.get("error"):
        parts.append(f"_error: {v['error']}_")
    return "\n\n".join(parts)


def llm_person_note(d: dict) -> str:
    parts = [f"LLM suggestion (not a decision): {d['priority']} | {d['role_family']} | route {d['commercial_route']}",
             f"**why:** {d['why_this_person']}", f"**hypothesis:** {d['primary_commercial_problem']}", f"_confidence {d['confidence']}: {d['confidence_reason']}_"]
    parts += [f"- {x}" for x in d.get("flags", [])]
    return "\n\n".join(parts)
