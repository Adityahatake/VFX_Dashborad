"""Sheet-safety tests (phase 5). Everything runs against FakeSheet, which reproduces the real API's trailing-cell trimming and its
'append lands after the first blank row' behaviour, with injectable failures. No network, no real sheet."""
import csv
import json
import os
import time
import urllib.error

import pytest
from conftest_steps import CFG, make_ctx

from core import append as ap, dedupe, http, jobs, paths, review, spend
from core.sheets import FakeSheet, GoogleSheets, SafeSheet, SheetsWriteError, a1_tab, col_index, col_letter
from core.steps.sheet_steps import AppendParams, AppendSheet

COLS = CFG.output.columns
W = CFG.output.write_tab.name


def mk(name, company, url=None, country="Germany", evidence="https://x.com/ai", **kw):
    d = dict.fromkeys(COLS, "")
    d.update(name=name, company=company, title="Founder", role="P1", country=country, ai_evidence="AI spot for a client", why_this_person="Owns the studio",
             qualification_decision="PASS-A", qa_decision="PASS", qa_confidence="High", outreach_readiness="Ready",
             contact_or_reference=url or f"https://linkedin.com/in/{name.lower().replace(' ', '-')}", contact_or_reference_type="Personal LinkedIn",
             evidence_source=evidence, **kw)
    return [d[c] for c in COLS]


def P(i):
    """A unique person name made only of letters (name_key strips digits, so 'Person1' and 'Person2' would be the same person)."""
    s = "".join(chr(97 + int(d)) for d in str(i))
    return f"Fn{s} Ln{s}"


def fresh(existing=None, **hooks):
    rows = [list(COLS)] + (existing if existing is not None else [mk("Anna Beispiel", "Neu Film"), mk("Full One", "Full Co"), mk("Full Two", "Full Co"), mk("Full Three", "Full Co")])
    fs = FakeSheet({W: rows, "X": [["name", "company"], ["Xavier Elsewhere", "Zed"]], "Stage 32": [["name", "company"], ["Stella Thirtytwo", "Studio Q"]]})
    for r in range(2, len(rows) + 1):
        fs.set_bg(W, r, (0.2, 0.8, 0.2))                       # other people's rows carry their own colour (green)
    return fs


def tab_snapshot(fs, tab):
    return [list(r) for r in fs.tabs[tab]]


# ---------------------------------------------------------------- fake sheet behaves like the API
def test_a1_helpers():
    assert [col_letter(n) for n in (1, 17, 26, 27, 30)] == ["A", "Q", "Z", "AA", "AD"] and col_index("AD") == 30
    assert a1_tab("'Stage 32'!A1:AC3000") == "Stage 32" and a1_tab("Linkedin!A1:Q9") == "Linkedin"


def test_fake_trims_trailing_cells_and_rows():
    fs = FakeSheet({"T": [["a", "b", ""], ["c", "", ""], [], ["", "", ""]]})
    assert fs.get_values("T!A1:C10") == [["a", "b"], ["c"]]


def test_fake_append_lands_after_the_first_blank_row_not_the_end():
    fs = FakeSheet({"T": [["h"], ["r1"], [], ["r3 after blank"]]})
    res = fs.append("T", [["new"]])
    assert res["updates"]["updatedRange"] == "'T'!A3:A3" and fs.tabs["T"][2] == ["new"] and fs.tabs["T"][3] == []     # lands mid-sheet: why blank rows must stop us


def test_safe_sheet_only_writes_the_write_tab_and_only_whitening():
    fs = fresh()
    ss = SafeSheet(fs, W)
    with pytest.raises(PermissionError):
        ss.append("X", [["a", "b"]])
    ids = fs.tab_ids()
    ok = {"repeatCell": {"range": {"sheetId": ids[W], "startRowIndex": 4, "endRowIndex": 5, "startColumnIndex": 0, "endColumnIndex": 17}, "cell": {"userEnteredFormat": {}}, "fields": "x"}}
    with pytest.raises(PermissionError, match="repeatCell"):
        ss.batch_update([{"deleteDimension": {"range": {"sheetId": ids[W], "dimension": "ROWS", "startIndex": 1, "endIndex": 3}}}])
    with pytest.raises(PermissionError, match="other than the write tab"):
        ss.batch_update([{"repeatCell": {**ok["repeatCell"], "range": {**ok["repeatCell"]["range"], "sheetId": ids["X"]}}}])
    with pytest.raises(PermissionError, match="one row at a time"):
        ss.batch_update([{"repeatCell": {**ok["repeatCell"], "range": {**ok["repeatCell"]["range"], "endRowIndex": 9}}}])
    ss.batch_update([ok])
    assert not any(hasattr(ss, n) for n in ("delete", "clear", "delete_rows", "sort", "update_values", "set_values"))   # no such operations exist


