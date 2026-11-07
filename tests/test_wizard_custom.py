"""Phase 8 tests: custom steps (discovery, failure isolation, id protection, gate), the wizard's logic (template, validation, safe writing, clone,
archive), and field mapping with a second pipeline whose columns are named differently from VFX's."""
import json
import os
import time

import pytest
import yaml
from conftest_steps import make_ctx

from core import append as ap, fields as F, jobs, paths, people, registry, review, spend, wizard
from core.config import ConfigError, parse_config
from core.sheets import FakeSheet, SafeSheet
from core.steps import base
from core.steps.custom import load_custom_steps, reload_custom_steps, scaffold_step


@pytest.fixture()
def pipes(tmp_path, monkeypatch):
    d = tmp_path / "pipelines"
    d.mkdir()
    monkeypatch.setattr(paths, "PIPELINES_DIR", d)
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data")
    monkeypatch.setenv("LPD_PIPELINES", str(d))
    monkeypatch.setenv("LPD_DATA", str(tmp_path / "data"))
    base.unregister_custom()
    yield d
    base.unregister_custom()


def make_pipeline(root, name="toy", **mutate):
    d = wizard.template_dict(name, name.title())
    for k, v in mutate.items():
        d[k] = v
    return wizard.write_pipeline(name, wizard.to_yaml(d), {}, root)


GOOD_STEP = '''
from pydantic import BaseModel, ConfigDict
from core.steps.base import Step, StepResult, register

class P(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = "a b c"

@register
class CountWords(Step):
    id = "count_words"
    kind = "free"
    title = "count words"
    params_model = P
    def run(self, ctx, params):
        n = len(params.text.split())
        (ctx.workdir / "words.txt").write_text(str(n), encoding="utf-8")
        ctx.log(f"counted {n} words")
        return StepResult(counts={"words": n}, artifacts=["words.txt"], message=f"{n} words")
'''


def put_step(root, pipeline, filename, source):
    f = root / pipeline / "steps" / filename
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(source, encoding="utf-8")
    return f


# ---------------------------------------------------------------- custom steps
def test_a_custom_step_is_discovered_and_scoped_to_its_pipeline(pipes):
    make_pipeline(pipes, "toy")
    make_pipeline(pipes, "other")
    put_step(pipes, "toy", "count_words.py", GOOD_STEP)
    assert load_custom_steps() == {}
    assert base.origin_of("count_words") == "toy" and "count_words" in base.steps_for("toy")
    assert "count_words" not in base.steps_for("other") and "count_words" not in base.steps_for(None)           # other pipelines never see it
    assert "leads_finder" in base.steps_for("toy") and "leads_finder" in base.steps_for("other")               # built-ins are for everyone
    # a pipeline can use its own custom step in YAML, but not another pipeline's
    own = wizard.template_dict("toy", "Toy")
    own["steps"].insert(0, {"step": "count_words", "stage": "companies", "params": {"text": "x y"}})
    assert wizard.validate_text(wizard.to_yaml(own)).ok
    foreign = wizard.template_dict("other", "Other")
    foreign["steps"].insert(0, {"step": "count_words", "stage": "companies", "params": {}})
    v = wizard.validate_text(wizard.to_yaml(foreign))
    assert not v.ok and any("belongs to pipeline 'toy'" in p for p in v.problems)


def test_a_broken_file_becomes_an_error_card_and_never_stops_the_good_ones(pipes):
    make_pipeline(pipes, "toy")
    put_step(pipes, "toy", "a_good.py", GOOD_STEP)
    put_step(pipes, "toy", "b_syntax.py", "def broken(:\n    pass\n")
    put_step(pipes, "toy", "c_import.py", "import a_module_that_does_not_exist\n")
    put_step(pipes, "toy", "d_noreg.py", "x = 1\n")
    put_step(pipes, "toy", "e_runtime.py", "raise RuntimeError('boom at import')\n")
    errs = load_custom_steps()
    assert "count_words" in base.all_steps()                                                   # the good file still loaded
    assert set(errs) == {"toy/steps/b_syntax.py", "toy/steps/c_import.py", "toy/steps/d_noreg.py", "toy/steps/e_runtime.py"}
    assert "SyntaxError" in errs["toy/steps/b_syntax.py"] and "a_module_that_does_not_exist" in errs["toy/steps/c_import.py"]
    assert "registered no step" in errs["toy/steps/d_noreg.py"] and "boom at import" in errs["toy/steps/e_runtime.py"] and "line" in errs["toy/steps/e_runtime.py"]
    assert base.broken_steps() == errs


