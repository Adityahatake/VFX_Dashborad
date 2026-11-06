"""Paid-step tests: Apify run flow (no relaunch on network errors, re-attach, recovery by INPUT, exactly-once spend), leads_finder and
Sales Navigator, and the pilot rule. Everything runs against FakeApify: no network, no key, no cost."""
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from conftest_steps import CFG, make_ctx, paid_ctx

from core import apify, gate, jobs, keys, paths, people, review, spend
from core.apify_fake import FakeApify
from core.steps import paid

DOMS = ["alpha.de", "beta.com"]


def lead(first, last, title, domain, url=None, country="Germany", **k):
    return {"first_name": first, "last_name": last, "title": title, "organization_primary_domain": domain, "organization_name": domain.split(".")[0].title(),
            "linkedin_url": url if url is not None else f"https://www.linkedin.com/in/{first.lower()}-{last.lower()}", "headline": f"{title}", "city": "Berlin", "country": country, **k}


def leads_actor(inp):
    return [lead("Anna", "Founder", "Founder & CEO", "alpha.de"), lead("Ben", "Creative", "Creative Director", "alpha.de"), lead("Cleo", "Producer", "Executive Producer", "alpha.de"),
            lead("Dan", "Junior", "Junior Designer", "alpha.de"), lead("Eve", "Sales", "Sales Director", "beta.com"), lead("Fox", "Owner", "Owner", "beta.com"),
            lead("Gus", "Mumbai", "CEO", "beta.com", country="India"), lead("Hal", "Nolink", "CTO", "beta.com", url=""), lead("Ivy", "Elsewhere", "CEO", "unapproved.com")]


@pytest.fixture()
def fake(monkeypatch):
    f = FakeApify({paid.LEADS_ACTOR: leads_actor})
    monkeypatch.setattr(apify, "get_client", lambda con, token: f)
    return f


def run(f, con, inp=None, job_id=1, **kw):
    return apify.run_actor(f, con, job_id=job_id, actor=paid.LEADS_ACTOR, inp=inp or {"company_domains": DOMS, "max_result": 50}, key_id="apify_api_TEST",
                           log=kw.pop("log", lambda m: None), sleep=lambda s: None, **kw)


@pytest.fixture()
def con(tmp_path):
    c = make_ctx(tmp_path)[1]
    c.execute("INSERT INTO jobs (id, step_id, status) VALUES (1,'x','running')")
    keys.save_status(c, keys.KeyStatus("apify_api_TEST", "apify", "usable", 4.0, 5, "", keys._now()))
    return c


# ---------------------------------------------------------------- the run flow
def test_run_id_is_saved_before_waiting(con, fake):
    fake.polls_until_done = 2
    seen = []
    orig = fake.get_run

    def spy(run_id):
        seen.append(con.execute("SELECT run_id, status FROM apify_runs").fetchall())
        return orig(run_id)
    fake.get_run = spy
    status, items, r, rec = run(fake, con)
    assert status == "SUCCEEDED" and len(items) == 9 and not rec and fake.start_calls == 1
    assert seen and all(len(s) == 1 and s[0]["run_id"] == r["id"] for s in seen)          # the row existed while we were still polling


def test_network_error_before_the_run_exists_is_not_relaunched(con, fake):
    fake.fail_start = "before"
    with pytest.raises(apify.RunNotFound, match="Nothing was relaunched"):
        run(fake, con)
    assert fake.start_calls == 1 and fake.runs == []
    assert con.execute("SELECT COUNT(*) FROM apify_runs").fetchone()[0] == 0


def test_network_error_after_the_run_was_created_recovers_it_by_input(con, fake):
    fake.fail_start = "after"                                      # the run exists on Apify, but we never saw the response
    logs = []
    status, items, r, rec = run(fake, con, log=logs.append)
    assert rec and status == "SUCCEEDED" and len(items) == 9
    assert fake.start_calls == 1 and len(fake.runs) == 1            # ONE run, never relaunched
    assert con.execute("SELECT run_id FROM apify_runs").fetchone()[0] == r["id"] and any("NOT relaunching" in m for m in logs)


def test_http_500_on_start_is_treated_as_unknown_and_not_retried(con, fake):
    fake.fail_start = 500
    with pytest.raises(apify.RunNotFound):
        run(fake, con)
    assert fake.start_calls == 1


