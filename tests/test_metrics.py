"""History / metrics tests: cycle overview numbers, source yield (screened -> hits -> approved -> rows), paid-step cost, LLM-vs-reviewer agreement,
exhausted-source warnings, and the crawl step recording per-source yield."""
import json

import pytest
from conftest_steps import CFG, make_ctx

from core import metrics, spend, web
from core.steps import crawl


@pytest.fixture()
def db(tmp_path):
    ctx, con, logs = make_ctx(tmp_path)
    con.execute("INSERT INTO pipelines (name, yaml_path) VALUES ('vfx_genai','x')")
    return ctx, con


def person(con, cid, name, url, conf, domain, decision="approved", reason=None):
    f = {"name": name, "company": "C", "contact_or_reference": url, "qa_confidence": conf}
    con.execute("INSERT INTO people (cycle_id, domain, fields_json, decision, reason_code) VALUES (?,?,?,?,?)", (cid, domain, json.dumps(f), decision, reason))


def company(con, cid, domain, source, decision="approved", reason=None, llm=None):
    con.execute("INSERT INTO companies (cycle_id, domain, name, source, decision, reason_code, llm_json) VALUES (?,?,?,?,?,?,?)", (cid, domain, domain, source, decision, reason, json.dumps(llm) if llm else None))


def appended(con, cid, n, url):
    con.execute("INSERT INTO appended_rows (cycle_id, tab, row_number, name, company, url) VALUES (?, 'Linkedin', ?, 'n', 'c', ?)", (cid, n, url))


def test_cycle_overview_numbers(db):
    ctx, con = db
    c1 = spend.create_cycle(con, CFG, 10, 3.0)
    company(con, c1, "a.de", "rb:vfx-studios")
    company(con, c1, "b.de", "rb:vfx-studios", "rejected", "tool_vendor")
    person(con, c1, "P1", "https://linkedin.com/in/p1", "High", "a.de")
    person(con, c1, "P2", "https://linkedin.com/in/p2", "Medium", "a.de")
    person(con, c1, "P3", "https://linkedin.com/in/p3", "Medium", "a.de", "rejected", "namesake")
    appended(con, c1, 6, "https://linkedin.com/in/p1")
    appended(con, c1, 7, "https://linkedin.com/in/p2")
    spend.record(con, cycle_id=c1, step_id="s", source="actor", actual_usd=0.30, results=10)
    spend.record(con, cycle_id=c1, step_id="s", source="model", kind="llm", actual_usd=0.05, results=1)
    con.execute("UPDATE cycles SET status='ended', started_at='2026-11-01 10:00:00', ended_at='2026-11-01 13:30:00' WHERE id=?", (c1,))
    o = metrics.cycles_overview(con, "vfx_genai")[0]
    assert (o["rows"], o["high"], o["medium"], o["other"]) == (2, 1, 1, 0)
    assert o["spend_usd"] == 0.3 and o["llm_usd"] == 0.05 and o["cost_per_row"] == 0.15 and o["hours"] == 3.5          # LLM spend is not in cost per row
    assert o["company_rejections"] == {"AI tool or SaaS vendor": 1} and o["person_rejections"] == {"namesake / different company": 1}
    assert {(s["source"], s["usd"]) for s in o["spend_by_source"]} == {("actor", 0.3), ("model", 0.05)}
    assert metrics.cycles_overview(con, "other_pipeline") == []


def test_source_yield_follows_a_company_through_to_its_sheet_rows(db):
    ctx, con = db
    c = spend.create_cycle(con, CFG, 10, 3.0)
    con.execute("INSERT INTO source_yield (cycle_id, pipeline, source, screened, hits) VALUES (?, 'vfx_genai', 'rb:vfx-studios', 500, 4)", (c,))
    con.execute("INSERT INTO source_yield (cycle_id, pipeline, source, screened, hits) VALUES (?, 'vfx_genai', 'rb:vfx-studios', 100, 1)", (c,))        # a resumed crawl adds a second row
    con.execute("INSERT INTO source_yield (cycle_id, pipeline, source, screened, hits) VALUES (?, 'vfx_genai', 'dir:animation-uk', 300, 0)", (c,))
    for d in ("a.de", "b.de", "c.de", "d.de", "e.de"):
        company(con, c, d, "rb:vfx-studios", "approved" if d in ("a.de", "b.de") else "rejected", None if d in ("a.de", "b.de") else "tool_vendor")
    person(con, c, "P1", "https://linkedin.com/in/p1", "High", "a.de")
    person(con, c, "P2", "https://linkedin.com/in/p2", "Medium", "a.de")
    appended(con, c, 6, "https://linkedin.com/in/p1")
    appended(con, c, 7, "https://linkedin.com/in/p2")
    rows = {r["source"]: r for r in metrics.source_yield(con, "vfx_genai")}
    rb = rows["rb:vfx-studios"]
    assert (rb["screened"], rb["hits"], rb["verified"], rb["rows"], rb["cost_usd"]) == (600, 5, 2, 2, 0.0) and rb["hit_rate"] == round(5 / 600, 4)
    assert rows["dir:animation-uk"]["screened"] == 300 and rows["dir:animation-uk"]["verified"] == 0
    assert rows["dir:animation-uk"]["dead"] is True and rb["dead"] is False                                            # 300 screened, nothing approved: flagged
    assert list(rows)[0] == "rb:vfx-studios"                                                                          # best source first


