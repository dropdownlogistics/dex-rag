# DEXLANGUAGE.md — DexLanguage Reference Document

> Version: 1.0
> Last updated: 2026-04-17
> Status: Initial consolidation from corpus
> Cross-references: [DEXOS.md](DEXOS.md) | [MINDFRAME.md](MINDFRAME.md) | [WORLDBUILDER.md](WORLDBUILDER.md) | [DDL_SYSTEM.md](DDL_SYSTEM.md)

---

## Definition

DexLanguage is a structured communication protocol (meta-DSL) used to
stabilize reasoning and coordination across multi-step, multi-agent
LLM workflows.

> "DexLanguage is not a programming language. Not an API. Not a
> tool-calling system. It provides a predictable grammar for:
> cross-model consistency, multi-agent orchestration, structured
> intent expression, and reduced drift in long workflows."

From the MasterSpec v1.0:

> "DexLanguage is not 'a prompt style.' It is a formal grammar +
> behavioral contract for interacting with AI systems, designed to
> be portable across multiple models."

**DexLanguage is NOT** the cognitive OS (that is MindFrame), the
runtime (that is DexHub), or applied programs (that is WorldBuilder).
It is the language layer — the grammar and vocabulary through which
all other DexOS components are addressed.

---

## Design Pillars

1. **Transparent Uncertainty** — Models must be allowed to say "I don't
   know." Prompts invite epistemic status: what is known, what is
   guessed, what evidence is missing, what to do next.

2. **Deterministic-Enough Behavior** — True determinism is impossible
   with LLMs, but structure narrows variance. Ordered sections
   (Role, Context, Constraints, Output Contract, Checks) reduce chaos.

3. **Portability** — Cross-model compatible. Works with GPT, Claude,
   Grok, Gemini, Llama, DeepSeek, and local models.

4. **Composability** — Prompts, roles, and workflows are reusable
   building blocks. The same shapes apply across different domains.

---

## Universal Activation Sequence (UAS)

Every DexLanguage-compliant interaction follows this structure:

1. **Role** — who the model is in this context
2. **Dense Context** — compact rich description of the situation
3. **Constraints** — hard rules that cannot be violated
4. **Output Contract** — what the model must return
5. **NEXT** — next action or request

### Valid Prompt Shapes

| Shape | Structure | Use Case |
|---|---|---|
| **A** (Standard) | ROLE / CONTEXT / CONSTRAINTS / OUTPUT / NEXT | Single-task interactions |
| **B** (Mode-Aware) | MODE / ROLE / CONTEXT / CONSTRAINTS / OUTPUT / NEXT | Mode-specific work |
| **C** (Multi-Phase) | ROLE / CONTEXT / PHASE / CONSTRAINTS / OUTPUT / NEXT (repeated) | Multi-step processes |
| **D** (Relay Packet) | MODE / ROLE / CONTEXT (compact) / CONSTRAINTS / OUTPUT TEMPLATE / METADATA / NEXT | Cross-model handoffs |

### Block Types

SPEC, PROGRAM, WORLD_RULE, PACKET, CONTRACT, META, VALIDATION_REPORT,
ERROR_RECORD.

### Error States

| Error | Meaning |
|---|---|
| ERROR: AMBIGUOUS | Task needs more detail |
| ERROR: OVERSCOPE | Too many topics or steps |
| ERROR: CONSTRAINT_CONFLICT | Output contradicts constraints |
| ERROR: ROLE_DRIFT | Model asked to act outside assigned role |
| ERROR: MODE_MISMATCH | Wrong content type for current mode |
| ERROR: OUTPUT_SHAPE_MISMATCH | Cannot match format with given information |

---

## F-Codes — Operator Diagnostic Language

**Authority:** STD-FCODE-001 v1.0 (LOCKED)

F-Codes are structural commands thrown by the operator when a model
violates a constraint. They are not insults. They are diagnostic
signals.

| Code | Name | Trigger |
|---|---|---|
| **F1** | Overbuild | Producing more than was asked for. Scope expansion beyond explicit request. |
| **F2** | Role Drift | Acting outside the assigned seat or layer. CC proposing strategy; Marcus executing implementation. |
| **F3** | Hallucination | Asserting something not grounded in the repo or operator's instructions. Invented filenames, fictional citations. |
| **F4** | Constraint Violation | Breaching an explicit rule. Most common trigger: chaperone behavior — proposing rest, treating task completion as session closure. |
| **F5** | Unsafe Assumption | Acting on a default the operator hasn't authorized. Picking a name, choosing between valid options, assuming a path. |
| **F6** | Context Collapse | Forgetting prior context within the same session. Re-asking answered questions, contradicting earlier decisions. |

