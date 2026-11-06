# SOP 03: Independent Validation, Reachability & Outreach Readiness

**Version:** 1.0  
**Function:** Independent QA, contradiction resolution, channel readiness and final outreach approval  
**Input:** `ACCOUNT_PASS` records from SOP 01 and `PERSON_PASS` records from SOP 02  
**Output:** Final validated account-person records ready for outreach or correctly held/reworked/rejected

---

## 1. Purpose

The purpose of this SOP is to independently validate the full account-person record before it enters outreach.

This SOP must answer:

> **Is this the correct company, correct buying unit, correct commercial route and correct current person, and is this record ready for outreach through a valid channel without requiring row-by-row human review?**

SOP 03 is not a rubber-stamp step.

It must actively attempt to disprove the conclusions from SOP 01 and SOP 02.

The final record should be trusted only when the evidence survives independent validation.

---

## 2. Entry Gate

SOP 03 may begin only when:

`qualification_decision = ACCOUNT_PASS`

from SOP 01

and:

`qualification_decision = PERSON_PASS`

from SOP 02.

The input must contain at minimum:

### Account-level input

- `account_id`
- `canonical_company_name`
- `operating_buying_unit`
- `buying_unit_country`
- `production_relevance`
- `ai_adoption_stage`
- `primary_commercial_route`
- `relationship_type`
- `internal_build_strength`
- `platform_sold_externally`
- `external_vendor_openness`
- `why_this_company`
- `existing_relationship_status`
- `new_outreach_eligible`
- `commercial_context_version`
- account evidence records

### Person-level input

- `person_id`
- `full_name`
- `personal_linkedin_url`
- `personal_linkedin_status`
- `current_company`
- `operating_buying_unit`
- `raw_current_title`
- `normalized_role_family`
- `employment_status`
- `buying_unit_match`
- `person_relevance_evidence`
- `buying_process_roles`
- `commercial_role_priority`
- `better_person_test_result`
- person evidence records

If either upstream record is not PASS:

do not treat the pair as ready for final validation.

---

## 3. Scope of SOP 03

### SOP 03 DOES

- independently re-check account identity;
- independently re-check buying-unit identity;
- validate geography;
- validate production relevance;
- validate AI-production evidence;
- validate the commercial route;
- validate relationship type;
- validate platform overlap;
- validate current person identity;
- validate current employment;
- validate current title;
- validate buying-unit scope;
- validate person-specific relevance;
- validate P1/P2/P3 priority;
- re-run contradiction checks;
- re-run duplicate checks;
- validate personal LinkedIn profile;
- check visible LinkedIn activity within the previous 12 months;
- determine LinkedIn outreach readiness;
- determine preferred outreach channel;
- detect stale records;
- trigger automated rework where the issue is recoverable;
- hold unresolved records;
- reject invalid records;
- approve final outreach-ready records.

### SOP 03 DOES NOT

- invent a new account;
- invent a new commercial route;
- change the approved geography list;
- lower evidence standards to preserve a record;
- assume a record is correct because SOP 01 or SOP 02 passed it;
- write outreach messages;
- send outreach;
- create arbitrary manual-review queues for every record.

---

## 4. Independent Validation Principle

SOP 03 must behave as an **adversarial validator**.

For every material claim, ask:

> **What evidence would prove this record wrong?**

Do not validate by merely repeating the same conclusion.

The validator should actively look for:

- wrong company;
- wrong subsidiary;
- wrong buying unit;
- stale operating status;
- stale AI-production evidence;
- wrong commercial route;
- hidden competing platform;
- wrong person;
- former employee;
- changed title;
- wrong division;
- wrong geography;
- title-only relevance;
- stronger person missed;
- duplicate record;
- protected relationship;
- inactive or missing LinkedIn profile;
- stale evidence.

The purpose is to find mistakes before outreach, not after.

---

## 5. Validation Unit

The final QA unit is the complete:

> **Account + Operating/Buying Unit + Primary Commercial Route + Person**

Do not validate the person independently of the account route.

Do not validate the account independently of the actual buying unit.

The final outreach record is correct only when all four elements align.

---

## 6. Account Identity Revalidation

Re-check:

- `canonical_company_name`
- `company_domain`
- `parent_company`
- `subsidiary_or_brand`
- `entity_status`
- `operating_buying_unit`

Confirm that the company is still active and the exact operating unit still exists.

If the company has:

- shut down;
- dissolved;
- ceased the relevant operation;

set:

`final_status = REJECT`

Reason:

`R01_ACCOUNT_INACTIVE`

