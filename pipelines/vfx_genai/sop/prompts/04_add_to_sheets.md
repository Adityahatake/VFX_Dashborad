# Stage 4: Add validated people to the Google Sheet

**Goal:** append validated people to the target tab, de-duplicated, correctly formatted, with only your own rows coloured white. Nothing else on the sheet changes.

Access is through the service account (`GOOGLE_APPLICATION_CREDENTIALS`) and the sheet ID (`GOOGLE_SHEET_ID`), both from the environment. The tab names are `Linkedin`, `X` and `Stage 32`.

## Linkedin tab: 17 columns, in this order

Confirm the header with `Linkedin!A1:Q1` before writing.

| # | Column | How to fill it |
|---|---|---|
| 1 | name | first + last, no titles or emoji |
| 2 | company | exact company name; when adding a second or third contact, reuse the **exact** string already on the tab |
| 3 | title | cleaned job title |
| 4 | role | P1 founder/CEO/MD; P2 operational or creative lead; P3 technical or other |
| 5 | country | approved country |
| 6 | primary_classification | short label, e.g. "AI-Enabled Creative/Production Lab" or "Production studio / agency" |
| 7 | ai_adoption_stage | `AI Core`, `Active Production` or `Active Transition` |
| 8 | ai_evidence | 1-2 sourced sentences: client or project and tool |
| 9 | primary_commercial_problem | one-sentence hypothesis (R1 AI film/series, R2 orchestration, R3 private/custom, R4 white-label, R5 context/IP). A hypothesis, not a fact |
| 10 | why_this_person | one person-specific sentence |
| 11 | qualification_decision | `PASS-A` (Tier A evidence and the site confirms the person) or `PASS-B` |
| 12 | qa_decision | `PASS` |
| 13 | qa_confidence | `High` or `Medium` (Medium when the title is from a database only, or evidence is thin) |
| 14 | outreach_readiness | `Ready` |
| 15 | contact_or_reference | the personal `linkedin.com/in/...` URL, exactly |
| 16 | contact_or_reference_type | `Personal LinkedIn` |
| 17 | evidence_source | full URLs separated by `;` (company evidence plus the page confirming the person). Never leave blank: fall back to the company website |

The X tab has 30 columns (the 17 above reordered with `x_handle`, plus check columns). Read `X!A1:AD1` and copy the style of an existing PASS row. Overlap with the Linkedin tab is allowed on the X tab only when explicitly permitted.

## Procedure

1. **Re-read all three tabs immediately before every append** (other people and agents write in parallel). Rebuild the dedupe sets each time.
2. **Dedupe** by normalised name+company, same full name at a company sharing its first significant word, accent and spelling variants, and LinkedIn URL. Skip duplicates silently and log them.
3. **Check** each row: exactly 17 columns, `linkedin.com/in/` in column 15, a non-empty evidence_source, company cap of 3 not exceeded, no India.
4. **Append** with `values:append` using `valueInputOption=RAW` and `insertDataOption=INSERT_ROWS`, range `'Linkedin'!A1`, in batches of 5-10. Check the returned updated range.
5. **Format only your own rows.** After appending, find the row numbers of the rows you just wrote (match by name and company against your log) and apply, **per row**, a white background and black text over columns A-Q. Appended rows can inherit the colour of the row above (this once produced blue and green rows). Never format a range that could include other people's rows, and never touch an existing colour.
6. **Do not** delete, reorder or edit rows you did not add. If you must remove one of your own rows (for example it breaks the contact cap), say so.
7. **Verify** afterwards: count rows added against your baseline, re-run the duplicate, India, cap and URL checks on your rows, and confirm the row colours.

## Things that went wrong before (avoid)

- Appending rows without re-reading the tab, which created duplicates and over-cap companies.
- Blank `evidence_source` when the earlier row for that company had none.
- Rewriting a whole range white, which wiped the green markings the team had put on rows.
- Counting rows other people added as your own. Always count from your logs plus a baseline, and report any extra rows you did not add.
- A fourth contact at a company, an India-based contact, and a person whose LinkedIn headline was only a name with no company.

## Report

Rows added (net new since baseline), rows rejected as duplicates, any rows removed, checks passed, and the row range written.