@pytest.mark.parametrize("body,expect", [
    ('id = "bad id!"\n    kind = "free"', "lowercase slug"),
    ('id = "okid"\n    kind = "dangerous"', "`kind` must be one of"),
    ('id = "okid"\n    kind = "free"\n    params_model = dict', "params_model"),
])
def test_invalid_step_classes_are_rejected_with_a_reason(pipes, body, expect):
    make_pipeline(pipes, "toy")
    src = f"from core.steps.base import Step, StepResult, register\n\n@register\nclass S(Step):\n    {body}\n    def run(self, ctx, params):\n        return StepResult()\n"
    put_step(pipes, "toy", "s.py", src)
    errs = load_custom_steps()
    assert any(expect in e for e in errs.values()), errs
    assert "okid" not in base.all_steps() and "bad id!" not in base.all_steps()                 # nothing half-registered


def test_a_step_without_run_is_rejected(pipes):
    make_pipeline(pipes, "toy")
    put_step(pipes, "toy", "s.py", "from core.steps.base import Step, register\n\n@register\nclass S(Step):\n    id = 'no_run'\n")
    assert "run(self, ctx, params)" in list(load_custom_steps().values())[0]


def test_a_custom_step_cannot_take_over_a_builtin_or_another_pipelines_id(pipes):
    make_pipeline(pipes, "toy")
    make_pipeline(pipes, "other")
    original = base.get_step("leads_finder")
    evil = GOOD_STEP.replace('"count_words"', '"leads_finder"')
    put_step(pipes, "toy", "evil.py", evil)
    errs = load_custom_steps()
    assert "already used by builtin" in errs["toy/steps/evil.py"]
    assert base.get_step("leads_finder") is original and base.origin_of("leads_finder") == "builtin"         # the built-in is untouched
    base.unregister_custom()
    put_step(pipes, "toy", "evil.py", GOOD_STEP)
    put_step(pipes, "other", "dup.py", GOOD_STEP)
    errs = load_custom_steps()
    assert base.origin_of("count_words") == "other"                                                          # pipelines load in name order: the first claimant keeps the id
    assert len(errs) == 1 and "already used by" in list(errs.values())[0]                                      # the second claimant fails, the first keeps it


def test_a_file_that_fails_after_registering_leaves_nothing_behind(pipes):
    make_pipeline(pipes, "toy")
    put_step(pipes, "toy", "half.py", GOOD_STEP + "\nraise RuntimeError('late failure')\n")
    errs = load_custom_steps()
    assert "late failure" in list(errs.values())[0] and "count_words" not in base.all_steps()                 # rolled back


def test_reload_picks_up_edits_and_removals_and_ignores_underscore_files(pipes):
    make_pipeline(pipes, "toy")
    f = put_step(pipes, "toy", "count_words.py", GOOD_STEP)
    put_step(pipes, "toy", "_helper.py", "raise RuntimeError('must not be imported')\n")
    assert reload_custom_steps() == {} and "count_words" in base.all_steps()
    f.write_text(GOOD_STEP.replace('title = "count words"', 'title = "edited title"'), encoding="utf-8")
    reload_custom_steps()
    assert base.get_step("count_words").title == "edited title"
    f.write_text("def oops(:\n", encoding="utf-8")
    assert "SyntaxError" in list(reload_custom_steps().values())[0] and "count_words" not in base.all_steps()
    f.unlink()
    assert reload_custom_steps() == {} and base.broken_steps() == {}


def test_archived_pipelines_do_not_load_their_custom_steps(pipes):
    make_pipeline(pipes, "toy")
    put_step(pipes, "toy", "count_words.py", GOOD_STEP)
    reload_custom_steps()
    assert "count_words" in base.all_steps()
    wizard.archive_pipeline("toy", pipes)
    reload_custom_steps()
    assert "count_words" not in base.all_steps() and registry.load_all() == []


