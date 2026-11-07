# CLAUDE.md

Local single-user Streamlit dashboard for lead-generation pipelines. First pipeline: `pipelines/vfx_genai`, ported from the read-only VFX repo (`C:\Users\adity\OneDrive\Desktop\TRIAL\VFX`). Never modify that repo; never import from it at runtime.

## Run (Windows, use `py`)
- Setup: `py -m venv .venv`, `.\.venv\Scripts\python -m pip install -r requirements.txt`, `pip install -e .`
- App: `.\.venv\Scripts\python -m streamlit run app/Home.py`
- Tests: `.\.venv\Scripts\python -m pytest`

## Hard rules (from the VFX CLAUDE.md; non-negotiable)
- Show before write. Nothing reaches a sheet without Review confirmation.
- Never retry a Sheets write (POST/PUT). Re-read the tail to see what landed; append only missing rows.
- Never delete, reorder, edit or recolour rows we did not add. Whiten only our own rows, one row at a time.
- Development and tests use `SANDBOX_SHEET_ID` or mocks, never the real sheet. No real paid API calls in tests.
- Ask the user before any real paid call, any write to a real sheet, any new dependency, or an architecture change.
- One job per API key. Persist the Apify run ID before waiting; never relaunch after a network error.
- Stop rules: cost/row > $0.50, pass rate < 3%, usable credit < $3, two cycles under 5 rows. Never lower the quality bar.
- Never print full keys (prefix only). CSVs are UTF-8 without BOM. `.gitignore` is an allowlist; do not weaken it.
- Manager overrides: max 3 people per company, database-only title = Medium, India always excluded.

## Layout
`core/` logic (config, db, registry, wizard, fields, jobs, worker, keys, spend, gate, sheets, dedupe, append, review, people, metrics, apify, llm/), `core/steps/` built-in steps and custom-step discovery, `app/` Streamlit pages, `pipelines/<name>/` YAML + SOPs + optional `steps/*.py` (`pipelines/_archived/` is ignored), `scripts/`, `tests/`, `data/` git-ignored runtime state.

## More rules learned while building
- People fields in the database use INTERNAL names (`core/fields.py`); the pipeline's `field_map` is applied only when building a sheet row or reading one. Never hard-code a sheet column name in a step.
- Never write a Streamlit page edit through shell escapes: backslash sequences get reinterpreted. Use the Edit/Write tools, or `chr(92)`.
- Custom steps are trusted code; the gate (kind paid/llm/write) is the control, not a sandbox.
- Run the full suite (`.\.venv\Scripts\python -m pytest`) before committing; it includes a headless render of every page.
