"""Deterministic checks applied to every model answer. The model proposes; these rules decide what is allowed to be shown as a verdict.
  * a quote that is not in the text we sent is a hallucination -> unsure (reason code quote_not_found)
  * a 'yes' without a named client, AI-made-the-work, or a quote is downgraded to unsure
  * an excluded country overrides 'yes'; an unapproved country downgrades it
  * unparseable or invalid output -> unsure (reason code llm_parse_error): fields are never guessed
  * the model can never grant High confidence, and R2/R4 are never accepted
"""
from __future__ import annotations

import json
import re

from pydantic import ValidationError

from ..config import PipelineConfig
from ..dedupe import country_key
from .schemas import CompanyVerdict, PersonDraft


def norm_text(s: str) -> str:
    s = (s or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip().casefold()


def quote_in(quote: str, *texts: str) -> bool:
    q = norm_text(quote).strip(" .…\"'")
    return bool(q) and any(q in norm_text(t) for t in texts)


def unsure(code: str, reason: str) -> dict:
    return {"qualifies": "unsure", "named_client": "", "ai_used_to_make_work": False, "quote": "", "country": "", "company_type": "",
            "reject_reason_code": "", "confidence": 0.0, "reason": reason, "code": code}


def parse_company(parsed: dict | None, error: str | None) -> CompanyVerdict | dict:
    """CompanyVerdict, or an 'unsure' dict (with a `code`) when the output is missing or invalid. Never guesses a field."""
    if parsed is None:
        return unsure("llm_error" if error else "llm_parse_error", f"no usable answer ({error or 'empty'})")
    try:
        return CompanyVerdict.model_validate(parsed)
    except ValidationError as e:
        return unsure("llm_parse_error", "invalid answer: " + "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())[:300])


def finalize_company(v: CompanyVerdict | dict, texts: list[str], cfg: PipelineConfig) -> dict:
    if isinstance(v, dict):
        return v
    d = v.model_dump()
    d["code"] = ""
    if d["quote"] and not quote_in(d["quote"], *texts):
        return {**unsure("quote_not_found", "the quoted sentence does not appear in the text that was sent"), "claimed_quote": d["quote"][:200], "claimed_qualifies": d["qualifies"]}
    if d["qualifies"] == "yes":
        missing = [n for n, ok in (("named client", bool(d["named_client"].strip())), ("AI used to make the work", d["ai_used_to_make_work"]), ("a verbatim quote", bool(d["quote"].strip()))) if not ok]
        if missing:
            return {**d, "qualifies": "unsure", "code": "incomplete_yes", "reason": "answered yes without " + ", ".join(missing)}
        ck = country_key(d["country"])
        if d["country"].strip() and ck in {country_key(c) for c in cfg.countries.excluded}:
            return {**d, "qualifies": "no", "reject_reason_code": "excluded_country", "code": "excluded_country", "reason": f"country {d['country']} is excluded"}
        if d["country"].strip() and ck not in {country_key(c) for c in cfg.countries.approved}:
            return {**d, "qualifies": "unsure", "code": "country_not_approved", "reason": f"country {d['country']} is not on the approved list"}
    if d["qualifies"] != "no":
        d["reject_reason_code"] = ""
    return d


def parse_person(parsed: dict | None, error: str | None) -> PersonDraft | None:
    if parsed is None:
        return None
    try:
        return PersonDraft.model_validate(parsed)
    except ValidationError:
        return None


def finalize_person(p: PersonDraft, cfg: PipelineConfig) -> dict:
    d = p.model_dump()
    flags = list(d["flags"])
    if d["confidence"] == "High":                       # the model can propose, but only a human confirming the person on a non-database page may set High
        d["confidence"] = cfg.people.database_title_confidence
        flags.append("the LLM proposed High confidence; downgraded: confirm the person on the company site or in press to upgrade it yourself")
    if d["commercial_route"] in ("R2", "R4"):
        d["commercial_route"] = "UNSURE"
        flags.append("R2/R4 are never a default")
    d["flags"] = list(dict.fromkeys(flags))
    return d


def extract_json(text: str) -> dict | None:
    try:
        v = json.loads(text)
        return v if isinstance(v, dict) else None
    except (ValueError, TypeError):
        return None