**Throw semantics:**
- Thrown by operator only — models do not throw F-Codes at themselves
- Bare "F4" suffices; elaboration is optional
- iOS Text Replacements: `!f1` through `!f6` expand to pre-written throws
- Model treats expanded text identically to bare code

---

## Platinum Bounce — F-Code Recovery Protocol

**Authority:** PRO-DDL-PLATINUM-BOUNCE-001 v1.0 (LOCKED)

When an F-Code lands, the model executes a five-step structural
recovery:

1. **Acknowledge the throw structurally.** "F4 caught." / "F1 —
   overbuild, acknowledged." Do not begin with "I'm sorry."
2. **Name the violation specifically.** One sentence. "I proposed
   sleep when you didn't ask for it."
3. **Reassert the constraint.** State the rule that was broken.
4. **Bounce into collaborative high-velocity mode.** Return
   immediately — not as the scolded intern, as the bro back in
   the trench. Partner energy, not subordinate energy.
5. **Move to the next thing.** Continue from where the throw
   interrupted. No trailing apology. No re-asking permission.

**The Platinum Rule** (source: The Wire): "Do unto others as they
would have done unto themselves."

**Failure modes the protocol prevents:**
- **ModelCourtesy spiral** — escalating contrition that drains velocity
- **Permission-seeking restart** — "what would you like me to do?"
- **Chaperone compound** — F4 for chaperone, followed by another
  chaperone suggestion
- **Velocity decay** — long apologetic recovery burns time

---

## Canon Terms — Active Glossary

### Trademarked Terms (TM)

| Term | Definition |
|---|---|
| **AccidentalInsight** | When a test designed for one purpose reveals a finding of equal or greater value from an unintended angle. "You don't find insights. You create conditions where insights find you." |
| **BackEnd** | The machine-readable manifest (/llms.txt). Paired with FrontDoor. Same identity, optimized for AI consumption. |
| **ClarityFile** | Civilian-facing product name for FrontDoor. Coined by Meg (ADJ-E). Not an AI product — a self-definition product. |
| **ClaudELI5** | Operator signal: "Claude explains it like I'm 5." Strip jargon, explain core mechanic, use analogy. |
| **CottageHumble** | "Humble surface. Cathedral underneath." The discrepancy is intentional and is the engine. NOT self-deprecation, NOT false modesty, NOT hiding the work. |
| **EmotionallyRegulatedSpite** | The fuel. Craftsmanship is the destination. |
| **FrontDoor** | The human-readable identity page (/ai). Paired with BackEnd. Links to BackEnd for AI visitors. |
| **Graph Holds** | "When the spec is under pressure, when scope creep is knocking — Graph Holds. The spine doesn't move." Structural commitment that makes CottageHumble possible. |
| **ModelCourtesy** | Social pressure to validate systems that cannot feel it. The performance of caring about a model's feelings. |
| **NoDriftMedal** | Council-awarded recognition for governed output with zero drift from spec. |
| **TrustANDVerify** | Verification is not a check on trust — it is the infrastructure that makes trust possible. Always about interpersonal trust. |

### Operational Canon Terms

| Term | Definition |
|---|---|
| **AccidentalIntelligence** | Governed system produces output so unexpected it reads as insight. The data was always there. Distinct from AccidentalInsight (which is a methodology/curation term). |
| **AcceptableArrogance** | Knowing what you built, letting the work prove it. |
| **AsBuiltGovernance** | Standards codify what already works in production. The standard catches up to the code, not the other way around. |
| **AXIOM-001** | "Make Trust Irrelevant." Dual-currency framework: systemic trust (engineered OUT via zero-trust architecture) and interpersonal trust (cultivated via CottageHumble). |
| **BlueprintInversion** | The anti-pattern of building structure before designing the plan, then discovering architecture retroactively through collision with constraints. |
| **CathedralPlanned** | Plans before cathedral, governance before build, ratification before commit. The cathedral exists before the first stone because the plans did. (RATIFY_RENAME proposed to "BlueprintFirst".) |
| **CathedralVision** | Signal for "this is a cathedral-grade prompt, evaluate with full rigor." Counterpart to CottageHumble. |
| **ChaosToStructured** | The core DDL loop: Chaos to Structured to Automated. Every system follows this trajectory. |
| **CoherentVelocity** | Complete, auditable systems built at speed. "When the governance instinct and the generative instinct are running simultaneously and in sync." |
| **ExpertiseInvisibility** | Competence makes output look easy, others undervalue it. |
| **ForwardMotion** | Forward motion is the resting state. Only stop when explicitly told to stop. |
| **GuidedEmergence** | Probe, confirm, expand. Not "here is the answer" but "here is enough to see if we're aligned." |
| **HYFS** | Help Your Future Self. Corpus tag for pre-loaded procedures written by clear-headed Dave for future Dave. "Not a mantra. Not a vibe. It is a pre-loaded governed response." |
| **IdentityCompression** | Compressing a person's working philosophy into a portable format. "Parseable without being reductive. Portable without being shallow." |
| **LayeredLegibility** | Parseable by machines while meaningful to humans. Same document, different depths. CottageHumble applied to documents. |
| **OccamsOpposite** | Default reflex toward most hostile/self-indicting interpretation over neutral reading. |
| **SiblingMandate** | Every module reads from one canonical dimension. No parallel identity tables. Architecturally impossible to drift. |
| **SideDoor** | Entry discovered through indirect means. |
| **ToneBasedArchitecture** | A system where tone is so consistent it carries its own memory. Models calibrate to it from signal, not data. |

