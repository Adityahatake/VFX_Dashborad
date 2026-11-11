"""Unified key management: Groq checks, low-credit warnings, safe add / replace / remove, and the API never echoing a secret."""
import os
import urllib.error

import pytest
from fastapi.testclient import TestClient

from core import http, keys, paths
from core.db import open_db, set_setting

A1 = "apify_api_" + "ZoxD1234567890"
T1 = "tvly-" + "dev-abcdef1234567890"
T2 = "tvly-" + "dev-zyxwvu0987654321"
G1 = "gsk_" + "Abcd1234567890xyz"
G2 = "gsk_" + "Wxyz0987654321abc"


def http_error(code):
    return urllib.error.HTTPError("u", code, "x", {}, None)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(paths, "ROOT", repo)
    monkeypatch.setenv("LPD_ENV_BACKUP_DIR", str(tmp_path / "backups"))
    for v in ("APIFY_TOKEN_POOL", "TAVILY_API_KEYS", "GROQ_API_KEYS"):
        monkeypatch.setenv(v, "")
    (repo / ".env").write_text(f"APIFY_TOKEN_POOL={A1}\nTAVILY_API_KEYS={T1}\nOTHER=1\n", encoding="utf-8")
    monkeypatch.setenv("APIFY_TOKEN_POOL", A1)
    monkeypatch.setenv("TAVILY_API_KEYS", T1)
    return repo, open_db(tmp_path / "t.sqlite")


def fake_net(monkeypatch, groq_headers=None, groq_code=None, tavily_left=(1000, 990)):
    def rjh(url, key=None, body=None, timeout=40):
        if groq_code:
            raise http_error(groq_code)
        return {"data": []}, dict(groq_headers or {})
    monkeypatch.setattr(http, "request_json_headers", rjh)

    def gj(url, key=None, timeout=40):
        if "tavily" in url:
            return {"account": {"plan_limit": tavily_left[0], "plan_usage": tavily_left[1]}}
        return {"data": {"limits": {"maxMonthlyUsageUsd": 5}, "current": {"monthlyUsageUsd": 1}, "monthlyUsageCycle": {"endAt": ""}}}
    monkeypatch.setattr(http, "get_json", gj)


# ------------------------------------------------------------------ Groq
def test_groq_key_id_is_short():
    assert keys.key_id(G1) == "gsk_Abcd" and G1 not in keys.key_id(G1)


def test_groq_check_reads_the_quota_headers(monkeypatch):
    fake_net(monkeypatch, {"x-ratelimit-remaining-requests": "13", "x-ratelimit-limit-requests": "14400", "x-ratelimit-reset-requests": "2m"})
    s = keys.check_groq(G1)
    assert (s.state, s.remaining, s.cap, s.resets) == ("usable", 13.0, 14400.0, "2m")


def test_groq_without_headers_is_valid_but_quota_unknown(monkeypatch):
    fake_net(monkeypatch, {})
    s = keys.check_groq(G1)
    assert s.state == "usable" and s.remaining is None


@pytest.mark.parametrize("code,state", [(401, "dead"), (403, "dead"), (429, "out"), (500, "error")])
def test_groq_error_states(monkeypatch, code, state):
    fake_net(monkeypatch, groq_code=code)
    assert keys.check_groq(G1).state == state


def test_groq_live_probe_is_opt_in(monkeypatch):
    calls = []

    def rjh(url, key=None, body=None, timeout=40):
        calls.append((url, body))
        return {}, {"x-ratelimit-remaining-requests": "99"}
    monkeypatch.setattr(http, "request_json_headers", rjh)
    keys.check_groq(G1)
    assert [c[1] for c in calls] == [None]                                   # free GET only
    calls.clear()
    keys.check_groq(G1, live_probe=True)
    assert calls[1][1]["max_tokens"] == 1                                    # one tiny completion, only when asked


def test_record_groq_headers_updates_the_status(env):
    _, con = env
    keys.record_groq_headers(con, "gsk_Abcd", {"X-RateLimit-Remaining-Requests": "7", "X-RateLimit-Limit-Requests": "1000"})
    r = keys.statuses(con, "groq")[0]
    assert (r["remaining"], r["cap"], r["state"]) == (7, 1000, "usable")