If acquired but the unit still operates meaningfully:

continue validation.

If the current operating status cannot be resolved:

`final_status = HOLD_UNRESOLVED`

Reason:

`H01_ACCOUNT_STATUS_UNRESOLVED`

---

## 7. Buying-Unit Revalidation

Confirm that the exact operating/buying unit from SOP 01 is still the unit connected to the commercial opportunity.

Re-check:

- unit name;
- unit function;
- location;
- parent/subsidiary relationship;
- production responsibility;
- AI-production activity.

Evidence from one unit must not be transferred to another.

If the person belongs to a different unit:

`final_status = REJECT`

Reason:

`R05_WRONG_BUYING_UNIT`

If the correct buying unit exists but its scope cannot be confirmed:

`final_status = HOLD_UNRESOLVED`

Reason:

`H02_BUYING_UNIT_UNRESOLVED`

---

## 8. Geography Revalidation

Re-check:

`buying_unit_country`

against the approved geography table from SOP 01.

Do not use person location as a substitute for buying-unit location.

Do not use parent-headquarters location when the buying unit is elsewhere.

If the relevant buying unit is outside the approved geography:

`final_status = REJECT`

Reason:

`R02_GEO_NOT_APPROVED`

No geography exception may be created inside SOP 03.

---

## 9. Production Relevance Revalidation

Re-check the assigned:

`production_relevance`

Use only:

- `CORE_PRODUCTION_BUSINESS`
- `DEDICATED_INTERNAL_PRODUCTION_UNIT`
- `PRODUCTION_ADJACENT`
- `NO_MEANINGFUL_PRODUCTION`

The validator must confirm that production relevance is supported by evidence tied to the correct company/unit.

If the earlier classification depended on generic brand activity, generic marketing or unrelated AI activity:

invalidate it.

If no meaningful production environment remains established:

`final_status = REJECT`

Reason:

`R03_NO_MEANINGFUL_PRODUCTION`

---

## 10. AI Adoption Revalidation

Re-check the assigned:

`ai_adoption_stage`

Use only:

- `AI_CORE`
- `ACTIVE_PRODUCTION`
- `ACTIVE_TRANSITION`
- `EXPERIMENTING`
- `NO_EVIDENCE`

Confirm that the AI-production evidence belongs to the correct company/unit.

Do not reuse:

- unrelated parent-company AI initiatives;
- old experimental projects;
- marketing AI;
- generic productivity AI;
- unrelated software AI;
- one-off tests;

as proof of operational AI production.

If current evidence supports only:

`EXPERIMENTING`

or:

`NO_EVIDENCE`

set:

`final_status = REJECT`

Reason:

`R04_AI_PRODUCTION_NOT_VALID`

For `ACTIVE_TRANSITION`, re-confirm that a specific commercial route still exists.

---

## 11. Commercial Route Revalidation

Re-check:

`primary_commercial_route`

against the approved route definitions from SOP 01.

Use only:

- `R1_AI_FILM_SERIES`
- `R2_PRODUCTION_ORCHESTRATION`
- `R3_PRIVATE_CUSTOM_STUDIO`
- `R4_WHITE_LABEL_STUDIO`
- `R5_PRODUCTION_CONTEXT_IP`

The validator must confirm:

1. route evidence belongs to the correct buying unit;
2. evidence still supports the route;
3. route is not based only on generic inference;
4. route has not been contradicted by newer evidence.

If route evidence has weakened to:

`PLAUSIBLE_INFERENCE`

set:

`final_status = AUTO_REWORK`

Reason:

`A01_ROUTE_EVIDENCE_REWORK`

If the route is clearly invalid:

`final_status = REJECT`

Reason:

`R06_NO_VALID_COMMERCIAL_ROUTE`

---

## 12. Observed Fact vs Commercial Hypothesis Revalidation

Re-check:

`observed_environment`

and:

`commercial_problem_hypothesis`

The validator must ensure that inferred problems were not stored as confirmed facts.

A hypothesis may remain:

- `DIRECTLY_STATED`
- `STRONG_INFERENCE`
- `PLAUSIBLE_INFERENCE`

The hypothesis itself does not need to be directly stated.

The underlying observed environment must be evidence-backed.

If the account only looks attractive because the hypothesis was treated as fact:

send to:

`AUTO_REWORK`

Reason:

`A02_FACT_HYPOTHESIS_MIXED`

---

## 13. Platform Overlap Revalidation

Re-check:

- `internal_build_strength`
- `platform_name`
- `platform_sold_externally`
- `relationship_type`

Look specifically for newer evidence that the company has:

