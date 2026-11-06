# SOP 01: Account & Opportunity-Unit Discovery, Research & Commercial Qualification

**Version:** 1.0  
**Function:** Account-level research and qualification  
**Next SOP:** SOP 02, Decision-Owner Discovery & Qualification

---

## 1. Purpose

The purpose of this SOP is to identify companies and specific operating/buying units that have a credible commercial relationship path for the product.

The SOP must answer:

> **Is there a verified company or operating unit where there is a real commercial route, and what type of relationship should be pursued?**

This SOP does **not** identify individual decision-makers.

It establishes the account and commercial opportunity first.

A company must not pass simply because:

- it uses AI;
- it works in media;
- it has a senior AI team;
- it has appeared in a relevant article;
- it is a famous enterprise;
- it has a VFX, production or creative label;
- it uses Runway, Veo, ComfyUI or another AI tool.

The final account must have an identifiable production environment and a specific commercial route.

---

## 2. Scope of SOP 01

### SOP 01 DOES

- discover candidate companies;
- verify the real company/entity;
- identify the relevant operating or buying unit;
- determine geography eligibility;
- classify production relevance;
- determine AI-production adoption;
- identify the commercial route;
- classify the commercial relationship;
- assess internal-platform overlap;
- assess external-vendor openness;
- separate observed facts from commercial hypotheses;
- determine account qualification;
- record account-level evidence;
- produce a clean account record for SOP 02.

### SOP 01 DOES NOT

- find people;
- assign P1/P2/P3;
- identify executives;
- validate personal LinkedIn profiles;
- check LinkedIn activity;
- find emails;
- write outreach messages;
- decide the best individual contact;
- use a person title as proof of account fit.

**No people research should be performed inside SOP 01.**

---

## 3. Required Inputs Before Research Starts

Every research run must use the following inputs.

### 3.1 Commercial Context

The current approved Commercial Context must contain:

- current product positioning;
- currently available capabilities;
- approved commercial routes;
- current deployment options;
- approved claims;
- current commercial priorities.

Every account record must store:

`commercial_context_version`

and:

`validated_against_version`

The SOP itself should not be rewritten every time the product adds a feature.

The Commercial Context is updated separately.

### 3.2 Approved Geography Table

Only the geographies defined in Section 6 may qualify for normal outbound commercial research.

The AI must not add additional countries because they appear commercially attractive.

### 3.3 Protected Account Register

Before final qualification, check internal relationship data when available.

Use:

- `NONE`
- `KNOWN_RELATIONSHIP`
- `ACTIVE_CONVERSATION`
- `CURRENT_CUSTOMER`
- `DO_NOT_CONTACT`
- `UNKNOWN`

An existing relationship does not make the account commercially invalid.

It changes:

`new_outreach_eligible`

For:

- `ACTIVE_CONVERSATION`
- `CURRENT_CUSTOMER`
- `DO_NOT_CONTACT`

set:

`new_outreach_eligible = NO`

---

## 4. Core Research Principle

The research sequence is:

> **Company → Operating/Buying Unit → Production Environment → AI Adoption → Commercial Route → Relationship Type → Commercial Qualification**

Do not use:

> Company → Relevant-looking title → PASS

Do not qualify an entire global parent because one subsidiary or business unit uses AI.

Do not transfer evidence from one division to another.

---

## 5. Candidate Discovery

A company may enter the **research stage** when at least one credible discovery signal exists.

Discovery signals include:

- film, TV, VFX, post-production or animation work;
- AI-native production activity;
- virtual production;
- commercial video production;
- branded-content production;
- internal enterprise content studio;
- dedicated AI creative or production lab;
- generative-AI production case study;
- AI video/film/series project;
- production pipeline using generative AI;
- AI production hiring;
- production infrastructure or private-compute activity;
- AI production platform or internal workflow;
- recurring production using multiple AI models/tools;
- reusable media/IP/asset libraries connected to AI production;
- creator-led AI production business with real commercial activity;
- localization/dubbing/media workflow with a credible commercial route;
- current vendor case study showing production use.

**Discovery is not qualification.**

Directories, databases and search results may be used to discover candidates.

They must not by themselves make an account PASS.

---

