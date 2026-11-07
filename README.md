# Lead Pipeline Dashboard

A local, single-user Streamlit console for building and running **lead-generation pipelines**. A pipeline is a YAML file (plus optional Python step files) that says what a qualifying company looks like, where to find candidates, who to look for, and which Google Sheet tab the approved rows go to. The first pipeline, `vfx_genai`, finds decision-makers at production companies that use generative AI in client work; it is a port of the scripts in the read-only VFX repo.

Everything here runs on `localhost`. Keys stay in `.env`. Nothing reaches a sheet without your confirmation on the Review page.

## What it does, in one picture

```
harvest (free) -> deep crawl (free) -> REVIEW companies -> find people (free / cheap) -> REVIEW people
        -> build review CSV -> dry run -> typed confirmation -> safe append to the sheet
every paid or LLM step stops at a cost screen first; every step runs as a background job you can cancel and resume
```

## Safety rules the code enforces (each has tests)

- **Show before write.** Appending needs approved rows, a built CSV, a dry run and you typing the row count.
- **Safe append.** All checked tabs are re-read before every batch of 8. It stops if the header changed or the data contains blank rows. It verifies the landing range by reading the rows back, recolours only our own rows (one row at a time), and **never retries a write**. After a write error with an unknown outcome, appending is blocked until a recovery step has read the sheet tail and produced a CSV of only the missing rows.
- **No delete, edit or reorder** of anyone's rows exists anywhere in the Sheets client.
- **Sandbox first.** The default sheet target is `SANDBOX_SHEET_ID`. Switching to the real sheet needs you to type `REAL SHEET`. Demo mode never calls Google.
- **Spend control.** Before any paid run you see the maximum cost, the key (by short id), its live balance and the remaining cycle cap, and you confirm. Caps never exceed the pipeline's hard maximum. Four stop rules (cost per row over $0.50, pass rate under 3%, usable credit under $3, two low-yield cycles) block paid steps until you acknowledge them. An actor never paid for must be piloted at 25 records or fewer first.
- **Apify runs are never relaunched after a network error.** The run id is saved before waiting; recovery looks the run up by its input; a resumed job re-attaches to its saved run; spend is recorded once per run.
- **One job per API key**, enforced with a lease.
- **The LLM only suggests** (optional; see below). Manager rules are applied in code: at most 3 people per company, a title from a database only is Medium confidence, India is always excluded.
- Keys are shown by short id only, masked in logs, and `.gitignore` is an allowlist. CSVs are UTF-8 without a BOM.

## Setup (Windows)

```
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pip install -e .
copy .env.example .env
```

Fill in `.env` (it is git-ignored; the app never prints full keys):

| Variable | Used for |
|---|---|
| `APIFY_TOKEN_POOL` | comma-separated Apify tokens (people search) |
| `TAVILY_API_KEYS` | comma-separated Tavily keys (balances; the Tavily steps are not all built, see Known gaps) |
| `GOOGLE_APPLICATION_CREDENTIALS` | path to a service-account JSON with edit access to the sheets |
| `SANDBOX_SHEET_ID` | the sandbox copy of the sheet: **all development and first runs write here** |
| `GOOGLE_SHEET_ID` | the real shared sheet (used only after you switch the target and type `REAL SHEET`) |
| `ANTHROPIC_API_KEY` | optional LLM assist |
| `LPD_ENV_BACKUP_DIR` | where `.env` backups go when you add keys in the app (must be outside the repo) |

The sandbox sheet must have the same tab names and header row as the pipeline. For `vfx_genai`: tabs `Linkedin`, `X` and `Stage 32`, and `Linkedin` row 1 holds the 17 columns in `pipelines/vfx_genai/pipeline.yaml`.

```
.\.venv\Scripts\python scripts\import_vfx_history.py --dry-run    # read-only look at the VFX history
.\.venv\Scripts\python scripts\import_vfx_history.py              # import it (safe to rerun)
.\.venv\Scripts\python -m streamlit run app/Home.py
```

The import reads the VFX repo's `data/` folder (read-only) and loads about 22,000 known domains, 2,000 company names, the spend history and 93 pool files, so the harvest steps do not re-propose companies you already crawled.

## Run your first VFX cycle from the dashboard

Do this against the **sandbox** sheet. Nothing is paid or written until steps 7 to 9.