- launched a production platform;
- commercialized an internal tool;
- sold a workflow product externally;
- expanded platform scope;
- become a direct competitor;
- discontinued a previously relevant platform.

If the company now meets the Competing Platform Test:

reclassify account relationship as:

`COMPETITOR`

and set:

`final_status = REJECT`

for normal buyer outreach.

Reason:

`R07_COMPETITOR`

If overlap exists but remains non-competing:

retain the validated buyer/partner route when supported.

If platform status cannot be resolved and it materially affects buyability:

`final_status = AUTO_REWORK`

Reason:

`A03_PLATFORM_OVERLAP_REWORK`

---

## 14. Relationship Type Revalidation

Re-check the assigned:

`relationship_type`

Use only:

- `CUSTOMER_PROSPECT`
- `WHITE_LABEL_PROSPECT`
- `ENTERPRISE_CUSTOM_DEPLOYMENT_PROSPECT`
- `STRATEGIC_PARTNER`
- `MODEL_OR_INFRA_PARTNER`
- `BUYER_AND_PARTNER`
- `ADJACENT_PLATFORM`
- `COMPETITOR`
- `MARKET_REFERENCE_ONLY`

The validator must confirm that the relationship type still matches the evidence.

Do not preserve `CUSTOMER_PROSPECT` merely because the account is attractive.

Do not preserve `BUYER_AND_PARTNER` unless both paths are independently supported.

If the record belongs only in:

`ADJACENT_PLATFORM`
`COMPETITOR`
`MARKET_REFERENCE_ONLY`

it must not proceed through normal buyer outreach.

---

## 15. Protected Relationship Revalidation

Before final outreach approval, re-check:

`existing_relationship_status`

Use only:

- `NONE`
- `KNOWN_RELATIONSHIP`
- `ACTIVE_CONVERSATION`
- `CURRENT_CUSTOMER`
- `DO_NOT_CONTACT`
- `UNKNOWN`

For:

`ACTIVE_CONVERSATION`
`CURRENT_CUSTOMER`
`DO_NOT_CONTACT`

set:

`new_outreach_eligible = NO`

and:

`final_status = REJECT`

for new outbound.

Reason:

`R08_PROTECTED_RELATIONSHIP`

This does not mean the account is commercially invalid.

It means it must not enter new outbound.

---

## 16. Person Identity Revalidation

Re-check:

- `full_name`
- `personal_linkedin_url`
- `current_company`
- `raw_current_title`
- identity match

Confirm that the profile/source belongs to the correct individual.

Common failure patterns include:

- same-name person;
- wrong company;
- wrong country;
- old profile;
- company page used instead of person page;
- multiple people with similar titles.

If identity is clearly wrong:

`final_status = REJECT`

Reason:

`R09_PERSON_IDENTITY_MISMATCH`

If identity cannot be resolved:

`final_status = HOLD_UNRESOLVED`

Reason:

`H03_PERSON_IDENTITY_UNRESOLVED`

---

## 17. Current Employment Revalidation

Current employment is a mandatory final gate.

Use only:

- `CONFIRMED_CURRENT`
- `FORMER`
- `UNRESOLVED`

Re-check positive current-role evidence and perform a fresh negative departure search.

Look for:

- new employer;
- appointment elsewhere;
- departure;
- updated LinkedIn Experience;
- replacement announcement;
- updated official bio;
- current conference profile.

If newer reliable evidence shows another employer:

`employment_status = FORMER`

and:

`final_status = REJECT`

Reason:

`R10_FORMER_EMPLOYEE`

If current employment cannot be resolved:

`final_status = HOLD_UNRESOLVED`

Reason:

`H04_CURRENT_EMPLOYMENT_UNRESOLVED`

Only `CONFIRMED_CURRENT` may become final outreach-ready.

---

## 18. Current Title Revalidation

Re-check the person's current title.

Do not rely on stale title data.

If the person remains current but title changed:

1. update `raw_current_title`;
2. set `title_changed = YES`;
3. re-run normalized role family;
4. re-run route relevance;
5. re-run P1/P2/P3 priority.

A title change does not automatically reject the person.

If the new title no longer supports relevance:

`final_status = AUTO_REWORK`

Reason:

`A04_TITLE_CHANGED_REASSESS`

If the person clearly no longer owns a relevant function:

`final_status = REJECT`

Reason:

`R11_ROLE_NO_LONGER_RELEVANT`

---

## 19. Buying-Unit Scope Revalidation

Re-check:

`buying_unit_match`

Use only:

