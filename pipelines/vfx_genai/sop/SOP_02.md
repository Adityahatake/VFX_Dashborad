# SOP 02: Decision-Owner Discovery & Qualification

**Version:** 1.0  
**Function:** Decision-maker discovery, current-role verification and commercial-role qualification  
**Input:** `ACCOUNT_PASS` records from SOP 01  
**Next SOP:** SOP 03, Independent Validation, Reachability & Outreach Readiness

---

## 1. Purpose

The purpose of this SOP is to identify the **current people who materially own, influence, evaluate or approve the specific commercial route already established in SOP 01**.

The SOP must answer:

> **Who currently owns or materially influences this exact commercial route inside this exact operating/buying unit, and what is each person's role in the buying process?**

This SOP does not search for generic senior people.

It does not treat job title alone as decision-maker proof.

It does not assume the CEO, CTO, Creative Director, Producer, Head of AI or Head of Production is automatically the best first contact.

The person must be linked to:

1. the correct company;
2. the correct operating/buying unit;
3. the specific primary commercial route;
4. a current role;
5. a commercially relevant function or scope.

---

## 2. Entry Gate

SOP 02 may begin only when SOP 01 has produced:

`qualification_decision = ACCOUNT_PASS`

The SOP 01 record must contain at minimum:

- `account_id`
- `canonical_company_name`
- `operating_buying_unit`
- `buying_unit_country`
- `production_relevance`
- `ai_adoption_stage`
- `primary_commercial_route`
- `relationship_type`
- `observed_environment`
- `why_this_company`
- `commercial_context_version`

If the account is:

- `ACCOUNT_REVIEW`
- `ACCOUNT_REJECT`
- `STRATEGIC_NON_BUYER`

do not run normal buyer decision-owner discovery.

---

## 3. Scope of SOP 02

### SOP 02 DOES

- discover current people in the verified buying unit;
- verify personal identity;
- verify current employment;
- verify current title;
- verify operating-unit or functional scope;
- classify role family;
- determine person-specific relevance;
- determine buying-process role;
- assign P1/P2/P3;
- apply the better-person test;
- detect duplicate and former-employee records;
- correct stale titles when current evidence exists;
- identify unresolved person records;
- produce a clean person set for SOP 03.

### SOP 02 DOES NOT

- re-qualify the company from zero;
- change geography rules;
- create new commercial routes;
- write outreach messages;
- judge LinkedIn activity within the last 12 months;
- decide final outreach readiness;
- decide final outreach channel;
- find or validate email addresses;
- perform final independent QA;
- create artificial person quotas.

If research reveals a material contradiction in the SOP 01 account record, do not silently correct it inside SOP 02.

Flag:

`ACCOUNT_REVALIDATION_REQUIRED = YES`

and return the account for account-level revalidation.

---

## 4. Core Research Principle

The research sequence is:

> **Verified Buying Unit → Primary Commercial Route → Required Buying Roles → Candidate Person → Current Employment → Functional Scope → Person-Specific Relevance → Commercial Priority**

Do not use:

> **Company → Senior Title → P1**

Do not use:

> **Company → Search Result → P1**

Do not use:

> **Title Sounds Relevant → PASS**

The purpose is not to collect many executives.

The purpose is to identify the **smallest evidence-backed set of people that covers the actual buying process**.

---

## 5. Research Unit

Every person must be evaluated against:

`account_id`

plus:

`operating_buying_unit`

plus:

`primary_commercial_route`

This combination is the **Opportunity Unit**.

A person may be relevant to the parent company but irrelevant to the specific Opportunity Unit.

A person cannot inherit relevance solely because they work somewhere inside the same global company.

---

## 6. Candidate Discovery Sources

Candidate people may be discovered from:

- personal LinkedIn profiles;
- official company leadership/team pages;
- official company announcements;
- company newsroom;
- production credits;
- official project/case-study pages;
- conference speaker pages;
- industry event bios;
- official technical or creative presentations;
- current employee posts;
- reputable trade interviews;
- production-industry databases;
- search engines;
- company org pages;
- current job or team announcements.

Discovery sources may reveal candidates.

They do not automatically prove current employment, current scope or commercial priority.

---

## 7. Role Families

