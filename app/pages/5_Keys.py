import streamlit as st

from core import keys, paths
from core.db import get_setting, open_db
from core.registry import load_all

paths.load_env()
st.set_page_config(page_title="Keys", layout="wide")
st.title("Keys")
con = open_db()
demo = keys.is_demo(con)
if demo:
    st.warning("DEMO MODE: fake Apify keys and fake balances, no network calls. Turn it off in Settings to use your real .env keys.")

cfgs = [p.config for p in load_all() if p.config]
floor = cfgs[0].budget.min_key_balance_usd if cfgs else keys.APIFY_FLOOR

st.subheader("Balances")
c1, c2 = st.columns([1, 2])
live = c2.checkbox("Also run one live Tavily search per key (costs 1 credit each)", value=False,
                   help="Tavily's /usage call is free but shows a per-key figure; the account-wide limit only shows on a real search.")
if c1.button("Check balances", type="primary"):
    with st.spinner("Checking (Apify limits calls are free)..."):
        res = keys.check_all(con, floor, live_tavily=live)
    st.success(f"Checked {len(res)} key(s).")

rows = keys.statuses(con)
leased = keys.leased_ids(con)
if not rows:
    st.info("No balances yet. Add keys to .env (or switch on demo mode in Settings), then press Check balances.")
else:
    ICON = {"usable": "usable", "low": "LOW", "out": "OUT OF CREDIT", "dead": "INVALID", "error": "check failed", "unchecked": "unchecked"}
    known = {k: {keys.key_id(s) for s in keys.load_keys(k, demo)} for k in keys.PROVIDERS}
    st.dataframe([{
        "provider": r["provider"], "key": r["key_prefix"] + "…", "state": ICON.get(r["state"], r["state"]) + ("  (in use)" if r["key_prefix"] in leased else ""),
        "remaining": r["remaining"], "limit": r["cap"], "resets": r["resets"],
        "checked": f"{int(keys.age_s(r['checked_at']) // 60)} min ago", "in .env": "yes" if r["key_prefix"] in known[r["provider"]] else "no (stale row)",
    } for r in rows], hide_index=True, use_container_width=True)
    usable = [r for r in rows if r["provider"] == "apify" and r["state"] == "usable" and (r["remaining"] or 0) >= floor]
    st.metric(f"Usable Apify credit (keys at or above ${floor:.2f})", f"${keys.usable_credit(con, floor):.2f}", f"{len(usable)} key(s)")
    st.caption("Keys are shown by short id only. A key is rotated out on 401/403 (invalid) or 429/432/'limit exceeded' (out of credit); balances older than 10 minutes are never trusted for a paid run.")

st.subheader("Add keys")
st.caption("Pasted keys go into .env only. The old .env is backed up outside the repo first. Keys are never shown again.")
prov = st.selectbox("Provider", list(keys.PROVIDERS))
pasted = st.text_input("Keys (comma-separated)", type="password")
if st.button("Add to .env"):
    try:
        n, backup = keys.add_keys(prov, keys.split_keys(pasted))
        st.success(f"Added {n} new key(s). Previous .env saved to {backup}. Press Check balances.")
    except ValueError as e:
        st.error(str(e))

st.subheader("Sync to keys sheet")
st.button("Sync (dry run first)", disabled=True, help="Arrives with the Google Sheets client in phase 5.")