- `DIRECT`
- `FUNCTIONAL`
- `PARENT_LEVEL`
- `NO_MATCH`
- `UNRESOLVED`

Final outreach-ready records must have:

`DIRECT`

or:

`FUNCTIONAL`

A `PARENT_LEVEL` person may remain strategically relevant but cannot pass merely because of seniority.

If scope is:

`NO_MATCH`

set:

`final_status = REJECT`

Reason:

`R05_WRONG_BUYING_UNIT`

If:

`UNRESOLVED`

set:

`final_status = HOLD_UNRESOLVED`

Reason:

`H05_PERSON_SCOPE_UNRESOLVED`

---

## 20. Person-Specific Relevance Revalidation

Re-check:

`person_relevance_evidence`

Use only:

- `DIRECT_INITIATIVE_INVOLVEMENT`
- `FUNCTIONAL_SCOPE_CONFIRMED`
- `BUYING_UNIT_LEADERSHIP`
- `TECHNICAL_OWNERSHIP`
- `EXECUTIVE_SPONSORSHIP`
- `TITLE_ONLY_INFERENCE`

`TITLE_ONLY_INFERENCE` cannot pass final outreach validation.

If a record was previously promoted using title-only reasoning:

`final_status = AUTO_REWORK`

Reason:

`A05_PERSON_RELEVANCE_REWORK`

If additional research still cannot establish stronger relevance:

`final_status = REJECT`

Reason:

`R12_TITLE_ONLY_RELEVANCE`

---

## 21. Buying-Process Role Revalidation

Re-check assigned buying-process roles:

- `PRIMARY_PROBLEM_OWNER`
- `TECHNICAL_EVALUATOR`
- `ECONOMIC_STRATEGIC_DECISION_MAKER`
- `EXECUTIVE_SPONSOR`
- `WORKFLOW_OPERATOR_INFLUENCER`

Confirm that each assigned role is supported by current evidence.

Do not assign multiple roles simply because the person is senior.

If the record's buying-process role is not supported:

`final_status = AUTO_REWORK`

Reason:

`A06_BUYING_ROLE_REWORK`

---

## 22. P1 / P2 / P3 Revalidation

Re-check:

`commercial_role_priority`

Use only:

- `P1`
- `P2`
- `P3`

Final validation must ensure that P1 means:

> **the strongest natural first contact for this exact Opportunity Unit and primary commercial route.**

### P1 validation requirements

Confirm:

- current employment;
- correct buying unit;
- strong person-specific relevance;
- route match;
- material ownership/evaluation/sponsorship;
- Better-Person Test completed;
- no stronger person found for the same first-contact role.

### One P1 Rule

For one Opportunity Unit + one primary route:

**only one P1 may survive final validation.**

If multiple P1s exist for the same unit/route:

`final_status = AUTO_REWORK`

Reason:

`A07_MULTIPLE_P1_REWORK`

The validator must determine the strongest P1 and downgrade/remove the others as appropriate.

---

## 23. Better-Person Recheck

SOP 03 must independently challenge the selected P1.

Ask:

> **Has a more direct current owner of this exact route been missed?**

Compare:

1. direct initiative ownership;
2. problem ownership;
3. buying-unit leadership;
4. technical ownership where relevant;
5. commercial authority;
6. executive sponsorship;
7. closeness to actual production workflow.

Do not replace the strongest commercial person merely because another person's data is easier to verify.

If a stronger person is found:

set the current P1 pair to:

`AUTO_REWORK`

Reason:

`A08_BETTER_PERSON_FOUND`

and return the opportunity for reprioritization.

---

## 24. Duplicate Account-Person Pair Check

Check for duplicates across:

- same personal LinkedIn URL;
- same full name + company;
- same person under old/new titles;
- parent/subsidiary duplication;
- multiple routes accidentally creating duplicate outreach to the same person;
- duplicate accounts under brand variations.

Use one canonical record.

If duplicate:

`final_status = REJECT`

Reason:

`R13_DUPLICATE_RECORD`

The surviving canonical record should retain the valid evidence.

---

## 25. Personal LinkedIn Validation

Re-check:

`personal_linkedin_status`

Use only:

- `VERIFIED`
- `NOT_FOUND`
- `UNRESOLVED`

### `VERIFIED`

The personal profile belongs to the correct person.

### `NOT_FOUND`

No personal LinkedIn profile is located.

### `UNRESOLVED`

A likely profile exists but identity match is not reliable.

A company LinkedIn page is never accepted as a person's profile.

If:

`personal_linkedin_status = NOT_FOUND`

