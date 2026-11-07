"""Pipeline wizard logic (no UI): a valid starting template, live validation, safe writing, cloning and archiving.
The wizard edits a plain config dict (the same shape as pipeline.yaml); the YAML preview and the saved file come from that dict, and the saved
file is always re-validated. Nothing here deletes anything: 'archive' moves a pipeline folder to pipelines/_archived/, and edits keep a backup."""
from __future__ import annotations

import copy
import datetime
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import paths
from .config import ConfigError, PipelineConfig, parse_config

SLUG = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
SOP_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}\.md$")
MAX_SOP_BYTES = 1_000_000

GENERIC_COLUMNS = ["name", "company", "title", "role", "country", "ai_evidence", "why_this_person", "qa_confidence", "contact_or_reference", "evidence_source"]
COMMON_COUNTRIES = ["US", "Canada", "UK", "Ireland", "Australia", "New Zealand", "France", "Germany", "Netherlands", "Belgium", "Switzerland", "Austria", "Italy", "Spain",
                    "Portugal", "Sweden", "Norway", "Denmark", "Finland", "UAE", "Singapore", "Japan", "South Korea", "Israel", "Hong Kong", "Poland", "Czech Republic",
                    "South Africa", "Malaysia", "Argentina", "Brazil", "Mexico", "India"]


def template_dict(name: str = "my_pipeline", title: str = "My pipeline") -> dict:
    """A small VALID config to start from. Every list is something the user is expected to replace."""
    return {
        "schema_version": 1, "name": name, "title": title,
        "icp": {"description": "Describe the ideal company in one or two sentences.", "reject_company_types": ["marketing / SEO / PR / web agency", "tool vendor"], "reject_names": []},
        "countries": {"approved": ["US", "UK", "Germany"], "excluded": [], "excluded_patterns": []},
        "evidence": {"strong_terms": ["generative AI"], "client_cues": ["client", "campaign", "for {Brand}"], "false_positive_patterns": [], "reject_if": ["service line only"]},
        "people": {"decision_titles": ["Founder", "CEO", "Managing Director", "Creative Director"], "reject_titles": ["intern", "assistant", "junior", "sales", "HR"],
                   "max_per_company": 3, "role_families": {"ceo": ["founder", "ceo", "managing director"], "creative": ["creative director"]}, "database_title_confidence": "Medium"},
        "steps": [
            {"step": "harvest_directory", "stage": "companies", "params": {"urls": []}},
            {"step": "deep_crawl", "stage": "companies", "params": {"threads": 40, "max_inner_pages": 6}},
            {"step": "verify_companies", "stage": "review", "params": {}},
            {"step": "leads_finder", "stage": "people", "params": {"max_result": 50, "price_per_result": 0.003}},
            {"step": "verify_people", "stage": "review", "params": {}},
            {"step": "build_rows", "stage": "review", "params": {}},
            {"step": "append_sheet", "stage": "write", "params": {}},
        ],
        "output": {
            "sheet_id_env": "GOOGLE_SHEET_ID",
            "tabs": [{"name": "Leads", "range": "Leads!A1:J6000", "write": True, "header": list(GENERIC_COLUMNS)}],
            "columns": list(GENERIC_COLUMNS), "field_map": {},
            "dedupe": {"name_field": "name", "company_field": "company", "url_fields": ["contact_or_reference"], "evidence_field": "evidence_source", "country_field": "country",
                       "folded_name": True, "profile_url_markers": ["linkedin.com/in/"], "batch_size": 8},
            "colour_own_rows": {"background": "white", "text": "black"},
        },
        "budget": {"default_cycle_cap_usd": 3.0, "hard_max_cycle_cap_usd": 3.0, "min_key_balance_usd": 0.8,
                   "stop_rules": {"max_cost_per_row": 0.5, "min_pass_rate": 0.03, "min_usable_credit": 3.0, "low_yield_cycles": 2, "low_yield_rows": 5}},
        "llm": {"enabled": False, "provider": "none", "model": "", "cycle_cap_usd": 1.0, "effort": "low", "max_page_chars": 12000, "company_sop_files": [], "person_sop_files": []},
        "sop_files": [], "exhausted_sources": [],
    }


def from_config(cfg: PipelineConfig) -> dict:
    """The config as an editable dict (same shape as the YAML)."""
    return cfg.model_dump(mode="json")


def clone_dict(cfg: PipelineConfig, new_name: str, new_title: str | None = None) -> dict:
    d = from_config(cfg)
    d["name"], d["title"] = new_name, new_title or f"{cfg.title} (copy)"
    d["exhausted_sources"] = []              # a new pipeline has its own history: do not inherit "do not rerun" notes
    return d


def to_yaml(d: dict) -> str:
    return yaml.safe_dump(d, sort_keys=False, allow_unicode=True, width=110, default_flow_style=None)


def lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def unlines(items: list[str]) -> str:
    return "\n".join(items or [])


def parse_families(text: str) -> dict[str, list[str]]:
    """'ceo: founder, owner' per line -> {'ceo': ['founder', 'owner']}."""
    out = {}
    for ln in lines(text):
        if ":" in ln:
            k, v = ln.split(":", 1)
            if k.strip():
                out[k.strip()] = [x.strip() for x in v.split(",") if x.strip()]
    return out


def format_families(d: dict[str, list[str]]) -> str:
    return "\n".join(f"{k}: {', '.join(v)}" for k, v in (d or {}).items())


@dataclass
class Validation:
    config: PipelineConfig | None
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.config is not None and not self.problems


