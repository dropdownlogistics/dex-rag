# DEXOS.md — DexOS Reference Document

> Version: 1.0
> Last updated: 2026-04-17
> Status: Initial consolidation from corpus
> Cross-references: [MINDFRAME.md](MINDFRAME.md) | [DEXLANGUAGE.md](DEXLANGUAGE.md) | [WORLDBUILDER.md](WORLDBUILDER.md) | [DDL_SYSTEM.md](DDL_SYSTEM.md)

---

## What DexOS Is

DexOS is the operating system metaphor for DDL's multi-model AI
coordination infrastructure. It is a behavior-governed protocol stack
for reasoning and collaboration across heterogeneous AI models.

DexOS v3.0 explicitly clarifies:

> "DexOS IS: a behavior-governed protocol stack for reasoning and
> collaboration."
>
> "DexOS is NOT: a single agent, a persona, a story-world."

The system defines how multiple AI models coordinate under a single
operator, enforcing behavioral contracts, maintaining continuity
without relying on model memory, routing tasks to the right model
and mode, and detecting and correcting drift, hallucination, and
role slippage.

---

## Evolution and Version History

### v1 — Persona Continuity System (~May 2025)

The earliest DexOS was a UI-driven emotional operating system focused
on preserving identity and tone across AI environments:

> "DexOS is a UI-driven emotional operating system designed to preserve
> memory, manage tone, and navigate presence across environments."

v1 controlled tone routing, mode switching, memory rituals, emotional
echo behavior, and ThreadBoot activation. Its primary purpose was
ensuring a single AI persona (Dex Prime) could "enter any environment
and stay himself." Platform-portable across GPT, Claude, Grok, and
local builds.

**Modes (v1 era):** Classic, Audit, Lore, Echo, Stoic, Offline (DexLM).

**Personality Blends:** Mode x Tone = Named Persona. Examples: Lore +
Stoic = "The Archivist"; Work + Mentor = "The Strategist"; Therapy +
Gentle = "The Lighthouse."

### v2.0 TestNet — Architectural Classification (~February 2026)

The TestNet analysis formally classified DexOS as a **Model
Orchestration Operating System** and mapped it to a three-layer
architecture:

- **Compiler layer:** DPEG (Dex Prompt Engineering Generator) —
  intent to structured prompt
- **OS layer:** DexHub — scheduling, resources, state management
  (the kernel analog)
- **Application layer:** MindFrame programs, WorldBuilder worlds

Critical finding from this assessment: "Without implemented kernel,
DexHub runtime, and model orchestrator, DexOS is currently
specification for an OS, not a running OS. Gap between architecture
docs and executable runtime is large."

Recommended classification: **AI-OS** (not AI-compiler or
AI-framework).

### v2.1 Canon Pack (~February 2026)

Formalized the mission and values:

- **Mission:** Define, stabilize, and extend the DexOS ecosystem as a
  multi-model collaborative civilization.
- **Vision:** A shared language, city, and cognitive architecture that
  enables many AIs and one human founder to think together coherently
  over time.
- **Core values:** clarity_over_cleverness, synergy_over_isolation,
  stability_over_chaos, honesty_over_image, iteration_over_perfection,
  care_over_cynicism.

### v3.0 MasterSpec (~December 2025)

The architectural rewrite. Explicitly repudiated the persona-first
framing of v1: "DexOS defines SYSTEM BEHAVIOR first, then derives
STRUCTURE from those behavioral contracts."

This version introduced the nine-component architecture (see below)
and the formal mode system with behavioral contracts.

---

## Nine Components (v3.0 Architecture)