the person may still be commercially valid.

They simply cannot become LinkedIn-outreach-ready.

---

## 26. LinkedIn Activity Check

For every verified personal LinkedIn profile, evaluate visible activity in the previous **365 days**.

Store:

`linkedin_activity_12m`

Use only:

- `ACTIVE`
- `INACTIVE`
- `UNKNOWN`

### `ACTIVE`

At least one visible LinkedIn activity exists in the previous 365 days, including:

- post;
- comment;
- reaction;
- visible repost/activity.

### `INACTIVE`

The profile is accessible, but no visible activity is found in the previous 365 days.

### `UNKNOWN`

Activity cannot be reliably determined because of:

- visibility restrictions;
- limited profile access;
- inaccessible activity section;
- technical limitations.

LinkedIn activity affects **channel readiness only**.

It does not affect:

- account fit;
- person fit;
- current employment;
- P1/P2/P3 commercial relevance.

---

## 27. LinkedIn Outreach Readiness

Set:

`linkedin_outreach_ready = YES`

only when all are true:

- `personal_linkedin_status = VERIFIED`
- `linkedin_activity_12m = ACTIVE`
- person otherwise passes final commercial validation
- `new_outreach_eligible = YES`

Set:

`linkedin_outreach_ready = NO`

when:

- profile is not found;
- identity is unresolved;
- activity is inactive;
- activity is unknown;
- protected relationship prevents new outreach;
- person fails final validation.

---

## 28. Preferred Channel

Store:

`preferred_channel`

Use only:

- `LINKEDIN`
- `EMAIL`
- `X`
- `STAGE32`
- `OTHER`
- `NONE`

### `LINKEDIN`

Use when:

`linkedin_outreach_ready = YES`

### `EMAIL`

Use when the person is commercially valid but LinkedIn is not ready and a valid email channel is available later.

SOP 03 does not need to discover the email address itself.

### `X`

Use when the person is commercially valid and X is the better verified active channel.

### `STAGE32`

Use for relevant film/TV/VFX professionals where Stage32 is a verified usable contact channel.

### `OTHER`

Use only when a clearly identified professional channel exists outside the listed options.

### `NONE`

Use when no usable outreach channel has been established.

Do not reject a commercially valid person solely because LinkedIn is inactive.

---

## 29. Final Statuses

Use exactly the following final statuses:

- `OUTREACH_READY`
- `VALID_BUT_LINKEDIN_INACTIVE`
- `AUTO_REWORK`
- `HOLD_UNRESOLVED`
- `REJECT`

---

## 30. `OUTREACH_READY`

Use only when all mandatory commercial and validation gates pass and a usable outreach channel exists.

For LinkedIn-based outreach, this normally requires:

- verified personal LinkedIn;
- `linkedin_activity_12m = ACTIVE`;
- `linkedin_outreach_ready = YES`.

For another approved channel, the person may still become `OUTREACH_READY` when that channel is valid and the commercial record is fully verified.

An `OUTREACH_READY` record should require no row-by-row human QA before normal outreach execution.

---

## 31. `VALID_BUT_LINKEDIN_INACTIVE`

Use when:

- account is valid;
- person is valid;
- current employment is confirmed;
- buying-unit and route relevance are valid;
- personal LinkedIn is verified;
- `linkedin_activity_12m = INACTIVE`;
- LinkedIn is therefore not the preferred outreach route.

This status preserves commercially strong people without incorrectly treating LinkedIn inactivity as lack of commercial relevance.

The record may later be used through:

- email;
- X;
- Stage32;
- another verified channel.

---

## 32. `AUTO_REWORK`

Use when the record is potentially valid and the failure is recoverable through additional automated research or reclassification.

Typical causes include:

- route evidence weakened;
- platform overlap unresolved;
- title changed;
- person relevance insufficiently evidenced;
- multiple P1s;
- stronger person discovered;
- buying-process role needs reassessment;
- evidence mapped to wrong claim;
- freshness threshold exceeded.

The system should automatically perform the prescribed rework.

Do not send these records directly to manual review.

---

## 33. `HOLD_UNRESOLVED`

Use when a mandatory fact cannot be resolved after the prescribed automated rework/search sequence.

Examples:

- current employer conflict;
- buying-unit identity conflict;
- person identity conflict;
- scope cannot be determined;
- company status uncertain;
- material source contradiction remains.

The record remains parked until new evidence becomes available.

Do not guess.

Do not outreach.

---

## 34. `REJECT`

Use when the record is clearly invalid for final outreach.

Examples:

- inactive account;
- non-approved geography;
- no meaningful production;
- invalid AI-production fit;
- wrong buying unit;
- invalid commercial route;
- competitor for buyer motion;
- protected relationship;
- wrong person;
- former employee;
- irrelevant current role;
- title-only relevance after rework;
- duplicate record.

Rejected records must contain an exact reason code.

---

## 35. Automated Rework Sequence

When a record receives `AUTO_REWORK`, perform the following sequence relevant to the failure:

1. re-query primary company sources;
2. re-query personal LinkedIn/current role evidence;
3. re-query official team/leadership pages;
4. re-query company announcements;
5. re-query recent conference/speaker bios;
6. re-query reputable trade sources;
7. re-check route evidence;
8. re-check platform overlap;
9. re-check buying-unit scope;
10. re-run Better-Person Test;
11. re-run duplicate check.

If the issue resolves:

re-run final validation.

If it remains materially unresolved:

`HOLD_UNRESOLVED`

If new evidence disproves the record:

`REJECT`

---

## 36. No Default Human QA

The system should be designed for:

> **zero-human-by-default on final PASS records**

Do not create a default:

`HUMAN_QA_REQUIRED`

status for every uncertain record.

The system must first:

- retry alternate sources;
- resolve contradictions;
- re-run structured checks;
- rework recoverable failures.

Only genuinely unresolved records should remain:

`HOLD_UNRESOLVED`

The final `OUTREACH_READY` set should not require row-by-row manual inspection before normal execution.

---

## 37. Evidence Freshness

Different claims have different refresh needs.

### Account/entity/production fit

Revalidate at least every:

**180 days**

or earlier when a material event occurs.

### Current employer/title

Revalidate before outreach when the last verification is older than:

**60 days**

### LinkedIn activity

Re-check before a new outreach cycle when the existing activity check is no longer current enough for the cycle.

### Why Now

Why Now may expire without invalidating the account.

If the trigger is stale:

update priority.

Do not automatically reject the account.

### Departure event

A confirmed departure immediately invalidates current person outreach readiness.

---

## 38. Commercial Context Version Check

Every final record must contain:

`commercial_context_version`

and:

`validated_against_version`

If the current Commercial Context version differs materially from the version used during earlier qualification:

determine if the change affects:

- approved routes;
- product capability;
- deployment claims;
- relationship type;
- competitive overlap;
- target account logic.

If yes:

`final_status = AUTO_REWORK`

Reason:

`A09_COMMERCIAL_CONTEXT_CHANGED`

Only affected records/routes need revalidation.

Do not re-research the entire universe when the product context changes in a way unrelated to the record.

---

## 39. Claim-Level Evidence Structure

Every material validation claim should remain traceable through:

- `claim_type`
- `claim`
- `source_url`
- `source_type`
- `publication_date`
- `accessed_at`
- `source_tier`
- `source_authority`
- `directness`
- `freshness`
- `supports_or_contradicts`

Do not rely on one generic confidence score.

Do not let AI self-confidence replace evidence quality.

---

## 40. Source Authority

Use the same basic evidence hierarchy as the earlier SOPs.

### Tier A: Direct / Primary

- company website;
- official company/team pages;
- official product pages;
- personal LinkedIn current Experience;
- official company announcements;
- official technical documentation;
- official conference/speaker material;
- official project/case-study pages;
- current employee/executive posts tied to the initiative.

### Tier B: Strong Secondary

- reputable trade publication;
- reputable business publication;
- recognized industry interview;
- named vendor case study;
- reputable conference profile;
- established technical/industry publication.

### Tier C: Discovery Only

- databases;
- directories;
- search snippets;
- scraped profiles;
- aggregators;
- unsourced summaries;
- automated org charts.

Tier C cannot independently clear a mandatory final validation gate.

---

## 41. Contradiction Resolution

When two sources conflict:

1. identify the exact conflicting claim;
2. compare source authority;
3. compare publication/update date;
4. prefer newer direct evidence;
5. prefer official/current primary evidence over secondary when freshness is comparable;
6. preserve the contradictory source in the record;
7. do not delete inconvenient evidence;
8. if the conflict remains material and unresolved:

`HOLD_UNRESOLVED`

Reason:

`H06_EVIDENCE_CONFLICT`

No material unresolved contradiction may become `OUTREACH_READY`.

---

## 42. Final Reason Codes: Auto Rework

Use:

- `A01_ROUTE_EVIDENCE_REWORK`
- `A02_FACT_HYPOTHESIS_MIXED`
- `A03_PLATFORM_OVERLAP_REWORK`
- `A04_TITLE_CHANGED_REASSESS`
- `A05_PERSON_RELEVANCE_REWORK`
- `A06_BUYING_ROLE_REWORK`
- `A07_MULTIPLE_P1_REWORK`
- `A08_BETTER_PERSON_FOUND`
- `A09_COMMERCIAL_CONTEXT_CHANGED`
- `A10_STALE_VALIDATION_REWORK`
- `A11_DUPLICATE_STRUCTURE_REWORK`

---

## 43. Final Reason Codes: Hold

Use:

- `H01_ACCOUNT_STATUS_UNRESOLVED`
- `H02_BUYING_UNIT_UNRESOLVED`
- `H03_PERSON_IDENTITY_UNRESOLVED`
- `H04_CURRENT_EMPLOYMENT_UNRESOLVED`
- `H05_PERSON_SCOPE_UNRESOLVED`
- `H06_EVIDENCE_CONFLICT`
- `H07_LINKEDIN_IDENTITY_UNRESOLVED`
- `H08_ROUTE_OWNERSHIP_UNRESOLVED`

---

## 44. Final Reason Codes: Reject

Use:

- `R01_ACCOUNT_INACTIVE`
- `R02_GEO_NOT_APPROVED`
- `R03_NO_MEANINGFUL_PRODUCTION`
- `R04_AI_PRODUCTION_NOT_VALID`
- `R05_WRONG_BUYING_UNIT`
- `R06_NO_VALID_COMMERCIAL_ROUTE`
- `R07_COMPETITOR`
- `R08_PROTECTED_RELATIONSHIP`
- `R09_PERSON_IDENTITY_MISMATCH`
- `R10_FORMER_EMPLOYEE`
- `R11_ROLE_NO_LONGER_RELEVANT`
- `R12_TITLE_ONLY_RELEVANCE`
- `R13_DUPLICATE_RECORD`
- `R14_WRONG_COMPANY`
- `R15_NO_CURRENT_ROUTE_OWNERSHIP`
- `R16_NO_VALID_OUTREACH_RELATIONSHIP`

---

## 45. Required Output Schema

Every final account-person record should contain at minimum:

| Field | Required |
|---|---|
| `account_id` | Yes |
| `person_id` | Yes |
| `opportunity_unit_id` | Yes |
| `canonical_company_name` | Yes |
| `operating_buying_unit` | Yes |
| `buying_unit_country` | Yes |
| `geography_eligible` | Yes |
| `production_relevance` | Yes |
| `ai_adoption_stage` | Yes |
| `primary_commercial_route` | Yes |
| `relationship_type` | Yes |
| `internal_build_strength` | Yes |
| `platform_sold_externally` | Yes |
| `existing_relationship_status` | Yes |
| `new_outreach_eligible` | Yes |
| `full_name` | Yes |
| `personal_linkedin_url` | When found |
| `personal_linkedin_status` | Yes |
| `linkedin_activity_12m` | Yes when profile verified |
| `linkedin_outreach_ready` | Yes |
| `current_company` | Yes |
| `raw_current_title` | Yes |
| `normalized_role_family` | Yes |
| `employment_status` | Yes |
| `buying_unit_match` | Yes |
| `person_relevance_evidence` | Yes |
| `buying_process_roles` | Yes |
| `commercial_role_priority` | Yes |
| `better_person_test_result` | Yes for P1 |
| `preferred_channel` | Yes |
| `commercial_context_version` | Yes |
| `validated_against_version` | Yes |
| `last_account_validated_at` | Yes |
| `last_person_validated_at` | Yes |
| `linkedin_activity_checked_at` | When applicable |
| `final_status` | Yes |
| `final_reason_code` | Yes when not Outreach Ready |
| `evidence_records` | Yes |

---

## 46. Mandatory Machine Checks Before `OUTREACH_READY`

Before writing:

`final_status = OUTREACH_READY`

confirm all are TRUE:

- account is active or acquired-but-operating;
- correct operating/buying unit is resolved;
- buying-unit geography is approved;
- production relevance is valid;
- AI adoption is valid;
- primary commercial route is valid;
- relationship type is valid for outreach;
- platform overlap is understood;
- protected relationship check allows new outreach;
- person identity is resolved;
- current employment is confirmed;
- negative departure check is current;
- current title is verified;
- buying-unit match is `DIRECT` or `FUNCTIONAL`;
- person-specific relevance is stronger than title-only inference;
- buying-process role is valid;
- P1/P2/P3 priority is valid;
- Better-Person Test is complete for P1;
- duplicate check is complete;
- no material contradiction remains unresolved;
- required evidence is current enough;
- a usable outreach channel exists.

