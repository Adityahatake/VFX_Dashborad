import importlib.util
import json
from pathlib import Path

from core import known, paths
from core.db import open_db

spec = importlib.util.spec_from_file_location("import_vfx_history", Path(__file__).resolve().parent.parent / "scripts" / "import_vfx_history.py")
imp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(imp)


def make_vfx(root: Path):
    d = root / "data"
    d.mkdir(parents=True)
    (d / "pool_a.json").write_text(json.dumps([{"organization_primary_domain": "www.PoolCo.com"}, {"organization_primary_domain": ""}]))
    (d / "x_crawl.jsonl").write_text(json.dumps({"domain": "crawled.com", "score": 0}) + "\nnot json\n")
    (d / "b1_rejected.csv").write_text("Rejected Co,Some Person,reason\nrej-domain.com,,x\n", encoding="utf-8")
    (d / "candidates_1.csv").write_text("company,domain\nCand Studio,cand.tv\n", encoding="utf-8")
    (d / "spend_n1.log").write_text("2026-10-28 c19people microworlds~leads-finder key=apify_api_ZoxD.. results=40 est_cost=$0.120 status=SUCCEEDED\n"
                                    "garbage line\n", encoding="utf-8")
    return root


def test_import_is_read_only_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data")
    vfx = make_vfx(tmp_path / "vfx")
    before = {p: p.read_bytes() for p in (vfx / "data").iterdir()}
    con = open_db(tmp_path / "t.sqlite")
    con.execute("INSERT INTO pipelines (name, yaml_path) VALUES ('vfx_genai','x')")
    c1 = imp.run(con, vfx, "vfx_genai")
    assert c1["pool_files"] == 1 and c1["pooled_domains"] == 1 and c1["spend_lines"] == 1 and c1["spend_unparsed"] == 1
    assert {"poolco.com", "crawled.com", "rej-domain.com", "cand.tv"} <= known.seen_domains(con, "vfx_genai")
    assert {"rejected", "cand"} <= known.known_names(con, "vfx_genai")                # "Rejected Co" / "Cand Studio" with filler words stripped
    assert (paths.DATA_DIR / "vfx_genai" / "pools" / "pool_a.json").exists()
    led = con.execute("SELECT * FROM spend_ledger").fetchall()
    assert len(led) == 1 and led[0]["actual_usd"] == 0.12 and led[0]["cycle_id"] is None and led[0]["key_prefix"] == "apify_api_ZoxD"
    snapshot = (con.execute("SELECT COUNT(*) FROM known_domains").fetchone()[0], con.execute("SELECT COUNT(*) FROM known_names").fetchone()[0])
    imp.run(con, vfx, "vfx_genai")                                                  # rerun: nothing duplicated
    assert (con.execute("SELECT COUNT(*) FROM known_domains").fetchone()[0], con.execute("SELECT COUNT(*) FROM known_names").fetchone()[0]) == snapshot
    assert con.execute("SELECT COUNT(*) FROM spend_ledger").fetchone()[0] == 1
    assert {p: p.read_bytes() for p in (vfx / "data").iterdir()} == before          # the VFX folder is untouched


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data")
    vfx = make_vfx(tmp_path / "vfx")
    con = open_db(tmp_path / "t.sqlite")
    imp.run(con, vfx, "vfx_genai", dry=True)
    assert con.execute("SELECT COUNT(*) FROM known_domains").fetchone()[0] == 0
    assert not (paths.DATA_DIR / "vfx_genai").exists()
