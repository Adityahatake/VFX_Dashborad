"""Jobs engine tests. These launch REAL detached worker processes running the free demo step (no network, no cost)."""
import os
import sqlite3
import time

import pytest

from core import jobs, paths
from core.db import open_db
from core.steps.base import LeaseBusy


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("LPD_DATA", str(tmp_path))           # inherited by worker subprocesses
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "dashboard.sqlite")
    con = open_db()
    yield con
    for j in con.execute("SELECT pid FROM jobs").fetchall():     # never leave stray workers behind (but never kill ourselves)
        if j["pid"] not in (os.getpid(), 1) and jobs.pid_alive(j["pid"]):
            jobs.kill_tree(j["pid"])


def wait_for(con, jid, statuses, timeout=40):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = jobs.get_job(con, jid)["status"]
        if s in statuses:
            return s
        time.sleep(0.3)
    raise AssertionError(f"job {jid} stuck in {jobs.get_job(con, jid)['status']}; log:\n{jobs.tail_log(jid)}")


def test_pid_alive_current_and_dead():
    assert jobs.pid_alive(os.getpid())
    assert not jobs.pid_alive(None)
    assert not jobs.pid_alive(2**22 + 12345)


def test_run_to_completion(env):
    jid = jobs.start_job(env, "demo_slow", {"duration_s": 2, "tick_s": 0.5})
    assert wait_for(env, jid, ("done",)) == "done"
    j = jobs.get_job(env, jid)
    assert j["exit_code"] == 0 and j["finished_at"]
    assert "tick 4/4" in jobs.tail_log(jid)
    assert (paths.DATA_DIR / "adhoc" / f"job_{jid}" / "demo_out.txt").exists()


def test_bad_params_and_unknown_step_create_nothing(env):
    with pytest.raises(Exception):
        jobs.create_job(env, "demo_slow", {"duration_s": -5})
    with pytest.raises(KeyError):
        jobs.create_job(env, "nope")
    assert env.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_failure_is_recorded(env):
    jid = jobs.start_job(env, "demo_slow", {"duration_s": 4, "tick_s": 0.5, "fail_at": 2})
    assert wait_for(env, jid, ("failed",)) == "failed"
    j = jobs.get_job(env, jid)
    assert "demo failure" in j["error"] and j["exit_code"] == 1


def test_graceful_cancel_then_resume_from_checkpoint(env):
    jid = jobs.start_job(env, "demo_slow", {"duration_s": 60, "tick_s": 0.5})
    wait_for(env, jid, ("running",))
    time.sleep(2.5)
    jobs.request_cancel(env, jid)
    assert wait_for(env, jid, ("cancelled",)) == "cancelled"
    done = __import__("json").loads((paths.DATA_DIR / "jobs" / str(jid) / "checkpoint.json").read_text())["done"]
    assert done >= 2
    jobs.resume_job(env, jid)
    wait_for(env, jid, ("running",))
    time.sleep(1.5)
    assert f"resuming from checkpoint: {done} ticks" in jobs.tail_log(jid)
    assert jobs.get_job(env, jid)["resumed_count"] == 1
    jobs.request_cancel(env, jid)
    wait_for(env, jid, ("cancelled",))


def test_kill_after_grace_when_step_ignores_cancel(env):
    jid = jobs.start_job(env, "demo_slow", {"duration_s": 120, "tick_s": 30})     # one long tick: cannot see the flag soon
    wait_for(env, jid, ("running",))
    jobs.request_cancel(env, jid)
    time.sleep(1)
    assert jobs.enforce_cancels(env, grace=60) == []                               # still inside the grace period
    assert jobs.enforce_cancels(env, grace=0) == [jid]
    j = jobs.get_job(env, jid)
    assert j["status"] == "cancelled" and "killed" in j["error"]
    t0 = time.time()
    while jobs.pid_alive(j["pid"]) and time.time() - t0 < 10:
        time.sleep(0.2)
    assert not jobs.pid_alive(j["pid"])


def test_reconcile_marks_dead_jobs_interrupted_and_frees_leases(env):
    jid = env.execute("INSERT INTO jobs (step_id, status, pid) VALUES ('demo_slow','running', 4194999)").lastrowid
    env.execute("INSERT INTO key_leases (key_prefix, job_id) VALUES ('apify_zzzz', ?)", (jid,))
    assert jobs.reconcile(env) == [jid]
    j = jobs.get_job(env, jid)
    assert j["status"] == "interrupted" and "ended without finishing" in j["error"]
    assert env.execute("SELECT COUNT(*) FROM key_leases").fetchone()[0] == 0


