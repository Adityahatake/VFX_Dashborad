"""Key importer and read-only sheet mode. FakeSheet stands in for Google; no network, no real key, no real sheet."""
import pathlib

import pytest
from conftest_steps import CFG

from core import append as ap, gate, keyimport, keys, paths, sheets
from core.db import open_db, set_setting
from core.sheets import FakeSheet, ReadOnlySheet, SafeSheet

REPO = pathlib.Path(__file__).resolve().parent.parent
K1, K2, K3, K4 = ("apify_api_" + b for b in ("AAAA1111aaaaBBBB", "CCCC2222ccccDDDD", "EEEE3333eeeeFFFF", "GGGG4444ggggHHHH"))
SECRETS = ["owner@example.com", "hunter2-password", "recovery@example.org"]       # things that must never be read or printed
TAV = "tvly-" + "dev-zzzz9999"


def keys_sheet(extra_rows=None):
    hdr = ["email", "password", "recovery", "API Key", "notes", "Live Status (latest check)"]
    rows = [hdr,
            [SECRETS[0], SECRETS[1], SECRETS[2], K1, "n", "USABLE, $4.20 left of $5, resets 2026-12-01 (checked 2026-11-05 10:00 UTC)"],
            ["a@x.com", "pw", "r@x.com", K2, "", "LOW, $0.50 left of $5 (below $0.80 floor)"],
            ["b@x.com", "pw", "r@x.com", K3, "", "OUT OF CREDIT, resets 2026-12-01"],
            ["c@x.com", "pw", "r@x.com", "", "", ""],                                           # no key on this row
            ["d@x.com", "pw", "r@x.com", K1, "", "USABLE, $4.20 left (checked 2026-11-06 09:00 UTC)"],       # duplicate of K1
            ["e@x.com", "pw", "r@x.com", "not-an-apify-key", "", "USABLE, $9"],                 # wrong prefix
            ["f@x.com", "pw", "r@x.com", K4, "", "usable, $3.00 left"]]                         # lower-case 'usable' still counts
    return FakeSheet({"Apify": rows + (extra_rows or []), "Tavily": [["key", "x", "Live Status"], [TAV, "", "USABLE, 100 credits"]]})


def test_only_the_key_and_status_columns_are_requested():
    fs = keys_sheet()
    keyimport.read_candidates(fs, "apify")
    asked = [c[1] for c in fs.calls if c[0] == "get"]
    assert asked and all(r.endswith(("!D2:D2000", "!F2:F2000")) for r in asked), asked        # never A, B, C (emails, passwords) or E


def test_selection_keeps_only_usable_prefixed_unique_keys():
    cands, notes = keyimport.read_candidates(keys_sheet(), "apify")
    sel = keyimport.select_usable(cands, "apify")
    assert sel.keys == [K1, K4]                                                                  # K2 low, K3 out, blank skipped, K1 duplicate dropped, wrong prefix dropped
    assert sel.counts == {"rows_with_a_key": 6, "wrong_prefix": 1, "not_marked_usable": 2, "duplicates": 1, "already_in_env": 0, "selected": 2}
    assert any("2026-11-05" in n and "2026-11-06" in n and "re-checked live" in n for n in sel.notes)
    again = keyimport.select_usable(cands, "apify", existing={K1})
    assert again.keys == [K4] and again.counts["already_in_env"] == 1                            # keys already in .env are not added twice


def test_what_is_printed_never_contains_a_key_an_email_or_a_password():
    cands, _ = keyimport.read_candidates(keys_sheet(), "apify")
    text = "\n".join(keyimport.describe(keyimport.select_usable(cands, "apify")))
    assert "apify_api_AAAA" in text and "apify_api_GGGG" in text                                 # short ids
    for secret in [K1, K4, K1[10:], *SECRETS, "pw"]:
        assert secret not in text, secret


def test_a_missing_tab_is_a_note_not_a_crash():
    fs = FakeSheet({"Apify": keys_sheet().tabs["Apify"]})                                        # no "Apify Accounts" tab
    cands, notes = keyimport.read_candidates(fs, "apify")
    assert len(cands) == 6 and any("Apify Accounts" in n for n in notes)


def run_script(monkeypatch, tmp_path, argv, sheet=None):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("import_keys", REPO / "scripts" / "import_keys.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cred = tmp_path / "sa.json"
    cred.write_text("{}")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(cred))
    monkeypatch.setenv("KEYS_SHEET_ID", "KEYSSHEET")
    seen = {}

    def fake_sheets(sid, c, scope=None):
        seen["scope"] = scope
        return sheet or keys_sheet()
    monkeypatch.setattr(mod, "GoogleSheets", fake_sheets)
    return mod.main(argv), seen


