import copy
import time

import pytest
import yaml

from core import gate, jobs, keys, paths, spend
from core.config import load_config
from core.db import open_db, set_setting

CFG = load_config(paths.PIPELINES_DIR / "vfx_genai" / "pipeline.yaml")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("LPD_DATA", str(tmp_path))
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "dashboard.sqlite")
    con = open_db()
    set_setting(con, "demo_mode", "1")
    keys.check_all(con)
    con.execute("INSERT INTO pipelines (name, yaml_path) VALUES ('vfx_genai','x')")
    yield con
    for j in con.execute("SELECT pid FROM jobs").fetchall():
        if j["pid"] and jobs.pid_alive(j["pid"]):
            jobs.kill_tree(j["pid"])


def cycle(con, cap=3.0):
    return spend.create_cycle(con, CFG, 20, cap)


def test_cap_is_clamped_to_hard_max(env):
    c = cycle(env, cap=10)
    assert env.execute("SELECT cap_usd FROM cycles WHERE id=?", (c,)).fetchone()[0] == 3.0


def test_free_step_needs_no_gate(env):
    g = gate.evaluate(env, CFG, None, "demo_slow", {})
    assert g.ok and g.estimate.max_usd == 0


def test_paid_step_shows_cost_key_balance_and_remaining(env):
    c = cycle(env)
    g = gate.evaluate(env, CFG, c, "demo_paid", {"max_result": 100})
    assert g.ok and g.estimate.max_usd == pytest.approx(0.3)
    assert g.key_id == "apify_api_AAAA" and g.key_balance == 4.2 and g.remaining == 3.0


def test_paid_step_blocked_without_cycle_or_over_cap(env):
    g = gate.evaluate(env, CFG, None, "demo_paid", {})
    assert not g.ok and "no active cycle" in g.blockers[0]
    c = cycle(env, cap=0.2)
    g = gate.evaluate(env, CFG, c, "demo_paid", {"max_result": 100})        # $0.30 > $0.20
    assert not g.ok and "exceeds the remaining cycle cap" in g.blockers[0]
    spend.record(env, cycle_id=c, step_id="s", source="x", actual_usd=0.15)
    g = gate.evaluate(env, CFG, c, "demo_paid", {"max_result": 20})        # $0.06 > $0.05 left
    assert not g.ok


def test_reserved_cost_of_running_jobs_counts_against_cap(env):
    c = cycle(env, cap=0.5)
    env.execute("INSERT INTO jobs (step_id, cycle_id, status, est_max_usd) VALUES ('demo_paid', ?, 'running', 0.4)", (c,))
    g = gate.evaluate(env, CFG, c, "demo_paid", {"max_result": 100})        # 0.30 > 0.5 - 0.4
    assert g.reserved == 0.4 and not g.ok


def test_blocked_when_no_key_above_floor_or_stale(env):
    c = cycle(env)
    env.execute("UPDATE key_status SET state='low', remaining=0.5 WHERE key_prefix='apify_api_AAAA'")
    g = gate.evaluate(env, CFG, c, "demo_paid", {})
    assert not g.ok and "no free key" in g.blockers[-1]
    env.execute("UPDATE key_status SET checked_at='2020-01-01 00:00:00'")
    g = gate.evaluate(env, CFG, c, "demo_paid", {})
    assert not g.ok and "Check balances" in g.blockers[-1]


def test_warning_when_cost_could_drain_the_key(env):
    cfg = CFG.model_copy(deep=True)
    cfg.budget.stop_rules.min_usable_credit = 0            # isolate this check from the usable-credit stop rule
    c = cycle(env, cap=3.0)
    env.execute("UPDATE key_status SET remaining=1.0 WHERE key_prefix='apify_api_AAAA'")
    g = gate.evaluate(env, cfg, c, "demo_paid", {"max_result": 100})      # 0.30 > 1.0 - 0.8
    assert g.ok and g.warnings and "below $0.80" in g.warnings[0]


def test_stop_rule_cost_per_row_blocks_until_acknowledged(env):
    c = cycle(env)
    spend.record(env, cycle_id=c, step_id="s", source="x", actual_usd=2.0)
    for i in range(3):
        env.execute("INSERT INTO appended_rows (cycle_id, tab, row_number, name, company) VALUES (?, 'Linkedin', ?, 'n', 'c')", (c, i + 2))
    assert spend.cost_per_row(env, c) == pytest.approx(0.6667, abs=1e-3)
    g = gate.evaluate(env, CFG, c, "demo_paid", {})
    assert not g.ok and "cost_per_row" in g.blockers[0]
    ev = spend.open_stop_events(env, c)[0]
    spend.acknowledge(env, ev["id"])
    assert gate.evaluate(env, CFG, c, "demo_paid", {}).ok                   # acknowledged, does not re-trip in this cycle


def test_no_false_cost_per_row_stop_before_any_rows(env):
    c = cycle(env)
    spend.record(env, cycle_id=c, step_id="s", source="x", actual_usd=0.9)
    assert spend.cost_per_row(env, c) is None and gate.evaluate(env, CFG, c, "demo_paid", {}).ok


def test_pass_rate_needs_enough_reviewed_candidates(env):
    c = cycle(env)
    def add(n, decision):
        for _ in range(n):
            env.execute("INSERT INTO people (cycle_id, fields_json, decision) VALUES (?, '{}', ?)", (c, decision))
    add(1, "approved"); add(10, "rejected")
    assert spend.pass_rate(env, c)[0] is None                               # 11 reviewed: too few to judge
    assert not any(t.rule == "pass_rate" for t in spend.evaluate_stop_rules(env, CFG, c))
    add(30, "rejected")                                                     # 1/41 = 2.4% < 3%
    assert any(t.rule == "pass_rate" for t in spend.evaluate_stop_rules(env, CFG, c))


