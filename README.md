# Lead Pipeline Dashboard

Local, single-user Streamlit console for running lead-generation pipelines. Pipelines are YAML configs (plus optional custom Python steps). The first one, `vfx_genai`, finds decision-makers at production companies using generative AI in client work.

**Status: phase 4 of 8 (free steps).** Adds config-driven free steps: RevenueBase category lists, directory/association pages, deep crawl (resumable; hits go to the Review queue as pending companies), Impressum/team evidence, and pool-match second contacts. Evidence terms come from `pipeline.yaml` (`strong_terms`, `client_cues` with `*` wildcards and `{Brand}`, `false_positive_patterns`). `scripts/import_vfx_history.py` imports the VFX repo's history read-only (22,086 known domains, 2,052 company names, 36 spend rows, 93 pool files) and is safe to rerun.

**Phase 3 (keys and spend):** Adds the Keys, Spend and Run Cycle pages, live key balances (read-only calls), a spend ledger, the four stop rules, and a pre-run cost gate for paid steps (max cost, key prefix, balance and remaining cap are shown; a confirm click is required; the gate re-checks at click time and again on resume). A Settings toggle turns on **demo mode** (three fake Apify keys, no network) so this can be shown without spending anything.

**Fixed in phase 4 - silent worker deaths:** workers sometimes vanished 1-2 s after starting (intermittent test failures, and a lost RevenueBase job). Most likely cause (observed: the layering and the PID race; not observed: the kill itself): on Windows `.venv\Scripts\python.exe` is only a launcher that runs the real interpreter inside a job object, and `launch()` could also overwrite the worker's pid/status. Workers now run the base interpreter directly (venv packages via PYTHONPATH) and `launch()` never overwrites a running worker's pid or status. Before: 7 of 20 launches showed a pid mismatch; after: 0 of 60, and the full suite passed twice in a row.

Earlier status: **phase 2 of 8 (jobs engine).** Config validation, SQLite schema, registry, Settings, Pipelines view, and background jobs (detached workers, live logs, cancel, resume, reconcile, one-job-per-key leases). Only a free demo step exists; no paid calls or sheet access yet.

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