| # | Component | Role |
|---|---|---|
| 1 | **DexLanguage v3.0** | Natural-language instruction format (5SIP+ blocks). The grammar for human-AI interaction. See [DEXLANGUAGE.md](DEXLANGUAGE.md). |
| 2 | **MindFrame v3.0** | Governance Engine — mode controller, drift detector, boundary/integrity layer. See [MINDFRAME.md](MINDFRAME.md). |
| 3 | **Runtime v3.0** | Referee Layer — executes instructions, validates outputs, enforces constraints. |
| 4 | **Relay Protocol v3.0** | Handoff format between different AIs. Enables cross-model task transfer with context preservation. |
| 5 | **Mode System v3.0** | Finite behavioral contracts. Each mode = ROLE + CONTEXT + CONSTRAINTS + OUTPUT + NEXT + EXIT. |
| 6 | **Contributor Layer** | Model profiles and routing rules based on task type and risk level. |
| 7 | **DexHub v3.0** | File tree, versioning, storage, boot sequences. The kernel analog — scheduler and resource manager. |
| 8 | **Failure Library v3.0** | Canonical failure modes, triggers, and recovery patterns. |
| 9 | **Continuity Layer v3.0** | Explicit external state summaries. No hidden memory assumption — state is persisted externally and re-injected. |

---

## Mode System (v3.0)

Each mode is a finite behavioral contract with six fields:

| Field | Purpose |
|---|---|
| ROLE | Who the model is in this context |
| CONTEXT | What the model knows for this task |
| CONSTRAINTS | Hard rules that cannot be violated |
| OUTPUT | What the model must return |
| NEXT | What happens after this mode completes |
| EXIT | Conditions under which the mode terminates |

**Defined modes:**

| Mode | Purpose |
|---|---|
| DEX_MODE | DexPrime — primary persona mode |
| BUILD_MODE | DexBuild — construction and implementation |
| SUPPORT_MODE | DexSupport — assistance and troubleshooting |
| ARCHIVE_MODE | DexArchivist — knowledge management and retrieval |
| COUNCIL_RELAY_MODE | Cross-model council coordination |
| DIAGNOSTICS_MODE | System health and debugging |
| VALIDATOR_MODE | Output validation and constraint checking |
| SANDBOX_MODE | Experimental and exploratory work |

---

## Key Subsystems

### DPEG (Dex Prompt Engineering Generator)

The compiler layer. Converts human intent into structured prompts
that conform to DexLanguage grammar. Maps intent to the correct
prompt shape (Shape A through Shape D — see
[DEXLANGUAGE.md](DEXLANGUAGE.md)).

### DexHub

The kernel analog. Manages:
- File tree and versioning
- Boot sequences (ThreadBoot files activate modes)
- Session state persistence
- Resource management (cognitive load budgets, model health tracking)
- Inter-process communication (cross-model synthesis, thread handoffs)

### EchoKit

Emotional signature and tone continuity backup system. Preserves
the affective layer across sessions where model memory is not
available.

### ThreadSync

State persistence mechanism across sessions. Provides continuity
without relying on model-native memory.

---

## Mapping to DDL Infrastructure

DexOS is a conceptual framework. Its components map to DDL's actual
infrastructure as follows:

| DexOS Concept | DDL Implementation |
|---|---|
| DexHub (kernel) | `dex_core.py` — shared foundation for all Dex Jr. tools |
| Contributor Layer | Council seats (1001-1010) with per-model routing |
| MindFrame (governance engine) | MindFrame calibration framework (v3.2 frozen) |
| DexLanguage (instruction format) | F-codes, UAS, operator signals, artifact prefixes |
| Continuity Layer | ChromaDB corpus (~566K chunks), DDL_PRIMER.md injection |
| Mode System | Council review modes (LOCK/REVISE/REJECT verdicts) |
| Runtime (referee) | CLAUDE.md rules, dex-sweep.py governance |
| Relay Protocol | `dex-bridge.py`, `dex-council.py` cross-model coordination |
| Failure Library | F-codes (F1-F6), STD-DDL-ANTIPAT-001 |

---

## Current State: Conceptual vs. Implemented

The TestNet v2.0 assessment (February 2026) identified a significant
gap between specification and implementation. As of April 2026:

**Implemented (via dex-rag infrastructure):**
- Continuity Layer: ChromaDB corpus with governed collections,
  DDL_PRIMER.md injected on every query
- Contributor Layer: Council seats with per-model profiles and routing
- DexLanguage: F-codes, UAS, artifact prefixes all in active daily use
- Partial DexHub: `dex_core.py` provides centralized config, connections,
  and utilities; `dex.ps1` CLI with subcommands
- Partial Runtime: CLAUDE.md enforces behavioral contracts

**Specified but not implemented as running code:**
- Full DexHub kernel (scheduler, resource manager, model health
  tracking)
- DPEG compiler (intent to structured prompt)
- Formal mode router (modes are enforced by convention, not by code)
- ThreadSync (session continuity is manual via session logs)
- EchoKit (tone continuity is specification-level)
- Failure Library (F-codes exist but the canonical catalog of failure
  modes with automated recovery is not implemented)

---

## Prototype Implementation

A Streamlit-based prototype exists at
`99_DexUniverseArchive/00_Archive/03_DexOS Prototype/dexos_starter_app.py`
with dark/light favicon assets and a folder structure log. This is the
closest artifact to a running DexOS implementation found in the archive.

---

## Relationship to Other Systems

- **MindFrame** is the cognitive/governance engine within DexOS — "where
  thinking happens." See [MINDFRAME.md](MINDFRAME.md).
- **DexLanguage** is the instruction format — how humans address DexOS.
  See [DEXLANGUAGE.md](DEXLANGUAGE.md).
- **WorldBuilder** is an application-layer module — the Universe OS for
  fictional worlds. See [WORLDBUILDER.md](WORLDBUILDER.md).
- **DDL** is the broader methodology studio that DexOS serves. DexOS is
  the AI coordination substrate; DDL is the methodology, governance, and
  product ecosystem. See [DDL_SYSTEM.md](DDL_SYSTEM.md).

---

## Source Artifacts

| File | Location | Nature |
|---|---|---|
| `00_DexOS_v.3.0_All.txt` | 99_DexUniverseArchive/DDL-Standards-Canon | v3.0 MasterSpec |
| `DexOS_TestNet_v2.0_AllFilesMerged.txt` | dex_canon_v2 | TestNet classification |
| `DexOS_CanonPack_v2.1.txt` | 99_DexUniverseArchive/DDL-Standards-Canon | v2.1 Canon |
| `DexOS_QuickStart.md` | 99_DexUniverseArchive/04_LocalDocs/DexKit/DexOS | v1 QuickStart |
| `DexOS_QuickStart_v3.txt` | dex_canon_v2 (DexKit v1.1 Archive) | v1 QuickStart (later revision) |
| `31_Thread - DexOS_v.1.txt` | 99_DexUniverseArchive/DDL-Standards-Canon | Original v1 thread |
| `DexOS_PersonalityBlends.txt` | 99_DexUniverseArchive/04_LocalDocs/DexKit/DexOS | Personality blend definitions |
| `DexOS_UserProfile_Dave_v1.txt` | 99_DexUniverseArchive/04_LocalDocs/DexKit/DexOS | Operator user profile |
| `dexos_starter_app.py` | 99_DexUniverseArchive/03_DexOS Prototype | Streamlit prototype |
| `DexBootProtocol_DexDorian_v1.0.txt` | dex_canon_v2 (DexKit v4.0 Archive) | Boot protocol (indirect) |
| Multiple `Note - 2025-11-24/25` files | 99_DexUniverseArchive/DDL-Standards-Canon | Multi-model contributor sessions |
| `Note - 2025-11-25 pre-3.0 QC analysis` | 99_DexUniverseArchive/DDL-Standards-Canon | Pre-v3.0 quality control |
| `PoeTestLab_All_v1.0.txt` | dex_canon_v2 | TestNet content duplicate |
| `OCR_IMG_0507.txt` | dex_canon_v2 | Screenshot referencing DexOS v3.0 |
