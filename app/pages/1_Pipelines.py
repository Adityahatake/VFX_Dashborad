import streamlit as st
import yaml

from core import paths
from core.config import ConfigError, parse_config
from core.registry import load_all

paths.load_env()
st.set_page_config(page_title="Pipelines", layout="wide")
st.title("Pipelines")

loaded = load_all()
if not loaded:
    st.info("No pipelines found under pipelines/*/pipeline.yaml")
for p in loaded:
    ok = p.config is not None
    with st.expander(f"{'OK' if ok else 'INVALID'}  {p.dir.name}" + (f" - {p.config.title}" if ok else ""), expanded=not ok):
        if not ok:
            for line in p.problems:
                st.write(f"- {line}")
            continue
        cfg = p.config
        st.write(f"**Steps:** {' > '.join(s.step for s in cfg.steps)}")
        st.write(f"**Write tab:** {cfg.output.write_tab.name} ({len(cfg.output.columns)} columns); dedupes against {', '.join(t.name for t in cfg.output.tabs)}")
        b = cfg.budget
        st.write(f"**Budget:** cap ${b.default_cycle_cap_usd:.2f} (hard max ${b.hard_max_cycle_cap_usd:.2f}), key floor ${b.min_key_balance_usd:.2f}")
        if cfg.exhausted_sources:
            st.write("**Exhausted sources (do not rerun):**")
            for e in cfg.exhausted_sources:
                st.write(f"- {e.source}: {e.note} ({e.date})")
        st.code((p.dir / "pipeline.yaml").read_text(encoding="utf-8"), language="yaml")

st.subheader("Validate YAML")
text = st.text_area("Paste a pipeline.yaml to check it (nothing is saved)", height=200)
if text.strip():
    try:
        cfg = parse_config(text)
        st.success(f"Valid: {cfg.name} with {len(cfg.steps)} steps")
    except ConfigError as e:
        st.error("Invalid")
        for line in e.problems:
            st.write(f"- {line}")