def test_a_source_below_the_screening_threshold_is_not_called_dead(db):
    ctx, con = db
    c = spend.create_cycle(con, CFG, 10, 3.0)
    con.execute("INSERT INTO source_yield (cycle_id, pipeline, source, screened, hits) VALUES (?, 'vfx_genai', 'x:y', ?, 0)", (c, metrics.DEAD_SOURCE_MIN_SCREENED - 1))
    assert metrics.source_yield(con, "vfx_genai")[0]["dead"] is False


def test_paid_steps_separate_this_app_from_imported_history(db):
    ctx, con = db
    c = spend.create_cycle(con, CFG, 10, 3.0)
    spend.record(con, cycle_id=c, step_id="s", source="actor-a", actual_usd=0.2, results=40)
    spend.record(con, cycle_id=c, step_id="s", source="actor-a", actual_usd=0.1, results=20)
    spend.record(con, cycle_id=c, step_id="s", source="model-x", kind="llm", actual_usd=0.05, results=1)
    spend.record(con, cycle_id=None, step_id="old", source="actor-a", actual_usd=1.0, results=300, note="imported:abc")
    rows = metrics.paid_steps(con, "vfx_genai")
    this = {(r["source"], r["kind"]): r for r in rows if r["origin"] == "this app"}
    assert this[("actor-a", "apify")]["usd"] == 0.3 and this[("actor-a", "apify")]["calls"] == 2 and this[("model-x", "llm")]["usd"] == 0.05
    hist = [r for r in rows if r["origin"].startswith("VFX")]
    assert len(hist) == 1 and hist[0]["usd"] == 1.0


def test_llm_agreement_counts_only_decided_yes_no_answers(db):
    ctx, con = db
    c = spend.create_cycle(con, CFG, 10, 3.0)
    v = lambda q, **k: {"qualifies": q, "model": "m1", "prompt_version": "company_verdict_v1", "error": "", **k}
    company(con, c, "1.de", "s", "approved", llm=v("yes"))                       # agree
    company(con, c, "2.de", "s", "rejected", llm=v("no"))                        # agree
    company(con, c, "3.de", "s", "rejected", llm=v("yes"))                       # LLM said yes, reviewer rejected
    company(con, c, "4.de", "s", "approved", llm=v("no"))                        # disagree
    company(con, c, "5.de", "s", "approved", llm=v("unsure"))                    # not counted
    company(con, c, "6.de", "s", "pending", llm=v("yes"))                        # not decided yet
    company(con, c, "7.de", "s", "approved", llm=v("yes", error="rate_limited"))  # errored answer: not counted
    company(con, c, "8.de", "s", "approved")                                     # no LLM verdict
    [row] = metrics.llm_agreement(con, "vfx_genai")
    assert (row["decided"], row["agree"], row["false_yes"], row["agreement"]) == (4, 2, 1, 0.5) and row["model"] == "m1"


def test_exhausted_source_warnings_match_by_keyword_before_a_rerun():
    hit = lambda sid, params=None: [e.source for e in metrics.matching_exhausted(CFG, sid, params)]
    assert any("RevenueBase" in s for s in hit("harvest_revenuebase", {"categories": ["vfx-studios"]}))
    assert any("Sales Navigator" in s for s in hit("salesnav", {"companies": ["A"]}))
    assert any("Trade press" in s for s in hit("harvest_tavily_press"))
    assert any("Agency categories" in s for s in hit("harvest_revenuebase", {"categories": ["advertising-agencies-with-video"]}))
    assert any("generative-ai-" in s for s in hit("harvest_revenuebase", {"categories": ["generative-ai-video"]}))
    assert hit("deep_crawl", {"tag": "rb"}) == [] and hit("evidence") == [] and hit("leads_finder", {"max_result": 40}) == []     # nothing exhausted about these


def test_every_exhausted_entry_in_the_vfx_config_can_actually_fire():
    assert all(e.match for e in CFG.exhausted_sources)                           # an entry with no keywords would never warn


def test_crawl_records_per_source_yield(db, monkeypatch):
    ctx, con = db
    sites = {"https://good.com": '<a href="/work">w</a>', "https://good.com/work": "<p>An AI-generated commercial for Nike, a client campaign with Midjourney.</p>",
             "https://plain.com": "<p>We shoot films for clients.</p>", "https://plain2.com": "<p>Commercials and spots.</p>"}
    monkeypatch.setattr(web, "fetch", lambda u, timeout=12: (u, sites.get(u, "")))
    ctx.workdir.mkdir(parents=True, exist_ok=True)
    meta = lambda cat: [{"organization_name": "x", "loc": "germany", "cat": cat}]
    (ctx.workdir / "rb_domains.json").write_text(json.dumps({"good.com": meta("vfx-studios"), "plain.com": meta("vfx-studios"), "plain2.com": meta("animation-studios"), "dead.com": meta("animation-studios")}))
    crawl.DeepCrawl().run(ctx, crawl.CrawlParams(threads=2))
    got = {r["source"]: (r["screened"], r["hits"]) for r in con.execute("SELECT * FROM source_yield")}
    assert got == {"rb:vfx-studios": (2, 1), "rb:animation-studios": (1, 0)}      # the unreachable site was not screened