def test_dry_run_changes_nothing_and_uses_a_read_only_token(monkeypatch, tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(paths, "ROOT", repo)
    monkeypatch.delenv("APIFY_TOKEN_POOL", raising=False)
    rc, seen = run_script(monkeypatch, tmp_path, [])
    out = capsys.readouterr().out
    assert rc == 0 and "dry run: nothing written" in out and seen["scope"] == sheets.SCOPE_READONLY
    assert not (repo / ".env").exists()
    assert K1 not in out and SECRETS[1] not in out


def test_write_adds_keys_backs_up_outside_the_repo_and_prints_no_key(monkeypatch, tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env").write_text("OTHER=1\nAPIFY_TOKEN_POOL=\n", encoding="utf-8")
    monkeypatch.setattr(paths, "ROOT", repo)
    monkeypatch.setenv("LPD_ENV_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.delenv("APIFY_TOKEN_POOL", raising=False)
    rc, _ = run_script(monkeypatch, tmp_path, ["--write"])
    out = capsys.readouterr().out
    env_text = (repo / ".env").read_text(encoding="utf-8")
    assert rc == 0 and f"APIFY_TOKEN_POOL={K1},{K4}" in env_text and "OTHER=1" in env_text
    assert list((tmp_path / "backups").glob("env_*.bak")) and "added 2 key(s)" in out
    for secret in (K1, K4, *SECRETS):
        assert secret not in out
    monkeypatch.setenv("APIFY_TOKEN_POOL", f"{K1},{K4}")
    rc, _ = run_script(monkeypatch, tmp_path, ["--write"])                                         # a rerun adds nothing
    assert "nothing to add" in capsys.readouterr().out and env_text == (repo / ".env").read_text(encoding="utf-8")


def test_the_script_refuses_to_run_without_credentials(monkeypatch, tmp_path, capsys):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("import_keys2", REPO / "scripts" / "import_keys.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("KEYS_SHEET_ID", raising=False)
    monkeypatch.setattr(mod.paths, "load_env", lambda *a, **k: None)
    assert mod.main([]) == 2


# ---------------------------------------------------------------- read-only sheet mode
LEAD_COLS = CFG.output.columns


def lead_sheet():
    row = ["Ana Founder", "Studio X", "Founder", "P1", "Germany", "", "", "AI spot", "", "why", "PASS-A", "PASS", "High", "Ready", "https://linkedin.com/in/ana", "Personal LinkedIn", "https://x.de"]
    return FakeSheet({"Linkedin": [list(LEAD_COLS), row], "X": [["name", "company"]], "Stage 32": [["name", "company"]]})


def test_read_only_wrapper_reads_but_can_never_write():
    fs = lead_sheet()
    ro = ReadOnlySheet(fs, "Linkedin")
    assert ro.get_values("Linkedin!A1:Q9")[0] == list(LEAD_COLS) and set(ro.tab_ids()) == {"Linkedin", "X", "Stage 32"}
    with pytest.raises(PermissionError, match="READ-ONLY"):
        ro.append("Linkedin", [["x"]])
    with pytest.raises(PermissionError, match="READ-ONLY"):
        ro.batch_update([{"repeatCell": {}}])
    assert not [c for c in fs.calls if c[0] in ("append", "batch_update")]


def test_dry_run_works_read_only_and_a_real_append_changes_nothing():
    fs = lead_sheet()
    ro = ReadOnlySheet(fs, "Linkedin")
    row = ["New Person", "New Co", "CEO", "P1", "Germany", "", "", "AI spot", "", "why", "PASS-A", "PASS", "Medium", "Ready", "https://linkedin.com/in/new-person", "Personal LinkedIn", "https://new.de"]
    rep = ap.dry_run(ro, CFG, [row])
    assert len(rep.added) == 1
    before = [list(r) for r in fs.tabs["Linkedin"]]
    with pytest.raises(PermissionError):
        ap.append_rows(ro, CFG, [row])
    assert fs.tabs["Linkedin"] == before and not [c for c in fs.calls if c[0] in ("append", "batch_update")]


def test_the_real_read_only_target_uses_a_read_only_token_and_no_sandbox_id(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    con = open_db(tmp_path / "t.sqlite")
    cred = tmp_path / "sa.json"
    cred.write_text("{}")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(cred))
    monkeypatch.setenv("GOOGLE_SHEET_ID", "REALSHEET")
    monkeypatch.delenv("SANDBOX_SHEET_ID", raising=False)
    assert sheets.TARGETS == ("sandbox", "real_readonly", "real")
    set_setting(con, "sheet_target", "real_readonly")
    client, label = sheets.get_client(con, CFG)
    assert isinstance(client, ReadOnlySheet) and client._inner.sid == "REALSHEET" and client._inner.scope == sheets.SCOPE_READONLY and "READ-ONLY" in label
    set_setting(con, "sheet_target", "real")
    client, label = sheets.get_client(con, CFG)
    assert isinstance(client, SafeSheet) and client._inner.scope == sheets.SCOPE and "READ-ONLY" not in label       # writes only after the explicit switch


def test_the_append_step_cannot_even_start_while_the_target_is_read_only(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    con = open_db(tmp_path / "t.sqlite")
    con.execute("INSERT INTO pipelines (name, yaml_path) VALUES ('vfx_genai','x')")
    from core import spend
    cid = spend.create_cycle(con, CFG, 5, 3.0)
    p = {"csv_name": "review.csv", "tag": "t", "expected_rows": 1}
    set_setting(con, "sheet_target", "real_readonly")
    g = gate.evaluate(con, CFG, cid, "append_sheet", p)
    assert not g.ok and "READ-ONLY" in g.blockers[0]
    with pytest.raises(gate.Blocked):
        gate.confirm_and_start(con, CFG, cid, "append_sheet", p, 0.0, None)
    set_setting(con, "sheet_target", "sandbox")
    assert gate.evaluate(con, CFG, cid, "append_sheet", p).ok
    set_setting(con, "sheet_target", "real_readonly")
    set_setting(con, "demo_mode", "1")                                                                # demo mode has its own in-memory sheet
    assert gate.evaluate(con, CFG, cid, "append_sheet", p).ok
