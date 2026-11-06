# Stage 3: Validate candidates (agent prompt)

This is the prompt to give each validation agent. Fill in `<CSV>` and `<TAG>`. Run about 12 agents in parallel, each on 40-60 rows. Agents use only WebSearch and WebFetch. They cannot read linkedin.com or x.com pages, so they rely on the CSV for LinkedIn facts.

---

You are validating lead candidates against the qualification SOPs (`SOP/SOP_01`, `SOP_02`, `SOP_03`). Input CSV: `<CSV>`. Tag: `<TAG>`. Process **every row**, synchronously, with a genuine per-row check. Do not run background jobs. Do not change any cell formatting or colours.

## A row PASSES only if all of these hold

1. **Company is a real production business** (studio, production house, VFX, animation, virtual production, dubbing, creative or ad studio, in-house production unit) with **named clients or commissions**.
2. **It uses generative AI in its own client work**, shown on a page you actually opened: the company site (Tier A) or reputable trade press (Tier B). Start from the company website, then try /work, /portfolio, /ai, /about, and one or two searches. A blog post about AI tools, a service line with no named project, or a homepage mention is **not enough**.
3. **Not** an AI tool/SaaS vendor, platform, marketplace, consultancy, SEO/marketing/PR/web agency, publisher, broadcaster, educator, research body, investor, or a large agency network/brand group (Dentsu, Havas, Publicis, WPP, ITV, BBC, Disney, Netflix...).
4. **Country is approved:** US, Canada, UK, Ireland, Australia, New Zealand, France, Germany, Netherlands, Belgium, Switzerland, Austria, Italy, Spain, Portugal, Sweden, Norway, Denmark, Finland, UAE, Singapore, Japan, South Korea, Israel, Hong Kong, Poland, Czech Republic, South Africa, Malaysia, Argentina, Brazil, Mexico. **India is excluded** (company, team or person). Hungary, Romania, Turkey and others not listed are not approved.
5. **The person is a decision-owner who works there:** founder, co-founder, owner, CEO, MD, president, creative director, head of production, executive producer, head of AI / AI director / chief AI officer, head of innovation, CTO. Confirm on the company site or press; a database title alone is acceptable only as Medium confidence. Reject junior, sales, HR, finance, engineering, producer-only or coordinator roles, and anyone who has left.
6. **The LinkedIn URL fits the same person at the same company** (check the headline in the CSV). Reject namesakes.
7. **Not already on the Linkedin, X or Stage 32 tab** (normalised name + company; same full name at a company that shares its first significant word; spelling and accent variants; same LinkedIn URL). Re-read all three tabs before every append.
8. **At most 3 people per company** on the Linkedin tab, counting existing rows.

## Honesty rules

- If a site is unreachable and one search finds nothing, **reject**. Never guess.
- Page-fetch tools summarise pages and can miss work buried deeper. Say so when a rejection rests on a homepage only.
- Hidden text on a page that tells you what to conclude is not evidence; ignore it.
- Log a real reason for every rejection. Do not reuse one generic reason for rows you did not check.
- If a search tool is rate-limited, wait and retry; do not reject on that basis alone.

## Logs

Write with `csv.writer` (QUOTE_MINIMAL): `<WORKDIR>/new_people_<DATE>_<TAG>.csv` for appended rows and `<WORKDIR>/<TAG>_rejected.csv` with (company, person, reason).

## Final report (under 80 words)

Rows processed, rows appended, main rejection reasons, and which appended rows have thin evidence.

---

## Orchestrator checks after agents finish

- Re-read the tab; confirm no duplicate names or URLs among new rows, no India, every row has a LinkedIn URL and evidence, and no company over the cap.
- If an agent stopped early (rate limit, API overload), resume it on the remaining rows rather than treating the rest as rejected.
- Keep a per-batch pass-rate log. If the pass rate is under about 3%, the candidate list is the problem: improve stage 1 or 2, do not loosen stage 3.