Every qualified person must receive exactly one primary normalized role family.

Use only the following role families.

### 7.1 `PRODUCTION_LEADERSHIP`

Typical functions:

- Head of Production
- VP Production
- Production Director
- Executive Production leadership
- Studio production leadership
- production operations leadership

Use when the person's current scope includes ownership of production delivery, workflow, resources or production operations.

---

### 7.2 `AI_GENERATIVE_PRODUCTION`

Typical functions:

- Head of Generative AI
- AI Production Lead
- Generative AI Producer
- Creative AI Lead
- AI filmmaking lead
- AI studio/lab production leadership

Use when the person's current role directly owns or leads generative-AI production activity.

---

### 7.3 `CREATIVE_TECHNOLOGY`

Typical functions:

- Head of Creative Technology
- Creative Technologist leadership
- Emerging Technology leadership
- Innovation Technology leadership
- AI creative systems leadership

Use only when the current scope connects technology to actual production or production workflow.

Generic innovation titles are not enough.

---

### 7.4 `VFX_LEADERSHIP`

Typical functions:

- Head of VFX
- VFX Supervisor leadership
- VFX Operations leadership
- senior VFX production leadership

Use when the commercial route materially touches VFX workflow, production integration or technical delivery.

---

### 7.5 `PIPELINE_PRODUCTION_TECHNOLOGY`

Typical functions:

- Head of Pipeline
- Pipeline Supervisor
- Production Technology leadership
- Workflow Engineering leadership
- Technical Pipeline leadership
- Production Systems leadership

Use when the person's current scope includes production pipelines, integrations, workflow systems or technical production infrastructure.

---

### 7.6 `TECHNOLOGY_INFRASTRUCTURE`

Typical functions:

- CTO
- Head of Technology
- VP Engineering
- Infrastructure leadership
- Compute/GPU leadership
- Platform Engineering leadership

Use when the primary route materially involves:

- deployment;
- private infrastructure;
- compute;
- APIs;
- platform integration;
- security;
- production architecture.

A CTO is not automatically relevant to every route.

---

### 7.7 `FILM_SERIES_LEADERSHIP`

Typical functions:

- Head of Film
- Head of Series
- Studio content leadership
- Development/production leadership
- narrative production leadership
- senior film/episodic production executive

Use when the primary route is specifically connected to film, episodic or long-form narrative production.

---

### 7.8 `PRODUCT_PLATFORM`

Typical functions:

- Product leadership
- Platform leadership
- Product Strategy leadership
- Product Operations leadership

Use when the commercial route involves:

- white-label productization;
- client-facing platform;
- workflow product;
- production software/platform deployment.

---

### 7.9 `FOUNDER_OPERATING_EXECUTIVE`

Typical functions:

- Founder
- Co-founder
- CEO
- Managing Director
- President
- Owner

Use primarily when:

- the company is small or founder-led; or
- the executive directly owns the relevant commercial or production function.

Do not use seniority alone as relevance.

---

### 7.10 `CREATIVE_LEADERSHIP`

Typical functions:

- Chief Creative Officer
- Executive Creative Director
- Creative Director
- Head of Creative

Use only when current evidence shows direct responsibility for:

- AI production;
- production systems;
- production adoption;
- relevant workflow;
- film/series production;
- production technology decisions.

Generic creative authority alone is not enough.

---

## 8. Normally Excluded Functions

The following functions are normally excluded from buyer decision-owner qualification unless current evidence directly ties them to the specific Opportunity Unit:

- Sales
- Business Development
- Partnerships
- PR
- Communications
- HR
- Talent Acquisition
- Finance
- Legal
- Marketing
- Brand Marketing
- Social Media
- Customer Success
- General Operations
- Account Management

They may only qualify when reliable evidence shows that the person directly owns or materially influences the specific commercial route.

Do not infer this from seniority.

---

## 9. Raw Title and Normalized Role Family

Store both:

`raw_current_title`

and:

`normalized_role_family`

Never replace the person's actual title with the normalized role family.

Example:

`raw_current_title = SVP, Creative & AI`

`normalized_role_family = AI_GENERATIVE_PRODUCTION`

The raw title preserves source accuracy.

The normalized role family supports consistent qualification.

---

## 10. Person Identity Verification

