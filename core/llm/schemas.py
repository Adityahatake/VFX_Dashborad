"""Output schemas. The JSON schemas are written by hand in the plain subset (types, enums, required, additionalProperties false) so the
API's structured-output mode accepts them; pydantic then validates again, because a schema-valid answer can still be out of range."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..review import REJECT_REASONS

REJECT_CODES = [""] + list(REJECT_REASONS)
FAMILIES = ["ceo", "creative", "production", "tech", "other"]
ROUTES = ["R1", "R3", "R5", "UNSURE"]           # R2 and R4 are deliberately not offered: never a default (SOP 01 s13, s37)


class CompanyVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    qualifies: Literal["yes", "no", "unsure"]
    named_client: str = ""
    ai_used_to_make_work: bool = False
    quote: str = Field("", max_length=400)
    country: str = ""
    company_type: str = ""
    reject_reason_code: str = ""
    confidence: float = Field(0.0, ge=0, le=1)
    reason: str = Field("", max_length=500)


COMPANY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "qualifies": {"type": "string", "enum": ["yes", "no", "unsure"]},
        "named_client": {"type": "string"},
        "ai_used_to_make_work": {"type": "boolean"},
        "quote": {"type": "string"},
        "country": {"type": "string"},
        "company_type": {"type": "string"},
        "reject_reason_code": {"type": "string", "enum": REJECT_CODES},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["qualifies", "named_client", "ai_used_to_make_work", "quote", "country", "company_type", "reject_reason_code", "confidence", "reason"],
}


class PersonDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_family: Literal["ceo", "creative", "production", "tech", "other"]
    priority: Literal["P1", "P2", "P3"]
    why_this_person: str = Field("", max_length=600)
    commercial_route: Literal["R1", "R3", "R5", "UNSURE"] = "UNSURE"
    primary_commercial_problem: str = Field("", max_length=600)
    confidence: Literal["High", "Medium"] = "Medium"
    confidence_reason: str = Field("", max_length=400)
    flags: list[str] = []


PERSON_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "role_family": {"type": "string", "enum": FAMILIES},
        "priority": {"type": "string", "enum": ["P1", "P2", "P3"]},
        "why_this_person": {"type": "string"},
        "commercial_route": {"type": "string", "enum": ROUTES},
        "primary_commercial_problem": {"type": "string"},
        "confidence": {"type": "string", "enum": ["High", "Medium"]},
        "confidence_reason": {"type": "string"},
        "flags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["role_family", "priority", "why_this_person", "commercial_route", "primary_commercial_problem", "confidence", "confidence_reason", "flags"],
}
