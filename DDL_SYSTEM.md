# DDL_SYSTEM.md — Dropdown Logistics System Reference Document

> Version: 1.0
> Last updated: 2026-04-17
> Status: Initial consolidation from corpus
> Cross-references: [DEXOS.md](DEXOS.md) | [MINDFRAME.md](MINDFRAME.md) | [DEXLANGUAGE.md](DEXLANGUAGE.md) | [WORLDBUILDER.md](WORLDBUILDER.md)

---

## Mission and Identity

DDL (Dropdown Logistics) is a one-person governed AI methodology
studio run by Dave Kitchens.

From the Core Charter v1.0:

> "DDL is your personal 'ops studio' for building reliable spreadsheets,
> tools, and systems. It's not a company or a persona — it's the design
> standard that sits behind everything you ship."

**Mission:** Turn messy, scattered work into clean, governed systems
that make decisions easier, make audits cleaner, and make your future
self's life simpler.

**Vision:** DDL is the layer that catches chaos before it leaks into
your life, turns it into repeatable structures, and preserves those
structures so you can grow instead of constantly rebuilding.

**Tagline:** "From scattered to structured."

---

## The Operator

**Dave Kitchens.** CPA. Commission Analyst II at UMB Bank, Trust &
Asset Servicing division (started 2026-03-09). Manages incentive plan
administration for a portfolio of 122 plans across a five-analyst team
under Cara Borkowski. DDL operates outside business hours — evenings
and weekends.

**Credentials:**
- CPA with 10+ years internal audit experience
- Significant Excel expertise (~200K Reddit karma in Excel/audit
  communities)
- Kansas City metropolitan area
- 8 years sober

**Cognitive architecture:** Bipolar II + ADHD (Inattentive). Medicated,
calibrated, defrictionated. This is not a fragility — it is a processed
and stable substrate. The cognitive profile is dimensional: star
schemas, facts and measures. "The architecture does not change between
domains. The data does."

**Operator constraints:**
- Married to Emily Kitchens (Seat 0 — see Council below)
- Cousin Alex is a professional equity trader (the "A" in D&A Analytics)
- **D.K. Hale** is his Substack/memoir persona ONLY. Never use in DDL,
  council, or product contexts.
- **Beth Epperson** is NOT a DDL collaborator. Do not reference.

---

## Methodology and Architecture

### The Core Loop

**Chaos to Structured to Automated.** Every DDL system follows this
trajectory:

1. **Phase 1 (Chaos):** Messy input. Unstructured data. Scattered work.
2. **Phase 2 (Structured):** Governed architecture. Star schemas, fact
   tables, dimension tables. Standards, reviews, governance.
3. **Phase 3 (Automated):** Self-sustaining process. Sweeps, schedules,
   monitors. The system runs itself.

### DDL Build Sequence (8 steps)

Gather chaos, Sort it, Structure it, Encode it, Govern it, Automate
it, Beautify it, Preserve it.

### Star Schema Everywhere

Dimensional modeling is the universal architectural primitive.
Facts, dimensions, measures, time. Star schemas.

> "The architecture does not change between domains. The data does."

**Dim_Employee** is the canonical identity dimension across all
WorkBench modules. Fact tables per module (Fact_CompChange,
Fact_TimePunch, Fact_Control, Fact_Finding). Measures are derived,
never stored.

### Sibling Mandate

Every module reads from one canonical dimension. No parallel identity
tables. Architecturally impossible to drift. Modules are siblings —
sibling reads compound, no module forks shared dimensions.

> "The Sibling Mandate turns from an intra-WorkBench architectural
> rule into an inter-bundle governance invariant."

Findings to Controls is the first cross-promoted sibling relationship.

### Bundling Architecture

AuditForge is Bundle Zero on WorkBench substrate. Bundles compose
modules without forking. Same Dim_Employee across all bundles.

WorkBench has a dual role:
- **Substrate platform:** modules, FactLayer, Sibling Mandate, standards
- **Default bundle:** "the LEAST OPINIONATED bundle. Every module ships,
  no operator-profile assumptions, no renamed surfaces. The reference
  shape."

