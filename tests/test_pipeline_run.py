"""Stage 1 Tavily discovery, the automatic company checks, and the one-click pipeline end to end. No network, no real keys, no spend:
Tavily, the websites, Apify and the sheet are all fakes."""
import json
import urllib.error

import pytest
from conftest_steps import CFG, paid_ctx

from core import apify, http, keys, paths, qualify, sheets, spend, web
from core.apify_fake import FakeApify
from core.steps import discover, paid, pipeline_run
from core.steps.discover import HarvestTavily, TavilyParams

TV = "tvly-" + "dev-abcdef1234567890"
AP = "apify_api_" + "TEST1234567890"

SITES = {
    "https://good.com": '<a href="/work">Work</a>',
    "https://good.com/work": "<p>Our AI-generated commercial for Nike used Midjourney, a great client campaign. " + "We love film. " * 60 +
                             "We also made a generative AI spot for our client Adidas with Runway.</p>",
    "https://weak.com": '<a href="/work">Work</a>',
    "https://weak.com/work": "<p>Our AI-generated commercial for Nike used Midjourney, a great client campaign.</p>",
    "https://noai.com": "<p>We shoot films for clients.</p>",
}


def result(url, title="Studio"):
    return {"url": url, "title": title, "content": "AI commercial for a client"}


RESULTS = [result("https://good.com/work/nike"), result("https://www.weak.com/"), result("https://noai.com"), result("https://www.adweek.com/story"),
           result("https://studio.in/x"), result("https://dailyvfxnews.com/a"), result("https://good.com/again")]


@pytest.fixture()
def ctx(tmp_path, monkeypatch):
    c, con, logs, cid = paid_ctx(tmp_path, key_id=keys.key_id(TV))
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data")
    monkeypatch.setenv("TAVILY_API_KEYS", TV)
    monkeypatch.setenv("APIFY_TOKEN_POOL", AP)
    con.execute("UPDATE jobs SET est_max_usd=1.0, step_id='vfx_pipeline' WHERE id=1")
    return c, con, logs, cid


def fake_tavily(monkeypatch, results=RESULTS, fail_on=None, calls=None):
    def post(url, body, key=None, timeout=60):
        assert "tavily" in url
        if calls is not None:
            calls.append(body["query"])
        if fail_on and len(calls or []) >= fail_on[0]:
            raise urllib.error.HTTPError(url, fail_on[1], "x", {}, None)
        return {"results": results}
    monkeypatch.setattr(http, "post_json", post)


def fake_web(monkeypatch):
    monkeypatch.setattr(web, "fetch", lambda u, timeout=12: (u, SITES.get(u.rstrip("/"), SITES.get(u, ""))))


# ------------------------------------------------------------------ discovery
def test_candidates_are_company_sites_only():
    out, why = discover.pick_candidates(CFG, RESULTS, {"noai"}, set(), 0)
    assert set(out) == {"good.com", "weak.com"}
    assert why["press / platform / social site"] == 1 and why["excluded country"] == 1 and why["looks like a publication"] == 1
    assert why["duplicate in this run"] == 1 and why["already known (sheet, crawled, verified or rejected)"] == 1


def test_tavily_step_records_one_credit_per_search_and_resumes(ctx, monkeypatch):
    c, con, logs, cid = ctx
    calls = []
    fake_tavily(monkeypatch, calls=calls)
    p = TavilyParams(tag="tv", queries=["a", "b", "c"], max_queries=2)
    r = HarvestTavily().run(c, p)
    assert r.counts["searches"] == 2 and calls == ["a", "b"]
    assert set(json.loads((c.workdir / "tv_domains.json").read_text())) == {"good.com", "weak.com", "noai.com"}
    led = con.execute("SELECT kind, source, actual_usd FROM spend_ledger").fetchall()
    assert [(x["kind"], x["source"]) for x in led] == [("tavily", "tavily~search")] * 2 and sum(x["actual_usd"] for x in led) == pytest.approx(0.016)
    HarvestTavily().run(c, TavilyParams(tag="tv", queries=["a", "b", "c"], max_queries=3))
    assert calls == ["a", "b", "c"]                                          # finished searches are never repeated or paid again