Every candidate must have a unique person identity.

Record:

- `full_name`
- `personal_linkedin_url`
- `current_company`
- `raw_current_title`
- `location` where available

A personal LinkedIn profile is preferred for identity resolution.

A company LinkedIn page is **not** a personal LinkedIn profile.

A company page must never be stored in:

`personal_linkedin_url`

If only a company page is found:

`personal_linkedin_status = NOT_FOUND`

The person may remain a candidate if identity is supported elsewhere, but cannot be treated as having a verified personal LinkedIn profile.

---

## 11. Current Employment Verification

Every candidate must receive exactly one:

`employment_status`

Use only:

- `CONFIRMED_CURRENT`
- `FORMER`
- `UNRESOLVED`

### 11.1 `CONFIRMED_CURRENT`

Use when at least one current reliable source explicitly supports the person's present role/employer and no newer contradictory evidence establishes departure.

Acceptable sources include:

- personal LinkedIn current Experience;
- official company leadership/team page;
- current company announcement;
- current company speaker/profile page;
- recent conference bio;
- current industry speaker bio;
- current official project/team page.

A headline alone is not enough when Experience or stronger current evidence contradicts it.

---

### 11.2 `FORMER`

Use when reliable newer evidence establishes that the person has left the relevant company or moved to another employer.

A former employee cannot qualify for current buyer outreach.

Result:

`PERSON_REJECT`

Reason:

`R01_FORMER_EMPLOYEE`

---

### 11.3 `UNRESOLVED`

Use when:

- current role cannot be confirmed;
- sources conflict;
- role dates are unclear;
- one source says current while newer evidence suggests departure;
- only stale secondary sources exist.

Result:

`PERSON_REVIEW`

Reason:

`U01_CURRENT_EMPLOYMENT_UNRESOLVED`

Do not guess.

---

## 12. Mandatory Negative Departure Check

For every serious candidate, perform a contradiction/departure check.

Search for evidence such as:

- joined another company;
- appointed at another company;
- new role announcement;
- departure announcement;
- official bio showing another employer;
- newer LinkedIn Experience;
- newer conference bio;
- company leadership replacement.

The negative check exists to prevent stale current-employer records.

A person cannot be marked `CONFIRMED_CURRENT` simply because an old article still lists them at the company.

---

## 13. Evidence Freshness for Current Role

For current-employment verification, prefer:

1. current personal LinkedIn Experience;
2. current official company team/leadership page;
3. current company announcement;
4. recent official conference/speaker bio;
5. recent reputable industry bio;
6. older direct evidence;
7. database or aggregator evidence only for discovery.

When two reliable sources conflict:

**newer direct evidence outranks older direct evidence.**

When freshness is similar:

**official/current primary evidence outranks secondary evidence.**

If conflict cannot be resolved:

`employment_status = UNRESOLVED`

---

## 14. Buying-Unit Match

Every candidate must receive:

`buying_unit_match`

Use only:

- `DIRECT`
- `FUNCTIONAL`
- `PARENT_LEVEL`
- `NO_MATCH`
- `UNRESOLVED`

### `DIRECT`

The person is explicitly part of the exact operating/buying unit.

### `FUNCTIONAL`

The person sits in a centralized function that clearly owns or materially governs the relevant route across the buying unit.

Example:

central production technology leadership supporting multiple studios.

### `PARENT_LEVEL`

The person works at parent-company level but no evidence establishes direct ownership of the relevant unit or route.

`PARENT_LEVEL` alone cannot create P1.

### `NO_MATCH`

Evidence places the person in another division, brand, geography or operating unit with no established relevance to the Opportunity Unit.

Result:

`PERSON_REJECT`

Reason:

`R03_WRONG_BUYING_UNIT`

### `UNRESOLVED`

Current evidence cannot establish unit scope.

Result:

`PERSON_REVIEW`

Reason:

`U02_BUYING_UNIT_SCOPE_UNRESOLVED`

---

## 15. Person-Specific Relevance Evidence

Company-level evidence cannot automatically become person-level evidence.

Every qualified person must receive one primary:

`person_relevance_evidence`

Use only:

