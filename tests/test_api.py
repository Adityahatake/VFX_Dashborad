"""The FastAPI layer: it must translate core/ faithfully and keep every safety property (gate, no secrets, VFX-only steps)."""
import json

import pytest
from fastapi.testclient import TestClient

from core import jobs, keys, paths, spend
from core.db import open_db, set_setting


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LPD_DATA", str(tmp_path))
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "dashboard.sqlite")
    monkeypatch.setattr(paths, "load_env", lambda *a, **k: None)          # never load the real .env in tests
    con = open_db()
    set_setting(con, "demo_mode", "1")
    keys.check_all(con)
    started = []
    monkeypatch.setattr(jobs, "start_job", lambda con, sid, params=None, cid=None, **kw: started.append((sid, params, cid, kw)) or len(started))
    from api import main
    with TestClient(main.app) as c:
        c.started, c.con = started, con
        yield c


def test_health_reports_the_single_vfx_pipeline(client):
    h = client.get("/api/health").json()
    assert h["pipeline"] == "vfx_genai" and h["demo"] is True and h["active_cycle"] is None


def test_keys_endpoint_never_returns_a_secret(client):
    r = client.post("/api/keys/check")
    assert r.status_code == 200
    assert "not_a_real_key" not in r.text                                  # the demo keys' full strings
    ids = {k["key_prefix"] for k in r.json()["providers"]["apify"]["keys"]}
    assert "apify_api_AAAA" in ids


def test_cycle_lifecycle(client):
    assert client.get("/api/cycle").json()["active"] is None
    r = client.post("/api/cycle", json={"goal_rows": 100, "cap_usd": 10})
    assert r.status_code == 200 and r.json()["cap_usd"] == 3.0             # clamped to the hard maximum
    assert client.post("/api/cycle", json={"goal_rows": 5}).status_code == 409
    assert client.get("/api/cycle").json()["active"]["goal_rows"] == 100
    assert client.post("/api/cycle/end").status_code == 200
    assert client.get("/api/cycle").json()["active"] is None


def test_steps_are_vfx_only_in_pipeline_order_without_test_helpers(client):
    ids = [s["id"] for s in client.get("/api/steps").json()]
    assert "demo_slow" not in ids and "demo_paid" not in ids
    assert ids.index("harvest_revenuebase") < ids.index("deep_crawl") < ids.index("leads_finder") < ids.index("append_sheet")


def test_free_step_starts_directly_and_bad_params_are_rejected(client):
    r = client.post("/api/jobs", json={"step_id": "deep_crawl", "params": {"tag": "rb", "limit": 5}})
    assert r.status_code == 200 and client.started[0][0] == "deep_crawl"
    assert client.post("/api/jobs", json={"step_id": "deep_crawl", "params": {"nope": 1}}).status_code == 422
    assert client.post("/api/jobs", json={"step_id": "demo_slow"}).status_code == 404


def test_paid_step_needs_the_gate_and_the_confirmed_cost(client):
    client.post("/api/cycle", json={"goal_rows": 10, "cap_usd": 3})
    p = {"max_result": 25}
    assert client.post("/api/jobs", json={"step_id": "leads_finder", "params": p}).status_code == 400       # no confirmation
    g = client.post("/api/steps/leads_finder/gate", json={"params": p}).json()
    assert g["kind"] == "paid" and g["estimate"]["max_usd"] == pytest.approx(0.075)
    r = client.post("/api/jobs", json={"step_id": "leads_finder", "params": p, "confirmed_max_usd": 0.01, "confirmed_key_id": g["key_id"]})
    assert r.status_code == 409 and "changed since you confirmed" in json.dumps(r.json())
    assert client.started == []                                            # nothing paid was started


def test_paid_gate_without_a_cycle_is_blocked(client):
    g = client.post("/api/steps/leads_finder/gate", json={"params": {"max_result": 25}}).json()
    assert g["ok"] is False and "no active cycle" in g["blockers"][0]


def test_records_and_jobs_endpoints(client):
    con = client.con
    from api import main
    cid = spend.create_cycle(con, main.cfg(), 5, 1.0)
    con.execute("INSERT INTO companies (cycle_id, domain, name, evidence_json) VALUES (?,?,?,?)", (cid, "studio.com", "Studio", json.dumps({"score": 2, "ev": [["u", "s"]]})))
    con.execute("INSERT INTO people (cycle_id, domain, fields_json) VALUES (?,?,?)", (cid, "studio.com", json.dumps({"name": "A B"})))
    con.execute("INSERT INTO jobs (step_id, status, params_json) VALUES ('deep_crawl','done','{}')")
    assert client.get("/api/companies").json()[0]["score"] == 2
    assert client.get("/api/people").json()[0]["fields"]["name"] == "A B"
    j = client.get("/api/jobs").json()[0]
    assert j["step_id"] == "deep_crawl" and "log_path" not in j and "pid" not in j
    assert client.get("/api/jobs/999").status_code == 404
    assert client.post(f"/api/jobs/{j['id']}/cancel").status_code == 409  # not running


def test_events_stream_sends_a_snapshot(client):
    with client.stream("GET", "/api/events?once=1") as r:
        body = "".join(r.iter_text())
    assert body.startswith("event: snapshot") and '"jobs"' in body


def test_pipeline_endpoints(client):
    from api import main
    st = client.get("/api/pipeline").json()
    assert st["stages"][0] == "Initializing pipeline" and st["live_job"] is None and st["defaults"]["tavily_queries"] == 20
    client.post("/api/cycle", json={"goal_rows": 10, "cap_usd": 3})
    g = client.post("/api/steps/vfx_pipeline/gate", json={"params": {}}).json()
    assert g["kind"] == "paid" and g["estimate"]["max_usd"] == pytest.approx(20 * 0.008 + 50 * 0.003) and g["ok"]
    assert client.post("/api/pipeline/run", json={"params": {}, "confirmed_max_usd": 0.01}).status_code == 409     # not what the gate showed
    r = client.post("/api/pipeline/run", json={"params": {}, "confirmed_max_usd": g["estimate"]["max_usd"]})
    assert r.status_code == 200
    jid = client.con.execute("INSERT INTO jobs (step_id, status) VALUES ('vfx_pipeline','running')").lastrowid
    assert client.post("/api/pipeline/run", json={"params": {}, "confirmed_max_usd": 0.31}).status_code == 409    # one run at a time
    client.con.execute("INSERT INTO pipeline_runs (job_id, cycle_id, counts_json) VALUES (?, 1, ?)", (jid, json.dumps({"companies_found": 4})))
    assert client.get("/api/pipeline/runs").json()[0]["counts"]["companies_found"] == 4
    assert client.get(f"/api/jobs/{jid}/progress").json() == {}
