"""Headless render of every Streamlit page (streamlit.testing AppTest). It runs against a temporary database and pipelines folder, never the real ones.
It catches the class of bug unit tests cannot: a page that raises when it renders (bad import, a typo in a widget call, an f-string, a missing key)."""
import json
import pathlib

import pytest
from streamlit.testing.v1 import AppTest

from core import paths, spend, wizard
from core.db import open_db, set_setting
from core.registry import get_config
from core.steps import base

ROOT = pathlib.Path(__file__).resolve().parent.parent
PIPELINES_PAGE = str(ROOT / "app" / "pages" / "1_Pipelines.py")
PAGES = [str(ROOT / "app" / n) for n in ("Home.py", "pages/1_Pipelines.py", "pages/2_Run_Cycle.py", "pages/3_Jobs.py", "pages/4_Review.py", "pages/5_Keys.py", "pages/6_Spend.py", "pages/7_History.py", "pages/8_Settings.py")]


@pytest.fixture()
def env(tmp_path, monkeypatch):
    pipes = tmp_path / "pipelines"
    pipes.mkdir()
    monkeypatch.setattr(paths, "PIPELINES_DIR", pipes)
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "data" / "dashboard.sqlite")
    monkeypatch.setenv("LPD_PIPELINES", str(pipes))
    monkeypatch.setenv("LPD_DATA", str(tmp_path / "data"))
    base.unregister_custom()
    wizard.write_pipeline("toy", wizard.to_yaml(wizard.template_dict("toy", "Toy pipeline")), {}, pipes)
    yield pipes
    base.unregister_custom()


def run(path):
    at = AppTest.from_file(path, default_timeout=60)
    at.run()
    return at


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_on_an_empty_database(env, page):
    at = run(page)
    assert not at.exception, [e.value for e in at.exception]


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_with_a_cycle_and_review_data(env, page):
    con = open_db()
    set_setting(con, "demo_mode", "1")
    set_setting(con, "llm.enabled", "1")
    from core import keys
    keys.check_all(con)
    cfg = get_config("toy")
    con.execute("INSERT OR IGNORE INTO pipelines (name, yaml_path) VALUES ('toy','x')")
    cid = spend.create_cycle(con, cfg, 5, 3.0)
    con.execute("INSERT INTO companies (cycle_id, domain, name, country, source, evidence_json, llm_json, decision) VALUES (?,?,?,?,?,?,?, 'pending')",
                (cid, "a.de", "A", "germany", "rb:vfx", json.dumps({"score": 1, "ev": [["https://a.de/work", "AI-generated spot for a client."]]}),
                 json.dumps({"qualifies": "yes", "confidence": 0.8, "reason": "r", "quote": "AI-generated spot", "code": "", "error": ""})))
    f = dict.fromkeys(cfg.output.columns, "")
    f.update(name="Ana Founder", company="A", title="Founder", role="P1", country="Germany", contact_or_reference="https://www.linkedin.com/in/ana", evidence_source="https://a.de/work", qa_confidence="Medium")
    con.execute("INSERT INTO people (cycle_id, domain, fields_json, confidence, flags_json, llm_json) VALUES (?,?,?,?,?,?)",
                (cid, "a.de", json.dumps(f), "Medium", "[]", json.dumps({"role_family": "ceo", "priority": "P1", "why_this_person": "Owns it.", "commercial_route": "R1",
                                                                         "primary_commercial_problem": "x", "confidence": "Medium", "confidence_reason": "db", "flags": []})))
    con.execute("INSERT INTO source_yield (cycle_id, pipeline, source, screened, hits) VALUES (?, 'toy', 'rb:vfx', 300, 1)", (cid,))
    spend.record(con, cycle_id=cid, step_id="s", source="actor", actual_usd=0.1, results=5)
    at = run(page)
    assert not at.exception, [e.value for e in at.exception]


def test_the_pipelines_page_lists_and_validates(env):
    at = run(PIPELINES_PAGE)
    assert not at.exception
    assert any("toy" in e.label for e in at.expander)


def walk_wizard(path, mode, data, sop):
    at = AppTest.from_file(path, default_timeout=60)
    at.session_state["pl_view"] = "Wizard"
    at.session_state["wz"], at.session_state["wz_mode"], at.session_state["wz_sop"] = data, mode, sop
    for page in range(7):
        at.session_state["wz_page"] = page
        at.run()
        assert not at.exception, (page, [e.value for e in at.exception])
    return at


def test_every_wizard_page_renders_for_new_edit_and_clone(env):
    cfg = get_config("toy")
    for mode, data in (("new", wizard.template_dict()), ("edit", wizard.from_config(cfg)), ("clone", wizard.clone_dict(cfg, "toy_copy"))):
        walk_wizard(PIPELINES_PAGE, mode, data, {})


def test_the_wizard_saves_a_valid_new_pipeline_from_the_last_page(env):
    d = wizard.template_dict("saved_one", "Saved one")
    d["icp"]["description"] = "Architecture firms that publish AI-generated renders for named clients."
    at = walk_wizard(PIPELINES_PAGE, "new", d, {})
    assert any("valid" in s.value.lower() for s in at.success)
    save = next(b for b in at.button if b.label == "Save pipeline")
    assert not save.disabled
    save.click().run()
    assert not at.exception
    assert (env / "saved_one" / "pipeline.yaml").exists() and get_config("saved_one").title == "Saved one"


def test_the_wizard_refuses_to_save_an_invalid_or_duplicate_pipeline(env):
    bad = wizard.template_dict("bad_one", "Bad")
    bad["steps"][0]["step"] = "no_such_step"
    at = walk_wizard(PIPELINES_PAGE, "new", bad, {})
    assert next(b for b in at.button if b.label == "Save pipeline").disabled and any("no_such_step" in e.value for e in at.error)
    dup = wizard.template_dict("toy", "Duplicate")
    at = walk_wizard(PIPELINES_PAGE, "new", dup, {})
    assert next(b for b in at.button if b.label == "Save pipeline").disabled and any("already exists" in e.value for e in at.error)


def test_run_cycle_offers_a_custom_step_only_to_its_own_pipeline(env):
    from core import jobs
    (env / "toy" / "steps").mkdir(parents=True)
    (env / "toy" / "steps" / "mine.py").write_text(
        "from core.steps.base import Step, StepResult, register\n\n@register\nclass Mine(Step):\n    id = 'only_for_toy'\n    def run(self, ctx, params):\n        return StepResult()\n", encoding="utf-8")
    wizard.write_pipeline("other", wizard.to_yaml(wizard.template_dict("other", "Other")), {}, env)
    from core.steps.custom import reload_custom_steps
    reload_custom_steps()
    con = open_db()
    for name in ("toy", "other"):
        con.execute("INSERT OR IGNORE INTO pipelines (name, yaml_path) VALUES (?, 'x')", (name,))
        spend.create_cycle(con, get_config(name), 5, 3.0)
    at = AppTest.from_file(str(ROOT / "app" / "pages" / "2_Run_Cycle.py"), default_timeout=60)
    at.run()
    assert not at.exception
    pipeline_box = next(s for s in at.selectbox if s.label == "Pipeline")
    options = lambda: next(s for s in at.selectbox if s.label == "Step").options
    pipeline_box.select("toy").run()
    assert any("only_for_toy" in o for o in options())
    next(s for s in at.selectbox if s.label == "Pipeline").select("other").run()
    assert not any("only_for_toy" in o for o in options())
    assert jobs.reconcile(con) == []
