"""Free-step tests. All web access is faked by monkeypatching core.web.fetch: no network."""
import json

import pytest
from conftest_steps import CFG, make_ctx

from core import known, patterns, registry, web
from core.steps import crawl, harvest, people_free
from core.steps.base import Cancelled
from core.textnorm import domain_is_known, norm, squash


# ---------------------------------------------------------------- patterns
@pytest.fixture(scope="module")
def pat():
    return patterns.build(CFG.evidence)


def hits(pat, text):
    return patterns.evidence_hits(text, pat)


def test_ai_wording_next_to_client_cue_is_a_hit(pat):
    assert hits(pat, "We made an AI-generated spot for Nike with Midjourney and ComfyUI.")
    assert hits(pat, "Unsere KI-generierte Kampagne für Audi war ein Erfolg.")        # wildcard + separators + {Brand}
    assert hits(pat, "Kunde: Mercedes. Wir nutzten generative KI für den Spot.")      # generativ* KI


def test_brand_placeholder_needs_a_capitalised_word_and_keeps_its_space():
    from core.config import Evidence
    p = patterns.build(Evidence(strong_terms=["Midjourney"], client_cues=["for {Brand}", "para {Brand}", "für {Brand}"]))
    for ok in ("Midjourney work for Nike.", "Midjourney para Natura.", "Midjourney für Audi gemacht."):
        assert patterns.evidence_hits(ok, p), ok
    for bad in ("Midjourney is great for example.", "Midjourney para redes sociais.", "Midjourney fornike"):   # not capitalised / no space
        assert not patterns.evidence_hits(bad, p), bad


def test_portuguese_commercial_wording_is_a_cue(pat):
    assert hits(pat, "Comerciais, institucionais e conteúdo criados com IA generativa, com roteiro e direção.")


def test_ai_wording_without_client_cue_is_not(pat):
    assert not hits(pat, "We love Midjourney and think about the future of images in general terms only.")


def test_false_positives_are_dropped(pat):
    assert not hits(pat, "Fashion runway show for a client campaign in Milan.")
    assert not hits(pat, "A regenerative approach for our client projects and generative art for a campaign.")
    assert not hits(pat, "Der Klinger Spot für Kunde Meyer, es klingt gut.")           # Kling must not match Klinger / klingt


def test_term_boundaries_and_versions(pat):
    assert hits(pat, "Client campaign made with Kling2.1 and Veo 3.")                  # digits after a tool name are fine
    assert not hits(pat, "The client project was about Soraya and Fluxwerk.")          # Sora / Flux inside longer words


def test_same_sentence_counts_once_across_pages(pat):
    seen = set()
    s = "AI-generated commercial for a client brand with great results in all markets worldwide today."
    assert len(patterns.evidence_hits(s, pat, seen=seen)) == 1
    assert len(patterns.evidence_hits(s, pat, seen=seen)) == 0


def test_empty_strong_terms_is_an_error():
    from core.config import Evidence
    with pytest.raises(ValueError):
        patterns.build(Evidence())


# ---------------------------------------------------------------- textnorm / known
def test_norm_and_domain_is_known():
    assert norm("Glassy Films GmbH") == "glassy" and squash("Mad Studio") == "mad"
    names = {"humain", "glassy", "picturehouse"}
    assert domain_is_known("glassyfilms.com", names)                    # filler stripped
    assert domain_is_known("www.humainmade.ai", names)                  # "humainmade" keeps "humain"
    assert domain_is_known("picturehouse.co.uk", names)
    assert not domain_is_known("totallynew.com", names)
    assert domain_is_known("anything.com", {"anythingcom"})             # the domain itself was logged


def test_known_sets(tmp_path):
    ctx, con, _ = make_ctx(tmp_path)
    known.add_domain(con, "p", "https://www.Foo-Bar.com/x", "crawled")
    known.add_domains(con, "p", ["a.com", "b.com"], "pooled")
    known.add_name(con, "p", "Mad Studio GmbH")
    assert known.seen_domains(con, "p") == {"foo-bar.com", "a.com", "b.com"}
    assert {"foobarcom", "mad"} <= known.known_names(con, "p")
    assert known.seen_domains(con, "other") == set()


def test_public_url_guard(monkeypatch):
    for bad in ("http://localhost/x", "http://127.0.0.1/", "http://192.168.1.5/", "http://10.0.0.1", "file:///etc/passwd", "ftp://x.com", "http://printer.local/"):
        assert not web.is_public_url(bad), bad
    assert web.is_public_url("https://example.com/a") and web.is_public_url("http://8.8.8.8/")
    assert web.fetch("http://127.0.0.1:9/") == ("http://127.0.0.1:9/", "")