@pytest.mark.parametrize("code,state", [(403, "dead"), (401, "dead"), (432, "out"), (429, "out")])
def test_definitive_rejections_mark_the_key_and_do_not_recover_or_retry(con, fake, code, state):
    fake.fail_start = code
    fake.fail_list_runs = True                                      # would raise if recovery were (wrongly) attempted
    with pytest.raises(apify.ApifyRejected) as e:
        run(fake, con)
    assert e.value.code == code and fake.start_calls == 1
    assert con.execute("SELECT state FROM key_status WHERE key_prefix='apify_api_TEST'").fetchone()[0] == state


def test_bad_input_400_is_refused_without_marking_the_key_dead(con, fake):
    fake.fail_start = 400
    with pytest.raises(apify.ApifyRejected):
        run(fake, con)
    assert con.execute("SELECT state FROM key_status").fetchone()[0] == "error"


def test_lost_contact_while_waiting_then_resume_reattaches_and_never_restarts(con, fake):
    fake.polls_until_done = 1
    fake.fail_get_run = 1
    with pytest.raises(apify.WaitFailed, match="NOT relaunched"):
        run(fake, con)
    assert fake.start_calls == 1 and con.execute("SELECT COUNT(*) FROM apify_runs").fetchone()[0] == 1
    logs = []
    status, items, r, rec = run(fake, con, log=logs.append)         # the resumed job: same job id, same input
    assert status == "SUCCEEDED" and len(items) == 9 and fake.start_calls == 1 and any("re-attaching" in m for m in logs)


def test_download_failure_then_resume_reattaches_and_never_restarts(con, fake):
    fake.fail_items = 1
    with pytest.raises(apify.WaitFailed, match="could not be downloaded"):
        run(fake, con)
    status, items, r, rec = run(fake, con)
    assert len(items) == 9 and fake.start_calls == 1 and len(fake.runs) == 1


def test_recovery_matches_on_input_and_ignores_old_or_other_runs(con, fake):
    other = fake._create(paid.LEADS_ACTOR, {"company_domains": ["other.com"], "max_result": 50})            # a different search on the same key
    old = fake._create(paid.LEADS_ACTOR, {"company_domains": DOMS, "max_result": 50})
    old["startedAt"] = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()                       # same input, but hours ago
    fake.fail_start = "before"
    with pytest.raises(apify.RunNotFound):
        run(fake, con)                                                                                       # neither may be adopted
    fake.fail_start = "after"
    status, items, r, rec = run(fake, con)
    assert rec and r["id"] not in (other["id"], old["id"])


def test_a_consumed_run_is_not_reattached_so_repeated_identical_polls_start_fresh_runs(con, fake):
    _, _, r1, _ = run(fake, con)
    apify.mark_consumed(con, r1["id"])
    _, _, r2, _ = run(fake, con)
    assert r2["id"] != r1["id"] and fake.start_calls == 2


def test_actual_cost_prefers_reported_usage():
    assert apify.actual_cost({"usageTotalUsd": 0.1234}, 40, 0.003) == 0.1234
    assert apify.actual_cost({"usageTotalUsd": None}, 40, 0.003) == 0.12
    assert apify.actual_cost({}, 0, 0, extra=0.5) == 0.5 and apify.actual_cost({}, 10, 0.01, extra=0.5) == 0.6


def test_spend_is_recorded_once_per_run_even_if_the_step_repeats(tmp_path):
    ctx, con, logs, cid = paid_ctx(tmp_path)
    for _ in range(3):
        apify.spend_once(ctx, "run7", source="a", est_max_usd=1, actual_usd=0.5, results=3, key_id="k", note="x")
    row = con.execute("SELECT COUNT(*) AS n, SUM(actual_usd) AS usd FROM spend_ledger").fetchone()
    assert (row["n"], row["usd"]) == (1, 0.5)


# ---------------------------------------------------------------- leads_finder
def approve_companies(con, cid, doms=DOMS):
    for d in doms:
        con.execute("INSERT INTO companies (cycle_id, domain, name, country, evidence_json, decision) VALUES (?,?,?,?,?, 'approved')",
                    (cid, d, d.split(".")[0].title(), "germany/berlin", json.dumps({"score": 1, "ev": [[f"https://{d}/work", "AI-generated spot for client Nike with Midjourney."]]})))


