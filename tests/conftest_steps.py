"""Helpers for step tests (imported by the test modules; not a pytest conftest, to keep it explicit)."""
from pathlib import Path

from core import paths
from core.config import load_config
from core.db import open_db
from core.steps.base import StepContext

CFG = load_config(paths.PIPELINES_DIR / "vfx_genai" / "pipeline.yaml")


def make_ctx(tmp_path: Path, cancel=lambda: False, cycle_id=None, sheet=None):
    con = open_db(tmp_path / "t.sqlite")
    logs: list[str] = []
    ctx = StepContext(job_id=1, cycle_id=cycle_id, workdir=tmp_path / "w", job_dir=tmp_path / "j", log=logs.append, is_cancelled=cancel,
                      lease=None, cfg=CFG, db=con, pipeline_dir=tmp_path / "p", sheet=sheet)
    (tmp_path / "j").mkdir(exist_ok=True)
    return ctx, con, logs
