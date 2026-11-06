import json

import streamlit as st

from core import gate, keys, paths, spend
from core.config import effective_cap
from core.db import get_setting, open_db
from core.registry import load_all
from core.steps import all_steps

paths.load_env()
st.set_page_config(page_title="Run Cycle", layout="wide")
st.title("Run Cycle")
con = open_db()
if keys.is_demo(con):
    st.warning("DEMO MODE: fake keys and mocked paid steps. No network calls, no real spending.")

pipes = {p.config.name: p.config for p in load_all() if p.config}
if not pipes:
    st.error("No valid pipeline found.")
    st.stop()

st.subheader("1. Cycle")
name = st.selectbox("Pipeline", list(pipes))
cfg = pipes[name]
active = con.execute("SELECT * FROM cycles WHERE pipeline=? AND status='active' ORDER BY id DESC LIMIT 1", (name,)).fetchone()

if active is None:
    c1, c2 = st.columns(2)
    goal = c1.number_input("Goal (rows)", 1, 1000, 20)
    default_cap = min(float(get_setting(con, "default_cap_usd", str(cfg.budget.default_cycle_cap_usd))), cfg.budget.hard_max_cycle_cap_usd)
    cap = c2.number_input(f"Spend cap (USD, never above ${cfg.budget.hard_max_cycle_cap_usd:.2f})", 0.05, 1000.0, default_cap, step=0.25)
    if cap > cfg.budget.hard_max_cycle_cap_usd:
        st.warning(f"The cap will be limited to ${effective_cap(cfg, cap):.2f}.")
    if st.button("Start cycle", type="primary"):
        cid = spend.create_cycle(con, cfg, int(goal), cap)
        st.success(f"Cycle #{cid} started with cap ${effective_cap(cfg, cap):.2f}.")
        st.rerun()
    st.caption("The sheet baseline is taken from the Google Sheet when the Sheets client arrives (phase 5).")
    st.stop()

cid = active["id"]
a, b, c, d = st.columns(4)
a.metric("Cycle", f"#{cid}")
b.metric("Goal rows", active["goal_rows"])
c.metric("Spent / cap", f"${spend.cycle_spend(con, cid):.3f} / ${active['cap_usd']:.2f}")
d.metric("Remaining", f"${spend.remaining_cap(con, cid):.3f}")
with st.expander("End this cycle"):
    if st.button("End cycle now"):
        con.execute("UPDATE cycles SET status='ended', ended_at=CURRENT_TIMESTAMP WHERE id=?", (cid,))
        st.rerun()

open_ev = spend.sync_stop_events(con, cfg, cid)
for ev in open_ev:
    st.error(f"Stop rule '{ev['rule']}': {ev['reason']}. Paid steps are blocked until acknowledged on the Spend page.")

st.subheader("2. Run a step")
steps = all_steps()
sid = st.selectbox("Step", list(steps), format_func=lambda s: f"{s}  [{steps[s].kind}]  {steps[s].title}")
step = steps[sid]
try:
    default = step.params_model().model_dump()
except Exception:
    default = {}
raw = st.text_area("Parameters (JSON)", json.dumps(default, indent=2), height=140, key=f"p_{sid}")
try:
    params = json.loads(raw or "{}")
    step.params_model(**params)
except Exception as e:
    st.error(f"Parameters are not valid: {e}")
    st.stop()

g = gate.evaluate(con, cfg, cid, sid, params)

if step.kind == "free":
    if st.button("Run (free)"):
        from core import jobs
        jid = jobs.start_job(con, sid, params, cid)
        st.success(f"Started job {jid}. Watch it on the Jobs page.")
else:
    st.markdown(f"#### Before this {step.kind} step runs")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Maximum cost", f"${g.estimate.max_usd:.3f}", g.estimate.note, delta_color="off")
    m2.metric("Key it will use", (g.key_id or "none") + ("…" if g.key_id else ""))
    m3.metric("Key balance", f"${g.key_balance:.2f}" if g.key_balance is not None else "n/a")
    m4.metric("Cycle cap remaining", f"${g.remaining:.3f}", f"after this run (worst case): ${g.remaining - g.estimate.max_usd:.3f}", delta_color="off")
    for w in g.warnings:
        st.warning(w)
    for bl in g.blockers:
        st.error("Blocked: " + bl)
    ok = st.checkbox(f"I confirm: run this {step.kind} step with a maximum cost of ${g.estimate.max_usd:.3f} on {g.key_id}…", disabled=not g.ok, key=f"ok_{sid}")
    if st.button(f"Run {step.kind} step", type="primary", disabled=not (g.ok and ok)):
        try:
            jid = gate.confirm_and_start(con, cfg, cid, sid, params, g.estimate.max_usd, g.key_id)
            st.success(f"Started job {jid} on {g.key_id}… Watch it on the Jobs page.")
        except gate.Blocked as e:
            st.error("Not started: " + "; ".join(e.blockers))
