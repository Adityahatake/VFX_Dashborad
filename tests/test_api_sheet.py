"""Sheet & append over the API: show before write is enforced by the server (dry run of exactly this CSV, typed count, gated job)."""
import json

import pytest
from fastapi.testclient import TestClient

from core import append as ap, jobs, keys, paths, spend
from core.db import open_db, set_setting

PERSON = {"name": "Nora Neu", "company": "Neu Studio", "title": "Founder", "role": "P1", "country": "Germany", "primary_classification": "Production studio",
          "ai_adoption_stage": "Active Production", "ai_evidence": "Runway spot for Nike.", "primary_commercial_problem": "Scaling AI spots.",
          "why_this_person": "Founder; owns AI production decisions.", "qualification_decision": "PASS-B", "qa_decision": "PASS", "qa_confidence": "Medium",
          "outreach_readiness": "Ready", "contact_or_reference": "https://www.linkedin.com/in/nora-neu", "contact_or_reference_type": "Personal LinkedIn",
          "evidence_source": "https://neustudio.de/work"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LPD_DATA", str(tmp_path))
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "dashboard.sqlite")
    monkeypatch.setattr(paths, "load_env", lambda *a, **k: None)
    con = open_db()
    set_setting(con, "demo_mode", "1")                        # the in-memory demo sheet: no Google calls
    started = []
    monkeypatch.setattr(jobs, "start_job", lambda con, sid, params=None, cid=None, **kw: started.append((sid, params)) or 99)
    from api import main
    with TestClient(main.app) as c:
        c.con, c.started = con, started
        c.post("/api/cycle", json={"goal_rows": 5, "cap_usd": 1})
        yield c


def approve(con, **over):
    cid = con.execute("SELECT id FROM cycles WHERE status='active'").fetchone()[0]
    con.execute("INSERT INTO people (cycle_id, domain, fields_json, decision) VALUES (?,?,?, 'approved')", (cid, "neustudio.de", json.dumps({**PERSON, **over})))
    return cid


def test_append_needs_csv_then_a_current_dry_run_then_the_typed_count(client):
    approve(client.con)
    assert client.post("/api/sheet/append", json={"typed_rows": 1}).status_code == 409                   # no CSV yet
    assert client.post("/api/sheet/csv").json() == {"rows": 1}
    r = client.post("/api/sheet/append", json={"typed_rows": 1})
    assert r.status_code == 409 and "dry run" in r.text                                                  # show before write
    d = client.post("/api/sheet/dry-run").json()
    assert d["add"] == 1 and d["stop"] is None and d["current"]
    assert client.post("/api/sheet/append", json={"typed_rows": 2}).status_code == 422                   # wrong count typed
    r = client.post("/api/sheet/append", json={"typed_rows": 1})
    assert r.status_code == 200 and client.started == [("append_sheet", {"csv_name": "review.csv", "tag": "c1", "expected_rows": 1})]


def test_a_changed_csv_needs_a_new_dry_run(client):
    approve(client.con)
    client.post("/api/sheet/csv")
    client.post("/api/sheet/dry-run")
    approve(client.con, name="Otto Other", contact_or_reference="https://www.linkedin.com/in/otto")
    client.post("/api/sheet/csv")                                                                        # rebuilt: 2 rows now
    assert client.get("/api/sheet").json()["dry_run"] is None
    assert client.post("/api/sheet/append", json={"typed_rows": 2}).status_code == 409


def test_dry_run_reports_skips(client):
    approve(client.con, name="Anna Beispiel", company="Neu Film", contact_or_reference="https://linkedin.com/in/anna-beispiel")   # already on the demo sheet
    client.post("/api/sheet/csv")
    d = client.post("/api/sheet/dry-run").json()
    assert d["add"] == 0 and "already" in d["skipped"][0]["why"]


def test_read_only_target_blocks_the_append(client):
    approve(client.con)
    client.post("/api/sheet/csv")
    client.post("/api/sheet/dry-run")
    set_setting(client.con, "demo_mode", "0")
    set_setting(client.con, "sheet_target", "real_readonly")
    r = client.post("/api/sheet/append", json={"typed_rows": 1})
    assert r.status_code == 409 and "READ-ONLY" in r.text and client.started == []


def test_real_target_needs_the_words(client):
    assert client.put("/api/sheet/target", json={"target": "real"}).status_code == 422
    assert client.put("/api/sheet/target", json={"target": "real", "confirm": "REAL SHEET"}).status_code == 200
    assert client.put("/api/sheet/target", json={"target": "sandbox"}).json() == {"target": "sandbox"}
    assert client.put("/api/sheet/target", json={"target": "prod"}).status_code == 422


def test_baseline_and_progress(client):
    b = client.post("/api/sheet/baseline").json()
    assert b["data_rows"] == 4
    st = client.get("/api/sheet?progress=1").json()
    assert st["progress"]["baseline"] == 4 and st["progress"]["ours"] == 0
    client.con.execute("INSERT INTO appended_rows (cycle_id, tab, row_number) VALUES (1, 'Linkedin', 6)")
    assert client.post("/api/sheet/baseline").status_code == 409                                         # never after appending


def test_recovery_logs_landed_rows_and_unblocks(client, monkeypatch):
    cid = approve(client.con)
    wd = jobs.workdir_for(cid, 0)
    wd.mkdir(parents=True, exist_ok=True)
    from core import fields as F
    from api import main
    row = F.row_from_fields(main.cfg(), PERSON)
    ap.write_review_csv(wd / "unknown_outcome_c1.csv", main.cfg().output.columns, [row])
    client.con.execute("INSERT INTO stop_events (cycle_id, rule, reason) VALUES (?, 'append_recovery', 'x')", (cid,))
    assert client.post("/api/sheet/csv").status_code == 200
    monkeypatch.setattr(ap, "find_landed", lambda client, cfg, rows: ([(7, rows[0])], []))
    r = client.post("/api/sheet/recover").json()
    assert r["landed"] == [7] and r["missing"] == 0
    assert spend.rows_appended(client.con, cid) == 1 and client.get("/api/sheet").json()["recovery"] is None
    assert client.post("/api/sheet/recover").status_code == 409


def test_settings_and_sources(client):
    s = client.get("/api/settings").json()
    assert s["demo_mode"] is True and "GROQ_API_KEYS" in s["env"]
    client.post("/api/keys/check")
    assert keys.statuses(client.con)
    s = client.put("/api/settings", json={"demo_mode": False, "default_cap_usd": 9}).json()
    assert s["demo_mode"] is False and s["default_cap_usd"] == 3.0 and keys.statuses(client.con) == []   # fake balances cleared; cap clamped
    assert client.put("/api/settings", json={"llm_prices": {"m": {"in": 1}}}).status_code == 422
    src = client.get("/api/sources").json()
    assert src["yield"] == [] and any("RevenueBase" in x["source"] for x in src["exhausted"])
    assert client.get("/api/cycle/report").status_code == 200