# ---------------------------------------------------------------- RevenueBase
def org(name, url, desc="d"):
    return f'"@type": "Organization", "name": "{name}", "url": "{url}", "description": "{desc}"'


def fake_rb(monkeypatch, calls=None):
    pages = {
        "https://revenuebase.ai/companies/browse/video-production-companies":
            "/companies/video-production-companies/germany/berlin /companies/video-production-companies/united-states "
            "/companies/video-production-companies/india/mumbai /companies/video-production-companies/russia",
        "https://revenuebase.ai/companies/browse/vfx-studios": "/companies/vfx-studios/united-kingdom",
        "https://revenuebase.ai/companies/video-production-companies/germany/berlin":
            org("Neu Film", "https://www.neufilm.de/") + org("Known GmbH", "https://known.de") + org("Indian Co", "https://studio.in"),
        "https://revenuebase.ai/companies/video-production-companies/united-states": org("Yankee Studio", "https://yankee.com/home"),
        "https://revenuebase.ai/companies/vfx-studios/united-kingdom": org("Brit VFX", "https://britvfx.co.uk"),
    }

    def fetch(u, timeout=12):
        if calls is not None:
            calls.append(u)
        return u, pages.get(u, "")
    monkeypatch.setattr(web, "fetch", fetch)


def test_revenuebase_filters_countries_known_and_india(tmp_path, monkeypatch):
    ctx, con, _ = make_ctx(tmp_path)
    calls = []
    fake_rb(monkeypatch, calls)
    known.add_domain(con, CFG.name, "known.de", "crawled")
    r = harvest.HarvestRevenueBase().run(ctx, harvest.RBParams(categories=["video-production-companies", "vfx-studios", "generative-ai-video"]))
    out = json.loads((ctx.workdir / "rb_domains.json").read_text())
    assert set(out) == {"neufilm.de", "yankee.com", "britvfx.co.uk"}               # no known.de, no studio.in, no india/russia pages
    assert out["neufilm.de"][0]["organization_name"] == "Neu Film"
    assert not any("generative-ai-video" in u for u in calls)                       # skip_prefixes honoured
    assert not any("/india/" in u or "/russia" in u for u in calls)                 # only approved countries are fetched
    assert r.counts["new"] == 3


def test_revenuebase_limit_pages_and_cancel(tmp_path, monkeypatch):
    ctx, con, _ = make_ctx(tmp_path)
    fake_rb(monkeypatch)
    r = harvest.HarvestRevenueBase().run(ctx, harvest.RBParams(categories=["video-production-companies"], limit_pages=1))
    assert r.counts["pages"] == 1
    ctx2, _, _ = make_ctx(tmp_path / "c", cancel=lambda: True)
    with pytest.raises(Cancelled):
        harvest.HarvestRevenueBase().run(ctx2, harvest.RBParams(categories=["video-production-companies"]))


def test_steps_need_a_pipeline(tmp_path):
    from core.steps.base import StepContext
    ctx = StepContext(job_id=1, cycle_id=None, workdir=tmp_path, job_dir=tmp_path, log=print, is_cancelled=lambda: False, lease=None)
    with pytest.raises(RuntimeError, match="needs a pipeline"):
        harvest.HarvestRevenueBase().run(ctx, harvest.RBParams())


# ---------------------------------------------------------------- directory
def test_directory_extracts_domains_and_reports_blocked(tmp_path, monkeypatch):
    ctx, con, logs = make_ctx(tmp_path)
    links = "".join(f'<a href="https://studio{i}.com/">s</a>' for i in range(35))
    noise = '<a href="https://www.linkedin.com/company/x">l</a><a href="https://example-assoc.org/about">self</a><a href="https://old.in/">in</a>'
    pages = {"https://assoc.org/members": "<html>" + links + noise + "x" * 2500 + "</html>", "https://blocked.org/list": "<html>js only</html>"}
    monkeypatch.setattr(web, "fetch", lambda u, timeout=12: (u, pages.get(u, "")))
    known.add_domain(con, CFG.name, "studio3.com", "crawled")
    r = harvest.HarvestDirectory().run(ctx, harvest.DirParams(urls=list(pages)))
    out = json.loads((ctx.workdir / "dir_domains.json").read_text())
    assert len(out) == 34 and "studio3.com" not in out                              # known dropped
    assert not any("linkedin" in d or d.endswith(".in") for d in out)               # social and .in dropped
    assert r.counts["blocked_pages"] == 1 and any("blocked.org" in line for line in logs)
    with pytest.raises(ValueError):
        harvest.HarvestDirectory().run(ctx, harvest.DirParams(urls=["http://127.0.0.1/members"]))
    with pytest.raises(ValueError):
        harvest.HarvestDirectory().run(ctx, harvest.DirParams(urls=[]))