# ---------------------------------------------------------------- duplicate / cap / country rules
def check(rows, existing=None, mutate=None):
    fs = fresh(existing)
    if mutate:
        mutate(fs)
    st, _ = dedupe.read_state(SafeSheet(fs, W), CFG)
    return dedupe.check_rows(rows, CFG, st)


def why(rows, **kw):
    ok, rej = check(rows, **kw)
    return [r[2] for r in rej], ok


def test_duplicate_rules():
    w, _ = why([mk("Anna Beispiel", "Other Co", url="https://linkedin.com/in/anna-other")])
    assert "same person already on a tab" in w[0]                                           # same person under another company
    w, _ = why([mk("Änna Beispiel", "Brand New Co", url="https://linkedin.com/in/anna-b")])
    assert "same person" in w[0]                                                            # accent folded
    w, _ = why([mk("Thorsten Jasper Weese", "A Co", url="https://linkedin.com/in/tjw")], existing=[mk("Thorsten Weese", "B Co")])
    assert "same person" in w[0]                                                            # middle name
    w, _ = why([mk("Hans Poecksteiner", "A Co", url="https://linkedin.com/in/hp1")], existing=[mk("Hans Pöcksteiner", "B Co", url="https://linkedin.com/in/hp2")])
    assert "same person" in w[0]                                                            # umlaut spelling
    w, _ = why([mk("New Person", "New Co", url="https://de.linkedin.com/in/anna-beispiel/?x=1")])
    assert "same profile URL" in w[0]                                                       # url normalised: language subdomain, query, slash
    w, _ = why([mk("Xavier Elsewhere", "Zed", url="https://linkedin.com/in/xavier-e")])
    assert "same person" in w[0]                                                            # person on ANOTHER tab (X)
    w, ok = why([mk("Fresh Face", "Fresh Co")])
    assert w == [] and len(ok) == 1


def test_company_cap_counts_existing_rows_and_rows_earlier_in_the_batch():
    w, _ = why([mk("Fourth Person", "Full Co")])
    assert "already has 3 people" in w[0]
    batch = [mk(f"Person{c} Name", "Cap Co") for c in "ABCD"]
    ok, rej = check(batch)
    assert len(ok) == 3 and "already has 3" in rej[0][2]                                    # 4th in the same batch is refused


def test_same_person_twice_in_one_batch():
    ok, rej = check([mk("Dup Person", "A Co"), mk("Dup Person", "B Co", url="https://linkedin.com/in/dup-2")])
    assert len(ok) == 1 and "same person" in rej[0][2]


def test_country_evidence_url_and_shape_rules():
    assert "excluded country (India)" in why([mk("A One", "A Co", country="India")])[0][0]
    assert "excluded country" in why([mk("B One", "B Co", country="Mumbai, Maharashtra")])[0][0]        # city pattern
    assert "country not approved" in why([mk("C One", "C Co", country="Russia")])[0][0]
    assert why([mk("D One", "D Co", country="United States"), mk("E One", "E Co", country="UK"), mk("F One", "F Co", country="Germany (Berlin)")])[0] == []   # aliases OK
    assert "empty evidence_source" in why([mk("G One", "G Co", evidence="  ")])[0][0]
    assert "no personal profile URL" in why([mk("H One", "H Co", url="https://linkedin.com/company/hco")])[0][0]
    assert "malformed" in why([["only", "three", "cells"]])[0][0]


def test_stray_markers_and_empty_rows_on_the_sheet_are_ignored_not_fatal():
    fs = fresh()
    fs.tabs["X"].append(["2026-11-07", ""])            # a stray date typed in the name column
    fs.tabs["X"].append([])
    st, _ = dedupe.read_state(SafeSheet(fs, W), CFG)
    assert ("2026-11-07",) not in st.names and not any(k[0] == ("2026-11-07",) for k in st.pairs)      # the marker row has no company: skipped, not indexed
    ok, _ = dedupe.check_rows([mk("Fresh Face", "Fresh Co")], CFG, st)
    assert len(ok) == 1