def test_job_survives_loss_of_the_launcher(env):
    """The worker is independent of the process that launched it: a fresh connection (as after a Streamlit restart) still sees it running."""
    jid = jobs.start_job(env, "demo_slow", {"duration_s": 60, "tick_s": 0.5})
    wait_for(env, jid, ("running",))
    other = open_db()
    assert jobs.reconcile(other) == []                       # not wrongly marked interrupted
    assert jobs.get_job(other, jid)["status"] == "running"
    jobs.request_cancel(env, jid)
    wait_for(env, jid, ("cancelled",))


@pytest.mark.skipif(os.name != "nt", reason="tree-kill semantics tested on Windows")
def test_worker_survives_tree_kill_of_the_launcher(env):
    """What happens when Streamlit's process tree is killed (terminal closed, tool stopped it): the worker must keep running."""
    import subprocess
    import sys
    code = ("from core import jobs, paths\nfrom core.db import open_db\nimport time\n"
            "c = open_db()\nprint(jobs.start_job(c, 'demo_slow', {'duration_s': 60, 'tick_s': 0.5}), flush=True)\ntime.sleep(120)")
    parent = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True, cwd=str(paths.ROOT))
    jid = int(parent.stdout.readline())
    wait_for(env, jid, ("running",))
    jobs.kill_tree(parent.pid)                                   # taskkill /T /F on the launcher
    parent.wait(timeout=10)
    time.sleep(3)
    j = jobs.get_job(env, jid)
    assert jobs.pid_alive(j["pid"]), "worker died with its launcher"
    assert jobs.reconcile(env) == [] and jobs.get_job(env, jid)["status"] == "running"
    jobs.request_cancel(env, jid)
    wait_for(env, jid, ("cancelled",))


def test_one_job_per_key(env):
    a = jobs.start_job(env, "demo_slow", {"duration_s": 60, "tick_s": 0.5, "lease_key": "apify_ZoxD"})
    wait_for(env, a, ("running",))
    time.sleep(1.5)
    b = jobs.start_job(env, "demo_slow", {"duration_s": 5, "tick_s": 0.5, "lease_key": "apify_ZoxD"})
    assert wait_for(env, b, ("failed",)) == "failed"
    assert "in use by job" in jobs.get_job(env, b)["error"]
    jobs.request_cancel(env, a)
    wait_for(env, a, ("cancelled",))
    assert env.execute("SELECT COUNT(*) FROM key_leases").fetchone()[0] == 0
    c = jobs.start_job(env, "demo_slow", {"duration_s": 1, "tick_s": 0.5, "lease_key": "apify_ZoxD"})
    assert wait_for(env, c, ("done",)) == "done"


def test_stale_lease_of_dead_job_is_stolen(env):
    dead = env.execute("INSERT INTO jobs (step_id, status, pid) VALUES ('demo_slow','running', 4194999)").lastrowid
    env.execute("INSERT INTO key_leases (key_prefix, job_id) VALUES ('k1', ?)", (dead,))
    me = env.execute("INSERT INTO jobs (step_id, status, pid) VALUES ('demo_slow','running', ?)", (os.getpid(),)).lastrowid
    jobs.acquire_lease(env, "k1", me)
    assert env.execute("SELECT job_id FROM key_leases WHERE key_prefix='k1'").fetchone()[0] == me
    other = env.execute("INSERT INTO jobs (step_id, status, pid) VALUES ('demo_slow','running', 1)").lastrowid
    with pytest.raises(LeaseBusy):
        jobs.acquire_lease(env, "k1", other)


def test_paid_steps_need_confirmation(env, monkeypatch):
    from core.steps import base

    class Paid(base.Step):
        id, kind = "t_paid", "paid"
    monkeypatch.setitem(base._REGISTRY, "t_paid", Paid())
    with pytest.raises(PermissionError):
        jobs.create_job(env, "t_paid")
    assert jobs.create_job(env, "t_paid", confirmed=True)


def test_resume_only_for_resumable(env):
    jid = env.execute("INSERT INTO jobs (step_id, status) VALUES ('demo_slow','running')").lastrowid
    with pytest.raises(ValueError):
        jobs.resume_job(env, jid)
