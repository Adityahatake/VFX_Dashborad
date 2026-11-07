"""Field mapping between the app's internal person fields and a pipeline's sheet columns (output.field_map: internal field -> column name).
People rows in the database always use the INTERNAL names below, so the steps (leads, pool match, LLM drafts, review) never depend on what a
sheet calls its columns. The mapping is applied only at the two boundaries: building a sheet row from a person, and reading a sheet row back.
A column that is not mapped keeps its own name as its internal name (extra columns the reviewer fills by hand)."""
from __future__ import annotations

from .config import PipelineConfig

INTERNAL_FIELDS = ["name", "company", "title", "role", "country", "primary_classification", "ai_adoption_stage", "ai_evidence", "primary_commercial_problem",
                   "why_this_person", "qualification_decision", "qa_decision", "qa_confidence", "outreach_readiness", "contact_or_reference",
                   "contact_or_reference_type", "evidence_source"]


def to_column(cfg: PipelineConfig, internal: str) -> str:
    return cfg.output.field_map.get(internal, internal)


def to_internal(cfg: PipelineConfig, column: str) -> str:
    inv = {v: k for k, v in cfg.output.field_map.items()}
    return inv.get(column, column)


def internal_columns(cfg: PipelineConfig) -> list[str]:
    """The internal names of the write tab's columns, in sheet order."""
    return [to_internal(cfg, c) for c in cfg.output.columns]


def row_from_fields(cfg: PipelineConfig, fields: dict) -> list[str]:
    """A person's fields (internal names) as a sheet row, in column order."""
    return [str(fields.get(i, "")) for i in internal_columns(cfg)]


def fields_from_row(cfg: PipelineConfig, header: list[str], row: list[str]) -> dict:
    """A sheet row as a fields dict keyed by internal names."""
    r = list(row) + [""] * (len(header) - len(row))
    return {to_internal(cfg, h): r[i] for i, h in enumerate(header)}


def evidence_key(cfg: PipelineConfig) -> str:
    return to_internal(cfg, cfg.output.dedupe.evidence_field)


def url_key_name(cfg: PipelineConfig) -> str:
    return to_internal(cfg, cfg.output.dedupe.url_fields[0])