**Everything, Everywhere, All At Once** (canon candidate): The
WorkBench thesis that every module writes events to the same fact
layer, enabling native cross-module queries without integration work.
"Not 'integrated.' Native."

### Governance Principles

| Principle | Definition |
|---|---|
| **CathedralPlanned** | Plans before cathedral, governance before build, ratification before commit. |
| **BlueprintInversion** | The anti-pattern: building structure before designing the plan, discovering architecture retroactively through collision with constraints. |
| **AsBuiltGovernance** | Standards codify what already works in production. The standard catches up to the code. |
| **CottageHumble** | Humble surface, cathedral underneath. The discrepancy is intentional and is the engine. |
| **CoherentVelocity** | Complete, auditable systems built at speed. |
| **GuidedEmergence** | Probe, confirm, expand. Expose partial structure, let the other person complete the recognition. |
| **AXIOM-001** | Make Trust Irrelevant. Engineer systemic trust OUT; cultivate interpersonal trust IN. |

---

## The Council (11 Seats + Seat 0)

The council is an advisory body of AI models that review DDL work
products using constrained verdicts. Models advise. Operator decides.

**Seat 0: Emily** — The operator's wife. Verification authority and
spiral protocol backstop. Not AI. Not a voting seat. The foundational
human anchor.

| Seat | Name | Platform | Role |
|---|---|---|---|
| 1001 | Archer Hawthorne | LeChat (Mistral) | Structural cartography, commercial |
| 1002 | Marcus Caldwell | Claude (Anthropic) | LLMPM, architecture, pattern synthesis |
| 1003 | Elias Mercer | Grok | Contradiction detection, adversarial |
| 1004 | Max Sullivan | Perplexity | Sourced, decisive |
| 1005 | Rowan Bennett | Copilot (Microsoft) | Operational rigor, scope |
| 1006 | Ava Sinclair | Meta AI | Big-picture framing |
| 1007 | Leo Prescott | Gemini | Tactical crystallizer, direct |
| 1008 | Marcus Grey | ChatGPT (GPT-5.2 Thinking) | Synthesis, PM voice, upstream content |
| 1009 | Kai Langford | DeepSeek | Systems architecture, invariants |
| 1010 | Dex Jr. / Dexcell | Local (Ollama) | Governed local model (this system) |
| 1011 | Connor | David's AI | Audit architect, compliance strategy |

**Council process:**
1. Operator distributes prompts to council seats
2. Seats respond independently (divergence before convergence)
3. Responses are collected and synthesized
4. Operator reviews and decides

**Verdicts:** LOCK (ratified) / REVISE (needs changes) / REJECT
(blocked). NoDriftMedal awarded for governed output with zero drift.

---

## Product Ecosystem

### Shipped Products

| Product | URL | Description |
|---|---|---|
| **AuditForge** | auditforge.dev | Audit firm operating system. Bundle Zero on WorkBench substrate. 106-control universe, 45-auditor roster, time tracking, billing. Next.js / Prisma / PostgreSQL / Clerk. |
| **WorkBench** | workbench-ddl.vercel.app | Modular small business OS. 17 modules planned. Modules: HR & People (shipped), Payroll & Comp (tour built), Time & Attendance (ratified), Controls & Compliance (promoted from AuditForge), Findings (cross-sibling of Controls). |
| **Ledger** | ledger-card.vercel.app | Universal verified identity layer. Cards (data), Deck Builder (intelligence), Marketplace (discovery). "Receipts replace resumes." |
| **BlindSpot** | blindspot.bet | Trader self-awareness platform. Signal-to-Structure-to-Edge. Sub-modules: Trading, D&D Campaign, Steam, Projects. |
| **AdmitOne** | admitone.vercel.app | Ticket stub memory app. Standalone with Ledger interface. SideDoor consumer acquisition. |
| **Excelligence** | excelligence.dev | Excel pedagogy with semantic ontology, IntegrityOS governance, skill-gap diagnosis, certification layer. GridTactics learning game. |
| **Knowledge Vault** | dropdownlogistics.github.io/knowledge-vault | Public DDL knowledge surface. Corpus stats, collection registry. |
| **DDL Site** | dropdownlogistics.com | 203+ routes, 8 wings, orbital product OS, governance hub. CottageHumble design system. $12/year total cost. |