def test_leads_finder_end_to_end(tmp_path, fake):
    ctx, con, logs, cid = paid_ctx(tmp_path)
    approve_companies(con, cid)
    r = paid.LeadsFinder().run(ctx, paid.LeadsParams(max_result=50))
    led = con.execute("SELECT * FROM spend_ledger").fetchall()          # exactly one ledger entry, on the confirmed key, cost = results x price
    assert len(led) == 1 and led[0]["key_prefix"] == "apify_api_TEST" and led[0]["results"] == 9 and led[0]["actual_usd"] == pytest.approx(0.027)
    assert led[0]["est_max_usd"] == pytest.approx(0.15) and "run:run1" in led[0]["note"]
    assert (ctx.pipeline_dir / "pools" / "pool_leads.json").exists() and con.execute("SELECT status FROM apify_runs").fetchone()[0] == "CONSUMED"
    inp = fake.inputs["kv1"]                                            # the run input carried the pipeline's titles and excluded countries
    assert inp["company_domains"] == DOMS and "founder" in inp["contact_job_titles"] and inp["contact_not_location"] == ["india"] and inp["max_result"] == 50
    # alpha -> best 2 of distinct families (CEO + creative); junior/sales/India/no-link/unapproved filtered; beta -> Fox only
    ppl = [json.loads(x["fields_json"]) for x in con.execute("SELECT * FROM people ORDER BY id")]
    assert [(p["name"], p["role"]) for p in ppl] == [("Anna Founder", "P1"), ("Ben Creative", "P2"), ("Fox Owner", "P1")]
    assert all(p["qa_confidence"] == "Medium" and p["contact_or_reference_type"] == "Personal LinkedIn" for p in ppl)
    assert ppl[0]["evidence_source"] == "https://alpha.de/work; https://www.linkedin.com/in/anna-founder" and ppl[0]["ai_evidence"].startswith("AI-generated spot")
    assert r.counts == {"leads": 9, "candidates": 3} and r.actual_cost == pytest.approx(0.027)
    probs = review.draft_problems(CFG, ppl[0])                          # nothing is pre-approved or pre-written for the reviewer
    assert any("why_this_person" in x for x in probs) and any("primary_commercial_problem" in x for x in probs)
    assert con.execute("SELECT COUNT(*) FROM people WHERE decision!='pending'").fetchone()[0] == 0


def test_leads_finder_second_run_uses_the_cache_and_spends_nothing(tmp_path, fake):
    ctx, con, logs, cid = paid_ctx(tmp_path)
    approve_companies(con, cid)
    paid.LeadsFinder().run(ctx, paid.LeadsParams())
    r = paid.LeadsFinder().run(ctx, paid.LeadsParams())
    assert fake.start_calls == 1 and con.execute("SELECT COUNT(*) FROM spend_ledger").fetchone()[0] == 1 and r.actual_cost == 0
    assert con.execute("SELECT COUNT(*) FROM people").fetchone()[0] == 3                              # and no duplicate people rows
    assert any("cached" in m for m in logs)


def test_leads_finder_resume_after_a_lost_download_does_not_pay_twice(tmp_path, fake):
    ctx, con, logs, cid = paid_ctx(tmp_path)
    approve_companies(con, cid)
    fake.fail_items = 1
    with pytest.raises(apify.WaitFailed):
        paid.LeadsFinder().run(ctx, paid.LeadsParams())
    assert con.execute("SELECT COUNT(*) FROM spend_ledger").fetchone()[0] == 0                         # nothing recorded for data we never got
    paid.LeadsFinder().resume(ctx, paid.LeadsParams())
    assert fake.start_calls == 1 and con.execute("SELECT COUNT(*) FROM spend_ledger").fetchone()[0] == 1


def test_leads_finder_network_error_at_start_recovers_and_charges_once(tmp_path, fake):
    ctx, con, logs, cid = paid_ctx(tmp_path)
    approve_companies(con, cid)
    fake.fail_start = "after"
    paid.LeadsFinder().run(ctx, paid.LeadsParams())
    assert fake.start_calls == 1 and len(fake.runs) == 1
    note = con.execute("SELECT note FROM spend_ledger").fetchone()[0]
    assert "recovered" in note and con.execute("SELECT COUNT(*) FROM spend_ledger").fetchone()[0] == 1


def test_leads_finder_partial_run_keeps_results_and_warns(tmp_path, fake):
    ctx, con, logs, cid = paid_ctx(tmp_path)
    approve_companies(con, cid)
    fake.final_status = "ABORTED"
    r = paid.LeadsFinder().run(ctx, paid.LeadsParams())
    assert any("may be partial" in m for m in logs) and r.counts["leads"] == 9
    assert "ABORTED" in con.execute("SELECT note FROM spend_ledger").fetchone()[0]