- `DIRECT_INITIATIVE_INVOLVEMENT`
- `FUNCTIONAL_SCOPE_CONFIRMED`
- `BUYING_UNIT_LEADERSHIP`
- `TECHNICAL_OWNERSHIP`
- `EXECUTIVE_SPONSORSHIP`
- `TITLE_ONLY_INFERENCE`

### 15.1 `DIRECT_INITIATIVE_INVOLVEMENT`

Use when the person is directly named in the relevant AI-production initiative, platform, project, studio, workflow or implementation.

This is the strongest person-specific evidence.

### 15.2 `FUNCTIONAL_SCOPE_CONFIRMED`

Use when reliable current evidence establishes that the person's function directly owns the workflow/problem represented by the primary commercial route.

### 15.3 `BUYING_UNIT_LEADERSHIP`

Use when the person leads the exact operating/buying unit and that unit owns the relevant commercial problem.

### 15.4 `TECHNICAL_OWNERSHIP`

Use when the person owns the technical architecture, pipeline, infrastructure, integrations or deployment environment tied to the commercial route.

### 15.5 `EXECUTIVE_SPONSORSHIP`

Use when the person has clear executive responsibility for the relevant unit/initiative and can materially sponsor commercial adoption.

### 15.6 `TITLE_ONLY_INFERENCE`

Use when relevance is inferred only from the person's title and not from stronger evidence.

`TITLE_ONLY_INFERENCE` cannot become P1.

It may remain a candidate for additional research.

---

## 16. Commercial Role in the Buying Process

Every qualified person must receive at least one buying-process role.

Use only:

- `PRIMARY_PROBLEM_OWNER`
- `TECHNICAL_EVALUATOR`
- `ECONOMIC_STRATEGIC_DECISION_MAKER`
- `EXECUTIVE_SPONSOR`
- `WORKFLOW_OPERATOR_INFLUENCER`

### 16.1 `PRIMARY_PROBLEM_OWNER`

The person most directly owns the workflow, production system, production operation or business problem represented by the route.

### 16.2 `TECHNICAL_EVALUATOR`

The person evaluates:

- architecture;
- integrations;
- deployment;
- security;
- APIs;
- compute;
- workflow feasibility;
- technical implementation.

### 16.3 `ECONOMIC_STRATEGIC_DECISION_MAKER`

The person materially controls:

- budget;
- commercial approval;
- strategic adoption;
- vendor approval;
- business-case acceptance.

### 16.4 `EXECUTIVE_SPONSOR`

The person can create internal priority, cross-functional access or organizational sponsorship.

### 16.5 `WORKFLOW_OPERATOR_INFLUENCER`

The person is close enough to the workflow to materially shape adoption, requirements or internal credibility, but is not the primary buyer.

A person may hold more than one buying-process role when evidence supports it.

---

## 17. Route-Specific Role Logic

Person priority must follow the primary commercial route.

Do not use the same title priority for every route.

### 17.1 R1 `AI_FILM_SERIES`

Most relevant role families normally include:

- `AI_GENERATIVE_PRODUCTION`
- `FILM_SERIES_LEADERSHIP`
- `PRODUCTION_LEADERSHIP`
- `CREATIVE_TECHNOLOGY`
- `FOUNDER_OPERATING_EXECUTIVE` in smaller companies

Technical roles may be P2/P3 when workflow/infrastructure evaluation matters.

---

### 17.2 R2 `PRODUCTION_ORCHESTRATION`

Most relevant role families normally include:

- `PRODUCTION_LEADERSHIP`
- `PIPELINE_PRODUCTION_TECHNOLOGY`
- `AI_GENERATIVE_PRODUCTION`
- `VFX_LEADERSHIP`
- `CREATIVE_TECHNOLOGY`

A CEO or CTO is not automatically P1 unless evidence shows direct ownership of the workflow problem.

---

### 17.3 R3 `PRIVATE_CUSTOM_STUDIO`

Most relevant role families normally include:

- `TECHNOLOGY_INFRASTRUCTURE`
- `PIPELINE_PRODUCTION_TECHNOLOGY`
- `PRODUCTION_LEADERSHIP`
- `AI_GENERATIVE_PRODUCTION`
- `FOUNDER_OPERATING_EXECUTIVE` for smaller organizations

Technical ownership carries more weight here than generic creative seniority.

