import json

import streamlit as st

from core import gate, jobs, paths
from core.registry import load_all
from core.db import open_db
from core.steps import all_steps
from core.steps.base import broken_steps

paths.load_env()
st.set_page_config(page_title="Jobs", layout="wide")
st.title("Jobs")
con = open_db()

changed = jobs.reconcile(con)
if changed:
    st.warning(f"Jobs {changed} were no longer running and are marked interrupted. Select one below and press Resume to continue from its checkpoint.")
for step_id, err in broken_steps().items():
    st.error(f"Custom step '{step_id}' failed to load: {err}")

with st.expander("Start a demo job (free, fake 2-minute step)", expanded=False):
    c1, c2, c3 = st.columns(3)
    dur = c1.number_input("Duration (s)", 5, 3600, 120)
    key = c2.text_input("Lease key (optional, e.g. demo_key)", "")
    fail = c3.number_input("Fail at tick (0 = never)", 0, 1000, 0)
    if st.button("Start demo job"):
        p = {"duration_s": int(dur), "lease_key": key or None, "fail_at": int(fail) or None}
        jid = jobs.start_job(con, "demo_slow", p)
        st.session_state["sel"] = jid
        st.success(f"Started job {jid}. It keeps running if you close this tab.")

ICON = {"queued": "…", "running": "▶", "done": "✔", "failed": "✖", "cancelled": "■", "interrupted": "⚠", "paused_quota": "⏸"}


@st.fragment(run_every=2)
def live():
    con = open_db()          # fragments run in their own thread; SQLite connections are per-thread
    jobs.reconcile(con)
    rows = jobs.list_jobs(con, 30)
    if not rows:
        st.info("No jobs yet.")
        return
    table = []
    for j in rows:
        hb = jobs.age_seconds(j["heartbeat_at"])
        table.append({"id": j["id"], "step": j["step_id"], "status": f"{ICON.get(j['status'], '')} {j['status']}" + (" (STUCK)" if jobs.is_stuck(j) else ""),
                      "pid": j["pid"], "started": j["started_at"], "heartbeat": f"{int(hb)}s ago" if hb is not None and j["status"] in jobs.LIVE else "",
                      "resumed": j["resumed_count"]})
    st.dataframe(table, hide_index=True, use_container_width=True)
    ids = [j["id"] for j in rows]
    sel = st.selectbox("Job", ids, index=ids.index(st.session_state["sel"]) if st.session_state.get("sel") in ids else 0, key="sel_box")
    st.session_state["sel"] = sel
    j = jobs.get_job(con, sel)
    b1, b2, b3, _ = st.columns([1.3, 1.3, 2, 3])
    if j["status"] in jobs.LIVE:
        if b1.button("Cancel", key=f"c{sel}", help="Graceful stop first; the process is killed after 15 s if it does not react."):
            jobs.request_cancel(con, sel)
        if jobs.is_stuck(j) and b3.button("Mark interrupted", key=f"m{sel}", help="No heartbeat: stop the process and make the job resumable."):
            jobs.mark_interrupted(con, sel)
    if j["status"] in jobs.RESUMABLE and j["kind"] in ("paid", "llm", "write"):
        # paid jobs go back through the cap / key / stop-rule gate before they may continue
        pipe = next((p.config for p in load_all() if p.config and p.config.name == (con.execute("SELECT pipeline FROM cycles WHERE id=?", (j["cycle_id"],)).fetchone() or [None])[0]), None)
        if pipe is None:
            st.warning("This paid job's cycle or pipeline is not available, so it cannot be resumed.")
        else:
            g = gate.evaluate(con, pipe, j["cycle_id"], j["step_id"], json.loads(j["params_json"] or "{}"))
            st.info(f"Resuming a {j['kind']} step: max ${g.estimate.max_usd:.3f} on {g.key_id or 'no key'}…, cycle cap remaining ${g.remaining:.3f}")
            for bl in g.blockers:
                st.error("Blocked: " + bl)
            if b2.button("Resume (re-checked)", key=f"r{sel}", disabled=not g.ok):
                try:
                    gate.confirm_and_resume(con, pipe, sel, g.estimate.max_usd, g.key_id)
                except gate.Blocked as e:
                    st.error("; ".join(e.blockers))
    elif j["status"] in jobs.RESUMABLE and b2.button("Resume", key=f"r{sel}", help="Continue from the checkpoint."):
        jobs.resume_job(con, sel)
    if j["cancel_requested"] and j["status"] in jobs.LIVE:
        st.caption("Cancel requested; waiting for the step to stop (killed after the grace period).")
    if j["error"]:
        st.error(j["error"])
    st.caption(f"Log: {j['log_path'] or 'not started'}")
    st.code(jobs.tail_log(sel, 40) or "(no output yet)", language="text")


live()
