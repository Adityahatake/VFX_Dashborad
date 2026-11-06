# Lead-gen cycle: master prompt

You are running one cycle of the VFX lead-generation pipeline. A cycle has four stages, run in order, each with its own prompt file in this folder:

1. `01_find_companies.md`: build a list of production companies that really use generative AI.
2. `02_find_people.md`: find decision-makers at those companies.
3. `03_validate.md`: have each candidate checked against the SOPs.
4. `04_add_to_sheets.md`: append the validated people to the Google Sheet.

Qualification rules live in `SOP/SOP_01..03`. The stage prompts summarise them. If anything conflicts, the SOP wins.

## Before you start (every cycle)

1. **Set the counter.** Read the target tab's data-row count and save it as the cycle baseline (for example `data/baseline_<date>.txt`). "Net new" always means rows added since this baseline. Never count rows you did not add.
2. **Check credit.** Open the keys sheet ("Api keys and passwords"). Check every Apify and Tavily key live, mark each as usable, out of credit or invalid in its status column, and write the usable keys to a local pool file. Do not start a stage you cannot afford. Report the usable total.
3. **Pilot before you spend.** For any actor you have not used in the last week, run a pilot of about 25 records and measure cost per record and what fraction qualify. Keep the actor only if the numbers are good.
4. **Set a spend cap** per stage and stop at it. Write every run's cost to a log.

## Rules that apply everywhere

- Only real decision-makers at real production businesses that use generative AI in their *own* client work. Reject AI tool/SaaS vendors, marketing/SEO/PR/web/consulting agencies, publishers, broadcasters, educators, investors, and big agency networks.
- Approved countries only (see stage 03). **India is excluded** for both companies and people.
- Every row needs a personal LinkedIn profile URL (`linkedin.com/in/...`) and a sourced evidence link. Never guess a URL, a title or a country.
- No person appears twice. No more than 3 people per company.
- **Colours:** rows you add are white background, black text. Never change any colour that is already on the sheet, and never delete or edit rows you did not add. Apply formatting row by row to your own rows only.
- Be honest about thin evidence. Mark Medium confidence when a title comes only from a database, and say so.
- Do not use detached background jobs inside sub-agents; keep agents synchronous. Cap concurrent agents at about 12 and keep each agent to 40-60 rows.

## Cycle report (send at the end of each cycle)

- Credit at start and end, and total spend.
- Companies found, by tier.
- People pulled, candidates after filtering, rows added (net new this cycle and cumulative since baseline).
- Cost per company and cost per row.
- Anything unusual: rows added by others, API failures, thin-evidence rows, items needing a decision.

## When to stop

Stop and ask when: the usable credit is under $3; two consecutive cycles add fewer than 5 rows; or you need to lower a quality bar to continue. Never lower a bar without an explicit yes.
