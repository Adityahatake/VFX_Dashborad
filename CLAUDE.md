# CLAUDE.md

Local single-user dashboard for ONE lead-generation pipeline: `pipelines/vfx_genai` (VFX / production studios using GenAI in client work), ported from the read-only VFX repo (`C:\Users\adity\OneDrive\Desktop\TRIAL\VFX`). Never modify that repo; never import from it at runtime. React app (`web/`) served by FastAPI (`api/`) over the Python core (`core/`).

## Run (Windows, use `py`)
- Setup: `py -m venv .venv`, `.\.venv\Scripts\python -m pip install -r requirements.txt`, `pip install -e .`, then `npm install` and `npm run build` in `web/`
- App: `.\.venv\Scripts\python -m uvicorn api.main:app --host 127.0.0.1 --port 8000` (open http://localhost:8000). UI dev: `npm run dev` in `web/`
- Tests: `.\.venv\Scripts\python -m pytest`; UI type-check and build: `npm run build` in `web/`

## Hard rules (from the VFX CLAUDE.md; non-negotiable)
- Show before write. Nothing reaches a sheet without review confirmation (dry run of the exact CSV + typed row count, enforced in `api/sheet.py`).
- Never retry a Sheets write (POST/PUT). Re-read the tail to see what landed; append only missing rows.
- Never delete, reorder, edit or recolour rows we did not add. Whiten only our own rows, one row at a time.
- Development and tests use `SANDBOX_SHEET_ID` or mocks, never the real sheet. No real paid API calls in tests.
- Ask the user before any real paid call, any write to a real sheet, any new dependency, or an architecture change.
- One job per API key. Persist the Apify run ID before waiting; never relaunch after a network error.
- Stop rules: cost/row > $0.50, pass rate < 3%, usable credit < $3, two cycles under 5 rows. Never lower the quality bar.
- Never print full keys (prefix only). CSVs are UTF-8 without BOM. `.gitignore` is an allowlist; do not weaken it.
- Manager overrides: max 3 people per company, database-only title = Medium, India always excluded. SOP 02 s8 functions (HR, recruiting, sales...) are excluded.
- SOP 01 s5: discovery is not qualification. Search results are candidates; a company qualifies only on evidence from its own site plus the machine checks. Automatic decisions never overwrite a human one.

## Layout
`api/` (main.py, deps.py, sheet.py), `web/src/` (home/, analytics/, keys/), `core/` logic (config, db, registry, fields, jobs, worker, keys, spend, gate, sheets, dedupe, append, review, people, qualify, analytics, metrics, apify, llm/), `core/steps/` (discover, harvest, crawl, people_free, paid, pipeline_run, llm_steps, sheet_steps, demo), `pipelines/vfx_genai/` YAML + SOPs, `scripts/`, `tests/`, `data/` git-ignored runtime state.

## More rules learned while building
- People fields in the database use INTERNAL names (`core/fields.py`); the pipeline's `field_map` is applied only when building a sheet row or reading one. Never hard-code a sheet column name in a step.
- Never write source edits through shell escapes: backslash sequences get reinterpreted (it happened to a regex in a .tsx file). Use the Edit/Write tools, or `chr(92)`.
- Every rule is enforced on the server (core/ or api/), never only in the browser.
- API connections: one SQLite connection per request (`api/deps.py`, `any_thread=True`, because FastAPI may use it from another worker thread).
- Tailwind v4 skips git-ignored files: new web source types must be added to the `.gitignore` allowlist.
- Run the full suite (`.\.venv\Scripts\python -m pytest`) and `npm run build` before committing.