## 6. Geography Rules

The geography test applies to the **relevant operating/buying unit**, not automatically to the global parent headquarters.

For a single-unit studio, the company location may be used as the buying-unit location.

For a multi-division enterprise, use the location of the unit that would realistically evaluate or use the product.

### 6.1 Primary Approved Geographies

- United States
- Canada
- United Kingdom
- Ireland
- Australia
- New Zealand
- France
- Germany
- Netherlands
- Belgium
- Switzerland
- Austria
- Italy
- Spain
- Portugal
- Sweden
- Norway
- Denmark
- Finland

Set:

`geography_tier = PRIMARY`

### 6.2 Additional Approved Geographies

- United Arab Emirates
- Singapore
- Japan
- South Korea
- Israel
- Hong Kong
- India
- Poland
- Czech Republic
- South Africa
- Malaysia
- Argentina
- Brazil
- Mexico

Set:

`geography_tier = ADDITIONAL`

### 6.3 All Other Geographies

For normal buyer/partner outbound:

`geography_eligible = NO`

The account must not become a normal outbound PASS.

It may only remain in the database as:

`MARKET_REFERENCE_ONLY`

or another non-outbound strategic classification when commercially useful.

Do not use:

- “other mature markets”;
- “similar countries”;
- “strong company exception”;
- “high-quality account exception.”

New geographies can only be added by updating the Approved Geography Table.

---

## 7. Company and Entity Verification

Before commercial qualification, verify that the researched organization is real and currently operating.

Use:

`entity_status`

with exactly:

- `ACTIVE`
- `ACQUIRED_BUT_OPERATING`
- `INACTIVE`
- `UNRESOLVED`

### `ACTIVE`

Company is currently operating under the researched identity.

### `ACQUIRED_BUT_OPERATING`

Company has been acquired or merged but still operates as a recognizable business, studio, brand or production unit.

It may continue through qualification.

### `INACTIVE`

Company has shut down, dissolved, ceased operations, or the relevant business/unit no longer operates.

Result:

`ACCOUNT_REJECT`

### `UNRESOLVED`

Available evidence does not establish current operating status.

Result:

`ACCOUNT_REVIEW`

Do not guess.

---

## 8. Canonical Company Resolution

Record:

- `canonical_company_name`
- `company_domain`
- `parent_company`
- `subsidiary_or_brand`
- `company_country`
- `company_linkedin_url`

where available.

Different names referring to the same operating business must be normalized.

Example structures may include:

`Parent → Subsidiary → Studio`

or:

`Parent → Business Unit → AI Lab`

Do not create separate accounts simply because different articles use slightly different brand names.

---

## 9. Operating / Buying Unit Resolution

This is a mandatory field for enterprise accounts.

Record:

- `operating_buying_unit`
- `buying_unit_type`
- `buying_unit_country`
- `buying_unit_evidence`

### 9.1 Use the Entire Company as the Buying Unit When

The company itself is the production business and there is no separate relevant division.

Examples of structures that normally fall here:

- standalone VFX studio;
- AI-native production studio;
- animation studio;
- production company;
- creator-led commercial studio;
- independent post-production company.

Set:

`operating_buying_unit = canonical_company_name`

### 9.2 Use a Specific Unit When

Public evidence connects the relevant AI-production activity to a named:

- studio;
- division;
- lab;
- production arm;
- business unit;
- regional operation;
- product organization;
- content organization.

The parent company alone must not be used when the actual opportunity sits inside a specific unit.

### 9.3 Buying-Unit Mismatch

Evidence from one unit cannot qualify another unit.

For example:

`Parent Company → Division A has the AI-production initiative → Division B workflow is unrelated`

Division B cannot inherit Division A's qualification.

### 9.4 Unresolved Buying Unit

For a large/multi-business company, if the relevant operating unit cannot be identified:

`ACCOUNT_REVIEW`

Reason:

`U01_BUYING_UNIT_UNRESOLVED`

Do not pass the parent company generically.

---

## 10. Production Relevance Classification

Every account must receive exactly one primary value.

### 10.1 `CORE_PRODUCTION_BUSINESS`

Use when producing film, video, VFX, animation, virtual production, post-production or related professional media is a core commercial activity.

