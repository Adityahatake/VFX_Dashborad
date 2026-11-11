"""Analytics come only from stored rows: counts, time buckets, date filters, run performance and spend by provider."""
import json

import pytest
from fastapi.testclient import TestClient

from core import analytics, paths
from core.db import open_db


@pytest.fixture()
def con(tmp_path):
    c = open_db(tmp_path / "t.sqlite")
    c.execute("INSERT INTO pipelines (name, yaml_path) VALUES ('vfx_genai','x')")
    c.execute("INSERT INTO cycles (id, pipeline, goal_rows, cap_usd, started_at) VALUES (1,'vfx_genai',10,3,'2026-11-01 09:00:00')")
    rows = [("a.com", "approved", "2026-11-01 10:00:00"), ("b.com", "rejected", "2026-11-01 11:00:00"), ("c.com", "approved", "2026-11-03 10:00:00"),
            ("d.com", "pending", "2026-11-10 10:00:00")]
    for d, dec, ts in rows:
        c.execute("INSERT INTO companies (cycle_id, domain, decision, created_at) VALUES (1,?,?,?)", (d, dec, ts))
    for i, (dec, ts) in enumerate([("approved", "2026-11-01 12:00:00"), ("pending", "2026-11-03 12:00:00"), ("approved", "2026-11-03 13:00:00")]):
        c.execute("INSERT INTO people (cycle_id, domain, fields_json, decision, created_at) VALUES (1,'a.com','{}',?,?)", (dec, ts))
    for kind, usd, ts in [("apify", 0.10, "2026-11-01 12:00:00"), ("tavily", 0.016, "2026-11-01 12:00:00"), ("apify", 0.05, "2026-11-03 12:00:00")]:
        c.execute("INSERT INTO spend_ledger (ts, cycle_id, step_id, source, kind, actual_usd, results) VALUES (?,1,'s','x',?,?,1)", (ts, kind, usd))
    for jid, st, s, f, counts in [(1, "done", "2026-11-01 10:00:00", "2026-11-01 10:30:00", {"companies_found": 9, "people_valid": 2}),
                                  (2, "failed", "2026-11-03 10:00:00", "2026-11-03 10:05:00", {}), (3, "done", "2026-11-03 11:00:00", "2026-11-03 12:00:00", {})]:
        c.execute("INSERT INTO jobs (id, step_id, status, started_at) VALUES (?, 'vfx_pipeline', ?, ?)", (jid, st, s))
        c.execute("INSERT INTO pipeline_runs (job_id, cycle_id, status, started_at, finished_at, counts_json, errors_json) VALUES (?,1,?,?,?,?,?)",
                  (jid, st, s, f, json.dumps(counts), json.dumps(["x"] if st == "failed" else [])))
    return c


def test_totals_and_conversion(con):
    s = analytics.summary(con)
    t = s["totals"]
    assert (t["companies"], t["companies_qualified"], t["people"], t["people_approved"]) == (4, 2, 3, 2)
    assert t["runs"] == 3 and t["runs_by_status"] == {"done": 2, "failed": 1}
    assert t["avg_run_minutes"] == pytest.approx(45.0)                       # done runs only: 30 and 60 minutes
    assert t["people_per_qualified_company"] == 1.5 and t["spend_usd"] == pytest.approx(0.166)
    assert s["spend_by_kind"]["tavily"]["usd"] == pytest.approx(0.016)
    assert s["runs"][0]["companies_found"] == 9 and s["runs"][1]["errors"] == 1


def test_daily_series_and_date_filter(con):
    s = analytics.summary(con, "2026-11-01", "2026-11-03", "day")
    comp = {r["bucket"]: r for r in s["series"]["companies"]}
    assert comp["2026-11-01"]["n"] == 2 and comp["2026-11-01"]["approved"] == 1 and comp["2026-11-01"]["rejected"] == 1
    assert "2026-11-10" not in comp and s["totals"]["companies"] == 3                      # the 'to' day is inclusive, later days are out
    spend = {r["bucket"]: r for r in s["series"]["spend"]}
    assert spend["2026-11-01"] == {"bucket": "2026-11-01", "apify": 0.1, "tavily": 0.016}
    runs = {r["bucket"]: r for r in s["series"]["runs"]}
    assert runs["2026-11-03"] == {"bucket": "2026-11-03", "done": 1, "failed": 1, "other": 0}


def test_weekly_and_monthly_buckets(con):
    assert [r["bucket"] for r in analytics.summary(con, bucket="month")["series"]["companies"]] == ["2026-11"]
    weeks = [r["bucket"] for r in analytics.summary(con, bucket="week")["series"]["companies"]]
    assert weeks == ["2026-W43", "2026-W44", "2026-W45"]                   # weeks start on Monday; 1 Nov 2026 is a Sunday
    with pytest.raises(ValueError):
        analytics.summary(con, bucket="year")


def test_empty_database_has_no_invented_numbers(tmp_path):
    s = analytics.summary(open_db(tmp_path / "e.sqlite"))
    assert s["totals"]["companies"] == 0 and s["totals"]["avg_run_minutes"] is None and s["totals"]["people_per_qualified_company"] is None
    assert all(v == [] for v in s["series"].values())


def test_new_rows_get_a_created_time(con):
    i = con.execute("INSERT INTO companies (cycle_id, domain) VALUES (1, 'new.com')").lastrowid
    assert con.execute("SELECT created_at FROM companies WHERE id=?", (i,)).fetchone()[0]


def test_api_validates_the_filter(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "dashboard.sqlite")
    monkeypatch.setattr(paths, "load_env", lambda *a, **k: None)
    from api import main
    with TestClient(main.app) as c:
        assert c.get("/api/analytics?from=2026-11-01&to=2026-11-30&bucket=week").status_code == 200
        assert c.get("/api/analytics?from=yesterday").status_code == 422
        assert c.get("/api/analytics?bucket=year").status_code == 422