def validate_text(text: str, sop_files: dict[str, str] | None = None, pipeline_dir: Path | None = None) -> Validation:
    """Parse + semantic checks. Unknown steps, steps of another pipeline and bad step parameters are PROBLEMS here (the Pipelines page only warns for steps
    that are 'not built yet'; a new pipeline should not reference them)."""
    from .registry import check_steps
    from .steps import all_steps
    try:
        cfg = parse_config(text)
    except ConfigError as e:
        return Validation(None, list(e.problems))
    v = Validation(cfg)
    step_problems, missing = check_steps(cfg)
    v.problems += step_problems
    known = sorted(all_steps())
    v.problems += [f"step '{m}' does not exist. Available: {', '.join(known)}" for m in missing]
    if cfg.output.write_tab.name and not any(s.stage == "write" for s in cfg.steps):
        v.problems.append("no 'write' stage step")
    provided = set((sop_files or {}).keys())
    for f in cfg.sop_files + cfg.llm.company_sop_files + cfg.llm.person_sop_files:
        name = Path(f).name
        exists = pipeline_dir is not None and (pipeline_dir / f).exists()
        if name not in provided and not exists:
            v.warnings.append(f"SOP file '{f}' is listed but not provided: add it in the SOP step or remove it from the list")
    if not cfg.countries.approved:
        v.warnings.append("no approved countries: the country check on rows will be skipped")
    if cfg.llm.enabled and cfg.llm.provider == "anthropic" and not (cfg.llm.company_sop_files or cfg.llm.person_sop_files):
        v.warnings.append("LLM assist is enabled but no SOP files are listed for it: its rubric would be only the ICP block")
    if cfg.icp.description.strip().startswith("Describe the ideal company"):
        v.warnings.append("the ICP description is still the template text")
    return v


def _safe_sop_name(name: str) -> str:
    base = Path(name).name
    if not SOP_NAME.match(base):
        raise ValueError(f"SOP file name '{name}' must be a simple name ending in .md")
    return base


def write_pipeline(name: str, yaml_text: str, sop_files: dict[str, str] | None = None, pipelines_dir: Path | None = None, overwrite: bool = False) -> Path:
    """Write pipelines/<name>/pipeline.yaml (+ sop/*.md). Validates first, refuses an existing pipeline unless overwrite=True (then backs the old YAML up
    under data/backups/). Returns the pipeline folder."""
    root = Path(pipelines_dir or paths.PIPELINES_DIR)
    if not SLUG.match(name):
        raise ValueError("name must be a lowercase slug (letters, digits, underscore; 2-41 characters)")
    folder = (root / name).resolve()
    if root.resolve() not in folder.parents:
        raise ValueError("pipeline folder must be inside the pipelines directory")
    sop = {_safe_sop_name(k): v for k, v in (sop_files or {}).items()}
    for k, v in sop.items():
        if len(v.encode("utf-8")) > MAX_SOP_BYTES:
            raise ValueError(f"SOP file '{k}' is larger than {MAX_SOP_BYTES // 1000} KB")
    v = validate_text(yaml_text, sop, folder if folder.exists() else None)
    if v.config is None or v.problems:
        raise ValueError("the pipeline is not valid: " + "; ".join((v.problems or ["unknown error"])[:5]))
    if v.config.name != name:
        raise ValueError(f"the YAML name '{v.config.name}' does not match '{name}'")
    exists = (folder / "pipeline.yaml").exists()
    if exists and not overwrite:
        raise FileExistsError(f"pipeline '{name}' already exists (use edit, or choose another name)")
    if not exists and folder.exists() and any(folder.iterdir()):
        raise FileExistsError(f"folder '{name}' exists and is not empty")
    if exists:
        bdir = paths.DATA_DIR / "backups"
        bdir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(folder / "pipeline.yaml", bdir / f"{name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml")
    (folder / "sop").mkdir(parents=True, exist_ok=True)
    for fname, text in sop.items():
        (folder / "sop" / fname).write_text(text, encoding="utf-8")
    tmp = folder / "pipeline.yaml.tmp"
    tmp.write_text(yaml_text if yaml_text.endswith("\n") else yaml_text + "\n", encoding="utf-8")
    tmp.replace(folder / "pipeline.yaml")
    return folder


def archive_pipeline(name: str, pipelines_dir: Path | None = None) -> Path:
    """Move pipelines/<name> to pipelines/_archived/<name>_<timestamp>. The files are kept; the pipeline just stops being listed or selectable."""
    root = Path(pipelines_dir or paths.PIPELINES_DIR)
    if not SLUG.match(name) or not (root / name / "pipeline.yaml").exists():
        raise ValueError(f"no pipeline '{name}'")
    dest = root / "_archived" / f"{name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(root / name), str(dest))
    return dest


def read_sop_files(cfg: PipelineConfig, folder: Path) -> dict[str, str]:
    """The SOP markdown files a pipeline lists (by file name), for cloning or editing."""
    out = {}
    for f in dict.fromkeys(cfg.sop_files + cfg.llm.company_sop_files + cfg.llm.person_sop_files):
        p = folder / f
        if p.exists():
            out[p.name] = p.read_text(encoding="utf-8")
    return out


def renamed_for_clone(d: dict, new_name: str) -> dict:
    """Clone dicts keep sop paths relative ('sop/x.md'), so they work unchanged in the new folder."""
    d = copy.deepcopy(d)
    d["name"] = new_name
    return d