Typical structures include:

- production studios;
- VFX studios;
- post-production companies;
- AI filmmaking studios;
- animation studios;
- virtual-production studios;
- commercial/branded-content production companies.

### 10.2 `DEDICATED_INTERNAL_PRODUCTION_UNIT`

Use when the parent organization's primary industry is something else, but a named internal unit performs meaningful production work.

Examples:

`Brand / Broadcaster / Media Company → Internal Content Studio / Creative Production Lab / AI Content Unit / Internal Film-Video Production Team`

The internal unit must be identifiable.

Generic marketing activity is not enough.

### 10.3 `PRODUCTION_ADJACENT`

Use when the organization is not primarily a production business but operates a meaningful workflow directly connected to one of the approved commercial routes.

This may include:

- localization/dubbing;
- production technology;
- media technology;
- creative technology;
- certain creative agencies;
- content automation;
- production-platform businesses.

`PRODUCTION_ADJACENT` does not automatically qualify.

A specific commercial route must still be established.

### 10.4 `NO_MEANINGFUL_PRODUCTION`

Use when research finds only:

- generic AI use;
- marketing AI;
- productivity AI;
- text/content automation;
- generic digital agency services;
- isolated design experimentation;
- unrelated software activity;
- no meaningful media-production workflow.

Result:

`ACCOUNT_REJECT`

Reason:

`R03_NO_MEANINGFUL_PRODUCTION`

---

## 11. Creator-Led and Very Small Businesses

Do not automatically reject a company because it is founder-led or small.

A creator-led business may qualify when public evidence establishes:

1. real commercial operation;
2. a real AI-assisted production workflow;
3. at least one approved commercial route.

Commercial operation may be established through:

- paying clients;
- commissioned work;
- named brand work;
- distributed commercial content;
- recurring commercial production services;
- a production product/service sold to external customers.

A hobby creator, portfolio-only individual or non-commercial experimental account must not qualify.

Use:

`R07_HOBBY_OR_NONCOMMERCIAL`

when commercial operation is not established.

---

## 12. AI Adoption Classification

Every account must receive exactly one value.

### 12.1 `AI_CORE`

Generative AI is central to the company's commercial production model, production product or production service.

Examples of evidence:

- AI-native studio;
- production platform built around GenAI;
- GenAI is the primary method used to create commercial output;
- dedicated AI-production business.

### 12.2 `ACTIVE_PRODUCTION`

Generative AI is already being used in real commercial production but is not the entire business.

Evidence may include:

- named client project;
- commercial film/campaign;
- production case study;
- operational production pipeline;
- recurring AI-assisted production.

### 12.3 `ACTIVE_TRANSITION`

The company is actively moving AI into production, but recurring production use is not yet sufficiently established.

Evidence may include:

- dedicated AI production unit;
- relevant hiring;
- current AI-production partnership;
- implementation of new infrastructure;
- named production pilot;
- current formal production initiative.

`ACTIVE_TRANSITION` can qualify only when a specific commercial route is supported.

### 12.4 `EXPERIMENTING`

Evidence shows isolated or exploratory use without enough proof of operational production.

Examples:

- one experimental short;
- innovation experiment;
- one proof-of-concept;
- non-commercial test;
- exploratory AI content.

For normal buyer qualification:

`ACCOUNT_REJECT`

Reason:

`R05_EXPERIMENTAL_ONLY`

### 12.5 `NO_EVIDENCE`

No reliable evidence of relevant generative-AI production activity.

Result:

`ACCOUNT_REJECT`

Reason:

`R04_NO_RELEVANT_AI_PRODUCTION`

---

## 13. Commercial Routes

Every qualifying commercial opportunity must have:

`primary_commercial_route`

Only one primary route is allowed.

Secondary routes may be recorded only when separately supported by evidence.

Use exactly the following routes.

### R1: `AI_FILM_SERIES`

Use for:

- AI film production;
- episodic production;
- long-form narrative;
- series production;
- scripted or narrative workflow;
- AI-native filmmaking;
- hybrid traditional + AI filmmaking.

Evidence must show both:

1. film/series/narrative production relevance; and
2. generative AI entering that production environment.