# ---------------------------------------------------------------- the append itself
def run_append(fs, rows, **kw):
    landed = []
    rep = ap.append_rows(SafeSheet(fs, W), CFG, rows, on_landed=lambda a, r: landed.append((a, len(r))), **kw)
    return rep, landed


def test_happy_path_lands_verifies_whitens_only_our_rows_and_logs():
    fs = fresh()
    before_other_tabs = {t: tab_snapshot(fs, t) for t in ("X", "Stage 32")}
    old = tab_snapshot(fs, W)
    rows = [mk(P(i), f"Company{i}") for i in range(20)]
    rep, landed = run_append(fs, rows)
    assert len(rep.added) == 20 and rep.batches == 3 and [n for _, n in landed] == [8, 8, 4]           # batches of 8
    assert rep.added[0][0] == 6 and rep.added[-1][0] == 25 and rep.rows == "6-25"
    assert tab_snapshot(fs, W)[:5] == old                                                              # existing rows untouched, in order
    assert fs.get_values(f"{W}!A6:Q25") == [[c for c in r] for r in rows]
    assert {t: tab_snapshot(fs, t) for t in ("X", "Stage 32")} == before_other_tabs                    # other tabs untouched
    white = {r for (t, r), c in fs.bg.items() if c == (1, 1, 1)}
    assert white == set(range(6, 26))                                                                  # ONLY our rows are white
    assert all(fs.bg[(W, r)] == (0.2, 0.8, 0.2) for r in range(2, 6))                                  # the green rows kept their colour
    assert all(row in range(6, 26) and (c0, c1) == (0, 17) for (_, row, c0, c1) in fs.format_log)      # one row at a time, columns A..Q only


def test_tabs_are_reread_before_every_batch():
    fs = fresh()
    run_append(fs, [mk(P(i), f"Company{i}") for i in range(17)])
    seq = [c[0] for c in fs.calls]
    appends = [i for i, c in enumerate(seq) if c == "append"]
    assert len(appends) == 3
    prev = 0
    for i in appends:
        gets = [c for c in fs.calls[prev:i] if c[0] == "get"]
        assert {a1_tab(c[1]) for c in gets} >= {W, "X", "Stage 32"}, "all tabs must be re-read before each batch"
        prev = i


def test_other_writer_between_read_and_append_is_detected_and_our_rows_are_verified():
    fs = fresh()
    fs.before_append = lambda s: s.tabs[W].append(mk("Intruder One", "Intruder Co"))        # someone appends while we are about to
    rep, landed = run_append(fs, [mk("Mine One", "Mine Co")])
    assert rep.added[0][0] == 7 and any("someone else wrote" in w for w in rep.warnings)       # expected 6, landed at 7
    assert fs.get_values(f"{W}!A7:Q7")[0][0] == "Mine One" and fs.get_values(f"{W}!A6:Q6")[0][0] == "Intruder One"
    assert (W, 6) not in {(t, r) for (t, r), c in fs.bg.items() if c == (1, 1, 1)}               # the intruder's row was NOT recoloured
    assert fs.bg[(W, 7)] == (1, 1, 1)


def test_a_duplicate_added_by_someone_else_between_batches_is_caught_by_the_next_reread():
    fs = fresh()
    rows = [mk(P(i), f"Company{i}") for i in range(10)]        # batch 1: rows 0-7, batch 2: rows 8-9
    fs.before_append = lambda s: s.tabs[W].append(mk(P(9), "Another Co", url="https://linkedin.com/in/p9-other"))
    rep, _ = run_append(fs, rows)
    assert len(rep.added) == 9 and any(P(9) == n and "same person" in w for _, n, w in rep.skipped)


def test_blank_row_in_the_data_stops_everything_and_never_deletes():
    fs = fresh()
    fs.tabs[W].insert(3, [])                                                             # a blank row inside the data
    snap = tab_snapshot(fs, W)
    with pytest.raises(ap.AppendStop, match="never deletes"):
        run_append(fs, [mk("Mine One", "Mine Co")])
    assert tab_snapshot(fs, W) == snap and not [c for c in fs.calls if c[0] in ("append", "batch_update")]


