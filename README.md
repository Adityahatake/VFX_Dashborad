# Lead Pipeline Dashboard

Local, single-user Streamlit console for running lead-generation pipelines. Pipelines are YAML configs (plus optional custom Python steps). The first one, `vfx_genai`, finds decision-makers at production companies using generative AI in client work.

**Status: phase 7 of 8 (LLM assist and history).** Adds an optional LLM layer (`core/llm/`, Anthropic only; the Groq amendment was not applied) and the History page. The LLM is **off unless all of these hold**: `ANTHROPIC_API_KEY` is set, the Settings toggle is on, the pipeline's `llm` block is enabled, and the model has a price in Settings (so the spend cap can be enforced). Otherwise every screen is plain manual review. It only **suggests**: `llm_verdicts` stores a verdict per pending company and `llm_person_drafts` a draft per pending person; nothing approves, rejects or appends. A reviewer applies a person draft with a button, and it still needs an explicit Approve. Calls use `claude-sonnet-5-5` (configurable), structured JSON output, low effort, and a cached system prompt (the pipeline's rubric plus SOP 01 for companies, SOP 02 for people). Safety checks in code: a quote must appear verbatim in the text that was sent (else the verdict becomes `unsure`), a `yes` needs a named client, AI-made work and a quote, an excluded country overrides `yes`, invalid output is `unsure` (never guessed), the model can never grant High confidence or choose R2/R4, and page text is fenced as untrusted data. LLM spend is recorded separately (kind `llm`) against its own cap; the cap check includes the one-off cost of writing the prompt cache. Results are checkpointed per item (rerun skips finished ones; a changed rubric marks old verdicts stale). Rate limits, auth and connection errors stop the batch and keep finished items.

**History page:** cycles (rows, High/Medium, rejections by reason, spend by source, cost per row, duration), source yield (screened -> hits -> approved -> rows, with a hint when a source looks dead), paid and LLM spend, and how often your decisions matched the LLM. Run Cycle now warns before you rerun a source listed under `exhausted_sources` (keywords in `match`).

**Not verified live:** nothing has called the real Anthropic API. The request shape was checked against the installed SDK (2.6.0) and its own response/error objects; prices are the published list prices at build time and are editable in Settings. The demo-mode LLM gives canned answers (it even calls a tool vendor "yes"), which is a test double, not a model.

**Phase 6 (paid people steps):** Adds `leads_finder` (decision-makers by company website, one key, results cached so a rerun is free) and `salesnav` (async gap fill: the search is submitted once, each result page is fetched once and saved immediately, empty polls are free), both on `core/apify.py`'s run flow. Rules enforced in code and tests: the Apify run id is saved **before** waiting; a network error never relaunches a run (the actor's recent runs on the same key are matched by INPUT and the matching dataset is downloaded; if none matches the job stops and a rerun needs a fresh gate confirmation); a resumed job re-attaches to its saved run; a refused request (400/401/403/429/432) marks the key and stops; spend is recorded once per run (actual usage if Apify reports it, else results x price); an actor that has never been paid for must be piloted at 25 records or fewer first (the imported VFX history counts as a pilot). Leads become **pending** people for Review, filtered by the pipeline's titles, excluded countries and per-company limit, with `ai_evidence`, `why_this_person` and `primary_commercial_problem` left as drafts the reviewer must write. Demo mode uses a scripted fake actor and writes its synthetic leads only into the throwaway cycle folder.

**Not verified against the live actors:** the Sales Navigator output field names (the mapping is tolerant and logs what it saw), Apify's `usageTotalUsd` run field, and the leads-finder input shape (taken from the VFX scripts). The first ~25-record pilot of each actor must confirm them; nothing here has made a real Apify call.

**Phase 5 (review and safe append):** Adds the Review page (companies: approve/reject with reason codes, matched sentence and evidence link; people: inline-editable, draft and flag warnings, approve/reject), baseline and progress (baseline + our own append log; rows added by others are reported separately), review-CSV building (UTF-8, no BOM), a read-only dry run, and the safe append as a worker job. Safety rules enforced in code and tests: all checked tabs are re-read before every batch of 8; stop on a changed header or blank rows; verify the landing range by read-back; recolour only our own rows, one row at a time; **a write is never retried**, and after a failed write the app blocks further appends until a recovery step has read the sheet tail and produced a CSV of only the missing rows. There is no delete, reorder, edit or clear operation anywhere in the Sheets client. Dedupe, cap and country rules are in `core/dedupe.py`.

**Sheet targets.** The default target is the **sandbox** sheet (`SANDBOX_SHEET_ID`); the real sheet needs Settings/Review confirmation (typing `REAL SHEET`). Demo mode uses an in-memory sheet and makes no Google call. The sandbox sheet must have the same tab names and header row as the pipeline (for `vfx_genai`: tabs `Linkedin`, `X`, `Stage 32`; `Linkedin` row 1 = the 17 columns in `pipeline.yaml`), and the service account needs edit access.

**Phase 4 (free steps):** Adds config-driven free steps: RevenueBase category lists, directory/association pages, deep crawl (resumable; hits go to the Review queue as pending companies), Impressum/team evidence, and pool-match second contacts. Evidence terms come from `pipeline.yaml` (`strong_terms`, `client_cues` with `*` wildcards and `{Brand}`, `false_positive_patterns`). `scripts/import_vfx_history.py` imports the VFX repo's history read-only (22,086 known domains, 2,052 company names, 36 spend rows, 93 pool files) and is safe to rerun.

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