# ---------------------------------------------------------------- deep crawl
SITES = {
    "https://good.com": '<a href="/work">Work</a><a href="/contact">c</a>',
    "https://good.com/work": "<p>Our AI-generated commercial for Nike used Midjourney, a great client campaign.</p>",
    "https://noai.com": "<p>We shoot films for clients and make commercials.</p>",
    "https://fp.com": "<p>Fashion runway show campaign for our client.</p>",
    "https://clientless.com": "<p>We use Midjourney all day long.</p>",
}


def fake_sites(monkeypatch, counter=None):
    def fetch(u, timeout=12):
        if counter is not None:
            counter.append(u)
        return u, SITES.get(u, "")
    monkeypatch.setattr(web, "fetch", fetch)


def seed_domains(ctx, doms):
    ctx.workdir.mkdir(parents=True, exist_ok=True)
    (ctx.workdir / "rb_domains.json").write_text(json.dumps({d: [{"organization_name": d.upper(), "loc": "germany/berlin", "cat": "vfx-studios"}] for d in doms}))


def test_deep_crawl_finds_evidence_and_feeds_review(tmp_path, monkeypatch):
    ctx, con, _ = make_ctx(tmp_path, cycle_id=None)
    fake_sites(monkeypatch)
    seed_domains(ctx, ["good.com", "noai.com", "fp.com", "clientless.com", "dead.com"])
    r = crawl.DeepCrawl().run(ctx, crawl.CrawlParams(threads=4))
    assert r.counts == {"crawled": 5, "with_evidence": 1, "unreachable": 1}
    rows = {x["domain"]: x for x in map(json.loads, (ctx.workdir / "rb_crawl.jsonl").read_text().splitlines())}
    assert rows["good.com"]["score"] == 1 and rows["good.com"]["ev"][0][0] == "https://good.com/work"
    assert rows["dead.com"]["score"] == -1 and rows["fp.com"]["score"] == 0 and rows["clientless.com"]["score"] == 0
    c = con.execute("SELECT * FROM companies").fetchall()
    assert [(x["domain"], x["name"], x["decision"]) for x in c] == [("good.com", "GOOD.COM", "pending")]
    assert {d for d in known.seen_domains(con, CFG.name)} == {"good.com", "noai.com", "fp.com", "clientless.com", "dead.com"}
    assert [h["domain"] for h in crawl.view_hits(ctx.workdir, "rb")] == ["good.com"]


def test_deep_crawl_resumes_without_refetching(tmp_path, monkeypatch):
    ctx, con, _ = make_ctx(tmp_path)
    counter = []
    fake_sites(monkeypatch, counter)
    seed_domains(ctx, ["good.com", "noai.com"])
    crawl.DeepCrawl().run(ctx, crawl.CrawlParams(threads=2, limit=1))                # first run: only 1 domain
    n1 = len(counter)
    r = crawl.DeepCrawl().resume(ctx, crawl.CrawlParams(threads=2))                  # resume: the other one only
    assert r.counts["crawled"] == 1 and len([u for u in counter[n1:] if "good.com" in u]) == 0
    r = crawl.DeepCrawl().resume(ctx, crawl.CrawlParams(threads=2))
    assert r.counts["crawled"] == 0
    assert len((ctx.workdir / "rb_crawl.jsonl").read_text().splitlines()) == 2


def test_deep_crawl_cancel_keeps_finished_sites(tmp_path, monkeypatch):
    state = {"n": 0}

    def cancel():
        state["n"] += 1
        return state["n"] > 1                                                         # let the first batch finish, then cancel
    ctx, con, _ = make_ctx(tmp_path, cancel=cancel)
    fake_sites(monkeypatch)
    doms = [f"s{i}.com" for i in range(10)]
    seed_domains(ctx, doms)
    with pytest.raises(Cancelled):
        crawl.DeepCrawl().run(ctx, crawl.CrawlParams(threads=2))                      # batch size 4
    done = (ctx.workdir / "rb_crawl.jsonl").read_text().splitlines()
    assert len(done) == 4 and known.seen_domains(con, CFG.name) == {f"s{i}.com" for i in range(4)}


def test_deep_crawl_without_harvest_file_is_a_clear_error(tmp_path):
    ctx, _, _ = make_ctx(tmp_path)
    with pytest.raises(FileNotFoundError, match="run a harvest step"):
        crawl.DeepCrawl().run(ctx, crawl.CrawlParams())