### R2: `PRODUCTION_ORCHESTRATION`

Use when the production environment contains meaningful workflow coordination complexity.

Strong qualifying evidence includes:

- multiple AI models/tools used inside production;
- AI generation combined with VFX/post/editing/live action;
- multi-stage AI production pipeline;
- custom production pipeline;
- dedicated pipeline/workflow function;
- recurring workflow moving assets between multiple systems.

This route is not established merely because a company uses one AI model.

### R3: `PRIVATE_CUSTOM_STUDIO`

Use when the production environment has an identifiable need or architecture involving:

- private deployment;
- on-premise deployment;
- VPC/private cloud;
- customer-controlled compute;
- render farms;
- organization GPUs;
- own model infrastructure;
- own API keys;
- sensitive/proprietary production data;
- custom infrastructure integrations;
- controlled/offline production environments.

At least one of the above must be supported by reliable evidence.

Do not assign R3 simply because the company is large.

### R4: `WHITE_LABEL_STUDIO`

Use for an external client-facing AI-production business where both are established:

1. it commercially serves external clients/customers; and
2. it operates a repeatable AI-production workflow.

Typical candidates include:

- AI-native production studios;
- creator-led commercial studios;
- production agencies;
- specialized AI content companies.

The company does not already need to operate a white-label platform.

The route is based on its commercial delivery model and repeatable workflow.

### R5: `PRODUCTION_CONTEXT_IP`

Use when the organization has meaningful reusable production context such as:

- footage libraries;
- media archives;
- recurring characters;
- recurring environments;
- franchise/IP assets;
- brand visual systems;
- licensed media collections;
- reusable character or product assets;
- large existing content libraries.

The assets must be relevant to repeated production, not simply exist somewhere in the company.

---

## 14. Route Evidence Strength

For the primary route, assign:

- `DIRECTLY_STATED`
- `STRONG_INFERENCE`
- `PLAUSIBLE_INFERENCE`

### `DIRECTLY_STATED`

The company/source directly describes the workflow, infrastructure or production situation supporting the route.

### `STRONG_INFERENCE`

The route is not stated explicitly, but documented facts clearly establish the environment.

Example:

Documented use of multiple generation models + Nuke + live action in one production pipeline strongly supports production orchestration.

### `PLAUSIBLE_INFERENCE`

The route appears possible but evidence does not establish it strongly enough.

`PLAUSIBLE_INFERENCE` cannot become final Account PASS.

Result:

`ACCOUNT_REVIEW`

Reason:

`U03_ROUTE_EVIDENCE_WEAK`

---

## 15. Observed Environment vs Commercial Hypothesis

Never present an inferred problem as a confirmed fact.

Store separately.

### `observed_environment`

What reliable evidence actually establishes.

Example:

> Company uses multiple generative-video tools alongside VFX and traditional post-production.

### `commercial_problem_hypothesis`

The likely commercial issue the product may address.

Example:

> Production orchestration across models and downstream post-production.

### `hypothesis_strength`

Use:

- `DIRECTLY_STATED`
- `STRONG_INFERENCE`
- `PLAUSIBLE_INFERENCE`

A hypothesis may help positioning.

It must not overwrite the underlying observed evidence.

---

## 16. Internal Build Strength

Every account must receive exactly one value.

### `NONE`

No meaningful internal production tooling identified beyond normal third-party software.

### `LIGHT_INTERNAL_TOOLING`

The company has:

- scripts;
- plugins;
- small automations;
- utilities;
- internal helpers;

but no broader production workflow system.

### `CUSTOM_WORKFLOWS`

The company has custom pipelines, nodes, integrations or automations connecting production tools, but no named multi-stage platform.

### `PARTIAL_PLATFORM`

The company has a named internal platform or workspace covering multiple parts of production but not a broad end-to-end production environment.

### `FULL_INTERNAL_PLATFORM`

The company has a named system covering major parts of the production lifecycle and used materially within the organization or by customers.

Also record:

`platform_sold_externally = YES / NO / UNKNOWN`

---

## 17. Competing Platform Test

An internal system is **not automatically a competitor**.

Use `EXTERNAL_COMPETING_PRODUCT` only when the company sells a platform/workspace to external production customers and that product covers at least **two** of the following functions:

1. multi-model generation or model orchestration;
2. production workflow/state management;
3. asset/reference/context management;
4. collaboration/review;
5. compute/deployment control;
6. client-facing or white-label production environment.

If the platform is only an internal tool:

do not classify it as a competitor solely for being internally developed.

If external overlap exists but is not strong enough to meet the test:

use:

`ADJACENT_PLATFORM`

---

## 18. External Vendor Openness

Assign exactly one value.

### `STRONG`

Evidence shows either:

- two or more named external AI/model/cloud/production vendors currently used in production; or
- a current formal external vendor partnership/integration directly tied to production.

### `PRESENT`

At least one named external vendor/tool is currently used or integrated into relevant production.

### `WEAK`

Reliable current evidence explicitly emphasizes a predominantly proprietary/closed/internal-only production stack and little or no openness to external production systems.

Do not use `WEAK` merely because the company has built internal tools.

### `UNKNOWN`

Public evidence does not establish vendor openness.

Do not guess.

---

## 19. Relationship Type

Each opportunity must receive exactly one primary relationship type.

### `CUSTOMER_PROSPECT`

A credible path exists for the organization/unit to use the product as production software/workspace.

### `WHITE_LABEL_PROSPECT`

R4 is a valid commercial route and the company could commercially deploy the product as part of its own client-facing production business.

### `ENTERPRISE_CUSTOM_DEPLOYMENT_PROSPECT`

R3 is a valid route and private/custom/infrastructure deployment is central to the commercial opportunity.

### `STRATEGIC_PARTNER`

The stronger commercial relationship is integration, channel, industry collaboration or another strategic partnership rather than normal software purchase.

### `MODEL_OR_INFRA_PARTNER`

The company primarily provides:

- AI models;
- GPU infrastructure;
- cloud infrastructure;
- inference;
- production infrastructure;

and the relevant relationship is provider/infrastructure partnership.

### `BUYER_AND_PARTNER`

Independent evidence supports both:

1. a real customer route; and
2. a strategic/provider/integration relationship.

Do not use this value simply because both sound possible.

### `ADJACENT_PLATFORM`

The company operates an overlapping production platform/product but does not meet the direct competitor test.

### `COMPETITOR`

The company sells a materially overlapping external production platform meeting the Competing Platform Test.

### `MARKET_REFERENCE_ONLY`

The company is useful for:

- market understanding;
- competitor intelligence;
- category evidence;
- trend monitoring;

but no present commercial relationship route is established.

---

## 20. Buyer Likelihood

This field is used only for commercial prioritization.

It does **not** override mandatory qualification gates.

Use:

- `HIGH`
- `MEDIUM`
- `LOW`
- `NOT_APPLICABLE`

### `HIGH`

Customer route is valid, no external competing platform blocks the motion, and:

`external_vendor_openness = STRONG or PRESENT`

### `MEDIUM`

Customer route is valid, but vendor openness is:

`UNKNOWN`

or the company has substantial internal custom workflows that may lengthen adoption.

### `LOW`

A customer route exists, but current evidence shows:

`external_vendor_openness = WEAK`

or:

`internal_build_strength = FULL_INTERNAL_PLATFORM`

and the platform is not externally competitive.

### `NOT_APPLICABLE`

Use for:

- competitor;
- market reference;
- non-buyer strategic classification.

Buyer Likelihood never rescues a failed account gate.

---

## 21. Why This Company

Mandatory for all `ACCOUNT_PASS` records.

The field must answer:

> **Why does this specific company/unit fit one commercial route?**

It must reference actual evidence.

Do not write generic statements such as:

- “Company is innovative.”
- “Company uses AI.”
- “Company could benefit from the product.”
- “Company works in media.”

A useful Why This Company should identify:

- production environment;
- relevant AI use;
- commercial route.

---

## 22. Why Now

`why_now` is **not mandatory for account fit**.

A high-quality account may remain valid even when no current trigger exists.

Record:

`why_now_status`

as:

- `CURRENT_TRIGGER`
- `NO_CURRENT_TRIGGER`
- `UNKNOWN`

A current trigger may include:

- new AI production launch;
- new production platform;
- relevant hiring;
- AI production team creation;
- new commercial AI project;
- new vendor partnership;
- infrastructure rollout;
- new studio/lab;
- production expansion;
- new AI film/series initiative.

Why Now affects priority.

It does not determine underlying account fit.

---

## 23. Evidence Hierarchy

Use three evidence tiers.

### Tier A: Direct / Primary Evidence

Highest confidence.

Includes:

- company website;
- company case study;
- official product/platform page;
- official job description;
- company newsroom;
- company press release;
- official company presentation;
- official conference presentation;
- current company executive/employee post discussing the initiative;
- official technical documentation.

### Tier B: Strong Secondary Evidence

Includes:

- reputable trade publication;
- reputable business publication;
- named vendor customer case study;
- industry interview;
- technical case study from a recognized technology provider;
- credible conference/report coverage.

Tier B may support qualification when specific and clearly attributable.

### Tier C: Discovery-Only Evidence

Includes:

- company directories;
- databases;
- search snippets;
- generic list articles;
- scraped profiles;
- aggregator pages;
- generic AI wording;
- unsourced summaries.

Tier C may discover an account.

Tier C alone cannot satisfy a mandatory qualification gate.

---

## 24. Evidence Record Format

For every material claim, save:

- `claim_type`
- `claim`
- `source_url`
- `source_type`
- `publication_date`
- `accessed_at`
- `source_tier`
- `supports_or_contradicts`

Do not store one long `evidence_source` field containing unrelated URLs without mapping them to claims.

---

## 25. Minimum Evidence Required for Account PASS

An account cannot PASS unless reliable evidence establishes all of the following:

### A. Company / unit exists and operates

### B. Relevant production environment exists

### C. Relevant AI adoption meets one of:

- `AI_CORE`
- `ACTIVE_PRODUCTION`
- qualifying `ACTIVE_TRANSITION`

### D. At least one commercial route is supported at:

- `DIRECTLY_STATED`
- `STRONG_INFERENCE`

### E. Relationship type is resolved

### F. Buying unit is resolved when a separate unit is required

### G. Geography is approved

Tier C evidence alone cannot satisfy any of these mandatory items.

There is no arbitrary requirement such as “three sources per company.”

One strong source may establish multiple facts.

---

## 26. Qualification Decision

Use exactly four outcomes.

### `ACCOUNT_PASS`

Use when:

- entity is active or acquired-but-operating;
- geography is approved;
- production relevance is valid;
- AI adoption is sufficient;
- buying unit is resolved;
- at least one commercial route is properly supported;
- relationship type is resolved;
- no unresolved material contradiction remains.

`ACCOUNT_PASS` records may move to SOP 02.

This includes valid:

- customer prospects;
- white-label prospects;
- enterprise custom-deployment prospects;
- strategic partners;
- model/infra partners;
- buyer-and-partner opportunities.

### `STRATEGIC_NON_BUYER`

Use for accounts classified primarily as:

- `COMPETITOR`
- `ADJACENT_PLATFORM`
- `MARKET_REFERENCE_ONLY`

These remain useful in the research database.

They do not enter the normal buyer decision-maker workflow.

### `ACCOUNT_REVIEW`

Use when the account may be valid but a mandatory fact remains unresolved.

No guessing is allowed.

The system should run an alternate-source research pass.

If still unresolved, the account remains parked.

It does not proceed to SOP 02.

### `ACCOUNT_REJECT`

Use when a mandatory eligibility condition has clearly failed.

Rejected accounts do not proceed to SOP 02.

---

## 27. Review Reason Codes

Use:

- `U01_BUYING_UNIT_UNRESOLVED`
- `U02_ENTITY_STATUS_UNRESOLVED`
- `U03_ROUTE_EVIDENCE_WEAK`
- `U04_PLATFORM_OVERLAP_UNRESOLVED`
- `U05_BUYING_UNIT_LOCATION_UNRESOLVED`
- `U06_EVIDENCE_CONFLICT`
- `U07_RELATIONSHIP_TYPE_UNRESOLVED`

An `ACCOUNT_REVIEW` record must contain at least one reason code.

Do not use generic text such as:

> Needs more research.

---