def test_changed_header_stops():
    fs = fresh()
    fs.tabs[W][0][3] = "ROLE"
    with pytest.raises(ap.AppendStop, match="header does not match"):
        run_append(fs, [mk("Mine One", "Mine Co")])
    assert not [c for c in fs.calls if c[0] == "append"]


def test_write_error_before_landing_is_not_retried_and_leaves_the_sheet_alone():
    fs = fresh()
    fs.fail_append = "before"
    snap = tab_snapshot(fs, W)
    rows = [mk("Mine One", "Mine Co"), mk("Mine Two", "Mine Co2")]
    with pytest.raises(ap.AppendStop, match="Not retried") as e:
        run_append(fs, rows)
    assert [c for c in fs.calls if c[0] == "append"] == [("append", W, 2)]               # called exactly ONCE
    assert tab_snapshot(fs, W) == snap and len(e.value.unknown) == 2
    landed, missing = ap.find_landed(SafeSheet(fs, W), CFG, e.value.unknown)
    assert landed == [] and len(missing) == 2


def test_write_error_after_landing_recovery_finds_the_rows_and_never_duplicates():
    fs = fresh()
    fs.fail_append = "after"                                                              # the rows landed but the connection dropped
    rows = [mk("Mine One", "Mine Co"), mk("Mine Two", "Mine Co2"), mk("Mine Three", "Mine Co3")]
    with pytest.raises(ap.AppendStop) as e:
        run_append(fs, rows)
    assert [c for c in fs.calls if c[0] == "append"] == [("append", W, 3)]               # still only one call
    landed, missing = ap.find_landed(SafeSheet(fs, W), CFG, e.value.unknown)
    assert [n for n, _ in landed] == [6, 7, 8] and missing == []
    # a rerun of the same CSV must not add them again (dedupe), proving a naive retry would be harmless-but-blocked
    fs.fail_append = None
    rep, _ = run_append(fs, rows)
    assert rep.added == [] and len(rep.skipped) == 3


def test_partial_landing_offers_only_the_missing_rows(tmp_path):
    fs = fresh()
    rows = [mk("Mine One", "Mine Co"), mk("Mine Two", "Mine Co2"), mk("Mine Three", "Mine Co3")]
    fs.tabs[W].append(rows[0])                                                            # only the first row made it
    landed, missing = ap.find_landed(SafeSheet(fs, W), CFG, rows)
    assert [n for n, _ in landed] == [6] and [r[0] for r in missing] == ["Mine Two", "Mine Three"]
    p = ap.write_missing_csv(tmp_path / "missing.csv", CFG, missing)
    hdr, back = ap.read_review_csv(p)
    assert hdr == COLS and [r[0] for r in back] == ["Mine Two", "Mine Three"]


def test_whitening_failure_stops_without_retry_and_the_rows_are_still_logged_as_ours():
    fs = fresh()
    fs.fail_batch_update = True
    logged = []
    with pytest.raises(ap.AppendStop, match="recolour") as e:
        ap.append_rows(SafeSheet(fs, W), CFG, [mk("Mine One", "Mine Co")], on_landed=lambda a, r: logged.append(a))
    assert [c for c in fs.calls if c[0] == "batch_update"] == [("batch_update", 1)]      # once
    assert logged == [6] and e.value.landed[0][0] == 6 and e.value.report.unwhitened == [6]
    assert (W, 6) not in fs.bg or fs.bg[(W, 6)] != (1, 1, 1)


def test_read_back_mismatch_stops_and_does_not_log_the_rows():
    class Mangler(FakeSheet):
        def append(self, tab, values):
            return super().append(tab, [[c + "!" if i == 0 else c for i, c in enumerate(r)] for r in values])     # the sheet stored something else
    base = fresh()
    fs = Mangler(base.tabs)
    logged = []
    with pytest.raises(ap.AppendStop, match="read-back"):
        ap.append_rows(SafeSheet(fs, W), CFG, [mk("Mine One", "Mine Co")], on_landed=lambda a, r: logged.append(a))
    assert logged == [] and not [c for c in fs.calls if c[0] == "batch_update"]