def test_deep_crawl_pools_mode_rescreens_unverified_pool_companies(tmp_path, monkeypatch):
    ctx, con, _ = make_ctx(tmp_path)
    fake_sites(monkeypatch)
    pools = ctx.pipeline_dir / "pools"
    pools.mkdir(parents=True)
    person = lambda d, t, li, **k: {"organization_primary_domain": d, "organization_name": d, "title": t, "linkedin_url": li, "first_name": "A", "last_name": "B", **k}
    (pools / "pool_x.json").write_text(json.dumps([
        person("good.com", "Founder & CEO", "https://linkedin.com/in/a"),
        person("junior.com", "Junior Designer", "https://linkedin.com/in/b"),
        person("india.com", "CEO", "https://linkedin.com/in/c", city="Mumbai"),
        person("seen.com", "CEO", "https://linkedin.com/in/d"),
        person("nolink.com", "CEO", ""),
    ]))
    known.add_domain(con, CFG.name, "seen.com", "crawled")
    r = crawl.DeepCrawl().run(ctx, crawl.CrawlParams(source="pools", tag="pl", threads=2))
    assert json.loads((ctx.workdir / "pl_domains.json").read_text()).keys() == {"good.com"}
    assert r.counts["with_evidence"] == 1


# ---------------------------------------------------------------- evidence
def test_evidence_extract_and_grep(tmp_path, monkeypatch):
    ctx, _, _ = make_ctx(tmp_path)
    site = {"https://s.de": '<a href="/impressum">i</a><a href="/team">t</a><p>Wir nutzen Midjourney.</p>',
            "https://s.de/impressum": "<p>Vertreten durch: Anna Beispiel, Geschäftsführerin</p>",
            "https://s.de/team": "<p>Team: Ben Muster, Creative Director</p>"}
    monkeypatch.setattr(web, "fetch", lambda u, timeout=12: (u, site.get(u, "")))
    r = people_free.Evidence().run(ctx, people_free.EvidenceParams(domains=["s.de", "gone.de"]))
    txt = (ctx.workdir / "evid_ev.txt").read_text()
    assert "Midjourney" in txt and "Vertreten durch" in txt and "Creative Director" in txt and "UNREACHABLE" in txt
    assert r.counts == {"domains": 2, "unreachable": 1}
    g = people_free.Evidence().run(ctx, people_free.EvidenceParams(mode="grep", urls=["https://s.de/impressum"], pattern="vertreten durch"))
    assert g.counts["matches"] == 1 and "Anna Beispiel" in (ctx.workdir / "grep_ev.txt").read_text()
    with pytest.raises(ValueError):
        people_free.Evidence().run(ctx, people_free.EvidenceParams(mode="grep"))


# ---------------------------------------------------------------- pool_match
HDR = CFG.output.columns


def sheet_row(name, company, title, role, country, url, evidence):
    d = dict.fromkeys(HDR, "")
    d.update(name=name, company=company, title=title, role=role, country=country, contact_or_reference=url, evidence_source=evidence)
    return [d[c] for c in HDR]


def lead(first, last, title, domain, org, li, **k):
    return {"first_name": first, "last_name": last, "title": title, "organization_primary_domain": domain, "organization_name": org,
            "linkedin_url": li, "headline": f"{title} at {org}", "city": "Berlin", "country": "Germany", **k}