---

### 17.4 R4 `WHITE_LABEL_STUDIO`

Most relevant role families normally include:

- `FOUNDER_OPERATING_EXECUTIVE`
- `PRODUCT_PLATFORM`
- `AI_GENERATIVE_PRODUCTION`
- `PRODUCTION_LEADERSHIP`

The P1 should normally be the person who can decide how the company productizes or delivers the workflow to customers.

---

### 17.5 R5 `PRODUCTION_CONTEXT_IP`

Most relevant role families normally include:

- `PRODUCTION_LEADERSHIP`
- `AI_GENERATIVE_PRODUCTION`
- `PRODUCT_PLATFORM`
- `CREATIVE_TECHNOLOGY`
- `TECHNOLOGY_INFRASTRUCTURE`
- relevant `FILM_SERIES_LEADERSHIP`

Priority depends on who owns the reusable production assets/context and how they are operationalized.

---

## 18. P1 / P2 / P3 Priority System

Priority is assigned **per Opportunity Unit**, not per company in general.

### 18.1 P1

P1 is:

> **The strongest natural first contact for this specific buying unit and this specific primary commercial route.**

A P1 must satisfy all of the following:

- `employment_status = CONFIRMED_CURRENT`
- buying-unit match is `DIRECT` or `FUNCTIONAL`
- person relevance is stronger than `TITLE_ONLY_INFERENCE`
- role directly matches the primary route
- person has material ownership, evaluation authority or commercial sponsorship
- no better current person has been identified for the same first-contact role

### One P1 Rule

For one Opportunity Unit + one primary commercial route:

**assign only one P1.**

A second P1 may exist only when the same account contains a **separate Opportunity Unit or separate primary commercial route** with a genuinely different natural owner.

Do not assign multiple P1s merely because several people are senior.

---

### 18.2 P2

P2 is a high-value secondary stakeholder who adds a different buying role.

Examples:

- technical evaluator behind a production-lead P1;
- production owner behind a technical P1;
- executive sponsor;
- product/platform owner;
- commercial approval stakeholder.

P2 must add distinct value.

Do not duplicate the P1's function with another similar title unless evidence shows separate authority.

---

### 18.3 P3

P3 is a useful tertiary stakeholder who may:

- influence implementation;
- influence workflow requirements;
- provide technical validation;
- provide operational credibility;
- help navigate the buying unit.

P3 is not a generic list of everyone relevant.

Each P3 must add a distinct buying-process function.

---

## 19. Better-Person Test

Before finalizing any P1, ask:

> **Is there another confirmed-current person in this buying unit who owns the problem more directly, owns the initiative more directly, or is a more natural first contact for this route?**

If yes:

the stronger person becomes P1.

The previous candidate may become P2/P3 or be removed.

The Better-Person Test must compare:

1. direct initiative involvement;
2. buying-unit ownership;
3. functional ownership;
4. route relevance;
5. buying authority;
6. current-role confidence.

Seniority alone does not win.

---

## 20. Commercial Priority vs Verification Status

Commercial relevance and verification confidence are separate.

Store:

`commercial_role_priority`

and:

`verification_status`

Do not demote a commercially ideal person merely because their data is harder to verify.

Example:

A direct head of the relevant AI-production initiative may remain the strongest commercial candidate even while employment verification is unresolved.

In that case:

`commercial_role_priority = P1_CANDIDATE`

but:

`qualification_decision = PERSON_REVIEW`

The system must research the unresolved evidence.

It must not silently replace the person with a weaker stakeholder simply because the weaker stakeholder is easier to verify.

---

## 21. Title Change Handling

If the person remains at the same company/unit but their title has changed:

1. keep the person record;
2. replace stale title with current verified title;
3. preserve previous title in history if needed;
4. re-evaluate normalized role family;
5. re-evaluate commercial priority;
6. record:

`title_changed = YES`

Do not reject a person solely because the title changed.

---

## 22. Former Employee Handling

If a candidate has left the company:

- set `employment_status = FORMER`
- set `qualification_decision = PERSON_REJECT`
- use reason `R01_FORMER_EMPLOYEE`
- do not retain them as a current P1/P2/P3
- do not use old company title as current evidence