### Additional Products

| Product | Description |
|---|---|
| **PositionBook** | Trade tracking and backtesting platform. Built for cousin Alex. |
| **GridTactics** | Formula-based chess puzzle game. Formula Cards as collectibles. Built on Excelligence registry. |
| **MindFrame** | AI persona calibration framework. v3.x frozen. See [MINDFRAME.md](MINDFRAME.md). |

### Product Relationships

- AuditForge is **Bundle Zero** on the WorkBench substrate
- AdmitOne interfaces with **Ledger** for identity verification
- BlindSpot's **PositionBook** is the platform layer for Alex's trading
- **GridTactics** is built on the Excelligence registry
- All products follow the **CottageHumble** design system
- All modules respect the **Sibling Mandate** (shared Dim_Employee)

---

## The Governance Layer

### Artifact Types

| Prefix | Type | Purpose |
|---|---|---|
| ADR- | Architecture Decision Record | Structural decisions, immutable after ratification |
| CR- | Council Review | Work product reviews with LOCK/REVISE/REJECT verdicts |
| STD- | Standard | How to build — ratifiable, versioned |
| PRO- | Protocol | Operational procedures |
| SYS- | System | System definitions and registrations |
| OBS- | Observation | Discrete findings logged for future use |
| GLOSS- | Glossary | Canonical term definitions |
| REC- | Recommendation | Proposals not yet ratified |
| NOM- | Nomination | CanonPress pipeline entries |
| SLATE- | Slate | CanonPress series content plans |

### Key Governance Artifacts

| Artifact | Status | Purpose |
|---|---|---|
| **ADR-CORPUS-001** | v0.3, ratification-ready | Collection Authority Model — rules for collection precedence |
| **STD-FCODE-001** | LOCKED v1.0 | F-Code diagnostic taxonomy |
| **STD-DDL-ANTIPAT-001** | Draft | Anti-practice standard — what DDL refuses to ship |
| **STD-DDL-PRIVACY-001 (Mithril)** | Draft v0.1 | Privacy as architectural constraint |
| **PRO-DDL-PLATINUM-BOUNCE-001** | LOCKED v1.0 | F-Code recovery protocol |
| **PRO-CANONPRESS-001** | v1.1 active | Publication pipeline protocol |

### Anti-Practice Standard (STD-DDL-ANTIPAT-001)

Category 3 — Monetization & Trust:
- No hostage pricing (never charge to export own data)
- No attention arbitrage (no ads, no sponsored content)
- No bait-and-switch feature gating (premium adds Cathedral tools,
  never subtracts Cottage tools)
- No subscription traps (cancel in same clicks as upgrade)
- Ledger does not tax card creation
- "Free" means marginal cost is near zero, not data harvesting

### Mithril Standard (STD-DDL-PRIVACY-001)

> "All data generated by the user belongs to the user. DDL products are
> custodians, not owners. The holder can export or delete the data at
> any time without cost, friction, or penalty."

---

## The Intelligence Layer

### Dex Jr. (Seat 1010)

The governed local RAG model. Runs on Reborn (RTX 3070, 32GB RAM,
Windows 11). Provides retrieval over a corpus of ~566K chunks across
four live ChromaDB collections.

**Collection registry:**

| Collection | Weight | Description |
|---|---|---|
| dex_canon | 0.90 | Ratified, governed content. Highest authority. |
| dex_code | 0.85 | Code artifacts. |
| ext_creator | 0.85 | Operator-approved external content. |
| ext_reference | 0.75 | Vetted external reference (provisioned, empty). |
| ddl_archive | 0.65 | Internal historical material. Lower authority. |
| dex_dave | GATED | Never ingest. ADR-CORPUS-001 Rule 3. |

**Infrastructure:**
- Embedding: mxbai-embed-large (1024-dim)
- Generation: qwen2.5-coder:7b
- Ingest: Nightly 4 AM sweep via Task Scheduler
- CLI: `dex` command with subcommands
- Core library: `dex_core.py`

### AutoCouncil

