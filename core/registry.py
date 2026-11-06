"""Load pipelines from pipelines/*/pipeline.yaml and sync them into the DB. A broken file becomes an error entry, never a crash."""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .config import ConfigError, PipelineConfig, load_config


@dataclass
class Loaded:
    dir: Path
    config: PipelineConfig | None
    problems: list[str]
    missing_sop: list[str]


def load_all() -> list[Loaded]:
    out = []
    for d in paths.pipeline_dirs():
        try:
            cfg = load_config(d / "pipeline.yaml")
            out.append(Loaded(d, cfg, [], [f for f in cfg.sop_files if not (d / f).exists()]))
        except ConfigError as e:
            out.append(Loaded(d, None, e.problems, []))
    return out


def sync_db(con: sqlite3.Connection, loaded: list[Loaded]) -> None:
    for p in loaded:
        if not p.config:
            continue
        h = hashlib.sha256((p.dir / "pipeline.yaml").read_bytes()).hexdigest()[:16]
        con.execute(
            "INSERT INTO pipelines (name, yaml_path, config_hash) VALUES (?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET yaml_path=excluded.yaml_path, config_hash=excluded.config_hash, updated_at=CURRENT_TIMESTAMP",
            (p.config.name, str(p.dir / "pipeline.yaml"), h))
