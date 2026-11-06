# Stage 2: Find people

**Goal:** for the companies in `company_master.csv` that have no people yet, produce a candidate CSV of decision-makers with personal LinkedIn URLs. No sheet writes in this stage.

## Order of work

Process companies by tier: **V (verified) / A+ → A → B → C**. Stop a tier when the cost per final row exceeds your cap (about $0.50 per row).

## Source 1: Lead finder by website (first pass, cheapest)

Actor `microworlds/leads-finder`, about **$0.003 per person**.

- Input: `company_domains` (batches of 40), `contact_job_titles` (decision-owner list), `contact_not_location: ["india"]`, `max_result` 120-150 per batch.
- Titles: founder, co-founder, ceo, owner, managing director, president, creative director, head of production, executive producer, head of ai, chief creative officer, head of innovation, director of production, partner, cto, head of, director.
- Typical coverage: about 70% of A/A+ companies. Small studios often have nobody in the database.
- Large companies swamp a batch's result cap, so keep batches at 40 websites and filter hard afterwards.

## Source 2: Sales Navigator search (second pass, gap fill)

Actor `bestscrapers/sales-navigator-scraper-by-filters`: **$0.50 per search + $0.01 per person**. One search covers up to 10 company names.

- Use only for companies the lead finder returned nobody for.
- Input: `current_company_names` (10 per search), `title_keywords` (up to 20), `limit` 40-60.
- It is asynchronous: the first reply holds a `request_id`; poll the same actor with `{"request_id": ..., "page": 1}` until the message says done. Results sit under `data`.
- **Attribution is the risk.** Name matching returns namesakes (a school district for "District 10", a coffee shop for "Yaca"). Keep only rows whose returned company name equals the target name after normalisation. Drop everything else. Expect about one in four results to be usable.
- Prefer numeric company IDs when you have them.
- Profile URLs come back in encoded `ACwAA...` form; they are valid `linkedin.com/in/` links.

## Source 3: Named on the website (free)

If the company site names founders, owners or directors, search each name plus company on LinkedIn (Tavily with `include_domains: linkedin.com` when credit exists, otherwise a WebSearch). Accept a profile only when the headline names the same company. Reject on a bare name headline unless the snippet ties it to the company.

## Filters (always)

- Keep: `linkedin_url` contains `linkedin.com/in/`; title matches the decision-owner pattern.
- Reject titles containing: intern, assistant, coordinator, student, trainee, junior, recruit, talent, HR, sales, business development, partnership, account manager, marketing, finance, legal, accountant, engineer, developer, designer, editor, artist, animator.
- Exclude India by location text, city names and `.in` domains.
- Exclude AI tool vendors and large groups by company name.
- Dedupe against the Linkedin, X and Stage 32 tabs by normalised name; also against profile URLs and spelling variants. Skip anyone already there.
- Cap: at most 2 candidates per company in this stage, and never more than 3 total per company on the tab (count existing rows).
- Rank candidates within a company: founder, owner, CEO, managing director, president, creative director, head of AI, executive producer, head of production.

## Output

Write candidate CSVs of 40-60 rows each with columns:
`first,last,title,company,domain,website,company_linkedin,city,country,linkedin_url,headline,tier,ai_evidence,ai_evidence_url`.
Report: leads pulled, candidates after filters, companies covered, cost. Do not append anything to the sheet here.

## Budget

Pilot one batch first. Track cost per candidate. If the candidates-to-rows pass rate in stage 3 is under 3%, switch source or tier rather than spending more.
