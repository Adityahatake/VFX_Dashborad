import copy

import pytest
import yaml

from core import paths
from core.config import ConfigError, effective_cap, load_config, parse_config

VFX = paths.PIPELINES_DIR / "vfx_genai" / "pipeline.yaml"


def raw():
    return yaml.safe_load(VFX.read_text(encoding="utf-8"))


def bad(mutate):
    d = copy.deepcopy(raw())
    mutate(d)
    with pytest.raises(ConfigError) as e:
        parse_config(yaml.safe_dump(d))
    return e.value.problems


def test_vfx_loads():
    cfg = load_config(VFX)
    assert cfg.name == "vfx_genai"
    assert len(cfg.output.columns) == 17
    assert cfg.output.write_tab.name == "Linkedin"
    assert cfg.people.max_per_company == 3
    assert "India" in cfg.countries.excluded
    assert cfg.budget.hard_max_cycle_cap_usd == 3.0
    assert [s.stage for s in cfg.steps][-1] == "write"


def test_sop_files_exist():
    cfg = load_config(VFX)
    for f in cfg.sop_files:
        assert (VFX.parent / f).exists(), f


def test_cap_never_above_hard_max():
    cfg = load_config(VFX)
    assert effective_cap(cfg, None) == 3.0
    assert effective_cap(cfg, 10) == 3.0
    assert effective_cap(cfg, 1.5) == 1.5


def test_unknown_key_rejected():
    assert any("typo" in p for p in bad(lambda d: d.update(typo=1)))


def test_header_must_match_columns():
    assert any("header must equal" in p for p in bad(lambda d: d["output"].update(columns=list(reversed(d["output"]["columns"])))))


def test_dedupe_field_must_exist():
    assert any("dedupe field" in p for p in bad(lambda d: d["output"]["dedupe"].update(name_field="nope")))


def test_default_cap_over_hard_max():
    assert any("cannot exceed" in p for p in bad(lambda d: d["budget"].update(default_cycle_cap_usd=5)))


def test_country_overlap():
    assert any("approved and excluded" in p for p in bad(lambda d: d["countries"]["approved"].append("India")))


def test_needs_write_step_and_one_write_tab():
    assert any("write" in p for p in bad(lambda d: d.update(steps=[s for s in d["steps"] if s["stage"] != "write"])))
    assert any("exactly one tab" in p for p in bad(lambda d: d["output"]["tabs"][1].update(write=True, header=d["output"]["columns"])))


def test_bad_name_and_yaml():
    assert any("slug" in p for p in bad(lambda d: d.update(name="Bad Name")))
    with pytest.raises(ConfigError):
        parse_config("a: [unclosed")
    with pytest.raises(ConfigError):
        parse_config("- just\n- a list")