def test_wrong_row_count_reported_stops():
    class Liar(FakeSheet):
        def append(self, tab, values):
            res = super().append(tab, values)
            res["updates"]["updatedRange"] = f"{tab}!A6:Q6"
            return res
    fs = Liar(fresh().tabs)
    with pytest.raises(ap.AppendStop, match="rows written"):
        run_append(fs, [mk("Mine One", "Mine Co"), mk("Mine Two", "Mine Co2")])


def test_cancel_between_batches_never_splits_a_batch():
    fs = fresh()
    n = {"c": 0}

    def cancel():
        n["c"] += 1
        if n["c"] > 1:
            raise RuntimeError("cancelled")
    with pytest.raises(RuntimeError):
        ap.append_rows(SafeSheet(fs, W), CFG, [mk(P(i), f"Company{i}") for i in range(20)], check_cancel=cancel)
    assert len(fs.tabs[W]) == 1 + 4 + 8                                                  # exactly one full batch of 8 landed


# ---------------------------------------------------------------- dry run
def test_dry_run_reports_without_writing_and_counts_earlier_batches():
    fs = fresh()
    rows = [mk(P(i), "Same Co") for i in range(5)] + [mk("Anna Beispiel", "Dup Co")]
    snap = tab_snapshot(fs, W)
    rep = ap.dry_run(SafeSheet(fs, W), CFG, rows)
    assert len(rep.added) == 3 and len(rep.skipped) == 3                                  # cap of 3 across the batch + the duplicate
    assert tab_snapshot(fs, W) == snap and not [c for c in fs.calls if c[0] in ("append", "batch_update")]
    fs.tabs[W].insert(2, [])
    with pytest.raises(ap.AppendStop):
        ap.dry_run(SafeSheet(fs, W), CFG, rows)                                           # the dry run reports the same stops


# ---------------------------------------------------------------- CSV, baseline, progress
def test_csv_is_utf8_without_bom_and_roundtrips(tmp_path):
    rows = [mk("Zoë Müller", "Café, \"Quoted\" Studio", evidence="https://x.com/a; https://y.com/b")]
    p = ap.write_review_csv(tmp_path / "r.csv", COLS, rows)
    raw = p.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and raw.decode("utf-8").splitlines()[0].startswith("name,company,title")
    hdr, back = ap.read_review_csv(p)
    assert hdr == COLS and back == rows
    (tmp_path / "bom.csv").write_bytes(b"\xef\xbb\xbf" + raw)
    assert ap.read_review_csv(tmp_path / "bom.csv")[0] == COLS                            # a BOM from another tool is tolerated on read


def test_baseline_and_progress_separate_ours_from_others():
    fs = fresh()
    client = SafeSheet(fs, W)
    base = ap.take_baseline(client, CFG)
    assert base["data_rows"] == 4 and base["last_row"] == 5 and base["last_row_name"] == "Full Three"
    run_append(fs, [mk("Mine One", "Mine Co"), mk("Mine Two", "Mine Co2")])
    fs.tabs[W].append(mk("Other Writer", "Other Co"))
    pg = ap.progress(base, 2, client.get_values(CFG.output.write_tab.range))
    assert pg == {"baseline": 4, "ours": 2, "current": 7, "added_by_others": 1}


# ---------------------------------------------------------------- real client request shape (mocked HTTP)
def test_real_client_never_retries_a_write_and_shapes_requests(monkeypatch, tmp_path):
    calls = []

    def fake_request(url, *, key=None, body=None, timeout=40):
        calls.append((url, body))
        if body is not None:
            raise ConnectionError("dropped")
        return {"values": [["a"]]}
    monkeypatch.setattr(http, "request_json", fake_request)
    g = GoogleSheets("SID", tmp_path / "nofile.json")
    monkeypatch.setattr(g, "_token", lambda: "tok")
    assert g.get_values("'Stage 32'!A1:AC3000") == [["a"]] and "%27Stage%2032%27%21A1%3AAC3000" in calls[0][0]
    with pytest.raises(SheetsWriteError, match="may or may not"):
        g.append("Linkedin", [["x"]])
    assert len(calls) == 2 and "valueInputOption=RAW" in calls[1][0] and "insertDataOption=INSERT_ROWS" in calls[1][0] and calls[1][1]["values"] == [["x"]]
    with pytest.raises(SheetsWriteError):
        g.batch_update([{"repeatCell": {}}])
    assert len(calls) == 3                                                                # each write attempted exactly once


