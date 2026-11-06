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


# ---- helpers for paid-step tests (no network: apify.get_client is patched to a FakeApify)
from contextlib import contextmanager

from core import spend as _spend


def paid_ctx(tmp_path: Path, key_id: str = "apify_api_TEST", job_id: int = 1):
    """A step context with a key lease stand-in and a real ledger writer. Returns (ctx, con, logs, cycle_id)."""
    ctx, con, logs = make_ctx(tmp_path)
    con.execute("INSERT OR IGNORE INTO pipelines (name, yaml_path) VALUES ('vfx_genai','x')")
    cid = _spend.create_cycle(con, CFG, 20, 3.0)
    con.execute("INSERT INTO jobs (id, step_id, status, cycle_id) VALUES (?, 'x', 'running', ?)", (job_id, cid))
    ctx.cycle_id, ctx.job_id = cid, job_id

    @contextmanager
    def use_key(provider):
        yield key_id, "secret-" + key_id

    def record_spend(*, source, est_max_usd, actual_usd, results, key_id, note, kind):
        _spend.record(con, cycle_id=cid, step_id="x", source=source, kind=kind, key_prefix=key_id, est_max_usd=est_max_usd, actual_usd=actual_usd, results=results, note=note)
    ctx._use_key, ctx._record_spend = use_key, record_spend
    return ctx, con, logs, cid