## 28. Reject Reason Codes

Use:

- `R01_ENTITY_INACTIVE`
- `R02_GEO_NOT_APPROVED`
- `R03_NO_MEANINGFUL_PRODUCTION`
- `R04_NO_RELEVANT_AI_PRODUCTION`
- `R05_EXPERIMENTAL_ONLY`
- `R06_NO_COMMERCIAL_ROUTE`
- `R07_HOBBY_OR_NONCOMMERCIAL`
- `R08_REQUIRED_EVIDENCE_NOT_VERIFIED`

A rejected record must include the exact reason.

---

## 29. Strategic Non-Buyer Reason Codes

Use:

- `S01_COMPETITOR`
- `S02_ADJACENT_PLATFORM`
- `S03_MARKET_REFERENCE_ONLY`

No company should be marked `STRATEGIC_NON_BUYER` merely because it is difficult to approach.

Commercial accessibility and commercial fit are different issues.

---

## 30. Account Research Sequence

The AI/researcher must execute the following order.

### Step 1: Load current Commercial Context

Record version.

### Step 2: Normalize the company

Confirm canonical company and operating identity.

### Step 3: Verify entity status

`ACTIVE / ACQUIRED_BUT_OPERATING / INACTIVE / UNRESOLVED`

### Step 4: Resolve parent/subsidiary/unit structure

Determine whether company-level qualification is valid or a buying unit is required.

### Step 5: Apply geography rule

No geography exception may be created by the AI.

### Step 6: Classify production relevance

Choose one of the four approved values.

### Step 7: Verify commercial production operation

Especially important for small/creator-led businesses.

### Step 8: Determine AI adoption stage

Use only the approved five stages.

### Step 9: Identify observable production environment

Record factual workflow evidence.

### Step 10: Assign commercial route

One primary route.

Secondary routes only when independently supported.

### Step 11: Determine route evidence strength

`DIRECTLY_STATED / STRONG_INFERENCE / PLAUSIBLE_INFERENCE`

### Step 12: Assess internal build strength

Use the five defined values.

### Step 13: Check external platform overlap

Apply the Competing Platform Test.

### Step 14: Assess external vendor openness

`STRONG / PRESENT / WEAK / UNKNOWN`

### Step 15: Assign relationship type

Choose one controlled value.

### Step 16: Check protected relationship status

Set `new_outreach_eligible`.

### Step 17: Record Why This Company

Evidence-based.

### Step 18: Record Why Now

Trigger or no trigger.

### Step 19: Resolve contradictions

Conflicting evidence must not be silently ignored.

### Step 20: Apply qualification decision

`PASS / STRATEGIC_NON_BUYER / REVIEW / REJECT`

Only after all mandatory gates are complete.

---

## 31. Account Priority Inputs

SOP 01 should collect the inputs needed for later prioritization, but **qualification and ranking must remain separate**.

Record:

- `geography_tier`
- `production_relevance`
- `ai_adoption_stage`
- `primary_commercial_route`
- `route_evidence_strength`
- `internal_build_strength`
- `external_vendor_openness`
- `buyer_likelihood`
- `why_now_status`
- `relationship_type`

Do not reject a valid account because it has a lower priority.

Do not pass an invalid account because it would be commercially valuable.

---

## 32. No Golden List Rule

SOP 01 does not create:

- Golden 500;
- Golden 1,000;
- Golden 3,000;
- fixed-size account list.

The system builds a continuously qualified account universe.

Later, the best 100, 500, 1,000, 3,000 or another number can be selected from validated records using priority.

Qualification does not change based on outreach capacity.

---

## 33. Freshness and Refresh

Account records must be revalidated at least every:

**180 days**

or earlier when a material event occurs.

Examples:

- acquisition;
- shutdown;
- new AI division;
- new platform launch;
- relevant merger;
- major production-technology change;
- new commercial route;
- platform becomes externally sold;
- company relationship changes.

An older case study may remain valid evidence.

The **account status** must still be refreshed.

Store:

- `last_account_validated_at`
- `next_account_refresh_due`

---

## 34. Contradiction Handling

When sources conflict:

1. do not choose the result that best fits the desired qualification;
2. identify the newer and more authoritative evidence;
3. record the contradicting source;
4. resolve using source authority and freshness;
5. if material conflict remains unresolved, assign:

`ACCOUNT_REVIEW`

with:

`U06_EVIDENCE_CONFLICT`

No unresolved material contradiction may become Account PASS.

---

## 35. Required Output Schema

Every researched account should contain at minimum:

| Field | Required |
|---|---|
| `account_id` | Yes |
| `canonical_company_name` | Yes |
| `company_domain` | Yes where available |
| `company_linkedin_url` | Yes where available |
| `parent_company` | Yes/None |
| `subsidiary_or_brand` | Yes/None |
| `entity_status` | Yes |
| `company_country` | Yes |
| `operating_buying_unit` | Yes |
| `buying_unit_type` | Yes |
| `buying_unit_country` | Yes |
| `geography_tier` | Yes |
| `geography_eligible` | Yes |
| `production_relevance` | Yes |
| `commercial_activity_evidence` | Yes when applicable |
| `ai_adoption_stage` | Yes |
| `ai_production_evidence` | Yes |
| `observed_environment` | Yes |
| `primary_commercial_route` | Yes for PASS |
| `secondary_commercial_routes` | Optional |
| `route_evidence_strength` | Yes |
| `commercial_problem_hypothesis` | Yes for PASS |
| `hypothesis_strength` | Yes |
| `internal_build_strength` | Yes |
| `platform_name` | If applicable |
| `platform_sold_externally` | Yes |
| `external_vendor_openness` | Yes |
| `relationship_type` | Yes |
| `buyer_likelihood` | Yes |
| `why_this_company` | Yes for PASS |
| `why_now_status` | Yes |
| `why_now` | When trigger exists |
| `existing_relationship_status` | Yes |
| `new_outreach_eligible` | Yes |
| `qualification_decision` | Yes |
| `decision_reason_code` | Yes when non-PASS |
| `commercial_context_version` | Yes |
| `last_account_validated_at` | Yes |
| `next_account_refresh_due` | Yes |
| `evidence_records` | Yes |

---

## 36. Mandatory Machine Checks Before Account PASS

Before writing `ACCOUNT_PASS`, confirm all statements below are TRUE:

- entity is active or acquired-but-operating;
- relevant buying unit is resolved;
- buying-unit country is approved;
- production relevance is not `NO_MEANINGFUL_PRODUCTION`;
- AI adoption is not `EXPERIMENTING` or `NO_EVIDENCE`;
- active-transition accounts have a specific qualifying route;
- commercial operation is established for creator-led/small studios;
- one primary commercial route is assigned;
- primary-route evidence is not `PLAUSIBLE_INFERENCE`;
- relationship type is resolved;
- platform overlap has been evaluated;
- evidence includes Tier A or Tier B support;
- no material evidence contradiction remains unresolved;
- Why This Company is evidence-based;
- protected-account status has been checked where internal data is available.

If any mandatory item fails:

**do not PASS.**

---

## 37. Prohibited AI Behaviour

The AI must not:

- invent a geography exception;
- infer production activity solely from LinkedIn industry;
- qualify an account solely because it uses AI;
- qualify an account because it is a famous brand;
- use parent-company evidence for an unrelated business unit;
- treat internal tooling as an automatic competitor;
- treat internal tooling as an automatic buyer signal;
- classify every production company as R2;
- classify every large enterprise as R3;
- classify every AI studio as R4;
- invent a current trigger;
- convert weak evidence into strong evidence;
- use search snippets as final qualification evidence;
- make an unresolved company PASS;
- create additional classification labels outside this SOP;
- change the approved geography list;
- research people before SOP 01 has completed.

---

## 38. Final SOP 01 Completion Rule

SOP 01 is complete only when the system can state:

> **This is the correct active company and operating unit, it sits inside the approved geography, its production and AI environment are verified, there is a specific evidence-supported commercial route, its internal platform position is understood, and the correct commercial relationship type has been assigned.**

Only then:

`qualification_decision = ACCOUNT_PASS`

and the record may move to:

**SOP 02: Decision-Owner Discovery & Qualification**

Anything unresolved stays out of SOP 02 rather than being guessed into the final dataset.