Where practical, continue discovery to identify the current replacement or current owner of the function.

---

## 23. Duplicate Person Handling

A person may appear through multiple sources, titles or search results.

Deduplicate using:

1. personal LinkedIn URL;
2. full name + company + current title;
3. official company bio;
4. location/function as supporting evidence.

Do not create separate records for:

- old title vs new title;
- shortened vs full name;
- multiple source URLs;
- parent-company and subsidiary references to the same person.

Use one canonical person record.

---

## 24. No Person Quota

There is no required number of people per company.

Do not force:

- 3 people;
- 5 people;
- 10 people;
- 15 people.

The correct number is:

> **the smallest set of verified people that covers the distinct buying roles needed for the Opportunity Unit.**

Stop adding people when a new person adds no new buying-process value.

Typical account sizes may naturally produce different numbers of people, but these are not quotas.

---

## 25. Small / Founder-Led Company Rule

For small or founder-led companies, the founder/CEO may legitimately be P1 when they directly control:

- production;
- product;
- commercial adoption;
- technology;
- customer delivery.

Do not force extra stakeholders when the organization is genuinely centralized.

One strong confirmed decision owner may be enough.

---

## 26. Large Enterprise Rule

For large enterprises:

do not default to parent-level executives.

First identify the exact unit that owns the Opportunity Unit.

Then identify the people responsible for:

- production/workflow ownership;
- technical evaluation;
- budget/strategic approval;
- executive sponsorship where needed.

A global executive may be useful, but parent-level seniority does not override unit-level ownership.

---

## 27. Personal LinkedIn Rules

Store:

`personal_linkedin_status`

Use only:

- `VERIFIED`
- `NOT_FOUND`
- `UNRESOLVED`

### `VERIFIED`

The URL clearly belongs to the correct person and matches current or historical company/role identity.

### `NOT_FOUND`

No personal LinkedIn profile could be located after reasonable search.

### `UNRESOLVED`

A likely profile exists but identity cannot be confidently matched.

A company page is never `VERIFIED` personal LinkedIn.

Personal LinkedIn availability does not determine commercial relevance.

It affects later channel readiness in SOP 03.

---

## 28. Evidence Hierarchy for Person Qualification

Use the following hierarchy.

### Tier A: Direct / Primary

- personal LinkedIn current Experience;
- official company bio;
- official team page;
- official company announcement;
- official project/case-study credit;
- official conference or event bio;
- current company-authored post;
- official technical/creative presentation.

### Tier B: Strong Secondary

- reputable trade interview;
- reputable industry publication;
- reputable business publication;
- recognized conference profile;
- current vendor case study naming the person.

### Tier C: Discovery Only

- people databases;
- scraped profiles;
- search snippets;
- generic directories;
- automated org charts;
- old list articles;
- aggregator pages.

Tier C may discover a person.

Tier C alone cannot establish:

- current employment;
- buying-unit match;
- P1 status.

---

## 29. Minimum Evidence Required for Person Qualification

A person cannot become `PERSON_PASS` unless reliable evidence establishes:

### A. Identity

The person is correctly identified.

### B. Current Employment

`employment_status = CONFIRMED_CURRENT`

### C. Relevant Unit or Function

`buying_unit_match = DIRECT or FUNCTIONAL`

### D. Person-Specific Relevance

One of:

- `DIRECT_INITIATIVE_INVOLVEMENT`
- `FUNCTIONAL_SCOPE_CONFIRMED`
- `BUYING_UNIT_LEADERSHIP`
- `TECHNICAL_OWNERSHIP`
- `EXECUTIVE_SPONSORSHIP`

### E. Route Relevance

The person's current role materially connects to the primary commercial route.

### F. Buying-Process Role

At least one approved buying-process role is assigned.

`TITLE_ONLY_INFERENCE` alone cannot satisfy Person PASS.

---

## 30. Person Qualification Decision

Use exactly three outcomes.

### `PERSON_PASS`

Use when:

- identity is resolved;
- employment is confirmed current;
- buying-unit/function match is established;
- route relevance is supported;
- person-specific relevance is stronger than title-only inference;
- buying-process role is resolved;
- no material contradiction remains.

The person may proceed to SOP 03.

---

### `PERSON_REVIEW`