1. **Check the setup.** Home shows no red alerts. In **Settings**, demo mode is off, the paths are right, and `SANDBOX_SHEET_ID` and the credentials show as set.
2. **Check balances.** On **Keys**, press *Check balances*. You need at least one Apify key at or above $0.80 before any paid step.
3. **Start a cycle.** On **Run Cycle**, pick `vfx_genai`, set the goal (rows) and the spend cap (default and maximum $3), press *Start cycle*.
4. **Baseline and snapshot.** On **Review > Sheet and append**, press *Take baseline now*. On Run Cycle run the free step `sheet_snapshot` (it reads the sheet read-only so later steps know who is already on it).
5. **Find companies for free.** Run `harvest_revenuebase`, then `deep_crawl` (use the same `tag`). Watch **Jobs**: logs stream live, Cancel is graceful, Resume continues from the checkpoint, and closing the browser does not stop anything. A crawl of thousands of sites takes a long time; start with `limit` set to a few dozen.
6. **Review companies.** On **Review > Companies**, read the matched sentence and open the evidence link. Approve, reject (with a reason code) or mark "needs a look". Optionally run `llm_verdicts` first for suggestions (see the LLM section); you still decide.
7. **Find people.** Approved companies feed `leads_finder`. Its first run must be a pilot of 25 records or fewer (the imported VFX history already counts as a pilot for this actor). The cost screen shows the maximum cost and the key; confirm to run. Then run `pool_match` (free second and third contacts). `salesnav` is a last resort at about $0.90 per row.
8. **Review people.** On **Review > People**, edit fields, write `why_this_person` and the commercial-route hypothesis yourself (the app leaves them as drafts and blocks approval until they are written), and approve or reject.
9. **Append.** On **Sheet and append**: *Build review CSV*, *Dry-run append* (it lists every row that would be skipped and why), type the row count, press *Append to sheet*. Check the result on the sandbox sheet.
10. **Wrap up.** Export the cycle report (Markdown), end the cycle on Run Cycle, and look at **History** (cost per row, source yield). Repeat on the sandbox until you trust it; only then switch the target to the real sheet.

## Add a new pipeline (worked example)

Goal: "architecture firms that publish AI renders". Most of a pipeline is configuration; Python is only for what configuration cannot express.

**1. Open the wizard.** **Pipelines > New pipeline** (or *Clone* an existing pipeline, which copies its config and SOP files but not its "exhausted sources" notes). Seven pages, with a live YAML preview and validation errors at the bottom of every page, and *Save pipeline* disabled until it is valid:

| Page | What you set |
|---|---|
| 1 Basics | name (a lowercase slug; it becomes the folder `pipelines/architecture_ai/`) and title |
| 2 Company profile | one or two sentences on who qualifies, company types and names to reject, approved and excluded countries |
| 3 Evidence | `strong_terms` (for example `Midjourney`, `AI-generated`, `KI-generiert*`), `client_cues` (`client`, `for {Brand}`), false-positive regexes, and what does not count. `*` ends a word, `{Brand}` means a capitalised word, and strong terms never match inside a longer word |
| 4 People | decision titles (best first), reject titles, people per company, role families |
| 5 Steps | the ordered steps, their stage and parameters (JSON). Only built-in steps and this pipeline's own custom steps are offered |
| 6 Sheet output | the write tab, its columns in sheet order, tabs checked for duplicates, which columns identify name/company/country/evidence/profile URL, and the **field mapping** |
| 7 Budget, LLM, SOPs | caps and stop rules, LLM switch, and SOP/rubric markdown files (upload or paste) |

**2. Map your columns.** The people steps fill *internal* fields (`name`, `company`, `title`, `role`, `country`, `ai_evidence`, `why_this_person`, `qa_confidence`, `contact_or_reference`, `evidence_source`, and so on). If your sheet calls them something else, map them on page 6; the mapping is applied only when a row is built for the sheet or read back from it. Example for the architecture sheet:

```yaml
output:
  columns: [person, firm, position, role, region, evidence_summary, why_this_person, confidence, profile, source_urls]
  field_map: {name: person, company: firm, title: position, country: region, ai_evidence: evidence_summary,
              qa_confidence: confidence, contact_or_reference: profile, evidence_source: source_urls}
  dedupe: {name_field: person, company_field: firm, url_fields: [profile], evidence_field: source_urls, country_field: region}
```

**3. Add a custom step when configuration is not enough.** On **Pipelines > Custom steps**, choose the pipeline, an id and a kind, and press *Create step file*. That writes `pipelines/architecture_ai/steps/render_check.py` from a template. Edit `run()`:

```python
from core.steps.base import Step, StepResult, register
from pydantic import BaseModel, ConfigDict, Field

class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field("...", max_length=5000)

@register
class RenderCheck(Step):
    id = "render_check"
    kind = "free"                      # free | paid | llm | write
    title = "Count sentences that mention AI renders"
    params_model = Params

    def run(self, ctx, params):
        ctx.check_cancel()             # lets Cancel stop it gracefully
        ctx.log("working...")
        (ctx.workdir / "out.txt").write_text("...", encoding="utf-8")
        return StepResult(counts={"hits": 1}, artifacts=["out.txt"], message="ok")
```

Press *Reload steps*. A file with a syntax error, a bad import, no `@register`, an invalid `kind`, or an id that is already taken shows an **error card** (file and line) and never stops the app or the other steps. Custom steps appear on Run Cycle for their own pipeline only, and can be added to the pipeline in wizard page 5. Paid, LLM and write kinds still go through the confirmation screen; for a paid step declare `estimate_cost` (price times maximum results), take the key with `ctx.use_key("apify")` and record every cost with `ctx.record_spend(...)`.

