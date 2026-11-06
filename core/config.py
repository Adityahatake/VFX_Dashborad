"""Pydantic models for pipeline.yaml. A bad file raises ConfigError with a list of readable problems."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

Stage = Literal["companies", "people", "review", "write"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ICP(Strict):
    description: str = ""
    reject_company_types: list[str] = []
    reject_names: list[str] = []


class Countries(Strict):
    approved: list[str]          # ISO-like codes or names, matched case-insensitively
    excluded: list[str] = []     # applies to company, team AND person
    excluded_patterns: list[str] = []   # regexes for city names / domain suffixes (e.g. India)

    @model_validator(mode="after")
    def _no_overlap(self):
        both = {c.casefold() for c in self.approved} & {c.casefold() for c in self.excluded}
        if both:
            raise ValueError(f"countries both approved and excluded: {sorted(both)}")
        return self


class Evidence(Strict):
    strong_terms: list[str] = []
    client_cues: list[str] = []
    false_positive_patterns: list[str] = []
    reject_if: list[str] = []


class People(Strict):
    decision_titles: list[str]
    reject_titles: list[str] = []
    max_per_company: int = Field(3, ge=1, le=10)
    role_families: dict[str, list[str]] = {}
    database_title_confidence: Literal["High", "Medium"] = "Medium"


class StepRef(Strict):
    step: str
    stage: Stage
    params: dict[str, Any] = {}


class Tab(Strict):
    name: str
    range: str                    # e.g. "Linkedin!A1:Q6000"
    header: list[str]
    write: bool = False           # only tabs with write=true can receive appended rows


class Dedupe(Strict):
    name_field: str = "name"
    company_field: str = "company"
    url_fields: list[str] = ["contact_or_reference"]
    evidence_field: str = "evidence_source"
    country_field: str = "country"
    folded_name: bool = True
    profile_url_markers: list[str] = ["linkedin.com/in/"]   # the first url field must contain one of these (a personal profile, not a company page)
    batch_size: int = Field(8, ge=1, le=10)                  # rows per append; the tabs are re-read before every batch


class Colour(Strict):
    background: str = "white"
    text: str = "black"


class Output(Strict):
    sheet_id_env: str = "GOOGLE_SHEET_ID"   # name of the env var; sheet IDs never live in git
    tabs: list[Tab]
    columns: list[str]
    field_map: dict[str, str] = {}          # internal field -> column (identity if absent)
    dedupe: Dedupe = Dedupe()
    colour_own_rows: Colour = Colour()

    @property
    def write_tab(self) -> Tab:
        return next(t for t in self.tabs if t.write)

    @model_validator(mode="after")
    def _check(self):
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("duplicate column names in output.columns")
        writers = [t for t in self.tabs if t.write]
        if len(writers) != 1:
            raise ValueError(f"exactly one tab must have write: true (found {len(writers)})")
        if writers[0].header != self.columns:
            raise ValueError(f"write tab '{writers[0].name}' header must equal output.columns")
        d = self.dedupe
        for f in [d.name_field, d.company_field, d.evidence_field, d.country_field, *d.url_fields]:
            if f not in self.columns:
                raise ValueError(f"dedupe field '{f}' is not in output.columns")
        for k, v in self.field_map.items():
            if v not in self.columns:
                raise ValueError(f"field_map['{k}'] -> '{v}' is not in output.columns")
        return self


class StopRules(Strict):
    max_cost_per_row: float = 0.50
    min_pass_rate: float = 0.03
    min_usable_credit: float = 3.0
    low_yield_cycles: int = 2
    low_yield_rows: int = 5


class Budget(Strict):
    default_cycle_cap_usd: float = Field(3.0, gt=0)
    hard_max_cycle_cap_usd: float = Field(3.0, gt=0)
    min_key_balance_usd: float = Field(0.80, ge=0)
    stop_rules: StopRules = StopRules()

    @model_validator(mode="after")
    def _cap(self):
        if self.default_cycle_cap_usd > self.hard_max_cycle_cap_usd:
            raise ValueError("default_cycle_cap_usd cannot exceed hard_max_cycle_cap_usd")
        return self


class LLM(Strict):
    enabled: bool = False                # pipeline-level switch; the global Settings toggle and ANTHROPIC_API_KEY must ALSO be on
    provider: Literal["none", "anthropic", "groq"] = "none"      # "groq" is accepted in YAML but not implemented (Anthropic-only build)
    model: str = ""
    cycle_cap_usd: float = Field(1.0, ge=0)
    effort: Literal["low", "medium", "high"] = "low"             # classification does not need deep thinking
    max_page_chars: int = Field(12000, ge=1000, le=60000)        # trimmed evidence text per company call
    company_sop_files: list[str] = []                            # rubric for company verdicts (cached in the system prompt)
    person_sop_files: list[str] = []                             # rubric for person drafts


class ExhaustedSource(Strict):
    source: str
    note: str
    date: str = ""
    match: list[str] = []                # words that identify this source in a step id or its parameters (used to warn before a rerun)


class PipelineConfig(Strict):
    schema_version: int = 1
    name: str
    title: str
    icp: ICP = ICP()
    countries: Countries
    evidence: Evidence = Evidence()
    people: People
    steps: list[StepRef]
    output: Output
    budget: Budget = Budget()
    llm: LLM = LLM()
    sop_files: list[str] = []
    exhausted_sources: list[ExhaustedSource] = []

    @field_validator("name")
    @classmethod
    def _slug(cls, v: str) -> str:
        import re
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", v):
            raise ValueError("name must be a lowercase slug (letters, digits, underscore)")
        return v

    @model_validator(mode="after")
    def _steps(self):
        if not self.steps:
            raise ValueError("at least one step is required")
        if not any(s.stage == "write" for s in self.steps):
            raise ValueError("a 'write' stage step is required (the safe append)")
        return self


class ConfigError(Exception):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def _fmt(e: ValidationError) -> list[str]:
    return [f"{'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}" for err in e.errors()]


def parse_config(text: str) -> PipelineConfig:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ConfigError([f"YAML syntax error: {e}"])
    if not isinstance(data, dict):
        raise ConfigError(["top level of the YAML must be a mapping"])
    try:
        return PipelineConfig.model_validate(data)
    except ValidationError as e:
        raise ConfigError(_fmt(e))


def load_config(path: Path) -> PipelineConfig:
    return parse_config(Path(path).read_text(encoding="utf-8"))


def effective_cap(cfg: PipelineConfig, requested: float | None) -> float:
    """The spend cap for a cycle: requested value, never above hard_max."""
    cap = cfg.budget.default_cycle_cap_usd if requested is None else requested
    return min(cap, cfg.budget.hard_max_cycle_cap_usd)
