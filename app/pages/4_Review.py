import json

import streamlit as st

from core import append as ap, fields as F, gate, jobs, keys, llm, paths, review, sheets, spend
from core.db import get_setting, open_db, set_setting
from core.registry import get_config

paths.load_env()
st.set_page_config(page_title="Review", layout="wide")
st.title("Review")
con = open_db()

active = con.execute("SELECT * FROM cycles WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
if not active:
    st.info("No active cycle. Start one on the Run Cycle page.")
    st.stop()
cid = active["id"]
cfg = get_config(active["pipeline"])
if cfg is None:
    st.error(f"Pipeline '{active['pipeline']}' is not loadable.")
    st.stop()
workdir = paths.DATA_DIR / "cycles" / str(cid)

if keys.is_demo(con):
    st.warning("DEMO MODE: the sheet below is an in-memory demo sheet, not Google Sheets.")
target = "demo" if keys.is_demo(con) else sheets.sheet_target(con)
st.caption(f"Cycle #{cid} · pipeline {cfg.name} · sheet target: **{target.upper()}**")

_res = llm.resolve(con, cfg)
if _res.on:
    st.caption(f"LLM assist is ON ({_res.model}, cap ${_res.cap_usd:.2f}). It only suggests: nothing is approved, rejected or appended by it. Run 'llm_verdicts' or 'llm_person_drafts' from Run Cycle.")
else:
    st.caption(f"Manual review: {_res.reason}.")

tab_c, tab_p, tab_s = st.tabs(["Companies", "People", "Sheet and append"])

# ------------------------------------------------------------------ companies
with tab_c:
    comps = con.execute("SELECT * FROM companies WHERE cycle_id=? ORDER BY CASE decision WHEN 'pending' THEN 0 WHEN 'look' THEN 1 ELSE 2 END, id", (cid,)).fetchall()
    pending = [c for c in comps if c["decision"] == "pending"]
    st.write(f"{len(pending)} pending · {sum(c['decision'] == 'approved' for c in comps)} approved · {sum(c['decision'] == 'rejected' for c in comps)} rejected · "
             f"{sum(c['decision'] == 'look' for c in comps)} need a look")
    show = st.radio("Show", ["pending + needs look", "all"], horizontal=True)
    for c in comps:
        if show != "all" and c["decision"] in ("approved", "rejected"):
            continue
        ev = review.company_evidence(c)
        with st.container(border=True):
            st.markdown(f"**{c['name']}** · `{c['domain']}` · {c['country'] or 'country unknown'} · source {c['source']} · _{c['decision']}_")
            for url, sent in (ev.get("ev") or [])[:3]:
                st.markdown(f"> {' '.join(sent.split())[:420]}")
                st.markdown(f"[{url}]({url})")
            if c["llm_json"]:
                st.info(review.llm_company_note(json.loads(c["llm_json"])))
            a, b, d, e = st.columns([1, 1, 1, 3])
            if a.button("Approve", key=f"ca{c['id']}"):
                review.decide_company(con, c["id"], "approved")
                st.rerun()
            if d.button("Needs look", key=f"cl{c['id']}"):
                review.decide_company(con, c["id"], "look")
                st.rerun()
            reason = e.selectbox("Reject reason", list(review.REJECT_REASONS), format_func=lambda k: review.REJECT_REASONS[k], key=f"cr{c['id']}", label_visibility="collapsed")
            if b.button("Reject", key=f"cx{c['id']}"):
                review.decide_company(con, c["id"], "rejected", reason)
                st.rerun()

# ------------------------------------------------------------------ people
with tab_p:
    people = con.execute("SELECT * FROM people WHERE cycle_id=? ORDER BY id", (cid,)).fetchall()
    if not people:
        st.info("No people yet. People arrive from pool_match (free) and, in phase 6, the paid people steps.")
    for pr in people:
        f = json.loads(pr["fields_json"])
        flags = json.loads(pr["flags_json"] or "[]") + review.draft_problems(cfg, f)
        with st.container(border=True):
            st.markdown(f"**{f.get('name')}** · {f.get('title')} · {f.get('company')} · {f.get('country')} · {f.get('role')} · confidence **{pr['confidence']}** · _{pr['decision']}_")
            for fl in dict.fromkeys(flags):
                st.warning(fl)
            if pr["llm_json"]:
                dr = json.loads(pr["llm_json"])
                if "why_this_person" in dr:
                    st.info(review.llm_person_note(dr))
                    if st.button("Use this suggestion (you still need to Approve)", key=f"us{pr['id']}"):
                        review.apply_person_suggestion(con, pr["id"])
                        st.rerun()
                elif dr.get("error"):
                    st.caption(f"LLM draft unavailable: {dr['error']}")
            with st.expander("Edit fields"):
                edited = {}
                for col in F.internal_columns(cfg):          # people fields use internal names; the sheet column names are applied when the row is built
                    edited[col] = st.text_area(col, f.get(col, ""), key=f"f{pr['id']}_{col}", height=68) if len(str(f.get(col, ""))) > 70 else st.text_input(col, f.get(col, ""), key=f"f{pr['id']}_{col}")
                if st.button("Save edits (resets the decision to pending)", key=f"sv{pr['id']}"):
                    review.update_person_fields(con, pr["id"], edited)
                    st.rerun()
            a, b, e = st.columns([1, 1, 3])
            blocked = bool(review.draft_problems(cfg, f))
            if a.button("Approve", key=f"pa{pr['id']}", disabled=blocked, help="Fix the draft problems above first" if blocked else None):
                review.decide_person(con, pr["id"], "approved")
                st.rerun()
            reason = e.selectbox("Reject reason", list(review.PERSON_REASONS), format_func=lambda k: review.PERSON_REASONS[k], key=f"pr{pr['id']}", label_visibility="collapsed")
            if b.button("Reject", key=f"px{pr['id']}"):
                review.decide_person(con, pr["id"], "rejected", reason)
                st.rerun()

# ------------------------------------------------------------------ sheet and append
with tab_s:
    try:
        client, label = sheets.get_client(con, cfg)
    except Exception as e:                      # missing env var, no credentials, ...
        st.error(str(e))
        st.stop()
    st.write(f"Connected to: **{label}**")
    if not keys.is_demo(con):
        t = st.radio("Sheet target", ["sandbox", "real"], index=0 if sheets.sheet_target(con) == "sandbox" else 1, horizontal=True)
        if t != sheets.sheet_target(con):
            if t == "real":
                word = st.text_input("To switch to the REAL shared sheet type REAL SHEET")
                if word == "REAL SHEET" and st.button("Switch to the real sheet"):
                    set_setting(con, "sheet_target", "real")
                    st.rerun()
            else:
                set_setting(con, "sheet_target", "sandbox")
                st.rerun()

    st.subheader("Baseline and progress")
    base = json.loads(active["baseline_json"]) if active["baseline_json"] else None
    if st.button("Take baseline now" if not base else "Retake baseline (only before appending anything)", disabled=bool(base) and spend.rows_appended(con, cid) > 0):
        con.execute("UPDATE cycles SET baseline_json=? WHERE id=?", (json.dumps(ap.take_baseline(client, cfg)), cid))
        st.rerun()
    if base:
        pg = ap.progress(base, spend.rows_appended(con, cid), client.get_values(cfg.output.write_tab.range))
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Baseline rows", pg["baseline"])
        c2.metric("Added by us (log)", pg["ours"], f"goal {active['goal_rows']}", delta_color="off")
        c3.metric("Rows on sheet now", pg["current"])
        c4.metric("Added by others", pg["added_by_others"], help="Reported, never counted as ours, never touched.")
    else:
        st.info("Take a baseline before appending, so progress is counted from it.")

    st.subheader("1. Build the review CSV")
    rows = review.approved_rows(con, cfg, cid)
    st.write(f"{len(rows)} approved people.")
    csv_path = workdir / "review.csv"
    if st.button("Build review CSV", disabled=not rows):
        ap.write_review_csv(csv_path, cfg.output.columns, rows)
        st.success(f"Wrote {csv_path.name} (UTF-8, no BOM, header + {len(rows)} rows).")
    if csv_path.exists():
        hdr, built = ap.read_review_csv(csv_path)
        st.dataframe([dict(zip(hdr, r)) for r in built], hide_index=True, use_container_width=True)

        st.subheader("2. Dry run (reads the sheet, writes nothing)")
        if st.button("Dry-run append"):
            try:
                rep = ap.dry_run(client, cfg, built)
                st.session_state["dry"] = {"rows": len(built), "add": len(rep.added), "skip": rep.skipped, "warn": rep.warnings}
            except ap.AppendStop as s:
                st.session_state["dry"] = {"stop": str(s)}
        dry = st.session_state.get("dry")
        if dry:
            if dry.get("stop"):
                st.error("Would stop: " + dry["stop"])
            else:
                st.success(f"Would add {dry['add']} of {dry['rows']} rows.")
                for c, n, why in dry["skip"]:
                    st.write(f"- skip **{n}** ({c}): {why}")
                for w in dry["warn"]:
                    st.warning(w)

        st.subheader("3. Append to the sheet")
        st.warning(f"This writes to **{label}**. Rows are appended in batches of {cfg.output.dedupe.batch_size}; the tabs are re-read before every batch; "
                   "nothing is ever retried, deleted or reordered.")
        typed = st.text_input(f"Type the number of rows to confirm ({len(built)})", key="typed_n")
        if st.button("Append to sheet", type="primary", disabled=typed.strip() != str(len(built)) or not dry or bool(dry.get("stop"))):
            try:
                jid = gate.confirm_and_start(con, cfg, cid, "append_sheet", {"csv_name": "review.csv", "tag": f"c{cid}", "expected_rows": len(built)}, 0.0, None)
                st.session_state["append_job"] = jid
                st.success(f"Started append job {jid}.")
            except gate.Blocked as e:
                st.error("Not started: " + "; ".join(e.blockers))
        jid = st.session_state.get("append_job")
        if jid:
            @st.fragment(run_every=2)
            def watch():
                c = open_db()
                j = jobs.get_job(c, jid)
                st.write(f"Job {jid}: **{j['status']}**")
                st.code(jobs.tail_log(jid, 25) or "(no output yet)")
                if j["error"]:
                    st.error(j["error"])
            watch()

    st.subheader("Recovery after a failed write")
    ev = con.execute("SELECT * FROM stop_events WHERE cycle_id=? AND rule='append_recovery' AND acknowledged_at IS NULL", (cid,)).fetchone()
    if ev:
        st.error(f"A write ended with an unknown outcome ({ev['reason']}). Appending is blocked until you run recovery.")
        unk = [p for p in workdir.glob("unknown_outcome_*.csv")]
        if unk and st.button("Read the sheet tail and find what landed"):
            _, rows_unk = ap.read_review_csv(unk[-1])
            landed, missing = ap.find_landed(client, cfg, rows_unk)
            st.write(f"{len(landed)} landed (rows {', '.join(str(n) for n, _ in landed) or 'none'}); {len(missing)} missing.")
            for n, r in landed:                                   # landed rows are ours: log them so progress counts them
                if not con.execute("SELECT 1 FROM appended_rows WHERE cycle_id=? AND row_number=? AND tab=?", (cid, n, cfg.output.write_tab.name)).fetchone():
                    review.record_append(con, cfg, cid, n, [r])
            if missing:
                mp = ap.write_missing_csv(workdir / "review_missing.csv", cfg, missing)
                st.success(f"Wrote {mp.name} with only the missing rows. Review it, dry-run it, and append it as a new batch.")
            spend.resolve_append_recovery(con, cid)
            st.info("Landed rows may need recolouring by hand if the colouring step did not run.")
    else:
        st.caption("No unresolved failures.")

    st.subheader("Cycle report")
    md = review.cycle_report_markdown(con, cfg, cid)
    st.download_button("Export report (Markdown)", md, file_name=f"cycle_{cid}_report.md", mime="text/markdown")
    with st.expander("Preview"):
        st.markdown(md)
