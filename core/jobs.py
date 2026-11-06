"""Jobs engine: every step runs as a detached subprocess (core.worker). State lives in SQLite, so jobs survive closing the
browser or restarting Streamlit. Provides launch, cancel (flag file, then kill after a grace period), reconcile (dead PIDs ->
interrupted), resume (continue from checkpoint) and one-job-per-key leases."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import paths
from .logmask import mask
from .steps import get_step
from .steps.base import LeaseBusy

LIVE = ("queued", "running")
RESUMABLE = ("interrupted", "failed", "cancelled")
HEARTBEAT_STALE_S = 60
CANCEL_GRACE_S = 15


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def age_seconds(ts: str | None) -> float | None:
    if not ts:
        return None
    return (datetime.now(timezone.utc) - datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)).total_seconds()


def job_dir(job_id: int) -> Path:
    d = paths.DATA_DIR / "jobs" / str(job_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def workdir_for(cycle_id: int | None, job_id: int) -> Path:
    return paths.DATA_DIR / ("cycles/" + str(cycle_id) if cycle_id else f"adhoc/job_{job_id}")


# ---------------------------------------------------------------- process helpers
def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        h = k.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = wintypes.DWORD()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259         # STILL_ACTIVE
    try:
        os.kill(pid, 0)                                # POSIX only: signal 0 just probes (on Windows it would terminate!)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def kill_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        import signal
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


# ---------------------------------------------------------------- queries
def get_job(con: sqlite3.Connection, job_id: int):
    return con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()


def list_jobs(con: sqlite3.Connection, limit: int = 50):
    return con.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def is_stuck(job) -> bool:
    """Running, process still alive, but no heartbeat for a while."""
    return job["status"] == "running" and pid_alive(job["pid"]) and (age_seconds(job["heartbeat_at"]) or 0) > HEARTBEAT_STALE_S


def tail_log(job_id: int, lines: int = 200) -> str:
    p = job_dir(job_id) / "job.log"
    if not p.exists():
        return ""
    data = p.read_bytes()[-200_000:].decode("utf-8", "replace")
    return "\n".join(data.splitlines()[-lines:])


# ---------------------------------------------------------------- create / launch
def create_job(con: sqlite3.Connection, step_id: str, params: dict | None = None, cycle_id: int | None = None, confirmed: bool = False,
               key_id: str | None = None, est_max_usd: float = 0.0, pipeline: str | None = None) -> int:
    step = get_step(step_id)                                   # KeyError for unknown steps
    p = step.params_model(**(params or {}))                    # ValidationError for bad params, before anything is created
    if step.kind in ("paid", "llm", "write") and not confirmed:
        raise PermissionError(f"step '{step_id}' is {step.kind}: it needs an explicit confirmation (core.gate.confirm_and_start)")
    if pipeline is None and cycle_id:                          # a cycle belongs to exactly one pipeline
        row = con.execute("SELECT pipeline FROM cycles WHERE id=?", (cycle_id,)).fetchone()
        pipeline = row[0] if row else None
    cur = con.execute("INSERT INTO jobs (step_id, params_json, cycle_id, status, key_id, est_max_usd, kind, pipeline) VALUES (?,?,?, 'queued', ?, ?, ?, ?)",
                      (step_id, json.dumps(p.model_dump()), cycle_id, key_id, est_max_usd, step.kind, pipeline))
    return cur.lastrowid


def worker_python() -> tuple[str, dict]:
    """(interpreter, extra env) for workers. In a venv on Windows, `.venv\\Scripts\\python.exe` is only a launcher that starts the real interpreter
    inside a kill-on-close job object; that extra layer made workers die silently when the launcher or its parent job went away, and it makes the
    PID we track differ from the real worker's. So run the base interpreter directly and hand it the venv's packages through PYTHONPATH."""
    if os.name == "nt" and sys.prefix != sys.base_prefix and getattr(sys, "_base_executable", None) and Path(sys._base_executable).exists():
        import sysconfig
        pp = os.pathsep.join(p for p in (sysconfig.get_path("purelib"), sysconfig.get_path("platlib"), str(paths.ROOT), os.environ.get("PYTHONPATH", "")) if p)
        return sys._base_executable, {"PYTHONPATH": pp}
    return sys.executable, {}


def launch(con: sqlite3.Connection, job_id: int, resume: bool = False) -> int:
    """Start core.worker as a detached process (survives the browser and Streamlit). Returns the PID."""
    jd = job_dir(job_id)
    py, extra_env = worker_python()
    args = [py, "-m", "core.worker", "--job", str(job_id)] + (["--resume"] if resume else [])
    env = {**os.environ, **extra_env, "PYTHONIOENCODING": "utf-8", "PYTHONFAULTHANDLER": "1"}   # a hard crash then leaves a traceback in worker.out
    kw: dict = dict(cwd=str(paths.ROOT), stdin=subprocess.DEVNULL, close_fds=True, env=env)
    out_path = jd / "worker.out"                               # crashes before logging starts land here
    con.execute("UPDATE jobs SET status='queued', pid=NULL, heartbeat_at=?, log_path=?, checkpoint_path=? WHERE id=?",
                (utcnow(), str(jd / "job.log"), str(jd / "checkpoint.json"), job_id))
    if os.name == "nt":
        # Windows: a short-lived intermediary starts the worker and exits, so the worker is not a child of Streamlit. Otherwise a tool or
        # terminal that kills Streamlit's process tree would take the job down with it.
        stub = ("import subprocess,sys;f=0x00000008|0x00000200|0x08000000\n"
                "a=sys.argv[2:];o=open(sys.argv[1],'ab')\n"
                "def go(fl): return subprocess.Popen(a,stdin=subprocess.DEVNULL,stdout=o,stderr=o,close_fds=True,creationflags=fl)\n"
                "try: p=go(f|0x01000000)\n"           # CREATE_BREAKAWAY_FROM_JOB, if the job object allows it
                "except OSError: p=go(f)\n"
                "print(p.pid)")
        r = subprocess.run([py, "-c", stub, str(out_path), *args], capture_output=True, text=True, timeout=30, cwd=kw["cwd"], env=env)
        pid = int(r.stdout.strip().splitlines()[-1])
    else:
        with open(out_path, "ab") as out:
            pid = subprocess.Popen(args, stdout=out, stderr=out, start_new_session=True, **kw).pid
    # The worker records its own pid as soon as it starts; only fill it in if it has not done so yet (never overwrite the worker's pid or status).
    con.execute("UPDATE jobs SET pid=? WHERE id=? AND pid IS NULL AND status='queued'", (pid, job_id))
    return pid


def start_job(con: sqlite3.Connection, step_id: str, params: dict | None = None, cycle_id: int | None = None, confirmed: bool = False,
              key_id: str | None = None, est_max_usd: float = 0.0, pipeline: str | None = None) -> int:
    jid = create_job(con, step_id, params, cycle_id, confirmed, key_id, est_max_usd, pipeline)
    launch(con, jid)
    return jid


# ---------------------------------------------------------------- cancel / resume / reconcile
def request_cancel(con: sqlite3.Connection, job_id: int) -> None:
    """Graceful first: set the flag (the step sees it at its next check_cancel). enforce_cancels() kills after the grace period."""
    (job_dir(job_id) / "cancel.flag").write_text("1")
    con.execute("UPDATE jobs SET cancel_requested=1, cancel_requested_at=COALESCE(cancel_requested_at, ?) WHERE id=? AND status IN ('queued','running')",
                (utcnow(), job_id))


def cancel_flag_set(job_id: int) -> bool:
    return (job_dir(job_id) / "cancel.flag").exists()


def release_leases(con: sqlite3.Connection, job_id: int) -> None:
    con.execute("DELETE FROM key_leases WHERE job_id=?", (job_id,))


def _finish(con, job_id: int, status: str, error: str | None = None) -> None:
    con.execute("UPDATE jobs SET status=?, finished_at=?, error=COALESCE(?, error) WHERE id=?", (status, utcnow(), error, job_id))
    release_leases(con, job_id)


def enforce_cancels(con: sqlite3.Connection, grace: float = CANCEL_GRACE_S) -> list[int]:
    """Kill jobs that were asked to cancel but are still alive after the grace period."""
    killed = []
    for j in con.execute("SELECT * FROM jobs WHERE cancel_requested=1 AND status IN ('queued','running')").fetchall():
        if (age_seconds(j["cancel_requested_at"]) or 0) < grace and pid_alive(j["pid"]):
            continue
        was_alive = pid_alive(j["pid"])
        if was_alive:
            kill_tree(j["pid"])
        _finish(con, j["id"], "cancelled", "killed after the grace period (checkpoint kept; you can resume)" if was_alive else None)
        killed.append(j["id"])
    return killed


def reconcile(con: sqlite3.Connection) -> list[int]:
    """Run on app start and on every Jobs refresh: live jobs whose process is gone become 'interrupted' and free their key leases."""
    changed = enforce_cancels(con)
    for j in con.execute("SELECT * FROM jobs WHERE status IN ('queued','running')").fetchall():
        if j["pid"] is None and (age_seconds(j["heartbeat_at"]) or 0) < 30:
            continue                      # launch() is still starting the process
        if not pid_alive(j["pid"]):
            _finish(con, j["id"], "interrupted", "process ended without finishing (app or machine restarted, or it crashed)")
            changed.append(j["id"])
    # leases whose holder is no longer live never block anyone
    con.execute("DELETE FROM key_leases WHERE job_id NOT IN (SELECT id FROM jobs WHERE status IN ('queued','running'))")
    return changed


def mark_interrupted(con: sqlite3.Connection, job_id: int) -> None:
    """For a stuck job (alive but silent): stop it and make it resumable."""
    j = get_job(con, job_id)
    if j and pid_alive(j["pid"]):
        kill_tree(j["pid"])
    _finish(con, job_id, "interrupted", "stopped by the user (no heartbeat)")


def resume_job(con: sqlite3.Connection, job_id: int, confirmed: bool = False) -> int:
    j = get_job(con, job_id)
    if j is None or j["status"] not in RESUMABLE:
        raise ValueError(f"job {job_id} cannot be resumed (status {j['status'] if j else 'missing'})")
    if j["kind"] in ("paid", "llm", "write") and not confirmed:
        raise PermissionError(f"job {job_id} is a {j['kind']} step: resume it through core.gate.confirm_and_resume so the cap and key checks run again")
    (job_dir(job_id) / "cancel.flag").unlink(missing_ok=True)
    con.execute("UPDATE jobs SET cancel_requested=0, cancel_requested_at=NULL, error=NULL, finished_at=NULL, resumed_count=resumed_count+1 WHERE id=?", (job_id,))
    return launch(con, job_id, resume=True)


# ---------------------------------------------------------------- key leases
def acquire_lease(con: sqlite3.Connection, key_prefix: str, job_id: int) -> None:
    """One job per API key. A lease held by a dead/finished job is stolen; a live holder raises LeaseBusy."""
    for _ in range(2):
        try:
            con.execute("INSERT INTO key_leases (key_prefix, job_id) VALUES (?,?)", (key_prefix, job_id))
            return
        except sqlite3.IntegrityError:
            holder = con.execute("SELECT l.job_id, j.status, j.pid FROM key_leases l JOIN jobs j ON j.id=l.job_id WHERE l.key_prefix=?", (key_prefix,)).fetchone()
            if holder and holder["job_id"] == job_id:
                return
            if holder and holder["status"] in LIVE and pid_alive(holder["pid"]):
                raise LeaseBusy(f"key {key_prefix} is in use by job {holder['job_id']}")
            con.execute("DELETE FROM key_leases WHERE key_prefix=?", (key_prefix,))
    raise LeaseBusy(f"could not acquire key {key_prefix}")


@contextmanager
def lease(con: sqlite3.Connection, key_prefix: str, job_id: int):
    acquire_lease(con, key_prefix, job_id)
    try:
        yield key_prefix
    finally:
        con.execute("DELETE FROM key_leases WHERE key_prefix=? AND job_id=?", (key_prefix, job_id))


def log_line(job_id: int, msg: str) -> None:
    from time import strftime
    with open(job_dir(job_id) / "job.log", "a", encoding="utf-8") as f:
        f.write(f"[{strftime('%H:%M:%S')}] {mask(str(msg))}\n")