def test_leads_finder_validation_and_batching(tmp_path, fake):
    ctx, con, logs, cid = paid_ctx(tmp_path)
    with pytest.raises(ValueError, match="approve companies"):
        paid.LeadsFinder().run(ctx, paid.LeadsParams())
    many = [f"co{i}.com" for i in range(55)]
    paid.LeadsFinder().run(ctx, paid.LeadsParams(domains=many, tag="big"))
    assert len(fake.inputs["kv1"]["company_domains"]) == 40 and any("first 40" in m for m in logs)
    with pytest.raises(Exception):
        paid.LeadsParams(max_result=0)
    assert paid.LeadsFinder().estimate_cost(None, paid.LeadsParams(max_result=40)).max_usd == pytest.approx(0.12)


def test_leads_are_filtered_by_config_not_by_hope():
    assert people.lead_problem(CFG, lead("A", "B", "Junior Designer", "x.de")) == "not a decision-owner title"
    assert people.lead_problem(CFG, lead("A", "B", "CEO", "x.de", country="India")) == "excluded country"
    assert people.lead_problem(CFG, lead("A", "B", "CEO", "x.de", city="Mumbai", country="")) == "excluded country"
    assert people.lead_problem(CFG, lead("A", "B", "Former CEO", "x.de")) == "rejected title"
    assert people.lead_problem(CFG, lead("A", "B", "CEO", "x.de", url="https://linkedin.com/company/x")) == "no personal profile URL"
    assert people.lead_problem(CFG, lead("A", "B", "Founder & CEO", "x.de")) == ""
    assert people.role_family(CFG, "Executive Producer") == "production" and people.role_family(CFG, "Head of AI") == "tech"


# ---------------------------------------------------------------- the pilot rule
def test_gate_demands_a_pilot_for_an_actor_never_paid_for(tmp_path, monkeypatch):
    monkeypatch.setenv("LPD_DATA", str(tmp_path))
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "dashboard.sqlite")
    from core.db import open_db, set_setting
    c = open_db()
    set_setting(c, "demo_mode", "1")
    keys.check_all(c)
    c.execute("INSERT INTO pipelines (name, yaml_path) VALUES ('vfx_genai','x')")
    cid = spend.create_cycle(c, CFG, 20, 3.0)
    g = gate.evaluate(c, CFG, cid, "leads_finder", {"max_result": 100})
    assert not g.ok and any("pilot first" in b for b in g.blockers)
    assert gate.evaluate(c, CFG, cid, "leads_finder", {"max_result": 25}).ok                         # a 25-record pilot is allowed
    spend.record(c, cycle_id=None, step_id="old", source=paid.LEADS_ACTOR, actual_usd=0.12, results=40, note="imported:abc")      # VFX history counts as a pilot
    assert gate.evaluate(c, CFG, cid, "leads_finder", {"max_result": 100}).ok
    g = gate.evaluate(c, CFG, cid, "salesnav", {"companies": ["A Co"], "limit": 40})                 # salesnav has no history in this DB
    assert any("pilot first" in b for b in g.blockers)
    assert g.estimate.max_usd == pytest.approx(0.9)                                                  # 0.50 + 40 x 0.01
    assert gate.evaluate(c, CFG, cid, "salesnav", {"companies": ["A Co"], "limit": 25}).ok


# ---------------------------------------------------------------- Sales Navigator
def sn_rows(n, company="Alpha", loc="Berlin, Germany", url=True, title="Founder & CEO"):
    return [{"full_name": f"Per{chr(97 + i)} Son{chr(97 + i)}", "title": title, "current_company": company, "location": loc,
             **({"profile_url": f"https://www.linkedin.com/in/ACwAA{chr(97 + i)}{chr(97 + i)}"} if url else {})} for i in range(n)]


class SNActor:
    """Scripted Sales Navigator: the search call returns a request_id; poll calls return 'check back' N times, then the rows."""
    def __init__(self, pages, pending=0):
        self.pages, self.pending, self.calls = pages, pending, []

    def __call__(self, inp):
        self.calls.append(inp)
        if "request_id" not in inp:
            return [{"request_id": "REQ1"}]
        if self.pending > 0:
            self.pending -= 1
            return [{"message": "Results are still processing, check back later"}]
        return [{"data": self.pages.get(inp["page"], [])}]


@pytest.fixture()
def sn(monkeypatch):
    actor = SNActor({1: sn_rows(8) + sn_rows(3, company="Alpha Records", loc="Texas, USA") + sn_rows(2, company="Alpha", loc="Sydney, Australia")})
    f = FakeApify({paid.SALESNAV_ACTOR: actor})
    monkeypatch.setattr(apify, "get_client", lambda con, token: f)
    monkeypatch.setattr(paid.time, "sleep", lambda s: None)
    return f, actor