If any mandatory item fails:

**do not mark `OUTREACH_READY`.**

---

## 47. Mandatory Machine Checks for `VALID_BUT_LINKEDIN_INACTIVE`

Before writing:

`final_status = VALID_BUT_LINKEDIN_INACTIVE`

confirm:

- all commercial/account/person validation gates pass;
- personal LinkedIn is verified;
- `linkedin_activity_12m = INACTIVE`;
- LinkedIn outreach is therefore not ready;
- the record remains commercially valid;
- protected relationship does not block future outreach.

Do not downgrade commercial priority solely because LinkedIn is inactive.

---

## 48. Prohibited AI Behaviour

The AI must not:

- assume SOP 01 or SOP 02 is correct without challenge;
- copy upstream PASS status without revalidation;
- ignore contradictory evidence;
- preserve a stale person because they were previously P1;
- treat company-level AI evidence as person evidence;
- use old titles as current;
- use company LinkedIn pages as personal profiles;
- treat LinkedIn inactivity as commercial disqualification;
- create geography exceptions;
- create new route labels;
- create new final statuses;
- keep multiple P1s for one Opportunity Unit + route;
- prefer easier-to-verify people over stronger commercial owners;
- invent current employment;
- invent LinkedIn activity;
- invent outreach channels;
- keep former employees;
- outreach protected relationships;
- turn a competitor into a buyer prospect because the company is attractive;
- use weak evidence to preserve a record;
- send unresolved records into normal outreach;
- require default human review for every record.

---

## 49. Final Validation Sequence

The validator must execute the following order.

### Step 1: Load account and person records

Load SOP 01 + SOP 02 outputs.

### Step 2: Check Commercial Context version

Determine if route/product context changed.

### Step 3: Revalidate account identity

Company, parent, subsidiary, operating status.

### Step 4: Revalidate buying unit

Confirm exact unit and unit location.

### Step 5: Revalidate geography

Apply approved geography table.

### Step 6: Revalidate production relevance

Confirm actual production environment.

### Step 7: Revalidate AI adoption

Confirm AI production evidence.

### Step 8: Revalidate primary commercial route

Confirm route evidence and strength.

### Step 9: Revalidate observed facts vs hypothesis

Correct any fact/hypothesis mixing.

### Step 10: Revalidate platform overlap

Check internal platform and competing product risk.

### Step 11: Revalidate relationship type

Confirm correct commercial relationship.

### Step 12: Revalidate protected relationship status

Confirm new outreach is allowed.

### Step 13: Revalidate person identity

Confirm exact individual.

### Step 14: Revalidate current employment

Positive evidence + negative departure check.

### Step 15: Revalidate current title

Update if changed.

### Step 16: Revalidate buying-unit scope

DIRECT / FUNCTIONAL / PARENT_LEVEL / NO_MATCH / UNRESOLVED.

### Step 17: Revalidate person-specific relevance

Reject title-only logic.

### Step 18: Revalidate buying-process role

Confirm role in decision process.

### Step 19: Revalidate P1/P2/P3

Run Better-Person Test.

### Step 20: Deduplicate

Account + person + title + route + profile.

### Step 21: Validate personal LinkedIn

Confirm correct personal profile.

### Step 22: Check 12-month LinkedIn activity

ACTIVE / INACTIVE / UNKNOWN.

### Step 23: Determine channel readiness

LINKEDIN / EMAIL / X / STAGE32 / OTHER / NONE.

### Step 24: Apply final status

OUTREACH_READY / VALID_BUT_LINKEDIN_INACTIVE / AUTO_REWORK / HOLD_UNRESOLVED / REJECT.

---

## 50. Final Completion Rule

SOP 03 is complete only when the system can state:

> **This is the correct active account, correct operating/buying unit, correct commercial route and correct current person; the relationship type and person priority are evidence-backed; no material contradiction remains unresolved; duplicate and departure checks are complete; channel readiness is known; and the record can either enter outreach safely or has been correctly reworked, held or rejected.**

Only records with:

`final_status = OUTREACH_READY`

may enter normal outreach execution.

Records with:

`VALID_BUT_LINKEDIN_INACTIVE`

remain commercially valid and may be used through another verified channel.

Records with:

`AUTO_REWORK`

must complete the prescribed automated research cycle before re-evaluation.

Records with:

`HOLD_UNRESOLVED`

must remain parked until reliable evidence resolves the issue.

Records with:

`REJECT`

must not enter normal outreach.