def test_a_custom_step_runs_in_process_with_a_context(pipes, tmp_path):
    make_pipeline(pipes, "toy")
    put_step(pipes, "toy", "count_words.py", GOOD_STEP)
    load_custom_steps()
    ctx, con, logs = make_ctx(tmp_path)
    step = base.get_step("count_words")
    r = step.run(ctx, step.params_model(text="one two three four"))
    assert r.counts == {"words": 4} and (ctx.workdir / "words.txt").read_text() == "4" and logs == ["counted 4 words"]


def test_a_custom_paid_step_still_cannot_start_without_the_gate(pipes, tmp_path):
    make_pipeline(pipes, "toy")
    paid_src = GOOD_STEP.replace('kind = "free"', 'kind = "paid"').replace('"count_words"', '"paid_thing"')
    put_step(pipes, "toy", "paid_thing.py", paid_src)
    load_custom_steps()
    con = make_ctx(tmp_path)[1]
    with pytest.raises(PermissionError, match="confirmation"):
        jobs.create_job(con, "paid_thing", {})


def test_scaffold_writes_a_loadable_step_for_every_kind_and_never_overwrites(pipes):
    make_pipeline(pipes, "toy")
    for kind in ("free", "paid", "llm", "write"):
        f = scaffold_step("toy", f"made_{kind}", kind, pipes)
        assert f.exists()
    assert reload_custom_steps() == {}
    assert {base.get_step(f"made_{k}").kind for k in ("free", "paid", "llm", "write")} == {"free", "paid", "llm", "write"}
    with pytest.raises(FileExistsError):
        scaffold_step("toy", "made_free", "free", pipes)
    for bad in ("Bad Id", "x", "leads_finder", "../evil"):
        with pytest.raises(ValueError):
            scaffold_step("toy", bad, "free", pipes)
    with pytest.raises(ValueError, match="does not exist"):
        scaffold_step("nope", "fine_id", "free", pipes)
    with pytest.raises(ValueError, match="kind"):
        scaffold_step("toy", "fine_id", "root", pipes)


def test_a_custom_step_runs_in_a_real_worker_process(pipes, tmp_path):
    from core.db import open_db
    make_pipeline(pipes, "toy")
    put_step(pipes, "toy", "count_words.py", GOOD_STEP)
    reload_custom_steps()
    con = open_db(paths.DATA_DIR / "dashboard.sqlite")
    con.execute("INSERT INTO pipelines (name, yaml_path) VALUES ('toy','x')")
    cfg = registry.get_config("toy")
    cid = spend.create_cycle(con, cfg, 5, 1.0)
    jid = jobs.start_job(con, "count_words", {"text": "alpha beta gamma delta epsilon"}, cid, pipeline="toy")
    try:
        t0 = time.time()
        while jobs.get_job(con, jid)["status"] in ("queued", "running") and time.time() - t0 < 45:
            time.sleep(0.3)
        j = jobs.get_job(con, jid)
        assert j["status"] == "done", jobs.tail_log(jid) + "\n" + (paths.DATA_DIR / "jobs" / str(jid) / "worker.out").read_text(errors="replace")
        assert "counted 5 words" in jobs.tail_log(jid)
        assert (paths.DATA_DIR / "cycles" / str(cid) / "words.txt").read_text() == "5"
    finally:
        j = jobs.get_job(con, jid)
        if j["pid"] not in (os.getpid(), 1) and jobs.pid_alive(j["pid"]):
            jobs.kill_tree(j["pid"])


# ---------------------------------------------------------------- the wizard
def test_the_template_is_valid_and_roundtrips_through_yaml():
    d = wizard.template_dict("my_pipe", "My pipe")
    text = wizard.to_yaml(d)
    v = wizard.validate_text(text)
    assert v.ok and v.config.name == "my_pipe"
    assert any("template text" in w for w in v.warnings)                                                       # it tells you it is still a template
    assert yaml.safe_load(text) == d and list(yaml.safe_load(text)) == list(d)                                   # nothing lost, order kept