def sn_params(**k):
    return paid.SalesNavParams(**{"companies": ["Alpha"], "locations": {"Alpha": "Germany"}, "limit": 40, "poll_wait_s": 0, **k})


def sn_setup(tmp_path):
    ctx, con, logs, cid = paid_ctx(tmp_path)
    approve_companies(con, cid, ["alpha.de"])
    return ctx, con, logs, cid


def test_salesnav_submits_once_waits_for_free_and_charges_per_fetched_result(tmp_path, sn):
    f, actor = sn
    ctx, con, logs, cid = sn_setup(tmp_path)
    actor.pending = 2
    r = paid.SalesNav().run(ctx, sn_params())
    searches = [c for c in actor.calls if "request_id" not in c]
    polls = [c for c in actor.calls if "request_id" in c]
    assert len(searches) == 1 and len(polls) == 3 and all(c["page"] == 1 for c in polls)             # 2 free empty polls, then data
    led = con.execute("SELECT note, actual_usd, results FROM spend_ledger ORDER BY id").fetchall()
    assert [(x["note"].split(" ", 1)[1], x["actual_usd"], x["results"]) for x in led] == [("search submitted", 0.5, 0), ("page 1", 0.13, 13)]   # $0.01 x 13 rows, empty polls free
    assert r.actual_cost == pytest.approx(0.63)
    st = json.loads((ctx.workdir / "salesnav_sn.json").read_text())
    assert st["request_id"] == "REQ1" and st["key_id"] == "apify_api_TEST" and len(st["pages"]["1"]) == 13


def test_salesnav_keeps_only_target_company_with_matching_location(tmp_path, sn):
    f, actor = sn
    ctx, con, logs, cid = sn_setup(tmp_path)
    r = paid.SalesNav().run(ctx, sn_params())
    assert r.counts["rows"] == 13 and r.counts["matched"] == 8                                       # "Alpha Records" (namesake) and the Sydney people are dropped
    assert any("8 match a target" in m for m in logs)
    ppl = [json.loads(x["fields_json"]) for x in con.execute("SELECT * FROM people")]
    assert len(ppl) == 1 and ppl[0]["company"] == "Alpha" and ppl[0]["contact_or_reference"].startswith("https://www.linkedin.com/in/ACwAA")    # best 1 (same family) of 8


def test_salesnav_never_resubmits_and_never_refetches_a_saved_page(tmp_path, sn):
    f, actor = sn
    ctx, con, logs, cid = sn_setup(tmp_path)
    paid.SalesNav().run(ctx, sn_params())
    calls_after_first = len(actor.calls)
    paid.SalesNav().resume(ctx, sn_params())                          # a rerun / resume with the same tag
    new = actor.calls[calls_after_first:]
    assert all(c.get("page") != 1 for c in new) and not [c for c in new if "request_id" not in c]
    assert sum(1 for c in actor.calls if "request_id" not in c) == 1                                  # the search was submitted exactly once, ever


def test_salesnav_stops_at_the_first_poll_that_returns_data_when_the_limit_is_reached(tmp_path, monkeypatch):
    actor = SNActor({1: sn_rows(40), 2: sn_rows(40)})
    f = FakeApify({paid.SALESNAV_ACTOR: actor})
    monkeypatch.setattr(apify, "get_client", lambda con, token: f)
    ctx, con, logs, cid = sn_setup(tmp_path)
    paid.SalesNav().run(ctx, sn_params(limit=40))
    assert [c["page"] for c in actor.calls if "request_id" in c] == [1]                               # one fetch, then done: never page 2


def test_salesnav_gives_up_after_max_polls_and_charges_only_the_search(tmp_path, monkeypatch):
    actor = SNActor({}, pending=99)
    f = FakeApify({paid.SALESNAV_ACTOR: actor})
    monkeypatch.setattr(apify, "get_client", lambda con, token: f)
    monkeypatch.setattr(paid.time, "sleep", lambda s: None)
    ctx, con, logs, cid = sn_setup(tmp_path)
    r = paid.SalesNav().run(ctx, sn_params(max_wait_polls=3))
    assert len([c for c in actor.calls if "request_id" in c]) == 4 and r.actual_cost == pytest.approx(0.5)      # 1 + 3 waits, all free
    assert (ctx.workdir / "salesnav_sn.json").exists()                                                # request_id is kept: a later resume polls the same search