Use when the person may be relevant but a mandatory fact remains unresolved.

The system should run additional source checks.

If still unresolved, the person remains parked.

Do not promote unresolved records to P1/P2/P3 final output.

---

### `PERSON_REJECT`

Use when the person clearly fails a current/relevance gate.

Rejected people do not proceed to SOP 03.

---

## 31. Review Reason Codes

Use:

- `U01_CURRENT_EMPLOYMENT_UNRESOLVED`
- `U02_BUYING_UNIT_SCOPE_UNRESOLVED`
- `U03_PERSON_IDENTITY_UNRESOLVED`
- `U04_PERSON_RELEVANCE_UNRESOLVED`
- `U05_ROUTE_RELEVANCE_UNRESOLVED`
- `U06_TITLE_SCOPE_CONFLICT`
- `U07_SOURCE_CONTRADICTION`
- `U08_BETTER_PERSON_TEST_INCOMPLETE`
- `U09_PERSONAL_LINKEDIN_UNRESOLVED`

Do not use generic:

> Needs more research.

---

## 32. Reject Reason Codes

Use:

- `R01_FORMER_EMPLOYEE`
- `R02_WRONG_COMPANY`
- `R03_WRONG_BUYING_UNIT`
- `R04_NO_ROUTE_RELEVANCE`
- `R05_TITLE_ONLY_NO_SUPPORT`
- `R06_DUPLICATE_PERSON`
- `R07_FUNCTION_NOT_COMMERCIALLY_RELEVANT`
- `R08_IDENTITY_MISMATCH`

A rejected person must have an exact reason.

---

## 33. Person Research Sequence

The AI/researcher must execute the following order.

### Step 1: Load the SOP 01 Opportunity Unit

Load:

- company;
- buying unit;
- primary route;
- relationship type;
- observed environment.

### Step 2: Determine required buying roles

Based on the primary route, identify which roles are likely needed:

- primary problem owner;
- technical evaluator;
- economic/strategic decision maker;
- executive sponsor;
- workflow influencer.

Do not search titles before defining the required buying roles.

### Step 3: Discover candidate people

Search within the exact company/unit/function.

### Step 4: Resolve person identity

Confirm the correct individual.

### Step 5: Verify current employment

Use direct/current evidence.

### Step 6: Run negative departure check

Look for newer employer/departure evidence.

### Step 7: Verify raw current title

Do not rely on stale title data.

### Step 8: Resolve buying-unit/function scope

Classify:

`DIRECT / FUNCTIONAL / PARENT_LEVEL / NO_MATCH / UNRESOLVED`

### Step 9: Normalize role family

Assign one approved role family.

### Step 10: Determine person-specific relevance

Use one of the approved relevance values.

### Step 11: Determine buying-process role

Assign one or more approved buying roles.

### Step 12: Evaluate route relevance

Confirm that the person's scope fits the primary route.

### Step 13: Run Better-Person Test

Compare against other verified candidates.

### Step 14: Assign commercial priority

P1 / P2 / P3 only after the better-person test.

### Step 15: Validate personal LinkedIn identity

Record status, but do not use activity yet.

### Step 16: Deduplicate

Merge duplicate person records.

### Step 17: Apply person qualification decision

`PERSON_PASS / PERSON_REVIEW / PERSON_REJECT`

### Step 18: Stop when buying-role coverage is complete

Do not keep adding people with no additional buying value.

---

## 34. P1 Selection Order

When several people appear relevant, compare them in this order:

1. direct involvement in the exact initiative/workflow;
2. direct ownership of the problem represented by the primary route;
3. direct leadership of the buying unit;
4. technical ownership where the route is technical;
5. authority to sponsor or approve adoption;
6. closeness to actual production use;
7. current-role verification strength.

Do not prioritize:

- highest corporate seniority;
- most impressive title;
- easiest person to find;
- strongest LinkedIn presence;
- source availability alone.

---

## 35. Required Output Schema

Every researched person should contain at minimum:

| Field | Required |
|---|---|
| `person_id` | Yes |
| `account_id` | Yes |
| `opportunity_unit_id` | Yes |
| `full_name` | Yes |
| `personal_linkedin_url` | When found |
| `personal_linkedin_status` | Yes |
| `current_company` | Yes |
| `operating_buying_unit` | Yes |
| `raw_current_title` | Yes |
| `normalized_role_family` | Yes |
| `employment_status` | Yes |
| `employment_evidence` | Yes |
| `negative_departure_check` | Yes |
| `buying_unit_match` | Yes |
| `buying_unit_scope_evidence` | Yes |
| `primary_commercial_route` | Yes |
| `person_relevance_evidence` | Yes |
| `person_relevance_evidence_detail` | Yes |
| `buying_process_roles` | Yes |
| `commercial_role_priority` | Yes |
| `better_person_test_result` | Yes for P1 |
| `title_changed` | Yes/No |
| `verification_status` | Yes |
| `qualification_decision` | Yes |
| `decision_reason_code` | Yes when non-PASS |
| `source_records` | Yes |
| `last_person_validated_at` | Yes |

---

## 36. Commercial Role Priority Values

Use:

- `P1`
- `P2`
- `P3`
- `P1_CANDIDATE`
- `UNPRIORITIZED`

### `P1`

Final strongest first contact for the Opportunity Unit.

### `P2`

Secondary stakeholder adding a distinct buying role.

### `P3`

Tertiary stakeholder adding distinct implementation, influence or validation value.

### `P1_CANDIDATE`

Commercially appears strongest, but verification is incomplete.

A `P1_CANDIDATE` cannot move forward as final P1 until the unresolved gate is cleared.

### `UNPRIORITIZED`

Candidate not yet ranked or not strong enough to merit P1/P2/P3.

---

## 37. Verification Status

Use:

- `VERIFIED`
- `PARTIALLY_VERIFIED`
- `UNRESOLVED`
- `CONTRADICTED`

This field describes evidence quality.

It does **not** replace `qualification_decision`.

Example:

A person may be commercially strongest but `verification_status = UNRESOLVED`.

They remain a candidate, not a final outreach-ready contact.

---

## 38. Mandatory Machine Checks Before `PERSON_PASS`

Before writing `PERSON_PASS`, confirm all are TRUE:

- person identity is resolved;
- current employer is confirmed;
- negative departure check is complete;
- raw current title is current;
- person belongs to the correct buying unit or directly relevant centralized function;
- normalized role family is valid;
- person-specific relevance is stronger than `TITLE_ONLY_INFERENCE`;
- primary commercial route relevance is established;
- at least one buying-process role is assigned;
- no material source contradiction remains unresolved;
- duplicate check is complete.

For P1, additionally confirm:

- Better-Person Test is complete;
- no stronger current person has been identified for the same first-contact role;
- this is the only P1 for this Opportunity Unit + primary route.

If any mandatory item fails:

**do not mark `PERSON_PASS`.**

---

## 39. Prohibited AI Behaviour

The AI must not:

- assign P1 because a title sounds senior;
- assign the CEO automatically;
- assign the CTO automatically;
- assign a Creative Director automatically;
- assign a Producer automatically;
- assign a Head of AI automatically;
- use company-level AI evidence as person-level evidence;
- infer current employment from an old article;
- use LinkedIn headline alone when Experience contradicts it;
- keep a former employee as current;
- use a company LinkedIn page as a personal LinkedIn profile;
- assign multiple P1s for the same Opportunity Unit and route merely because several people seem relevant;
- create person quotas;
- keep adding similar stakeholders with no new buying role;
- promote `TITLE_ONLY_INFERENCE` to P1;
- prioritize source availability over commercial ownership;
- treat parent-level seniority as buying-unit ownership;
- silently change a stale title without recording the correction;
- ignore newer contradictory employment evidence;
- invent additional role families;
- invent additional priority labels;
- invent additional buying-process roles.

---

## 40. Final SOP 02 Completion Rule

SOP 02 is complete only when the system can state:

> **The current people who materially own, evaluate, influence or approve this exact commercial route inside this exact buying unit have been identified; their employment, scope and relevance are evidence-backed; one natural first contact has been selected where appropriate; and every additional person adds a distinct buying-process role.**

Only `PERSON_PASS` records proceed to:

**SOP 03: Independent Validation, Reachability & Outreach Readiness**

Any unresolved candidate remains outside final outreach until the missing evidence is resolved.