def test_http_layer_retries_reads_but_never_posts(monkeypatch):
    n = {"get": 0, "post": 0}

    class Resp:
        def __init__(self, d): self.d = d
        def read(self, *a): return json.dumps(self.d).encode()

    def fake_open(req, timeout=None):
        if req.get_method() == "POST":
            n["post"] += 1
            raise urllib.error.HTTPError(req.full_url, 503, "x", {}, None)
        n["get"] += 1
        if n["get"] < 3:
            raise urllib.error.HTTPError(req.full_url, 503, "x", {}, None)
        return Resp({"ok": 1})
    monkeypatch.setattr(http.urllib.request, "urlopen", fake_open)
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    monkeypatch.setattr(http.json, "load", lambda r: r.d)
    assert http.get_json("https://x") == {"ok": 1} and n["get"] == 3
    with pytest.raises(urllib.error.HTTPError):
        http.post_json("https://x", {"a": 1})
    assert n["post"] == 1


# ---------------------------------------------------------------- the append_sheet step (in process)
def step_env(tmp_path, fs, rows):
    ctx, con, logs = make_ctx(tmp_path, cycle_id=None, sheet=SafeSheet(fs, W))
    con.execute("INSERT INTO pipelines (name, yaml_path) VALUES ('vfx_genai','x')")
    cid = spend.create_cycle(con, CFG, 20, 3.0)
    ctx.cycle_id = cid
    ap.write_review_csv(ctx.workdir / "review.csv", COLS, rows)
    return ctx, con, logs, cid


def test_append_step_success_logs_ours_and_writes_log_files(tmp_path):
    fs = fresh()
    rows = [mk("Mine One", "Mine Co"), mk("Anna Beispiel", "Dup Co", url="https://linkedin.com/in/anna-dup"), mk("Mine Three", "Mine Co3")]
    ctx, con, logs, cid = step_env(tmp_path, fs, rows)
    r = AppendSheet().run(ctx, AppendParams(csv_name="review.csv", tag="t1", expected_rows=3))
    assert r.counts == {"added": 2, "skipped": 1}
    assert [(x["row_number"], x["name"]) for x in con.execute("SELECT * FROM appended_rows ORDER BY row_number")] == [(6, "Mine One"), (7, "Mine Three")]
    assert spend.rows_appended(con, cid) == 2
    assert any("same person" in line for line in logs)
    files = {p.name for p in ctx.workdir.iterdir()}
    assert any(f.startswith("new_people_") for f in files) and "t1_rejected.csv" in files
    for f in ctx.workdir.glob("*.csv"):
        assert not f.read_bytes().startswith(b"\xef\xbb\xbf")


def test_append_step_refuses_a_row_count_mismatch_or_a_wrong_header(tmp_path):
    fs = fresh()
    ctx, con, logs, cid = step_env(tmp_path, fs, [mk("Mine One", "Mine Co")])
    with pytest.raises(ValueError, match="you confirmed 5"):
        AppendSheet().run(ctx, AppendParams(csv_name="review.csv", expected_rows=5))
    ap.write_review_csv(ctx.workdir / "bad.csv", COLS[::-1], [])
    with pytest.raises(ValueError, match="header"):
        AppendSheet().run(ctx, AppendParams(csv_name="bad.csv", expected_rows=1))
    assert not [c for c in fs.calls if c[0] == "append"]


def test_unknown_outcome_blocks_everything_until_recovery(tmp_path):
    fs = fresh()
    fs.fail_append = "after"
    rows = [mk("Mine One", "Mine Co"), mk("Mine Two", "Mine Co2")]
    ctx, con, logs, cid = step_env(tmp_path, fs, rows)
    with pytest.raises(ap.AppendStop):
        AppendSheet().run(ctx, AppendParams(csv_name="review.csv", tag="t", expected_rows=2))
    ev = con.execute("SELECT * FROM stop_events WHERE rule='append_recovery'").fetchone()
    assert ev and (ctx.workdir / "unknown_outcome_t.csv").exists()
    fs.fail_append = None
    with pytest.raises(RuntimeError, match="run recovery"):
        AppendSheet().run(ctx, AppendParams(csv_name="review.csv", tag="t", expected_rows=2))      # blocked
    with pytest.raises(ValueError, match="recovery"):
        spend.acknowledge(con, ev["id"])                                                           # cannot be waved through on the Spend page
    assert len([c for c in fs.calls if c[0] == "append"]) == 1
    spend.resolve_append_recovery(con, cid)
    r = AppendSheet().run(ctx, AppendParams(csv_name="review.csv", tag="t", expected_rows=2))      # after recovery: dedupe sees the landed rows
    assert r.counts == {"added": 0, "skipped": 2}