def test_tavily_key_out_of_credit_stops_and_is_marked(ctx, monkeypatch):
    c, con, logs, cid = ctx
    keys.save_status(con, keys.KeyStatus(keys.key_id(TV), "tavily", "usable", 50, 1000, "", keys._now()))
    calls = []
    fake_tavily(monkeypatch, calls=calls, fail_on=(2, 432))
    r = HarvestTavily().run(c, TavilyParams(tag="tv", queries=["a", "b", "c"]))
    assert r.status == "partial" and r.counts["searches"] == 1 and calls == ["a", "b"]
    assert keys.statuses(con, "tavily")[0]["state"] == "out"


def test_tavily_estimate_and_pilot():
    s, p = HarvestTavily(), TavilyParams(max_queries=30)
    assert s.estimate_cost(None, p).max_usd == pytest.approx(0.16) and s.planned_records(p) == 20       # only 20 default queries exist
    assert s.pilot_source == "tavily~search"


# ------------------------------------------------------------------ automatic company checks
@pytest.mark.parametrize("domain,name,country,score,expect", [
    ("good.com", "Good", "", 2, ("approved", "AUTO_PASS")),
    ("weak.com", "Weak", "", 1, ("look", "AUTO_HOLD:evidence score 1 < 2")),
    ("adweek.com", "Adweek", "", 5, ("rejected", "AUTO_REJECT:press / platform / social site")),
    ("wppstudio.com", "WPP Studio", "", 5, ("rejected", "AUTO_REJECT:rejected company name")),
    ("studio.in", "Studio", "", 5, ("rejected", "AUTO_REJECT:excluded country")),
])
def test_company_checks(domain, name, country, score, expect):
    assert qualify.check(CFG, domain, name, country, {"score": score}, 2) == expect


def test_qualify_never_overrides_a_human_decision(ctx):
    c, con, logs, cid = ctx
    for d, dec in (("a.com", "pending"), ("b.com", "rejected")):
        con.execute("INSERT INTO companies (cycle_id, domain, name, source, evidence_json, decision) VALUES (?,?,?,?,?,?)",
                    (cid, d, d, "r1:q0", json.dumps({"score": 5}), dec))
    assert qualify.qualify_cycle(con, CFG, cid, 2, "r1:") == {"approved": 1, "look": 0, "rejected": 0}
    assert con.execute("SELECT decision FROM companies WHERE domain='b.com'").fetchone()[0] == "rejected"


# ------------------------------------------------------------------ the whole pipeline
LEADS_INPUTS = []


def leads(inp):
    LEADS_INPUTS.append(inp)
    out = []
    for d in inp["company_domains"]:
        out += [{"first_name": "Ann", "last_name": d.split(".")[0].title(), "title": "Founder & CEO", "organization_primary_domain": d,
                 "organization_name": d.split(".")[0].title(), "linkedin_url": f"https://www.linkedin.com/in/ann-{d.split('.')[0]}", "country": "Germany"},
                {"first_name": "Bob", "last_name": "Sales", "title": "Sales Director", "organization_primary_domain": d,
                 "organization_name": d, "linkedin_url": f"https://www.linkedin.com/in/bob-{d.split('.')[0]}", "country": "Germany"}]
    return out[: inp["max_result"]]                                             # like the real actor: never more than max_result


@pytest.fixture()
def pipeline(ctx, monkeypatch):
    c, con, logs, cid = ctx
    fake_tavily(monkeypatch)
    fake_web(monkeypatch)
    LEADS_INPUTS.clear()
    fake = FakeApify({paid.LEADS_ACTOR: leads})
    monkeypatch.setattr(apify, "get_client", lambda con, token: fake)

    def check_all(con, *a, **k):
        keys.save_status(con, keys.KeyStatus(keys.key_id(TV), "tavily", "usable", 900, 1000, "", keys._now()))
        keys.save_status(con, keys.KeyStatus(keys.key_id(AP), "apify", "usable", 4.0, 5, "", keys._now()))
    monkeypatch.setattr(keys, "check_all", check_all)
    c._sheet = sheets.SafeSheet(sheets.FakeSheet({CFG.output.write_tab.name: [list(CFG.output.columns)],
                                                  **{t.name: [["name", "company"]] for t in CFG.output.tabs if not t.write}}), CFG.output.write_tab.name)
    spend.record(con, cycle_id=None, step_id="x", source="tavily~search", kind="tavily", actual_usd=0)           # both sources already piloted
    spend.record(con, cycle_id=None, step_id="x", source=paid.LEADS_ACTOR, actual_usd=0)
    return c, con, logs, cid, fake