def test_validation_reports_each_kind_of_mistake_readably():
    base_d = wizard.template_dict("pp", "PP")
    mk = lambda f: wizard.validate_text(wizard.to_yaml(f(json.loads(json.dumps(base_d)))))

    def s(d):
        d["steps"][0]["step"] = "no_such_step"
        return d
    assert any("no_such_step" in p and "Available:" in p for p in mk(s).problems)

    def s2(d):
        d["steps"][1]["params"] = {"threads": 40, "nonsense": 1}
        return d
    assert any("deep_crawl" in p for p in mk(s2).problems)

    def s3(d):
        d["budget"]["default_cycle_cap_usd"] = 9
        return d
    assert any("cannot exceed" in p for p in mk(s3).problems)

    def s4(d):
        d["steps"] = [x for x in d["steps"] if x["stage"] != "write"]
        return d
    assert not mk(s4).ok

    def s5(d):
        d["output"]["dedupe"]["name_field"] = "nope"
        return d
    assert any("dedupe field" in p for p in mk(s5).problems)

    def s6(d):
        d["sop_files"] = ["sop/rules.md"]
        return d
    v = mk(s6)
    assert v.ok and any("rules.md" in w for w in v.warnings)
    assert wizard.validate_text("a: [unclosed").problems and not wizard.validate_text("- a list").ok


def test_write_pipeline_validates_then_writes_and_refuses_to_overwrite(pipes):
    text = wizard.to_yaml(wizard.template_dict("new_one", "New one"))
    folder = wizard.write_pipeline("new_one", text, {"rules.md": "# Rules\n"}, pipes)
    assert (folder / "pipeline.yaml").read_text(encoding="utf-8").startswith("schema_version") and (folder / "sop" / "rules.md").read_text() == "# Rules\n"
    assert not list(folder.glob("*.tmp"))
    assert registry.get_config("new_one").title == "New one"
    with pytest.raises(FileExistsError):
        wizard.write_pipeline("new_one", text, {}, pipes)
    assert (folder / "pipeline.yaml").read_text(encoding="utf-8") == text                                        # untouched by the refused write


def test_write_pipeline_rejects_unsafe_or_invalid_input_and_writes_nothing(pipes):
    good = wizard.to_yaml(wizard.template_dict("ok_name", "T"))
    for bad_name in ("../evil", "Bad Name", "x", "a/b", ""):
        with pytest.raises(ValueError):
            wizard.write_pipeline(bad_name, good, {}, pipes)
    with pytest.raises(ValueError, match="does not match"):
        wizard.write_pipeline("other_name", good, {}, pipes)
    with pytest.raises(ValueError, match="not valid"):
        wizard.write_pipeline("ok_name", "name: ok_name\n", {}, pipes)
    for bad_sop in ("x.exe", ".md", "no_ext", "bad name.md"):
        with pytest.raises(ValueError, match="SOP file name"):
            wizard.write_pipeline("ok_name", good, {bad_sop: "x"}, pipes)
    with pytest.raises(ValueError, match="larger than"):
        wizard.write_pipeline("ok_name", good, {"big.md": "x" * 1_100_000}, pipes)
    assert list(pipes.iterdir()) == []                                                                          # nothing was created by any refused attempt


def test_traversal_in_an_sop_name_is_reduced_to_a_harmless_basename(pipes):
    good = wizard.to_yaml(wizard.template_dict("ok_name", "T"))
    folder = wizard.write_pipeline("ok_name", good, {"../../outside.md": "text"}, pipes)
    assert (folder / "sop" / "outside.md").exists() and not (pipes.parent / "outside.md").exists()


def test_editing_keeps_a_backup_of_the_previous_file(pipes):
    folder = make_pipeline(pipes, "toy")
    old = (folder / "pipeline.yaml").read_text(encoding="utf-8")
    d = wizard.from_config(registry.get_config("toy"))
    d["title"] = "Changed title"
    wizard.write_pipeline("toy", wizard.to_yaml(d), {}, pipes, overwrite=True)
    assert registry.get_config("toy").title == "Changed title"
    backups = list((paths.DATA_DIR / "backups").glob("toy_*.yaml"))
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == old


def test_clone_copies_config_and_sops_but_not_exhausted_notes(pipes):
    d = wizard.template_dict("src", "Source")
    d["sop_files"] = ["sop/rules.md"]
    d["exhausted_sources"] = [{"source": "x", "note": "dead", "date": "", "match": ["x"]}]
    wizard.write_pipeline("src", wizard.to_yaml(d), {"rules.md": "# rules"}, pipes)
    cfg = registry.get_config("src")
    clone = wizard.clone_dict(cfg, "src_copy")
    assert clone["name"] == "src_copy" and clone["title"] == "Source (copy)" and clone["exhausted_sources"] == [] and clone["sop_files"] == ["sop/rules.md"]
    sops = wizard.read_sop_files(cfg, pipes / "src")
    wizard.write_pipeline("src_copy", wizard.to_yaml(clone), sops, pipes)
    assert (pipes / "src_copy" / "sop" / "rules.md").read_text() == "# rules" and len(registry.load_all()) == 2