# ---------------------------------------------------------------- review logic
def pm_candidate(**k):
    c = {"first": "Ben", "last": "Creative", "title": "Creative Director", "family": "creative", "linkedin_url": "https://linkedin.com/in/ben", "lead_domain": "neufilm.de",
         "sheet_company": "Neu Film", "sheet_country": "Germany", "domain_differs": False, "existing": [("Anna Beispiel", "Founder", "P1")],
         "existing_row": dict(zip(COLS, mk("Anna Beispiel", "Neu Film", evidence="https://neufilm.de/ai; https://neufilm.de/impressum")))}
    c.update(k)
    return c


def test_pool_match_candidates_become_pending_people_with_honest_flags(tmp_path):
    ctx, con, _ = make_ctx(tmp_path)
    con.execute("INSERT INTO pipelines (name, yaml_path) VALUES ('vfx_genai','x')")
    cid = spend.create_cycle(con, CFG, 5, 3.0)
    n = review.people_from_pool_match(con, CFG, cid, [pm_candidate(), pm_candidate(domain_differs=True, linkedin_url="https://linkedin.com/in/dan", first="Dan")])
    assert n == 2 and review.people_from_pool_match(con, CFG, cid, [pm_candidate()]) == 0               # same LinkedIn URL: not added twice
    rows = con.execute("SELECT * FROM people ORDER BY id").fetchall()
    f = json.loads(rows[0]["fields_json"])
    assert (f["name"], f["company"], f["role"], f["qa_confidence"], f["country"]) == ("Ben Creative", "Neu Film", "P2", "Medium", "Germany")
    assert f["evidence_source"] == "https://neufilm.de/ai; https://neufilm.de/impressum; https://linkedin.com/in/ben" and f["ai_evidence"] == "AI spot for a client"
    flags = json.loads(rows[1]["flags_json"])
    assert flags[0].startswith("DOMAIN DIFFERS") and any("Medium" in x for x in flags)
    assert review.draft_problems(CFG, f)                                                               # the why_this_person draft blocks approval until edited
    f["why_this_person"] = "Runs creative direction on the studio's AI commercials."
    assert any("primary_commercial_problem" in x for x in review.draft_problems(CFG, f))      # the commercial-route hypothesis must be written too
    f["primary_commercial_problem"] = "Hypothesis R1: adding AI to film work."
    assert review.draft_problems(CFG, f) == []


def test_decisions_need_reasons_and_rejections_are_remembered(tmp_path):
    ctx, con, _ = make_ctx(tmp_path)
    con.execute("INSERT INTO pipelines (name, yaml_path) VALUES ('vfx_genai','x')")
    cid = spend.create_cycle(con, CFG, 5, 3.0)
    con.execute("INSERT INTO companies (cycle_id, domain, name) VALUES (?, 'bad.com', 'Bad')", (cid,))
    co = con.execute("SELECT id FROM companies").fetchone()[0]
    with pytest.raises(ValueError):
        review.decide_company(con, co, "rejected")
    with pytest.raises(ValueError):
        review.decide_company(con, co, "maybe")
    review.decide_company(con, co, "rejected", "tool_vendor")
    assert con.execute("SELECT status FROM known_domains WHERE domain='bad.com'").fetchone()[0] == "rejected"
    con.execute("INSERT INTO people (cycle_id, fields_json) VALUES (?, '{}')", (cid,))
    with pytest.raises(ValueError):
        review.decide_person(con, 1, "rejected", "nonsense")


def test_only_approved_people_reach_the_csv_and_report_is_exportable(tmp_path):
    ctx, con, _ = make_ctx(tmp_path)
    con.execute("INSERT INTO pipelines (name, yaml_path) VALUES ('vfx_genai','x')")
    cid = spend.create_cycle(con, CFG, 5, 3.0)
    review.people_from_pool_match(con, CFG, cid, [pm_candidate()])
    assert review.approved_rows(con, CFG, cid) == []
    review.decide_person(con, 1, "approved")
    rows = review.approved_rows(con, CFG, cid)
    assert len(rows) == 1 and len(rows[0]) == 17
    md = review.cycle_report_markdown(con, CFG, cid)
    assert "Ben Creative" in md and "Borderline" in md and "Medium" in md