def test_usable_credit_rule(env):
    c = cycle(env)
    rules = lambda: {t.rule for t in spend.evaluate_stop_rules(env, CFG, c)}
    assert "usable_credit" not in rules()                                   # demo keys: $4.20 usable (the $0.50 key is under the floor, not counted)
    env.execute("UPDATE key_status SET remaining=2.0 WHERE key_prefix='apify_api_AAAA'")
    assert "usable_credit" in rules()                                       # $2.00 < $3.00
    env.execute("DELETE FROM key_status")                                    # no balances checked yet: the rule stays silent
    assert "usable_credit" not in rules()


def test_low_yield_rule_needs_two_ended_cycles(env):
    for rows in (2, 4):
        c = cycle(env)
        for i in range(rows):
            env.execute("INSERT INTO appended_rows (cycle_id, tab, row_number, name, company) VALUES (?, 'Linkedin', ?, 'n', 'c')", (c, i + 2))
        env.execute("UPDATE cycles SET status='ended' WHERE id=?", (c,))
    nxt = cycle(env)
    assert any(t.rule == "low_yield" for t in spend.evaluate_stop_rules(env, CFG, nxt))


def test_llm_has_its_own_cap_separate_from_apify(env, monkeypatch):
    from core.steps import base

    class L(base.Step):
        id, kind = "t_llm", "llm"
        def estimate_cost(self, ctx, params):
            return base.CostEstimate(max_usd=0.6, provider="llm")
    monkeypatch.setitem(base._REGISTRY, "t_llm", L())
    set_setting(env, "llm.enabled", "1")                      # LLM-kind steps are blocked unless LLM assist is switched on (demo mode supplies the provider)
    c = cycle(env, cap=0.1)                                                 # tiny Apify cap must not matter for LLM
    assert gate.evaluate(env, CFG, c, "t_llm", {}).ok
    spend.record(env, cycle_id=c, step_id="s", source="llm", kind="llm", actual_usd=0.5)
    assert not gate.evaluate(env, CFG, c, "t_llm", {}).ok                   # 0.6 > 1.00 - 0.5
    assert spend.cycle_spend(env, c) == 0 and spend.llm_spend(env, c) == 0.5


def test_confirm_and_start_blocks_stale_confirmation(env):
    c = cycle(env)
    g = gate.evaluate(env, CFG, c, "demo_paid", {"max_result": 25, "seconds": 1})
    with pytest.raises(gate.Blocked):                                       # user saw $0.075 on AAAA, params changed to 50 results
        gate.confirm_and_start(env, CFG, c, "demo_paid", {"max_result": 50, "seconds": 1}, g.estimate.max_usd, g.key_id)
    with pytest.raises(gate.Blocked):
        gate.confirm_and_start(env, CFG, c, "demo_paid", {"max_result": 25, "seconds": 1}, g.estimate.max_usd, "apify_api_BBBB")


def test_paid_step_end_to_end_with_mock_run(env):
    """Gate -> confirm -> real detached worker -> key lease -> ledger entry with actual cost -> lease released."""
    c = cycle(env)
    p = {"max_result": 25, "seconds": 2, "actual_results": 20}
    g = gate.evaluate(env, CFG, c, "demo_paid", p)
    jid = gate.confirm_and_start(env, CFG, c, "demo_paid", p, g.estimate.max_usd, g.key_id)
    assert spend.reserved(env, c) == pytest.approx(0.075)                   # worst case reserved while it runs
    t0 = time.time()
    while jobs.get_job(env, jid)["status"] not in ("done", "failed") and time.time() - t0 < 40:
        time.sleep(0.3)
    j = jobs.get_job(env, jid)
    assert j["status"] == "done", f"pid {j['pid']} alive={jobs.pid_alive(j['pid'])}\n" + jobs.tail_log(jid)
    row = env.execute("SELECT * FROM spend_ledger WHERE cycle_id=?", (c,)).fetchone()
    assert (row["key_prefix"], row["results"], row["est_max_usd"]) == ("apify_api_AAAA", 20, pytest.approx(0.075))
    assert row["actual_usd"] == pytest.approx(0.06)
    assert spend.cycle_spend(env, c) == pytest.approx(0.06) and spend.reserved(env, c) == 0
    assert env.execute("SELECT COUNT(*) FROM key_leases").fetchone()[0] == 0


def test_paid_job_cannot_resume_without_the_gate(env):
    jid = env.execute("INSERT INTO jobs (step_id, status, kind) VALUES ('demo_paid','interrupted','paid')").lastrowid
    with pytest.raises(PermissionError):
        jobs.resume_job(env, jid)


def test_worker_refuses_paid_step_without_confirmed_key(env):
    c = cycle(env)
    jid = jobs.create_job(env, "demo_paid", {"seconds": 1}, c, confirmed=True)       # no key_id: as if someone bypassed the gate
    jobs.launch(env, jid)
    t0 = time.time()
    while jobs.get_job(env, jid)["status"] not in ("failed", "done") and time.time() - t0 < 30:
        time.sleep(0.3)
    j = jobs.get_job(env, jid)
    assert j["status"] == "failed" and "none was confirmed" in j["error"]
    assert env.execute("SELECT COUNT(*) FROM spend_ledger").fetchone()[0] == 0