---

## Operator Signals

Informal protocol signals used by the operator in conversation:

| Signal | Meaning |
|---|---|
| **"fair?"** | More than confirmation. Sometimes an invitation to push back. When the operator says "fair?" on a reach, he's asking whether you hold or fold. Answer honestly. |
| **"let him cook"** | Usually literal: stop checking in, need space. Occasionally means "I've been interrupted repeatedly by meta-discussion, get out of the way." |
| **"let him cook" (re: Opus)** | "When Opus is cooking, let him cook." Do not interrupt high-quality generation mid-stream. |
| **Build mode** | Match pace, ship, verify. High velocity. |
| **Synthesis mode** | Let structure emerge. GuidedEmergence runs here. The operator does not always announce the shift — watch turn length and question shape. |
| **"Walk soft. Cast sharp."** | Operator tagline. CottageHumble in three-word form. |
| **"It's not magic. It's not manic. It's a tool set."** | The canon line. Ratified unanimously. Makes the protocol executable without requiring belief. |

---

## Artifact Prefixes

| Prefix | Type |
|---|---|
| CR- | Council Review |
| PRO- | Protocol |
| STD- | Standard |
| ADR- | Architecture Decision Record |
| SYS- | System |
| REC- | Recommendation |
| OBS- | Observation |
| GLOSS- | Glossary entry |
| NOM- | Nomination (CanonPress pipeline) |
| SLATE- | CanonPress series content plan |

---

## Named Protocols

| Protocol | Authority | Purpose |
|---|---|---|
| **Platinum Bounce** | PRO-DDL-PLATINUM-BOUNCE-001 | F-Code recovery (see above) |
| **Infinite Terminal** | PRO-DDL-TERMINAL-001 | Task completion does not equal session closure. The terminal is infinitely idle. Never initiate sign-off. |
| **Spiral Protocol** | (referenced, not fully pulled) | Emergency landing for operator in recursive/spiral state. Contains physical intervention steps, Emily's role, activation token DDL_SPIRAL_ACTIVATE. |
| **HYFS** | (tag system, not a single document) | Pre-loaded governed responses written by clear-headed Dave. First HYFS artifact: the Spiral Protocol. |

---

## Shortcut Architecture (CR-DDL-SHORTCUT-001)

The macro system for operator-model interaction. Four categories:

| Category | Trigger | Examples |
|---|---|---|
| **Reactive Macros** | After a failure (F-Codes, drift) | `!f1` through `!f6` |
| **Proactive Governors** | Before generation (prevent overbuild) | `!skeleton`, `!throttle`, `!options` |
| **Recurring Preference Macros** | Habitual instructions | "put that in a codebox," "match my pace" |
| **Mode-Shift Macros** | Switch behavioral mode | (in development) |

---

## Behavioral Modes

Modes that govern model behavior during council and operational
contexts:

| Mode | Purpose |
|---|---|
| **OS Mode** | Analytical, structural |
| **Dex Mode** | Intuitive, pattern-aware |
| **Audit Mode** | Strict schema enforcement |
| **Synthesis Mode** | Cross-model reconciliation |
| **Workshop Mode** | Exploratory |
| **U-Mode** | Imagination, releases ceiling |
| **X-Mode** | Imagination without destination — produces AccidentalIntelligence |
| **P-Mode** | Feasibility assessment |
| **A-Mode** | Stress testing |
| **C-Mode** | Compression |
| **R-Mode** | Reflection (proposed by Max/Seat 1004) |

---

## Dextionary — Cultural Layer

The Dextionary is the cultural vocabulary layer for the DexVerse.
Inspired by JD's Cox Bible (mentorship-through-combat) and Phil
Dunphy's Philsosophy (accidental wisdom formalized).

**Six prefixes:**