# ---------------------------------------------------------------- end to end: gate -> real worker process -> demo sheet
@pytest.fixture()
def demo_env(tmp_path, monkeypatch):
    from core.db import open_db, set_setting
    monkeypatch.setenv("LPD_DATA", str(tmp_path))
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "dashboard.sqlite")
    con = open_db()
    set_setting(con, "demo_mode", "1")
    con.execute("INSERT INTO pipelines (name, yaml_path) VALUES ('vfx_genai','x')")
    yield con
    for j in con.execute("SELECT pid FROM jobs").fetchall():
        if j["pid"] not in (os.getpid(), 1) and jobs.pid_alive(j["pid"]):
            jobs.kill_tree(j["pid"])


def test_append_runs_as_a_real_worker_job_against_the_demo_sheet(demo_env):
    from core import gate, sheets
    con = demo_env
    cid = spend.create_cycle(con, CFG, 5, 3.0)
    wd = paths.DATA_DIR / "cycles" / str(cid)
    rows = [mk("Mine One", "Mine Co"), mk("Anna Beispiel", "Dup Co", url="https://linkedin.com/in/anna-dup"), mk("Mine Three", "Mine Co3")]
    ap.write_review_csv(wd / "review.csv", COLS, rows)
    p = {"csv_name": "review.csv", "tag": "e2e", "expected_rows": 3}
    with pytest.raises(PermissionError):
        jobs.create_job(con, "append_sheet", p, cid)                                         # a write step cannot start without the gate
    jid = gate.confirm_and_start(con, CFG, cid, "append_sheet", p, 0.0, None)
    t0 = time.time()
    while jobs.get_job(con, jid)["status"] not in ("done", "failed") and time.time() - t0 < 40:
        time.sleep(0.3)
    j = jobs.get_job(con, jid)
    assert j["status"] == "done", jobs.tail_log(jid)
    demo = sheets.FakeSheet.load(paths.DATA_DIR / sheets.DEMO_TABS_FILE, {})
    assert [r[0] for r in demo.tabs[W][-2:]] == ["Mine One", "Mine Three"] and len(demo.tabs[W]) == 7        # 5 demo rows + 2 appended
    assert {r for (t, r), c in demo.bg.items() if c == (1, 1, 1)} == {6, 7}                                   # only our rows white
    assert [(r["row_number"], r["name"]) for r in con.execute("SELECT * FROM appended_rows ORDER BY row_number")] == [(6, "Mine One"), (7, "Mine Three")]
    assert "same person" in jobs.tail_log(jid)


# ---------------------------------------------------------------- which sheet is used
def test_sheet_target_defaults_to_sandbox_and_never_falls_back_to_the_real_sheet(tmp_path, monkeypatch):
    from core import sheets
    from core.db import open_db, set_setting
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    con = open_db(tmp_path / "t.sqlite")
    monkeypatch.delenv("SANDBOX_SHEET_ID", raising=False)
    monkeypatch.setenv("GOOGLE_SHEET_ID", "REAL_SHEET_ID_123")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "sa.json"))
    (tmp_path / "sa.json").write_text("{}")
    assert sheets.sheet_target(con) == "sandbox"
    with pytest.raises(RuntimeError, match="SANDBOX_SHEET_ID is not set"):           # the real ID is set, but sandbox mode must not use it
        sheets.get_client(con, CFG)
    monkeypatch.setenv("SANDBOX_SHEET_ID", "SANDBOX_ID_456")
    client, label = sheets.get_client(con, CFG)
    assert client._inner.sid == "SANDBOX_ID_456" and "SANDBOX" in label
    set_setting(con, "sheet_target", "real")
    client, label = sheets.get_client(con, CFG)
    assert client._inner.sid == "REAL_SHEET_ID_123" and "REAL" in label
    set_setting(con, "demo_mode", "1")                                                # demo mode always wins: no Google call is possible
    client, label = sheets.get_client(con, CFG)
    assert isinstance(client._inner, sheets.FakeSheet) and "DEMO" in label