# ------------------------------------------------------------------ warnings
def test_low_credit_warnings_use_the_threshold(env, monkeypatch):
    _, con = env
    monkeypatch.setenv("GROQ_API_KEYS", G1)
    fake_net(monkeypatch, {"x-ratelimit-remaining-requests": "5"}, tavily_left=(1000, 990))     # 10 Tavily credits, 5 Groq requests
    keys.check_all(con)
    w = {(x["provider"], x["level"]) : x["message"] for x in keys.warnings(con)}
    assert "fewer than 20 credits" in w[("tavily", "warning")]
    assert "fewer than 20 requests today" in w[("groq", "warning")]
    set_setting(con, "low_credit_threshold", "5")
    w = {(x["provider"], x["level"]) for x in keys.warnings(con)}
    assert ("tavily", "warning") not in w and ("groq", "warning") not in w


def test_warnings_flag_missing_dead_and_unchecked_keys(env, monkeypatch):
    _, con = env
    w = keys.warnings(con)
    assert any(x["provider"] == "groq" and "No Groq keys" in x["message"] for x in w)
    assert any(x["provider"] == "tavily" and "never checked" in x["message"] for x in w)
    monkeypatch.setattr(http, "get_json", lambda *a, **k: (_ for _ in ()).throw(http_error(401)))
    keys.check_all(con)
    assert any(x["provider"] == "tavily" and x["level"] == "error" for x in keys.warnings(con))


# ------------------------------------------------------------------ add / replace / remove
def test_remove_key_backs_up_and_touches_only_that_key(env):
    repo, con = env
    keys.add_keys("tavily", [T2])
    backup = keys.remove_key(con, "tavily", keys.key_id(T1))
    text = (repo / ".env").read_text(encoding="utf-8")
    assert T1 not in text and T2 in text and A1 in text and "OTHER=1" in text
    assert T1 in backup.read_text(encoding="utf-8") and repo not in backup.parents
    assert os.environ["TAVILY_API_KEYS"] == T2


def test_remove_refuses_unknown_or_leased_keys(env):
    repo, con = env
    before = (repo / ".env").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="found 0"):
        keys.remove_key(con, "tavily", "tvly-nothere1")
    con.execute("INSERT INTO jobs (step_id, status) VALUES ('x','running')")
    con.execute("INSERT INTO key_leases (key_prefix, job_id) VALUES (?, 1)", (keys.key_id(T1),))
    with pytest.raises(ValueError, match="in use"):
        keys.remove_key(con, "tavily", keys.key_id(T1))
    assert (repo / ".env").read_text(encoding="utf-8") == before


def test_replace_adds_the_new_key_before_removing_the_old(env):
    repo, con = env
    with pytest.raises(ValueError, match="must start with"):
        keys.replace_key(con, "tavily", keys.key_id(T1), G1)
    keys.replace_key(con, "tavily", keys.key_id(T1), T2)
    text = (repo / ".env").read_text(encoding="utf-8")
    assert T2 in text and T1 not in text


# ------------------------------------------------------------------ API
@pytest.fixture()
def api(env, monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "t.sqlite")
    monkeypatch.setattr(paths, "load_env", lambda *a, **k: None)
    fake_net(monkeypatch, {"x-ratelimit-remaining-requests": "500", "x-ratelimit-limit-requests": "1000"})
    from api import main
    with TestClient(main.app) as c:
        yield c


def test_api_lists_all_three_providers(api):
    d = api.get("/api/keys").json()["providers"]
    assert set(d) == {"apify", "tavily", "groq"}
    assert d["tavily"]["keys"][0]["state"] == "unchecked" and d["groq"]["configured"] == 0


def test_api_add_replace_remove_never_echoes_secrets(api, env):
    repo, _ = env
    r = api.post("/api/keys/groq", json={"keys": [G1]})
    assert r.status_code == 200 and r.json()["added"] == 1 and G1 not in r.text
    g = r.json()["providers"]["groq"]
    assert g["keys"][0]["key_prefix"] == "gsk_Abcd" and g["keys"][0]["remaining"] == 500
    r = api.put("/api/keys/groq/gsk_Abcd", json={"key": G2})
    assert r.status_code == 200 and G2 not in r.text and G1 not in (repo / ".env").read_text(encoding="utf-8")
    r = api.delete("/api/keys/groq/gsk_Wxyz")
    assert r.status_code == 200 and r.json()["providers"]["groq"]["configured"] == 0
    assert api.post("/api/keys/groq", json={"keys": ["not-a-key"]}).status_code == 422
    assert api.delete("/api/keys/nope/x").status_code == 404


def test_api_check_and_threshold(api):
    r = api.post("/api/keys/check", json={})
    assert r.json()["providers"]["tavily"]["keys"][0]["state"] == "usable"
    assert api.put("/api/settings/low-credit", json={"threshold": 50}).json()["low_credit_threshold"] == 50
    assert api.get("/api/keys").json()["low_credit_threshold"] == 50