def test_pipeline_runs_every_stage_and_saves_people_for_review(pipeline):
    c, con, logs, cid, fake = pipeline
    p = pipeline_run.RunParams(tavily_queries=2, min_evidence_score=2, leads_max_result=20, pool_match=False)
    r = pipeline_run.VfxPipeline().run(c, p)
    prog = json.loads((c.job_dir / "progress.json").read_text())
    assert prog["stage"] == "Pipeline completed" and prog["percent"] == 100.0 and prog["errors"] == []
    k = prog["counts"]
    assert k["companies_found"] == 3 and k["companies_crawled"] == 3 and k["companies_qualified"] == 1 and k["companies_held"] == 1
    assert k["people_found"] == 1 and k["people_valid"] == 1                    # the sales director is filtered by SOP 02 s8 titles
    assert {r["domain"]: r["decision"] for r in con.execute("SELECT domain, decision FROM companies")} == {"good.com": "approved", "weak.com": "look"}
    person = con.execute("SELECT * FROM people").fetchone()
    assert person["decision"] == "pending" and person["domain"] == "good.com"   # waits for a human: nothing goes to the sheet from here
    assert LEADS_INPUTS[0]["company_domains"] == ["good.com"]
    run = con.execute("SELECT * FROM pipeline_runs WHERE job_id=1").fetchone()
    assert run["status"] == "done" and run["spent_usd"] == pytest.approx(prog["api"]["total_usd"]) and prog["api"]["tavily_usd"] == pytest.approx(0.016)
    assert any("== 5/8 Searching for people" in m for m in logs)


def test_pipeline_budget_limits_the_paid_stages(pipeline):
    c, con, logs, cid, fake = pipeline
    con.execute("UPDATE jobs SET est_max_usd=0.02 WHERE id=1")                  # confirmed max: $0.02
    pipeline_run.VfxPipeline().run(c, pipeline_run.RunParams(tavily_queries=5, min_evidence_score=1, leads_max_result=50, pool_match=False))
    assert con.execute("SELECT COUNT(*) FROM spend_ledger WHERE kind='tavily' AND cycle_id=?", (cid,)).fetchone()[0] == 2     # $0.016 of $0.02
    assert LEADS_INPUTS[0]["max_result"] == 1                   # what is left ($0.004) buys one result
    assert spend.cycle_spend(con, cid) <= 0.02 + 1e-9


def test_pipeline_needs_a_tavily_key(pipeline, monkeypatch):
    c, con, logs, cid, fake = pipeline
    monkeypatch.setattr(keys, "check_all", lambda con, *a, **k: None)
    with pytest.raises(pipeline_run.NoKey, match="Tavily"):
        pipeline_run.VfxPipeline().run(c, pipeline_run.RunParams())
    assert con.execute("SELECT status FROM pipeline_runs").fetchone()[0] == "failed"
    assert json.loads((c.job_dir / "progress.json").read_text())["errors"]


def test_pipeline_resume_skips_finished_stages(pipeline, monkeypatch):
    c, con, logs, cid, fake = pipeline
    calls = []
    fake_tavily(monkeypatch, calls=calls)
    c.save_checkpoint({"stage": 3, "ledger_start": 0, "people_start": 0, "snapshot": False})
    pipeline_run.VfxPipeline().run(c, pipeline_run.RunParams(pool_match=False))
    assert calls == []                                                          # no search repeated on resume
    assert json.loads((c.job_dir / "progress.json").read_text())["stage"] == "Pipeline completed"


def test_pipeline_stop_rule_skips_paid_stages(pipeline, monkeypatch):
    c, con, logs, cid, fake = pipeline
    monkeypatch.setattr(spend, "evaluate_stop_rules", lambda *a, **k: [spend.Trip("min_usable_credit", "usable credit under $3")])
    pipeline_run.VfxPipeline().run(c, pipeline_run.RunParams(pool_match=False))
    assert con.execute("SELECT COUNT(*) FROM spend_ledger WHERE cycle_id=?", (cid,)).fetchone()[0] == 0
    assert fake.runs == []
    assert any("stop rule tripped" in w for w in json.loads((c.job_dir / "progress.json").read_text())["warnings"])
