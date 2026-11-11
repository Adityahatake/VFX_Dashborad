# VFX Lead Ops

A local, single-user dashboard that finds **VFX, animation and production studios using generative AI in client work**, finds their decision-makers, and adds approved rows to the team's Google Sheet. It follows the VFX SOPs (`pipelines/vfx_genai/sop/`) and the manager's overrides. It is a port of the scripts in the read-only VFX repo, which it never modifies or imports.

Everything runs on `localhost`: a FastAPI server (Python, the tested core in `core/`) serves a React app. Keys stay in `.env`. Nothing reaches a sheet without your confirmation.

## What it does

```
Run pipeline (one click, one confirmed maximum cost):
  1 initialise  2 check keys + read the sheet (read-only)  3 Tavily search for candidate studios (SOP 01 s5: candidates only)
  4 crawl each studio's OWN site for AI + client evidence, then the SOP machine checks (pass / hold / reject)
  5 people search on qualified studios (Apify leads finder) + free pool matching  6 check every new person against the sheet (read-only)
  7 save to the database  8 done
Then YOU review companies and people on Home, build the review CSV, dry-run it, type the row count, and append.
```

## Safety rules the code enforces (each has tests)

- **Show before write.** The append needs approved people, a built CSV, a dry run of exactly that CSV (checked by content hash on the server), and you typing the row count. A person can be approved only when `why_this_person`, the commercial hypothesis, `ai_evidence` and `evidence_source` are written.
- **Safe append.** All checked tabs are re-read before every batch of 8; it stops on a changed header or blank rows; it reads the rows back, recolours only our own rows one at a time, and **never retries a write**. After an unknown write outcome, appending is blocked until recovery has read the sheet tail and logged what landed.
- **No delete, edit or reorder** of anyone's rows exists anywhere in the Sheets client.
- **Sheet target.** Sandbox, real read-only, or real with writes (you type `REAL SHEET`). Demo mode never calls Google.
- **Spend control.** Every paid step, and the whole pipeline run, shows its maximum cost and needs confirmation. Inside a run every paid stage is sized to what is left of that confirmation and of the cycle cap (hard maximum $3). Stop rules (cost per row over $0.50, pass rate under 3%, usable credit under $3, two low-yield cycles) block paid stages until you acknowledge them. A source never paid for here runs at pilot size (25) first.
- **Apify runs are never relaunched after a network error**; the run id is saved before waiting. **One job per API key** (leases).
- **AI only suggests.** Drafts are labelled; you still approve. The model can never grant High confidence or choose R2/R4.
- **Manager overrides:** at most 3 people per company, a database-only title is Medium, India is always excluded. Recruiters, HR, sales and other SOP 02 s8 functions are excluded.
- Keys are shown by short id only and masked in logs; `.env` is backed up outside the repo before the app changes it. `.gitignore` is an allowlist. CSVs are UTF-8 without a BOM.

## Setup (Windows)

```
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pip install -e .
copy .env.example .env
cd web
npm install
npm run build
cd ..
```

Fill in `.env` (git-ignored), or add the API keys later on **API & Keys**:

| Variable | Used for |
|---|---|
| `TAVILY_API_KEYS` | comma-separated Tavily keys (company discovery, 1 credit per search) |
| `APIFY_TOKEN_POOL` | comma-separated Apify tokens (people search) |
| `GROQ_API_KEYS` | comma-separated Groq keys (`gsk_...`) |
| `GOOGLE_APPLICATION_CREDENTIALS` | path to a service-account JSON with access to the sheets |
| `SANDBOX_SHEET_ID` | the sandbox copy of the sheet (same tabs and header) |
| `GOOGLE_SHEET_ID` | the real shared sheet |
| `ANTHROPIC_API_KEY` | optional AI suggestions |
| `LPD_ENV_BACKUP_DIR` | where `.env` backups go (must be outside the repo) |