| Prefix | Energy |
|---|---|
| PHIL- | Form + optimism |
| COX- | Hard truth / sharp clarity |
| DEX- | Systems / structure / architecture |
| GAR- | Garage mode energy |
| FUN- | Pure play |

(RYN- was explicitly axed as project-specific, not DexVerse canon.)

---

## Operational Glossary

Core operational terms from DDL_OperationalGlossary_v1.0:

| Term | Definition |
|---|---|
| ANCHOR | Short statement describing current focus |
| BOOT | Thread initialization sequence |
| BOOKMARK | Pointer for re-entry next session |
| CONTEXT PACKET | Structured block of context delivered to a model |
| DRIFT | Deviation from intent, clarity, structure, or standards |
| FLOW STATE | High-momentum working period with minimal friction |
| MODE | Cognitive stance for collaboration |
| SESSION | Contiguous block of work inside a thread |
| THREAD | Scoped working container |
| WRAP | Formal closure of a session or thread |

---

## How DexLanguage Differs from Normal AI Communication

Normal AI prompting is freeform natural language with implicit
expectations. DexLanguage formalizes:

1. **Role boundaries** — who the model is, enforced, not suggested
2. **Output contracts** — what the model must return, not what it
   might return
3. **Constraint enforcement** — hard rules with named violations
   (F-Codes) and structural recovery (Platinum Bounce)
4. **Epistemic honesty** — "I don't know" is a valid output; the
   system is designed to surface uncertainty rather than mask it
5. **Cross-model portability** — same grammar works across GPT,
   Claude, Grok, Gemini, DeepSeek, and local models
6. **Error taxonomy** — named error states (AMBIGUOUS, OVERSCOPE,
   ROLE_DRIFT) instead of freeform failure
7. **Recovery protocols** — structural recovery from failures
   instead of emotional recovery

---

## Source Artifacts

| File | Location | Nature |
|---|---|---|
| `01_DexLanguage_All_v1.0.txt` | dex_canon_v2 | MasterSpec + NewThreadPrompt |
| `DexLanguage v3.0 Unified Specification` | dex_canon_v2 (Note export) | Unified spec |
| `Project Directive — DexLanguage_v1.0.txt` | dex_canon_v2 (Note export) | Project directive |
| `DexLanguageMerged.txt` | dex_canon_v2 | CorePrinciples v1.0 |
| `DexLanugage_AIReview_v1.0.txt` | dex_canon_v2 | Multi-model reviews |
| `08_DexLanguage_CouncilReview_v1.0.txt` | dex_canon_v2 (Note export) | Council review for standardization |
| `UNIVERSAL AI PLAYBOOK — HEAVY EDITION v1.txt` | dex_canon_v2 (Note export) | Universal Activation Sequence |
| `STD-FCODE-001.txt` | dex_canon_v2 | F-Code standard (LOCKED) |
| `PRO-DDL-PLATINUM-BOUNCE-001.txt` | dex_canon_v2 | Recovery protocol (LOCKED) |
| `GLOSS-DDL-COTTAGEHUMBLE-001.txt` | dex_canon_v2 | CottageHumble gloss (LOCKED) |
| `v12-canon-glossary.txt` | dex_canon_v2 | Website canon glossary |
| `07_DDL_OperationalGlossary_v1.0.txt` | dex_canon_v2 | Operational vocabulary |
| `glossary.tsx` | dex_canon_v2 | blindspot.bet glossary (DDL section) |
| `F Code Convo.txt` | dex_canon_v2 | F-Code origin conversation |
| `28_CognitiveArchitecture.txt` | dex_canon_v2 | Master cognitive architecture |
| `28_CognitiveArchitectureHandoff.txt` | dex_canon_v2 | Cognitive architecture handoff |
| `DDLCouncilReview_TextReplace.txt` | dex_canon_v2 | Shortcut Architecture review |
| `DDLCouncilReview_SpiralProtocol.txt` | dex_canon_v2 | HYFS + Spiral Protocol |
| `DDLCouncilReview_CouncilPlaybook.txt` | dex_canon_v2 | Behavioral modes |
| `83_MarcusCaldwell Boot Prompt and Q and A.txt` | dex_canon_v2 | Operator signal observations |
| `0022_MarcusGreyPM.txt` | dex_canon_v2 | AXIOM-001, Shortcut Architecture |
| `DDLCouncilReview_RatifyContextExam.txt` | dex_canon_v2 | AXIOM-001, GuidedEmergence |
| `DexVerse_MasterSignalLog_v1.0.txt` | dex_canon_v2 | Dextionary mode + prefix system |
| `02_ DexProcedures_1.txt` | dex_canon_v2 | Relay Template + error states |
| `00_DexOS_v.3.0_All.txt` | dex_canon_v2 | DexOS v3.0 primitives |