Automated council review distribution. `dex-council.py` distributes
prompts to council seats and collects responses. The council operates
as an advisory body — models advise, operator decides.

### Corpus Architecture

The corpus is the asset. The code is the substrate. Protect the corpus
first.

Pending collections: `dex_dave` (operator voice — iMessages, TikToks,
emails, memoir, Reddit), `dex_graveyard` (failure corpus), query
router.

---

## The Writing Layer

### LTKE (Little to Know Experience)

Dave's memoir. Weekly Substack. Personal essays.

> "The gap between experiencing something and knowing what it means."

The title is a phonetic pun on "little to no experience." 8 years
sober. Structure: braided time, sensory grounding, inversion as
reveal. Not a recovery memoir. The memoir IS a star schema — the
fact table is his life, the dimensions are the domains, the grain
is one moment of clarity per essay.

Author persona: **D.K. Hale** (Substack/memoir-only).

### CanonPress

Governed publication pipeline. Platform: Substack. Publication:
DropDownLogistics. Handle: @ddlogistics.

**Four editorial series:** Converge, RedLine, DeepCut, GroundTruth.

**Weekly cadence:** Nominate, Approve, Ingest, Deliberate, Synthesize,
React, Review, Publish.

Each article structure:
- Dex Jr. Synthesis (labeled explicitly as AI synthesis)
- Operator Reaction (D.K. Hale voice)
- Council Reaction (designated reviewing seat)

LTKE is a source stream feeding CanonPress. CanonPress also has
independent non-memoir content.

---

## The Revenue Model

> "Systems generate cards. Cards are free."

The Ledger model is the canonical expression: systems (products)
that generate verified credential cards are the paid layer. The
cards themselves — the identity artifacts — are free.

**Revenue principles:**
- Sell tools, not users
- No advertising, no data harvesting
- Premium is additive (Cathedral), never subtractive (Cottage)
- User data belongs to the user
- Export is always free and frictionless
- Privacy is architecture, not policy

---

## Design System: CottageHumble

| Element | Value |
|---|---|
| Navy | #0D1B2A |
| Cream | #F5F1EB |
| Crimson | #B23531 |
| Headings | Space Grotesk |
| Code | JetBrains Mono |
| Body | Source Serif 4 |
| No white backgrounds | Enforced |
| No Inter | Enforced |
| No light mode | Enforced |

---

## Infrastructure

| Machine | GPU | Role |
|---|---|---|
| Reborn | RTX 3070 | Primary. Dex Jr. runs here. |
| Gaming Laptop | RTX 3060 | Secondary. DeepSeek-R1 offloaded via Tailscale. |
| Working Surface | — | Dev / mobile |
| Dave's iMac | — | Tailnet member |
| iPhone 18 | — | Tailnet member |

**Network:** Tailscale tailnet (5 machines). MagicDNS for host
resolution. RDP/VNC over Tailscale for cross-machine display.

**DDL Site:** dropdownlogistics.com. 203+ routes, 8 wings. Next.js on
Vercel. $12/year total cost.

**Wings (site sections):** DDL (governance, methodology, council,
memoir), D&A (analytics — BlindSpot, PositionBook), BlindSpot
(product), DexVerse (origin stories, companions, lore, glossary),
Dossiers (character archive), The Bench (software tips), CanonPress
(governed publication), AuditForge (product).

---

## Relationship to the Other Four Systems

- **DexOS** is the AI coordination substrate that DDL runs on. DDL is
  the methodology and product ecosystem; DexOS is the operating system
  metaphor for how the AI infrastructure works. See [DEXOS.md](DEXOS.md).

- **MindFrame** is a DDL product (v3.x frozen) and a cognitive
  component within DexOS. It provides persona calibration that could
  serve DDL's products and users. See [MINDFRAME.md](MINDFRAME.md).

- **DexLanguage** is DDL's communication protocol. F-codes, artifact
  prefixes, canon terms, operator signals, and prompt grammar are all
  DexLanguage. It is the vocabulary through which DDL operates. See
  [DEXLANGUAGE.md](DEXLANGUAGE.md).