**Custom steps are trusted code.** They run as you with the same access. The app cannot sandbox them and cannot know if a step claiming `kind = "free"` spends money somewhere else.

**4. Test it safely.** Turn on **Settings > Demo mode** (fake keys, an in-memory sheet, a scripted fake Apify and a canned LLM, no network) to click through the whole flow, then run a real cycle against the sandbox sheet. Edit or archive a pipeline from the Pipelines list: *Edit* keeps a backup of the old file in `data/backups/`, and *Archive* moves the folder to `pipelines/_archived/` (nothing is deleted). Archive is blocked while the pipeline has an active cycle.

## The pieces, briefly

- **Jobs.** Every step runs as a detached worker process (`core.worker`) started through a short-lived intermediary, so closing the browser, stopping Streamlit or killing its process tree does not stop a job. State is in SQLite. Dead workers are marked `interrupted` and can be resumed from their checkpoint. Cancel is graceful first, then a kill after 15 seconds. On Windows the worker runs the base interpreter directly (venv packages via `PYTHONPATH`) because the venv launcher layer made workers die silently.
- **Keys and spend.** Balances come from read-only calls (Apify limits are free; a Tavily live search costing one credit is opt-in). The ledger records every paid call; LLM spend is recorded separately against its own cap.
- **Companies.** `harvest_revenuebase` and `harvest_directory` are free; `deep_crawl` is free, resumable and records per-source yield; `evidence` greps Impressum and team pages.
- **People.** `leads_finder` (one key, cached results), `salesnav` (async; submit once, fetch each page once, empty polls free), `pool_match` (free second and third contacts with a namesake flag).
- **LLM assist (optional, off by default).** Active only when `ANTHROPIC_API_KEY` is set, the Settings toggle is on, the pipeline's `llm` block is enabled and the model has a price in Settings. `llm_verdicts` and `llm_person_drafts` store suggestions; a reviewer applies a person draft with a button and it still needs an explicit Approve. Checks in code: a quote must appear verbatim in the text that was sent, a `yes` needs a named client, AI-made work and a quote, the model can never grant High confidence or choose R2/R4, and page text is fenced as untrusted data. Anthropic only (the Groq amendment was not applied).
- **History.** Cycles, source yield with a hint when a source looks dead, paid and LLM spend, and how often your decisions matched the LLM. Run Cycle warns before you rerun a source listed under `exhausted_sources`.

## Layout

```
app/Home.py, app/pages/1_Pipelines ... 8_Settings     the Streamlit pages
core/                    config, db, registry, wizard, fields, jobs, worker, keys, spend, gate, sheets, dedupe, append, review, people, metrics, apify, llm/
core/steps/              built-in steps (harvest, crawl, people_free, paid, llm_steps, sheet_steps, demo) and custom-step discovery
pipelines/<name>/        pipeline.yaml, sop/*.md, optional steps/*.py     (pipelines/_archived/ is ignored)
scripts/import_vfx_history.py
tests/                   pytest (a headless render of every page included)
data/                    git-ignored runtime state: SQLite, job logs, cycle folders, pools, backups
```

Run the tests with `.\.venv\Scripts\python -m pytest`. They launch real worker processes against fakes and never touch the network, a key or a real sheet.

## Known gaps and what has not been verified live

- **Nothing here has called the real Apify, Tavily, Anthropic or Google APIs.** Request shapes follow the VFX scripts, the Claude API reference and the installed SDK; the Sheets client is tested against a fake that reproduces the API's trimming and "append lands after the first blank row" behaviour. The first real runs (a roughly 25-record pilot per actor, and one small append to the sandbox sheet) must confirm: Sales Navigator output field names, Apify's `usageTotalUsd` field, the leads-finder input shape, and real token costs. Prices in Settings are the published list prices at build time.
- **Not built:** `harvest_tavily_press` (the trade-press search; it is the one step in the VFX pipeline still marked "not built yet" on the Pipelines page, because the VFX script for it was not in the repo), the Tavily-extract fallback in `harvest_directory`, and the "Sync to keys sheet" button (the `KEYS_SHEET_ID` variable is reserved for it).
- **Stricter than VFX:** the append also rejects countries that are not on the approved list, not only India.
- **Server-side refusal fallbacks** recommended by the Claude API reference are not enabled; a refusal becomes an `unsure` suggestion.
- The pipeline wizard edits one pipeline at a time and does not edit `exhausted_sources`; edit that list in the YAML.

## Build history

| Phase | Commit |
|---|---|
| 1 skeleton: config, SQLite, pages | `c9a4853` |
| 2 jobs engine | `3896d61` |
| 3 keys, spend, cost gate | `dc4b737` |
| 4 free steps, VFX history import, worker fix | `4df9e69` |
| 5 Review and safe append | `6a45678` |
| 6 paid people steps | `7f34a10` |
| 7 LLM assist and History | `2fbc8a6` |
| 8 pipeline wizard, custom steps, field mapping | see `git log` |