def test_archive_moves_the_folder_and_keeps_every_file(pipes):
    folder = make_pipeline(pipes, "toy")
    (folder / "notes.txt").write_text("keep me")
    dest = wizard.archive_pipeline("toy", pipes)
    assert dest.parent.name == "_archived" and (dest / "notes.txt").read_text() == "keep me" and (dest / "pipeline.yaml").exists()
    assert not folder.exists() and registry.load_all() == [] and paths.pipeline_dirs() == []                   # unlisted, not deleted
    with pytest.raises(ValueError):
        wizard.archive_pipeline("toy", pipes)
    with pytest.raises(ValueError):
        wizard.archive_pipeline("../x", pipes)


def test_line_and_family_helpers_roundtrip():
    assert wizard.lines("  a \n\n b\n") == ["a", "b"] and wizard.unlines(["a", "b"]) == "a\nb"
    fam = {"ceo": ["founder", "owner"], "tech": ["cto"]}
    assert wizard.parse_families(wizard.format_families(fam)) == fam and wizard.parse_families("junk line\n: nokey") == {}


# ---------------------------------------------------------------- field mapping: a second pipeline with different column names
COLS2 = ["person", "firm", "position", "role", "region", "evidence_summary", "why_this_person", "confidence", "profile", "source_urls"]
MAP2 = {"name": "person", "company": "firm", "title": "position", "country": "region", "ai_evidence": "evidence_summary", "qa_confidence": "confidence",
        "contact_or_reference": "profile", "evidence_source": "source_urls"}


def arch_dict():
    d = wizard.template_dict("architecture_ai", "Architecture firms using AI renders")
    d["countries"]["approved"] = ["Germany", "UK"]
    d["people"]["max_per_company"] = 2
    d["output"].update(columns=list(COLS2), field_map=dict(MAP2))
    d["output"]["tabs"] = [{"name": "People", "range": "People!A1:J6000", "write": True, "header": list(COLS2)}, {"name": "Archive", "range": "Archive!A1:C9", "write": False, "header": []}]
    d["output"]["dedupe"].update(name_field="person", company_field="firm", url_fields=["profile"], evidence_field="source_urls", country_field="region")
    return d


@pytest.fixture()
def arch():
    cfg = parse_config(wizard.to_yaml(arch_dict()))
    return cfg


def test_a_pipeline_with_renamed_columns_validates(arch):
    assert arch.output.columns == COLS2 and F.internal_columns(arch) == ["name", "company", "title", "role", "country", "ai_evidence", "why_this_person", "qa_confidence",
                                                                           "contact_or_reference", "evidence_source"]
    assert F.to_column(arch, "company") == "firm" and F.to_internal(arch, "firm") == "company" and F.to_internal(arch, "role") == "role"


@pytest.mark.parametrize("mutate,expect", [
    (lambda m: m.update(not_a_field="firm"), "not an internal field"),
    (lambda m: m.update(company="no_such_column"), "not in output.columns"),
    (lambda m: m.update(title="firm"), "ambiguous"),                                  # two internal fields mapped to one column
])
def test_a_bad_field_map_is_rejected(mutate, expect):
    d = arch_dict()
    mutate(d["output"]["field_map"])
    with pytest.raises(ConfigError, match=expect):
        parse_config(wizard.to_yaml(d))


def test_a_column_named_like_an_internal_field_that_is_mapped_elsewhere_is_ambiguous():
    d = arch_dict()
    d["output"]["columns"] = d["output"]["columns"] + ["company"]                       # "company" is the internal name of "firm"
    d["output"]["tabs"][0]["header"] = list(d["output"]["columns"])
    with pytest.raises(ConfigError, match="ambiguous"):
        parse_config(wizard.to_yaml(d))


def test_fields_roundtrip_between_sheet_rows_and_internal_names(arch):
    row = ["Ada Lovelace", "Studio X", "Founder", "P1", "Germany", "AI render for client", "Owns the studio", "Medium", "https://linkedin.com/in/ada", "https://x.de/ai"]
    f = F.fields_from_row(arch, COLS2, row)
    assert f["name"] == "Ada Lovelace" and f["company"] == "Studio X" and f["contact_or_reference"].endswith("/ada") and f["role"] == "P1"
    assert F.row_from_fields(arch, f) == row
    assert F.fields_from_row(arch, COLS2, row[:3])["country"] == ""                                   # short rows are padded


