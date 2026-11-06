import streamlit as st

from core import keys, metrics, paths
from core.db import open_db
from core.registry import load_all

paths.load_env()
st.set_page_config(page_title="History", layout="wide")
st.title("History and metrics")
con = open_db()
if keys.is_demo(con):
    st.warning("DEMO MODE may be on: demo cycles appear here until you clear them.")

pipes = {p.config.name: p.config for p in load_all() if p.config}
if not pipes:
    st.stop()
name = st.selectbox("Pipeline", list(pipes))
cfg = pipes[name]

# ------------------------------------------------------------------ cycles
st.subheader("Cycles")
cycles = metrics.cycles_overview(con, name)
if not cycles:
    st.info("No cycles yet.")
else:
    st.dataframe([{
        "cycle": c["cycle"], "status": c["status"], "goal": c["goal"], "rows added": c["rows"], "High": c["high"], "Medium": c["medium"],
        "spend $": c["spend_usd"], "LLM $": c["llm_usd"], "cost / row $": c["cost_per_row"], "pass rate": (f"{c['pass_rate']:.1%}" if c["pass_rate"] is not None else "n/a"),
        "reviewed": c["reviewed"], "hours": c["hours"], "started": c["started"],
    } for c in cycles], hide_index=True, use_container_width=True)
    done = [c for c in cycles if c["status"] == "ended"]
    if len(done) >= 2:
        st.caption("Rows added per ended cycle")
        st.bar_chart({f"#{c['cycle']}": c["rows"] for c in reversed(done)})
    pick = st.selectbox("Cycle details", [c["cycle"] for c in cycles], format_func=lambda i: f"#{i}")
    c = next(x for x in cycles if x["cycle"] == pick)
    a, b = st.columns(2)
    a.write("**Company rejections**")
    a.write(c["company_rejections"] or "none")
    b.write("**Person rejections**")
    b.write(c["person_rejections"] or "none")
    st.write("**Spend by source**")
    st.dataframe(c["spend_by_source"] or [], hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ source yield
st.subheader("Source yield")
st.caption("Per discovery source: sites screened, crawl hits, companies you approved, and rows that reached the sheet. Free sources cost $0. This replaces the hand-written 'state of supply' notes.")
sy = metrics.source_yield(con, name)
if not sy:
    st.info("No crawl results recorded yet. Run a harvest and a deep crawl first.")
else:
    st.dataframe([{"source": r["source"], "screened": r["screened"], "hits": r["hits"], "approved": r["verified"], "rows on sheet": r["rows"], "hit rate": r["hit_rate"], "cost $": r["cost_usd"]} for r in sy],
                 hide_index=True, use_container_width=True)
    st.bar_chart({r["source"]: r["hits"] for r in sy[:15]})
    for r in sy:
        if r["dead"]:
            st.warning(f"**{r['source']}**: {r['screened']} sites screened and nothing approved. Consider adding it to `exhausted_sources` in pipeline.yaml so it warns before a rerun.")

st.subheader("Exhausted sources (warned about before a rerun)")
if cfg.exhausted_sources:
    st.dataframe([{"source": e.source, "note": e.note, "date": e.date, "matches": ", ".join(e.match)} for e in cfg.exhausted_sources], hide_index=True, use_container_width=True)
else:
    st.caption("None listed.")

# ------------------------------------------------------------------ paid / LLM spend
st.subheader("Paid and LLM spend")
ps = metrics.paid_steps(con, name)
if ps:
    st.dataframe(ps, hide_index=True, use_container_width=True)
else:
    st.caption("No paid spend recorded yet.")

# ------------------------------------------------------------------ LLM agreement
st.subheader("LLM suggestions vs your decisions")
st.caption("How often your decision matched the LLM's yes/no on companies you decided. 'unsure' is not counted. This is information, not a gate: nothing is ever approved automatically.")
ag = metrics.llm_agreement(con, name)
if not ag:
    st.info("No LLM verdicts with a decision yet.")
else:
    st.dataframe([{"model": r["model"], "prompt": r["prompt"], "cycle": r["cycle"], "decided": r["decided"], "agreement": r["agreement"], "LLM said yes, you rejected": r["false_yes"]} for r in ag],
                 hide_index=True, use_container_width=True)
    st.line_chart({f"{r['model']} #{r['cycle']}": r["agreement"] for r in ag})
