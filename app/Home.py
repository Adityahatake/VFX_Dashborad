import streamlit as st

from core import jobs, paths
from core.db import open_db
from core.registry import load_all, sync_db

paths.load_env()
paths.ensure_dirs()

st.set_page_config(page_title="Lead Pipeline Dashboard", layout="wide")
st.title("Lead Pipeline Dashboard")

con = open_db()
interrupted_now = jobs.reconcile(con)     # on app start: dead PIDs become 'interrupted' and their key leases are freed
loaded = load_all()
sync_db(con, loaded)

c1, c2, c3 = st.columns(3)
c1.metric("Pipelines loaded", sum(1 for p in loaded if p.config))
c2.metric("Running jobs", con.execute("SELECT COUNT(*) FROM jobs WHERE status='running'").fetchone()[0])
cyc = con.execute("SELECT * FROM cycles WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
c3.metric("Active cycle", f"#{cyc['id']} ({cyc['pipeline']})" if cyc else "none")

n_int = con.execute("SELECT COUNT(*) FROM jobs WHERE status='interrupted'").fetchone()[0]
if n_int:
    st.warning(f"{n_int} interrupted job(s) can be resumed from the Jobs page.")
stuck = [j["id"] for j in con.execute("SELECT * FROM jobs WHERE status='running'") if jobs.is_stuck(j)]
if stuck:
    st.error(f"Job(s) {stuck} are alive but have sent no heartbeat for over {jobs.HEARTBEAT_STALE_S}s.")

bad = [p for p in loaded if not p.config]
for p in bad:
    st.error(f"{p.dir.name}/pipeline.yaml is invalid")
    for line in p.problems:
        st.write(f"- {line}")
for p in loaded:
    if p.missing_sop:
        st.warning(f"{p.dir.name}: SOP files listed but missing: {', '.join(p.missing_sop)}")

st.caption("Phase 1 skeleton: config loading, database and settings. Run Cycle, Jobs, Review, Keys and Spend arrive in later phases.")
