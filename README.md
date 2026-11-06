# Lead Pipeline Dashboard

Local, single-user Streamlit console for running lead-generation pipelines. Pipelines are YAML configs (plus optional custom Python steps). The first one, `vfx_genai`, finds decision-makers at production companies using generative AI in client work.

**Status: phase 2 of 8 (jobs engine).** Config validation, SQLite schema, registry, Settings, Pipelines view, and background jobs (detached workers, live logs, cancel, resume, reconcile, one-job-per-key leases). Only a free demo step exists; no paid calls or sheet access yet.

## Jobs engine in one paragraph

Each step runs as its own detached process (`py -m core.worker --job <id>`), launched through a short-lived intermediary so it is not a child of Streamlit: closing the tab, stopping Streamlit or killing its process tree does not stop a job. State (PID, heartbeat, log and checkpoint paths) is in SQLite. On every app start and Jobs refresh, jobs whose process is gone become `interrupted`; **Resume** continues from the checkpoint. **Cancel** sets a flag file the step checks, and kills the process after 15 s if it does not react. A key lease allows one job per API key; a lease held by a dead job is released. Paid, LLM and write steps cannot be started without an explicit confirmation.

## Setup (Windows)

```
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pip install -e .
copy .env.example .env      # then fill it in; .env is git-ignored
```

## Run

```
.\.venv\Scripts\python -m streamlit run app/Home.py
.\.venv\Scripts\python -m pytest
```

## Layout

- `core/config.py`: pydantic models for `pipeline.yaml`
- `core/db.py`: SQLite (WAL) schema and migrations
- `core/registry.py`: discovers pipelines; a broken YAML shows an error card instead of crashing
- `core/logmask.py`: masks API keys in logs
- `pipelines/vfx_genai/`: config, SOPs and manager overrides
- `app/`: Streamlit pages

Later sections ("Run your first VFX cycle", "Add a new pipeline") are added in phase 8.
