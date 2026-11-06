"""Detached job entry point: `py -m core.worker --job <id> [--resume]`. Runs one step, heartbeats, honours cancel, records the outcome."""
from __future__ import annotations

import argparse
import os
import threading
import traceback

from . import jobs, paths
from .db import open_db
from .logmask import mask
from .steps import get_step
from .steps.base import Cancelled, LeaseBusy, StepContext


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", type=int, required=True)
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args(argv)
    paths.load_env()
    con = open_db()
    job = jobs.get_job(con, a.job)
    if job is None:
        return 2
    jid = a.job

    if a.resume is False and jobs.cancel_flag_set(jid) and job["cancel_requested"]:
        jobs.log_line(jid, "cancelled before start")
        con.execute("UPDATE jobs SET status='cancelled', finished_at=? WHERE id=?", (jobs.utcnow(), jid))
        return 0

    con.execute("UPDATE jobs SET status='running', pid=?, started_at=COALESCE(started_at, ?), heartbeat_at=?, error=NULL, finished_at=NULL WHERE id=?",
                (os.getpid(), jobs.utcnow(), jobs.utcnow(), jid))
    jobs.log_line(jid, f"{'resuming' if a.resume else 'starting'} step {job['step_id']} (pid {os.getpid()})")

    stop = threading.Event()

    def beat():
        c = open_db()                                    # sqlite connections are per-thread
        while not stop.wait(5):
            c.execute("UPDATE jobs SET heartbeat_at=? WHERE id=?", (jobs.utcnow(), jid))
    threading.Thread(target=beat, daemon=True).start()

    status, error, code = "done", None, 0
    try:
        step = get_step(job["step_id"])
        params = step.params_model(**__import__("json").loads(job["params_json"] or "{}"))
        ctx = StepContext(job_id=jid, cycle_id=job["cycle_id"], workdir=jobs.workdir_for(job["cycle_id"], jid), job_dir=jobs.job_dir(jid),
                          log=lambda m: jobs.log_line(jid, m), is_cancelled=lambda: jobs.cancel_flag_set(jid),
                          lease=lambda prefix: jobs.lease(con, prefix, jid))
        result = (step.resume if a.resume else step.run)(ctx, params)
        jobs.log_line(jid, f"finished: {result.message or result.status} {result.counts or ''}".strip())
        if result.status == "partial":
            status = "interrupted"
    except Cancelled:
        status = "cancelled"
        jobs.log_line(jid, "cancelled by request; progress is checkpointed, you can resume")
    except LeaseBusy as e:
        status, error, code = "failed", str(e), 3
        jobs.log_line(jid, f"cannot start: {e}")
    except BaseException as e:                           # noqa: BLE001: a job must always record why it died
        status, error, code = "failed", mask(f"{type(e).__name__}: {e}"), 1
        jobs.log_line(jid, "FAILED\n" + mask(traceback.format_exc()))
    finally:
        stop.set()
        jobs._finish(con, jid, status, error)
        con.execute("UPDATE jobs SET exit_code=?, heartbeat_at=? WHERE id=?", (code, jobs.utcnow(), jid))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