def test_salesnav_refuses_to_continue_a_search_with_a_different_key(tmp_path, sn):
    f, actor = sn
    ctx, con, logs, cid = sn_setup(tmp_path)
    paid.SalesNav().run(ctx, sn_params())

    @contextmanager
    def other_key(provider):
        yield "apify_api_OTHER", "secret"
    ctx._use_key = other_key
    with pytest.raises(RuntimeError, match="can only be continued with it"):
        paid.SalesNav().run(ctx, sn_params())


def test_salesnav_network_error_on_the_search_recovers_the_request_id_without_a_second_search(tmp_path, sn):
    f, actor = sn
    ctx, con, logs, cid = sn_setup(tmp_path)
    f.fail_start = "after"                                            # the search was accepted (and charged!) but we never saw the response
    paid.SalesNav().run(ctx, sn_params())
    assert len([c for c in actor.calls if "request_id" not in c]) == 1
    assert json.loads((ctx.workdir / "salesnav_sn.json").read_text())["request_id"] == "REQ1"
    assert con.execute("SELECT COUNT(*) FROM spend_ledger WHERE note LIKE '%search submitted%'").fetchone()[0] == 1


def test_salesnav_rows_without_a_profile_url_are_skipped_and_explained(tmp_path, monkeypatch):
    actor = SNActor({1: sn_rows(3, url=False)})
    f = FakeApify({paid.SALESNAV_ACTOR: actor})
    monkeypatch.setattr(apify, "get_client", lambda con, token: f)
    ctx, con, logs, cid = sn_setup(tmp_path)
    r = paid.SalesNav().run(ctx, sn_params())
    assert r.counts["candidates"] == 0 and any("without a profile URL" in m and "confirm the actor's field names" in m for m in logs)


def test_salesnav_limits():
    with pytest.raises(Exception):
        paid.SalesNavParams(companies=[f"c{i}" for i in range(11)])                                   # at most 10 companies per search
    with pytest.raises(Exception):
        paid.SalesNavParams(companies=[])


# ---------------------------------------------------------------- end to end through the gate and a real worker (demo mode)
def test_leads_finder_runs_as_a_real_worker_job_in_demo_mode(tmp_path, monkeypatch):
    from core.db import open_db, set_setting
    monkeypatch.setenv("LPD_DATA", str(tmp_path))
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "dashboard.sqlite")
    c = open_db()
    set_setting(c, "demo_mode", "1")
    keys.check_all(c)
    c.execute("INSERT INTO pipelines (name, yaml_path) VALUES ('vfx_genai','x')")
    cid = spend.create_cycle(c, CFG, 20, 3.0)
    approve_companies(c, cid, ["kinetic-frames.de", "other-studio.com"])
    p = {"tag": "demo", "max_result": 20}
    g = gate.evaluate(c, CFG, cid, "leads_finder", p)
    assert g.ok and g.estimate.max_usd == pytest.approx(0.06) and g.key_id == "apify_api_AAAA"
    jid = gate.confirm_and_start(c, CFG, cid, "leads_finder", p, g.estimate.max_usd, g.key_id)
    t0 = time.time()
    while jobs.get_job(c, jid)["status"] not in ("done", "failed") and time.time() - t0 < 45:
        time.sleep(0.3)
    j = jobs.get_job(c, jid)
    try:
        assert j["status"] == "done", jobs.tail_log(jid)
        led = c.execute("SELECT * FROM spend_ledger WHERE cycle_id=?", (cid,)).fetchall()
        assert len(led) == 1 and led[0]["key_prefix"] == "apify_api_AAAA" and led[0]["actual_usd"] == pytest.approx(led[0]["results"] * 0.003)
        assert c.execute("SELECT COUNT(*) FROM people WHERE cycle_id=?", (cid,)).fetchone()[0] >= 1
        assert c.execute("SELECT COUNT(*) FROM key_leases").fetchone()[0] == 0
        assert (paths.DATA_DIR / "cycles" / str(cid) / "pool_demo.json").exists()                          # demo leads stay in the throwaway cycle folder ...
        assert not list((paths.DATA_DIR / "vfx_genai" / "pools").glob("pool_*.json")) if (paths.DATA_DIR / "vfx_genai" / "pools").exists() else True   # ... never in the shared pools
    finally:
        if j["pid"] not in (os.getpid(), 1) and jobs.pid_alive(j["pid"]):
            jobs.kill_tree(j["pid"])
