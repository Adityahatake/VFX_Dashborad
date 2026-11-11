"""Shared FastAPI dependencies and helpers (one pipeline: vfx_genai)."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator

from fastapi import HTTPException

from core import jobs
from core.config import PipelineConfig
from core.db import connect
from core.registry import get_config

PIPELINE = "vfx_genai"
HIDDEN_STEPS = {"demo_slow", "demo_paid"}           # test helpers: never offered in the production UI


def db() -> Iterator[sqlite3.Connection]:
    con = connect(any_thread=True)
    try:
        yield con
    finally:
        con.close()


def cfg() -> PipelineConfig:
    c = get_config(PIPELINE)
    if c is None:
        raise HTTPException(500, f"pipelines/{PIPELINE}/pipeline.yaml is missing or invalid")
    return c


def row(r) -> dict | None:
    return dict(r) if r is not None else None


def active_cycle(con) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM cycles WHERE pipeline=? AND status='active' ORDER BY id DESC LIMIT 1", (PIPELINE,)).fetchone()


def job_view(j) -> dict:
    d = dict(j)
    d["stuck"] = jobs.is_stuck(j)
    d["heartbeat_age_s"] = jobs.age_seconds(j["heartbeat_at"]) if j["status"] in jobs.LIVE else None
    d["params"] = json.loads(d.pop("params_json") or "{}")
    for k in ("log_path", "checkpoint_path", "pid"):
        d.pop(k, None)                                   # local paths and pids are not the UI's business
    return d
