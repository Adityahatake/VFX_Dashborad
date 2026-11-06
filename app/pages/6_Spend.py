import streamlit as st

from core import keys, paths, spend
from core.db import open_db
from core.registry import load_all

paths.load_env()
st.set_page_config(page_title="Spend", layout="wide")
st.title("Spend")
con = open_db()
if keys.is_demo(con):
    st.warning("DEMO MODE: amounts below come from mocked steps, not real spending.")

cfgs = {p.config.name: p.config for p in load_all() if p.config}
cycles = con.execute("SELECT * FROM cycles ORDER BY id DESC").fetchall()
if not cycles:
    st.info("No cycles yet. Create one on the Run Cycle page.")
    st.stop()

sel = st.selectbox("Cycle", [c["id"] for c in cycles], format_func=lambda i: next(f"#{c['id']}  {c['pipeline']}  ({c['status']})" for c in cycles if c["id"] == i))
cyc = next(c for c in cycles if c["id"] == sel)
cfg = cfgs.get(cyc["pipeline"])

spent, resv = spend.cycle_spend(con, sel), spend.reserved(con, sel)
a, b, c, d = st.columns(4)
a.metric("This cycle", f"${spent:.3f}", f"cap ${cyc['cap_usd']:.2f}", delta_color="off")
b.metric("Reserved by running jobs", f"${resv:.3f}")
c.metric("Remaining under cap", f"${spend.remaining_cap(con, sel):.3f}")
d.metric("Today (all cycles)", f"${spend.today_spend(con):.3f}")
st.progress(min(1.0, (spent + resv) / cyc["cap_usd"]) if cyc["cap_usd"] else 0.0, text=f"${spent + resv:.3f} of ${cyc['cap_usd']:.2f} used or reserved")

rows_n, cpr = max(spend.rows_appended(con, sel), spend.rows_approved(con, sel)), spend.cost_per_row(con, sel)
pr, decided = spend.pass_rate(con, sel)
e, f, g = st.columns(3)
e.metric("Rows (approved or appended)", rows_n, f"goal {cyc['goal_rows']}", delta_color="off")
f.metric("Cost per final row", f"${cpr:.2f}" if cpr is not None else "n/a")
g.metric("Pass rate", f"{pr:.1%}" if pr is not None else "n/a", f"{decided} reviewed (needs {spend.MIN_DECIDED_FOR_PASS_RATE})", delta_color="off")

st.subheader("Stop rules")
if cfg is None:
    st.error(f"Pipeline '{cyc['pipeline']}' is not loadable, so stop rules cannot be evaluated.")
else:
    sr = cfg.budget.stop_rules
    st.caption(f"Cost per row over ${sr.max_cost_per_row:.2f} · pass rate under {sr.min_pass_rate:.0%} · usable credit under ${sr.min_usable_credit:.2f} · "
               f"{sr.low_yield_cycles} cycles in a row under {sr.low_yield_rows} rows. Never lower the quality bar to hit a number.")
    open_ev = spend.sync_stop_events(con, cfg, sel) if cyc["status"] == "active" else []
    if not open_ev:
        st.success("No stop rule is blocking paid steps.")
    for ev in open_ev:
        st.error(f"**{ev['rule']}**: {ev['reason']}. Paid steps are disabled until you acknowledge this.")
        if st.button("Acknowledge and allow paid steps", key=f"ack{ev['id']}"):
            spend.acknowledge(con, ev["id"])
            st.rerun()
    done = con.execute("SELECT * FROM stop_events WHERE cycle_id=? AND acknowledged_at IS NOT NULL ORDER BY id", (sel,)).fetchall()
    if done:
        st.caption("Acknowledged: " + "; ".join(f"{e['rule']} ({e['acknowledged_at']})" for e in done))

st.subheader("By source")
src = spend.by_source(con, sel)
if src:
    st.dataframe([{"source": r["source"], "kind": r["kind"], "calls": r["calls"], "usd": round(r["usd"] or 0, 4), "results": r["results"]} for r in src],
                 hide_index=True, use_container_width=True)
else:
    st.caption("No spend recorded yet.")

st.subheader("LLM spend (separate cap)")
if cfg:
    st.write(f"${spend.llm_spend(con, sel):.3f} of ${cfg.llm.cycle_cap_usd:.2f}" + ("" if cfg.llm.enabled else "  (LLM assist is off for this pipeline)"))

st.subheader("Ledger")
led = con.execute("SELECT ts, step_id, source, kind, key_prefix, est_max_usd, actual_usd, results, note FROM spend_ledger WHERE cycle_id=? ORDER BY id DESC", (sel,)).fetchall()
if led:
    st.dataframe([dict(r) for r in led], hide_index=True, use_container_width=True)
else:
    st.caption("Empty.")