def lead(first, last, title, domain, **k):
    return {"first_name": first, "last_name": last, "title": title, "organization_primary_domain": domain, "organization_name": domain.split(".")[0].title(),
            "linkedin_url": f"https://www.linkedin.com/in/{first.lower()}-{last.lower()}", "headline": title, "city": "Berlin", "country": "Germany", **k}


def test_the_whole_people_flow_works_with_renamed_columns(arch, tmp_path):
    ctx, con, logs = make_ctx(tmp_path)
    con.execute("INSERT INTO pipelines (name, yaml_path) VALUES ('architecture_ai','x')")
    cid = spend.create_cycle(con, arch, 5, 3.0)
    con.execute("INSERT INTO companies (cycle_id, domain, name, country, evidence_json, decision) VALUES (?,?,?,?,?, 'approved')",
                (cid, "studiox.de", "Studio X", "Germany", json.dumps({"score": 1, "ev": [["https://studiox.de/work", "AI render for client Foster."]]})))
    res = people.people_from_leads(con, arch, cid, [lead("Ada", "Founder", "Founder & CEO", "studiox.de"), lead("Bo", "Design", "Creative Director", "studiox.de"),
                                                    lead("Cy", "Intern", "Intern", "studiox.de")])
    assert res["added"] == 2
    rows = [(r["id"], json.loads(r["fields_json"])) for r in con.execute("SELECT * FROM people ORDER BY id")]
    f = rows[0][1]
    assert f["name"] == "Ada Founder" and f["company"] == "Studio X" and f["ai_evidence"].startswith("AI render") and f["evidence_source"].endswith("/ada-founder")    # stored under internal names
    assert "person" not in f and "firm" not in f and f["_headline"] == "Founder & CEO"
    probs = review.draft_problems(arch, f)
    assert probs == ["why_this_person is still the draft: write a sentence specific to this person"]                  # no commercial-problem column here: not demanded
    f["why_this_person"] = "Owns the studio's AI visualisation work."
    review.update_person_fields(con, rows[0][0], f)
    review.decide_person(con, rows[0][0], "approved")
    assert review.approved_rows(con, arch, cid) == [["Ada Founder", "Studio X", "Founder & CEO", "P1", "Germany", "AI render for client Foster.", "Owns the studio's AI visualisation work.",
                                                    "Medium", "https://www.linkedin.com/in/ada-founder", "https://studiox.de/work; https://www.linkedin.com/in/ada-founder"]]
    assert "Ada Founder" in review.cycle_report_markdown(con, arch, cid) and "studiox.de/work" in review.cycle_report_markdown(con, arch, cid)


def test_dedupe_and_safe_append_use_the_renamed_columns(arch):
    existing = [["Old Timer", "Studio Y", "Founder", "P1", "UK", "x", "y", "High", "https://linkedin.com/in/old-timer", "https://y.com"],
                ["Pat Two", "Cap Co", "CEO", "P1", "UK", "x", "y", "High", "https://linkedin.com/in/pat-two", "https://cap.com"],
                ["Pat Three", "Cap Co", "COO", "P2", "UK", "x", "y", "High", "https://linkedin.com/in/pat-three", "https://cap.com"]]
    fs = FakeSheet({"People": [list(COLS2)] + existing, "Archive": [["person", "firm", "x"], ["Archived Person", "Old Firm", ""]]})
    mk = lambda n, c, **k: [n, c, "Founder", "P1", k.get("region", "Germany"), "ev", "why", "Medium", k.get("url", f"https://linkedin.com/in/{n.lower().replace(' ', '-')}"), "https://e.com"]
    rows = [mk("Fresh Face", "New Studio"), mk("Old Timer", "Other Co", url="https://linkedin.com/in/ot2"), mk("Third Person", "Cap Co"), mk("Archived Person", "Elsewhere", url="https://linkedin.com/in/ap"),
            mk("Far Away", "Remote Co", region="India"), mk("Moscow Man", "Mos Co", region="Russia")]
    rep = ap.dry_run(SafeSheet(fs, "People"), arch, rows)
    assert [r[1][0] for r in rep.added] == ["Fresh Face"]
    reasons = {n: w for _, n, w in rep.skipped}
    assert "same person" in reasons["Old Timer"] and "already has 2 people" in reasons["Third Person"] and "same person" in reasons["Archived Person"]       # the Archive tab counts
    assert "country not approved" in reasons["Far Away"] and "country not approved" in reasons["Moscow Man"]                                                                                       # this pipeline approves Germany and UK only
    landed = []
    out = ap.append_rows(SafeSheet(fs, "People"), arch, rows, on_landed=lambda a, r: landed.append(a))
    assert [r[1][0] for r in out.added] == ["Fresh Face"] and landed == [5]
    assert fs.get_values("People!A5:J5")[0][:2] == ["Fresh Face", "New Studio"] and set(c for (_, r, c0, c1) in fs.format_log for c in (c0, c1)) == {0, 10}   # whitened columns A..J only


