import os

import streamlit as st

from core import paths
from core.db import get_setting, open_db, set_setting
from core.logmask import prefix

paths.load_env()
st.set_page_config(page_title="Settings", layout="wide")
st.title("Settings")
con = open_db()

st.subheader("Paths")
st.write(f"Repo root: `{paths.ROOT}`")
st.write(f"Data folder: `{paths.DATA_DIR}`")
st.write(f"Database: `{paths.DB_PATH}`")

st.subheader("Environment (prefix only)")
rows = []
for name in ["GOOGLE_SHEET_ID", "SANDBOX_SHEET_ID", "GOOGLE_APPLICATION_CREDENTIALS", "KEYS_SHEET_ID", "APIFY_TOKEN_POOL", "TAVILY_API_KEYS", "ANTHROPIC_API_KEY"]:
    v = os.environ.get(name, "")
    if name in ("GOOGLE_APPLICATION_CREDENTIALS",):
        shown = "set (file exists)" if v and os.path.exists(v) else ("set (file NOT found)" if v else "not set")
    elif name in ("APIFY_TOKEN_POOL", "TAVILY_API_KEYS"):
        n = len([k for k in v.replace(",", "\n").split() if k.strip()])
        shown = f"{n} key(s)" if n else "not set"
    else:
        shown = prefix(v) if v else "not set"
    rows.append({"variable": name, "status": shown})
st.table(rows)

st.subheader("Demo mode")
st.caption("Swaps in three fake Apify keys with fake balances and makes no network calls, so the paid-step gate and spend tracking can be shown safely.")
demo_on = st.toggle("Demo mode (fake keys, no network)", value=get_setting(con, "demo_mode", "0") == "1")
if demo_on != (get_setting(con, "demo_mode", "0") == "1"):
    set_setting(con, "demo_mode", "1" if demo_on else "0")
    con.execute("DELETE FROM key_status")          # never mix fake and real balances
    st.rerun()

st.subheader("LLM assist")
st.caption("Optional. Manual mode works with the toggle off or no key. The LLM only pre-fills; every item still needs your click on Review.")
on = st.toggle("Enable LLM assist", value=get_setting(con, "llm.enabled", "0") == "1", disabled=not os.environ.get("ANTHROPIC_API_KEY"))
if not os.environ.get("ANTHROPIC_API_KEY"):
    st.info("LLM off: manual mode (no ANTHROPIC_API_KEY).")
model = st.text_input("Model", value=get_setting(con, "llm.model", "claude-sonnet-5-5"))
cap = st.number_input("LLM cap per cycle (USD)", min_value=0.0, value=float(get_setting(con, "llm.cycle_cap_usd", "1.0")), step=0.25)

st.subheader("Defaults")
dcap = st.number_input("Default cycle spend cap (USD, never above the pipeline's hard max)", min_value=0.0, value=float(get_setting(con, "default_cap_usd", "3.0")), step=0.5)

if st.button("Save settings"):
    set_setting(con, "llm.enabled", "1" if on else "0")
    set_setting(con, "llm.model", model)
    set_setting(con, "llm.cycle_cap_usd", str(cap))
    set_setting(con, "default_cap_usd", str(dcap))
    st.success("Saved")