def test_pool_match_second_contacts(tmp_path):
    ctx, con, logs = make_ctx(tmp_path)
    rows = [
        sheet_row("Anna Founder", "Neu Film", "Founder", "P1", "Germany", "https://linkedin.com/in/anna", "https://neufilm.de/ai; https://lbbonline.com/x"),
        sheet_row("Full One", "Full Co", "CEO", "P1", "Germany", "https://linkedin.com/in/f1", "https://fullco.com"),
        sheet_row("Full Two", "Full Co", "Creative Director", "P2", "Germany", "https://linkedin.com/in/f2", "https://fullco.com"),
        sheet_row("Full Three", "Full Co", "Head of Production", "P3", "Germany", "https://linkedin.com/in/f3", "https://fullco.com"),
    ]
    ctx.pipeline_dir.mkdir(parents=True, exist_ok=True)
    (ctx.pipeline_dir / "sheet_snapshot.json").write_text(json.dumps({"tabs": {"Linkedin": {"header": HDR, "rows": rows},
                                                                          "X": {"header": ["name", "company"], "rows": [["Known Elsewhere", "Zed"]]}}}))
    (ctx.pipeline_dir / "pools").mkdir()
    (ctx.pipeline_dir / "pools" / "pool_a.json").write_text(json.dumps([
        lead("Ben", "Creative", "Creative Director", "neufilm.de", "Neu Film", "https://linkedin.com/in/ben"),          # new family: keep
        lead("Cara", "Another", "CEO", "neufilm.de", "Neu Film", "https://linkedin.com/in/cara"),                        # same family as Anna: skip
        lead("Dan", "Namesake", "Executive Producer", "neufilm.com", "Neu Film", "https://linkedin.com/in/dan"),          # domain differs: keep but flag
        lead("Eve", "Junior", "Junior Producer", "neufilm.de", "Neu Film", "https://linkedin.com/in/eve"),                # rejected title
        lead("Anna", "Founder", "CTO", "neufilm.de", "Neu Film", "https://linkedin.com/in/anna2"),                        # person already on the sheet
        lead("Fay", "Same", "CTO", "neufilm.de", "Neu Film", "https://linkedin.com/in/anna/"),                            # LinkedIn URL already on the sheet
        lead("Gus", "India", "CTO", "neufilm.de", "Neu Film", "https://linkedin.com/in/gus", city="Mumbai"),             # excluded country
        lead("Hal", "Capped", "Head of AI", "fullco.com", "Full Co", "https://linkedin.com/in/hal"),                      # company already at 3
        lead("Ida", "Elsewhere", "CTO", "neufilm.de", "Neu Film", "https://linkedin.com/in/ida", first_name="Known", last_name="Elsewhere"),  # name on the X tab
        lead("Jo", "NoLink", "CTO", "neufilm.de", "Neu Film", ""),                                                        # no personal URL
    ]))
    r = people_free.PoolMatch().run(ctx, people_free.PoolMatchParams())
    got = json.loads((ctx.workdir / "pm_pool_match.json").read_text())
    by = {c["first"]: c for c in got}
    assert set(by) == {"Ben", "Dan"}, logs
    assert by["Ben"]["domain_differs"] is False and by["Ben"]["family"] == "creative" and by["Ben"]["sheet_domain"] == "neufilm.de"
    assert by["Dan"]["domain_differs"] is True and r.counts["domain_differs"] == 1
    assert by["Ben"]["existing"][0][0] == "Anna Founder"


def test_pool_match_errors_are_clear(tmp_path):
    ctx, _, _ = make_ctx(tmp_path)
    with pytest.raises(FileNotFoundError, match="sheet_snapshot.json"):
        people_free.PoolMatch().run(ctx, people_free.PoolMatchParams())
    ctx.pipeline_dir.mkdir(parents=True, exist_ok=True)
    (ctx.pipeline_dir / "sheet_snapshot.json").write_text(json.dumps({"tabs": {"Linkedin": {"header": ["name", "company"], "rows": []}}}))
    with pytest.raises(ValueError, match="no column"):
        people_free.PoolMatch().run(ctx, people_free.PoolMatchParams())


# ---------------------------------------------------------------- registry step validation
def test_pipeline_step_validation():
    steps, missing = registry.check_steps(CFG)
    assert steps == [] and missing == ["harvest_tavily_press"]            # the only step in the VFX pipeline not built yet (Tavily-credit gated)
    bad = CFG.model_copy(deep=True)
    bad.steps[0].params = {"nonsense": 1}
    problems, _ = registry.check_steps(bad)
    assert problems and "harvest_revenuebase" in problems[0]


def test_pools_mode_rescans_pool_only_companies_but_not_crawled_or_rejected_ones(tmp_path, monkeypatch):
    ctx, con, _ = make_ctx(tmp_path)
    fake_sites(monkeypatch)
    pools = ctx.pipeline_dir / "pools"
    pools.mkdir(parents=True)
    person = lambda d: {"organization_primary_domain": d, "organization_name": d, "title": "Founder & CEO", "linkedin_url": f"https://linkedin.com/in/{d}", "first_name": "A", "last_name": "B"}
    (pools / "pool_x.json").write_text(json.dumps([person("poolonly.com"), person("poolcrawled.com"), person("poolrejected.com"), person("good.com")]))
    for d in ("poolonly.com", "poolcrawled.com", "poolrejected.com", "good.com"):
        known.add_domain(con, CFG.name, d, "pooled")                               # every paid-pool domain is imported as 'pooled'
    known.add_domain(con, CFG.name, "poolcrawled.com", "crawled")                  # this one was also deep-crawled before
    known.add_domain(con, CFG.name, "poolrejected.com", "rejected")
    crawl.DeepCrawl().run(ctx, crawl.CrawlParams(source="pools", tag="pl", threads=2))
    assert set(json.loads((ctx.workdir / "pl_domains.json").read_text())) == {"poolonly.com", "good.com"}
