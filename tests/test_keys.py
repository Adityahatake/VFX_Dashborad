import urllib.error

import pytest

from core import http, keys, paths
from core.db import open_db, set_setting

A1 = "apify_api_" + "ZoxD1234567890"
A2 = "apify_api_" + "Qwer1234567890"
T1 = "tvly-" + "dev-abcdef1234567890"


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "ROOT", tmp_path / "repo")
    (tmp_path / "repo").mkdir()
    return open_db(tmp_path / "t.sqlite")


def http_error(code):
    return urllib.error.HTTPError("u", code, "x", {}, None)


def limits(cap, used, end="2026-12-01T00:00:00Z"):
    return {"data": {"limits": {"maxMonthlyUsageUsd": cap}, "current": {"monthlyUsageUsd": used}, "monthlyUsageCycle": {"endAt": end}}}


def test_key_id_shows_prefix_only():
    assert keys.key_id(A1) == "apify_api_ZoxD"
    assert A1 not in keys.key_id(A1)
    assert keys.key_id(T1) == "tvly-dev-abcdef"[:5 + 8]
    assert keys.key_id("weirdkey123") == "weirdk…"


def test_apify_states(monkeypatch):
    monkeypatch.setattr(http, "get_json", lambda url, key=None, timeout=40: limits(5, 1.0))
    s = keys.check_apify(A1)
    assert (s.state, s.remaining, s.cap, s.resets) == ("usable", 4.0, 5, "2026-12-01")
    monkeypatch.setattr(http, "get_json", lambda *a, **k: limits(5, 4.5))
    assert keys.check_apify(A1).state == "low"           # 0.50 left: under the $0.80 floor
    monkeypatch.setattr(http, "get_json", lambda *a, **k: limits(5, 5))
    assert keys.check_apify(A1).state == "out"


def test_apify_errors(monkeypatch):
    def boom(code):
        def f(*a, **k):
            raise http_error(code)
        return f
    monkeypatch.setattr(http, "get_json", boom(401))
    assert keys.check_apify(A1).state == "dead"
    monkeypatch.setattr(http, "get_json", boom(500))
    assert keys.check_apify(A1).state == "error"


def test_tavily_usage_is_free_and_live_search_is_opt_in(monkeypatch):
    calls = []
    monkeypatch.setattr(http, "get_json", lambda url, key=None, timeout=40: {"account": {"plan_limit": 1000, "plan_usage": 400}})
    monkeypatch.setattr(http, "post_json", lambda url, body, key=None, timeout=60: calls.append(url) or {})
    s = keys.check_tavily(T1)
    assert (s.state, s.remaining) == ("usable", 600.0) and calls == []          # no credit spent by default
    keys.check_tavily(T1, live_search=True)
    assert len(calls) == 1

    def over(*a, **k):
        raise http_error(432)
    monkeypatch.setattr(http, "post_json", over)
    assert keys.check_tavily(T1, live_search=True).state == "out"


def test_error_check_keeps_last_balance(con):
    keys.save_status(con, keys.KeyStatus("apify_api_ZoxD", "apify", "usable", 3.0, 5, "x", keys._now()))
    keys.save_status(con, keys.KeyStatus("apify_api_ZoxD", "apify", "error", checked_at=keys._now()))
    r = keys.statuses(con, "apify")[0]
    assert r["state"] == "error" and r["remaining"] == 3.0


def test_pick_key_rules(con, monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN_POOL", f"{A1},{A2}")
    now = keys._now()
    keys.save_status(con, keys.KeyStatus("apify_api_ZoxD", "apify", "usable", 2.0, 5, "", now))
    keys.save_status(con, keys.KeyStatus("apify_api_Qwer", "apify", "usable", 4.0, 5, "", now))
    assert keys.pick_key(con).key_id == "apify_api_Qwer"                         # most credit first
    jid = con.execute("INSERT INTO jobs (step_id, status, pid) VALUES ('x','running',1)").lastrowid
    con.execute("INSERT INTO key_leases (key_prefix, job_id) VALUES ('apify_api_Qwer', ?)", (jid,))
    assert keys.pick_key(con).key_id == "apify_api_ZoxD"                         # leased key skipped
    keys.save_status(con, keys.KeyStatus("apify_api_ZoxD", "apify", "low", 0.5, 5, "", now))
    assert keys.pick_key(con) is None                                            # below floor / in use
    con.execute("UPDATE key_status SET checked_at='2020-01-01 00:00:00'")
    con.execute("DELETE FROM key_leases")
    assert keys.pick_key(con) is None                                            # stale balance is never trusted


def test_mark_failed_rotation_rules(con):
    keys.save_status(con, keys.KeyStatus("k1", "apify", "usable", 3, 5, "", keys._now()))
    assert keys.mark_failed(con, "k1", "apify", 403) == "dead"
    assert keys.mark_failed(con, "k1", "apify", 432) == "out"
    assert keys.mark_failed(con, "k1", "apify", None, "Free user run limit exceeded") == "out"
    assert keys.mark_failed(con, "k1", "apify", 500) == "error"


def test_demo_mode_makes_no_network_calls(con, monkeypatch):
    def nope(*a, **k):
        raise AssertionError("network used in demo mode")
    monkeypatch.setattr(http, "get_json", nope)
    monkeypatch.setattr(http, "post_json", nope)
    set_setting(con, "demo_mode", "1")
    res = {s.key_id: s.state for s in keys.check_all(con)}
    assert res == {"apify_api_AAAA": "usable", "apify_api_BBBB": "low", "apify_api_CCCC": "dead"}
    assert keys.usable_credit(con) == 4.2


def test_add_keys_backs_up_outside_repo_and_never_echoes(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(paths, "ROOT", repo)
    env = repo / ".env"
    env.write_text(f"APIFY_TOKEN_POOL={A1}\nOTHER=1\n", encoding="utf-8")
    monkeypatch.setenv("APIFY_TOKEN_POOL", A1)
    n, backup = keys.add_keys("apify", [A2, A1, "junk"], env, tmp_path / "backups")
    assert n == 1 and backup.exists() and repo not in backup.parents
    assert A1 in backup.read_text() and A2 not in backup.read_text()             # backup is the OLD file
    assert env.read_text().splitlines()[0] == f"APIFY_TOKEN_POOL={A1},{A2}" and "OTHER=1" in env.read_text()
    with pytest.raises(ValueError):
        keys.add_keys("apify", [A2], env, repo / "inside")                      # backup inside the repo is refused
    with pytest.raises(ValueError):
        keys.add_keys("apify", ["not-a-key"], env, tmp_path / "backups")
