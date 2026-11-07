"""Load pipelines from pipelines/*/pipeline.yaml and sync them into the DB. A broken file becomes an error entry, never a crash."""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .config import ConfigError, PipelineConfig, load_config


@dataclass
class Loaded:
    dir: Path
    config: PipelineConfig | None
    problems: list[str]
    missing_sop: list[str]
    step_problems: list[str] = field(default_factory=list)     # steps the YAML names that are unavailable or have bad params
    step_unavailable: list[str] = field(default_factory=list)


def check_steps(cfg: PipelineConfig) -> tuple[list[str], list[str]]:
    """(problems, not-yet-available step ids). A step id with no implementation yet is a warning; bad params for a real step are a problem."""
    from .steps import all_steps
    from .steps.base import origin_of
    reg, problems, missing = all_steps(), [], []
    for s in cfg.steps:
        if s.step not in reg:
            missing.append(s.step)
            continue
        if origin_of(s.step) not in ("builtin", cfg.name):
            problems.append(f"step '{s.step}' belongs to pipeline '{origin_of(s.step)}', not '{cfg.name}'")
            continue
        try:
            reg[s.step].params_model(**s.params)
        except Exception as e:                                  # pydantic ValidationError
            errs = getattr(e, "errors", lambda: [{"loc": [], "msg": str(e), "type": "other"}])()
            errs = [x for x in errs if x.get("type") != "missing"]      # values only known at run time (e.g. the confirmed row count) are not YAML errors
            if errs:
                problems.append(f"step '{s.step}': " + "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in errs))
    return problems, missing


def load_all() -> list[Loaded]:
    out = []
    for d in paths.pipeline_dirs():
        try:
            cfg = load_config(d / "pipeline.yaml")
            sp, miss = check_steps(cfg)
            out.append(Loaded(d, cfg, [], [f for f in cfg.sop_files if not (d / f).exists()], sp, miss))
        except ConfigError as e:
            out.append(Loaded(d, None, e.problems, []))
    return out


def get_config(name: str) -> PipelineConfig | None:
    for p in load_all():
        if p.config and p.config.name == name:
            return p.config
    return None


def sync_db(con: sqlite3.Connection, loaded: list[Loaded]) -> None:
    for p in loaded:
        if not p.config:
            continue
        h = hashlib.sha256((p.dir / "pipeline.yaml").read_bytes()).hexdigest()[:16]
        con.execute(
            "INSERT INTO pipelines (name, yaml_path, config_hash) VALUES (?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET yaml_path=excluded.yaml_path, config_hash=excluded.config_hash, updated_at=CURRENT_TIMESTAMP",
            (p.config.name, str(p.dir / "pipeline.yaml"), h))