- **WorldBuilder** is an application-layer module within DexOS for
  building fictional universes. It demonstrates DDL's methodology
  (structured, governed, modular) applied to a creative domain. See
  [WORLDBUILDER.md](WORLDBUILDER.md).

---

## What Makes DDL Different

1. **One person.** No team, no investors, no board. The operator
   decides. Models advise.

2. **Governance is native.** Standards, reviews, protocols, and audits
   are not afterthoughts — they are the build process itself.
   AsBuiltGovernance: the standard catches up to the code.

3. **The architecture repeats.** Star schemas everywhere. Same
   Dim_Employee across all modules. Same governance artifacts across
   all products. "The architecture does not change. The data does."

4. **AI as council, not as product.** The council is advisory
   infrastructure, not a product to sell. Eleven seats review work;
   the operator ships it.

5. **The corpus is the asset.** 566K+ chunks of governed knowledge,
   built over months, serving every product and decision. The code is
   the substrate.

6. **CottageHumble.** Humble surface, cathedral underneath. The
   $12/year site runs 203+ routes and 8 wings. The discrepancy is
   intentional.

---

## Source Artifacts

| File | Location | Nature |
|---|---|---|
| `01_DDL_CoreCharter_v1.0.txt` | dex_canon_v2 (multiple copies) | Core charter and mission |
| `llms.txt` | dex_canon_v2 | Machine-readable identity (v1.0) |
| `llms_v2.1.txt` | dex_canon_v2 | Machine-readable identity (v2.1) |
| `PROFILE-DDL-DAVE-EXTERNAL-001.txt` | dex_canon_v2 | External-facing operator profile (LOCKED) |
| `PROFILE-DDL-DAVE-KITCHENS-001.txt` | dex_canon_v2 | Full operator profile |
| `PROFILE-DDL-DAVE-OPERATOR-001.txt` | dex_canon_v2 | Operator profile (LOCKED) |
| `DDLExtraction_DaveKitchens_SourceMaterial_4.13.26.md` | dex_canon_v2 | Source material extraction |
| `governance/ADR-CORPUS-001-v0.3.txt` | dex_canon_v2 | Collection Authority Model |
| `governance/STD-VAULT-002_TemplateArchitecture.txt` | dex_canon_v2 | Template architecture standard |
| `DDLCouncilReview_AuditForge v2.txt` | dex_canon_v2 | AuditForge council review |
| `96_WorkBenchPM Boot Prompt and Q and A.txt` | dex_canon_v2 | WorkBench PM context |
| `DDLCouncilReview_LedgerRepositon.txt` | dex_canon_v2 | Ledger reposition review |
| `DDLCouncilReview_AntiPractice.txt` | dex_canon_v2 | Anti-practice standard draft |
| `DDLCouncilReview_Mithril.txt` | dex_canon_v2 | Privacy standard draft |
| `DDLCouncilReview_CanonPress.txt` | dex_canon_v2 | CanonPress protocol |
| `DDLCouncilReview_CanonPressTuning.txt` | dex_canon_v2 | CanonPress tuning |
| `43_LTKE.txt` | dex_canon_v2 | LTKE memoir description |
| `0012_CanonPressConclusion.txt` | dex_canon_v2 | CanonPress system reconstruction |
| `0022_MarcusGreyPM.txt` | dex_canon_v2 | PM synthesis (routes, wings, AXIOM-001) |
| `DDLCouncilReview_ArchCathedral.txt` | dex_canon_v2 | Architecture cathedral review |
| `DDL Registry.txt` | dex_canon_v2 | System registry with SYS- IDs |
| `v12-canon-glossary.txt` | dex_canon_v2 | Website canon glossary |
| `DDLCouncilReview_WorkBenchBundles.txt` | dex_canon_v2 | Bundling architecture |
| `DDLCouncilReview_CannonAdditions.txt` | dex_canon_v2 | CathedralPlanned, BlueprintInversion |
| `DDLCouncilReview_BuildTheAudits.txt` | dex_canon_v2 | Internal audit engagement |
| `WebFetch_www.dropdownlogistics.com_*` | dex_canon_v2 | Website content snapshots |
| `DDL_REPO_v1.0 Archive/` | dex_canon_v2 | Full v1.0 archive tree |