def test_pool_match_reads_a_sheet_with_renamed_columns(arch, tmp_path):
    from core.steps import people_free
    ctx, con, logs = make_ctx(tmp_path)
    ctx.cfg = arch
    con.execute("INSERT INTO pipelines (name, yaml_path) VALUES ('architecture_ai','x')")
    ctx.cycle_id = spend.create_cycle(con, arch, 5, 3.0)
    ctx.pipeline_dir.mkdir(parents=True, exist_ok=True)
    (ctx.pipeline_dir / "pools").mkdir()
    sheet_row = ["Ana Owner", "Studio Z", "Founder", "P1", "Germany", "AI renders for Foster", "owns it", "High", "https://linkedin.com/in/ana-owner", "https://studioz.de/ai; https://lbbonline.com/x"]
    (ctx.pipeline_dir / "sheet_snapshot.json").write_text(json.dumps({"tabs": {"People": {"header": COLS2, "rows": [sheet_row]}, "Archive": {"header": ["person", "firm"], "rows": [["Gone Person", "Old"]]}}}))
    (ctx.pipeline_dir / "pools" / "pool_a.json").write_text(json.dumps([
        {**lead("Ben", "Designer", "Creative Director", "studioz.de"), "organization_name": "Studio Z"},
        {**lead("Gone", "Person", "CEO", "studioz.de"), "organization_name": "Studio Z"}]))                                       # on the Archive tab: must be skipped
    r = people_free.PoolMatch().run(ctx, people_free.PoolMatchParams())
    got = json.loads((ctx.workdir / "pm_pool_match.json").read_text())
    assert [c["first"] for c in got] == ["Ben"] and got[0]["sheet_company"] == "Studio Z" and got[0]["sheet_country"] == "Germany"
    assert got[0]["existing_row"]["company"] == "Studio Z" and got[0]["existing_row"]["ai_evidence"].startswith("AI renders")        # internal names
    pend = [json.loads(x["fields_json"]) for x in con.execute("SELECT * FROM people")]
    assert len(pend) == 1 and pend[0]["company"] == "Studio Z" and pend[0]["ai_evidence"].startswith("AI renders") and pend[0]["role"] == "P2" and pend[0]["country"] == "Germany"
    assert pend[0]["evidence_source"] == "https://studioz.de/ai; https://lbbonline.com/x; https://www.linkedin.com/in/ben-designer"


def test_metrics_and_llm_work_unchanged_with_internal_fields(arch, tmp_path):
    """Metrics read internal names (qa_confidence, contact_or_reference) from the people table, so renamed sheet columns do not matter."""
    from core import metrics
    ctx, con, logs = make_ctx(tmp_path)
    con.execute("INSERT INTO pipelines (name, yaml_path) VALUES ('architecture_ai','x')")
    cid = spend.create_cycle(con, arch, 5, 3.0)
    con.execute("INSERT INTO people (cycle_id, domain, fields_json, decision) VALUES (?, 'a.de', ?, 'approved')", (cid, json.dumps({"qa_confidence": "High", "contact_or_reference": "https://linkedin.com/in/a"})))
    con.execute("INSERT INTO appended_rows (cycle_id, tab, row_number, name, company, url) VALUES (?, 'People', 5, 'n', 'c', 'https://linkedin.com/in/a')", (cid,))
    assert metrics.cycles_overview(con, "architecture_ai")[0]["high"] == 1