```
.\.venv\Scripts\python scripts\import_vfx_history.py --dry-run    # read-only look at the VFX history
.\.venv\Scripts\python scripts\import_vfx_history.py              # import it (safe to rerun)
.\.venv\Scripts\python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open http://localhost:8000. For UI work, run `npm run dev` in `web/` (port 5173; API calls go to port 8000).

## Using it

**Home** (the control centre)
1. The health strip shows each provider, the sheet target and live status. Fix red items on **API & Keys** first.
2. **Cycle:** set the goal (rows) and spend cap, start. Acknowledge a stop rule here if one is shown (it is your call).
3. **Run pipeline:** adjust the size in *Settings* if you like, press *Check cost and readiness*, read the maximum cost and anything blocking it, tick the confirmation, run. Watch the stages, counts, spend and errors live; *Show technical log* opens the raw log. Cancel and Resume (re-checked) are on the run card and in **Jobs**.
4. **Latest companies:** read the evidence sentence, open the link, approve, mark "needs a look" or reject with a reason. Automatic checks are labelled `AUTO_PASS` / `AUTO_HOLD` / `AUTO_REJECT`; you can change any of them.
5. **Latest people:** *Edit fields*, write `why_this_person` and the hypothesis yourself, approve or reject. An AI draft, if present, can be copied in with one click and still needs your approval.
6. **Sheet & append:** take the baseline, build the CSV, dry-run (lists every skipped row and why), type the count, append. If a write ever ends with an unknown outcome, run recovery here.
7. **Run cycle step (advanced):** run one step on its own (for example a free RevenueBase harvest or a pools-mode crawl), with the same cost gate.

**Analytics:** companies and people over time (daily, weekly, monthly, any date range), pipeline runs (success vs failed, average time, records per run), people per qualified company, spend by provider over time, remaining credit, discovery-source yield, exhausted sources and every cycle's cost per row and pass rate. Every number comes from the database.

**API & Keys:** Groq, Tavily and Apify in one place: status, remaining credit (Apify in dollars, Tavily in credits, Groq in requests left today), usage, low-credit warnings (default below 20), add / replace / remove keys, free checks and opt-in live checks. Settings (demo mode, default cap, AI suggestions and prices, what `.env` contains) are at the bottom.

## Layout

```
api/                     FastAPI: main.py (health, keys, cycle, steps, gate, jobs, pipeline, review, analytics, SSE), sheet.py (append, recovery, settings, sources)
web/src/                 React app: home/, analytics/, keys/
core/                    config, db (migrations), registry, fields, jobs, worker, keys, spend, gate, sheets, dedupe, append, review, people, qualify, analytics, metrics, apify, llm/
core/steps/              discover (Tavily), harvest, crawl, people_free, paid, pipeline_run (the one-click pipeline), llm_steps, sheet_steps, demo
pipelines/vfx_genai/     pipeline.yaml and the SOPs
scripts/                 import_vfx_history.py, import_keys.py
tests/                   pytest: real worker processes against fakes; no network, keys or real sheet
data/                    git-ignored runtime state: SQLite, job logs, cycle folders, pools
```

Run the tests with `.\.venv\Scripts\python -m pytest`, and type-check the UI with `npm run build` in `web/`.

## Known gaps and what has not been verified live

- **Verified live:** reading the real sheet (read-only), Apify balance checks, the key import from the keys sheet, the free crawls.
- **Not yet verified live:** Tavily search (no Tavily key configured yet), Groq (no key; its quota is read from response headers, which is what Groq documents), the leads-finder pilot and Sales Navigator field names, Anthropic costs, and any sheet write (the target has been read-only so far).
- **Groq** is managed and checked, but the AI suggestion steps still call Anthropic; a Groq suggestion provider is not built yet.
- **Not built:** the Tavily-extract fallback in `harvest_directory`, and a "sync to keys sheet" button.
- **Stricter than VFX:** the append also rejects countries that are not on the approved list, not only India.

## Build history

| Phase | Commit |
|---|---|
| 1-8 Streamlit dashboard: jobs, keys, spend gate, free and paid steps, review, safe append, LLM assist | `c9a4853` … `11510b8` |
| Real-run support: read-only target, key import, pools crawl fix | `9fa1314` |
| Redesign 1: FastAPI layer | `b06e521` |
| Redesign 2: Apify, Tavily and Groq key management | `27e36e2` |
| Redesign 3: one-click pipeline with Tavily discovery | `3be42cf` |
| Redesign 4: React Home | `e63a173` |
| Redesign 5: Analytics and API & Keys | `36185be` |
| Redesign 6: sheet append in the new UI; VFX-only; Streamlit, wizard and custom steps removed | see `git log` |
