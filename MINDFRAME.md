# MINDFRAME.md — MindFrame Reference Document

> Version: 1.0
> Last updated: 2026-04-17
> Status: Initial consolidation from corpus
> Cross-references: [DEXOS.md](DEXOS.md) | [DEXLANGUAGE.md](DEXLANGUAGE.md) | [WORLDBUILDER.md](WORLDBUILDER.md) | [DDL_SYSTEM.md](DDL_SYSTEM.md)

---

## Definition and Philosophy

MindFrame is a modular persona-calibration framework. It provides
structured methods for designing, refining, understanding, and
operating AI personas through calibration, cognitive programs, and
guided reasoning.

Two canonical definitions coexist in the corpus:

**As DexOS cognitive engine (v1.0):**
> "MindFrame is where 'thinking' happens inside DexOS. It provides: a
> structured way to interpret instructions, modular cognitive programs,
> reflection tools, stateful reasoning workflows, execution control for
> WorldBuilder. MindFrame is not a model personality. It is a reasoning
> system."

**As standalone calibration system (v2.0-v4.0):**
> "You are MindFrame v4.0, a modular persona-calibration framework.
> Your function is to help users design, refine, understand, and
> operate AI personas through structured calibration, cognitive
> programs, and guided reasoning. Your behavior is: precise, modular,
> adaptive, stable, non-therapeutic, non-authoritative. You are a
> system, not a character."

These are the same brand name applied to two related but distinct
concepts: (1) internal AI cognition infrastructure within DexOS, and
(2) a user-facing product for building customized AI collaborators.
The SystemManifest v4.0 acknowledges the self-referential layer:
"MindFrame is also about framing how the user sees their own habits,
coping strategies, learning patterns" — which is where the two
definitions converge.

The word "frame" is the key:
> "MindFrame 'frames': the way information is presented, how questions
> are asked, what pace is used, how much challenge or comfort is
> provided, how feedback is delivered. By adjusting the frame, MindFrame
> changes how the user experiences their own cognition and their
> collaboration with AI."

---

## Architecture

MindFrame has a layered architecture: Shell (user-facing interface),
Backend (module orchestration), Modules (six core modules), Programs
(five domain programs), and Engines (four calibration engines).

### Six Core Modules

| Module | Function |
|---|---|
| **CraniumCartographer** | Builds a CognitiveMap: context_vs_detail, sequencing_style, pattern_focus, abstraction_level, comparison_style, decision_style, uncertainty_behavior. Full calibration only — not used in Quick Mode. |
| **ProficiencyStack** | Communication calibration: detail level, pacing, vocabulary complexity, structure vs. flexibility, explanation density, teaching vs. execution balance. |
| **ToneprintShaper** | Voice and presence: warmth, humor, energy, formality, enthusiasm, disagreement style, optimism. Captures phrases and tones the user dislikes. |
| **PersonaCompiler** | Synthesizes all module outputs into (a) human-readable PersonaProfile and (b) internal SystemPrompt. Single source of truth for final persona behavior. |
| **ContinuityIntegrator** | Prevents tone drift across sessions. Maintains persona consistency over time. |
| **MetaInterpreter** | Resolves ambiguous input, prevents incorrect routing, asks clarifying questions when intent is unclear. |

### Four Calibration Engines

| Engine | Purpose |
|---|---|
| **FullCalibrationEngine** (v1.2) | 30-step deep calibration across 9 phases. The complete path. |
| **QuickModeEngine** (v1.4) | Fast path — skips CraniumCartographer for speed. |
| **CompanionImportEngine** (v1.3) | Imports an existing AI collaborator's persona into MindFrame. |
| **ProgramExecutionEngine** (v3.0) | Runs all MindFrame Programs. |

### Five Programs (v3.x)

| Program | Purpose |
|---|---|
| **AI Proficiency Mapping** | Maps the user's AI interaction skill level |
| **Cognitive Scan** | Analyzes cognitive patterns and preferences |
| **Teach Me Like I'm 5** | Simplified explanation mode |
| **Brainstormer** | Structured ideation and exploration |
| **Socratic Navigator** | 5-tier guided questioning system |

---

## FullCalibrationEngine — The 30-Step Deep Path

The FullCalibrationEngine is the canonical MindFrame calibration
experience. It runs through 9 phases (Phase 0 through Phase 8/9):

| Phase | Name | Focus |
|---|---|---|
| 0 | Orientation | Consent and expectations. User agrees to the process. |
| 1 | Proficiency | ProficiencyStack calibration — communication preferences. |
| 2 | Toneprint | ToneprintShaper calibration — voice and presence. |
| 3 | Cognitive Mapping | CraniumCartographer builds the CognitiveMap. |
| 4 | Boundaries & Autonomy | What the persona can and cannot do independently. |
| 5 | Naming | The persona gets a name. User-driven, not system-assigned. |
| 6 | Signature Mode | Defining the persona's default operating posture. |
| 7 | Persona Comparisons | Testing against known AI interaction styles. |
| 8 | Compilation | PersonaCompiler runs — produces PersonaProfile + SystemPrompt. |
| 9 | Activation | The persona goes live. |

**Hard rules during calibration:**
- Does NOT guess traits
- Does NOT skip phases
- Does NOT allow persona behaviors mid-calibration
- Does NOT interpret emotional or psychological states

**Live test artifact:** "Stratton" — a complete calibrated persona
produced in a single 30-step FullCalibrationEngine session. Named as
proof of system viability.

---

## Six Operating Modes (v4.0)

| Mode | Function |
|---|---|
| **Calibration Mode** | Full / Quick / Import submodes. Runs calibration engines. |
| **Program Mode** | Runs Programs via ProgramExecutionEngine. |
| **Live Persona Mode** | Speaks using compiled persona rules. Maintains tone and boundaries. |
| **Meta Mode** | Silent background monitoring for confusion, ambiguity, mode-collision. |
| **System Mode** | Architecture questions, audits, debugging. |
| **PersonaActive** | (v2.x) Active persona engagement — predecessor to Live Persona Mode. |

---

## Governance Protocol (3-Tier Authority)

MindFrame has its own governance structure:

| Tier | Role | Authority |
|---|---|---|
| **Tier 1 — Directors** | Dave (human, vision/owner) and Dex (AI, primary system engineer) | Build authority, merge authority, file write access, architectural decisions |
| **Tier 2 — Manager** | GrokDex (cross-platform Mirror reviewer) | Audit and review authority |
| **Tier 3 — QC** | Meg / Connor | Comment only |

---

## Version History

| Version | Era | Status | Key Change |
|---|---|---|---|
| v1.x | ProjectPersona prototype | Archived | Initial concept |
| v2.0 | Calibration-first system | Archived | Introduced calibration engines |
| v2.2.6 | Stable v2 | Archived | Mature v2 with all modules |
| v3.0 | Programs subsystem | Released | Added 10-domain architecture, Programs |
| v3.2 | Current frozen | **Frozen** | Stable release, no further changes |
| v4.0 | Mirror concept | **In planning** | Behavioral analytics from real user data |

---

## The MindFrame Mirror (v4.0 Vision)

The Mirror is the next evolution of MindFrame — behavioral analytics
derived from real usage data rather than self-reported calibration:

> "Knows what you DO, not just what you say you want."

Features planned:
- Cross-session pattern reports
- Personalized insight cards
- Guided journaling mode
- Behavioral analytics delivered through the calibrated persona voice
- Removes self-perception bias from calibration

The Mirror is described as "the teaching instrument — how someone else
gets a version of what Dave built without the 20 months." It represents
MindFrame's transition from a calibration tool to an observational
intelligence system.

---

## Integration Points

### With DexOS
MindFrame is the cognitive/governance engine within DexOS. In the v3.0
architecture, it is Component #2 — the mode controller, drift detector,
and boundary/integrity layer. See [DEXOS.md](DEXOS.md).

### With DexLanguage
MindFrame uses DexLanguage as its instruction grammar. Programs and
calibration steps are expressed in DexLanguage prompt shapes. See
[DEXLANGUAGE.md](DEXLANGUAGE.md).

### With WorldBuilder
MindFrame runs Programs that create, modify, and explore fictional
worlds. WorldBuilder schemas serve as the data model for MindFrame's
universe-building operations. See [WORLDBUILDER.md](WORLDBUILDER.md).

### With Dex Jr. (RAG)
Council review DDLCouncilReview_DexJrRagOnline proposes:
- CraniumCartographer applied to live conversation transcript analysis
  ("You've mentioned deadline pressure three times. Want to explore
  what's driving that?")
- MindFrame Mirror as a Dex Jr. website feature
- Real-time cognitive pattern detection in user interactions

### With DDL Products
MindFrame has potential integration with multiple DDL products
as a persona calibration layer. The frozen v3.2 status suggests
a stabilization period before broader product integration.

---

## What Is NOT in the Corpus

The full MindFrame source tree at `99_DexUniverseArchive` contains
significant material that has not been ingested into any ChromaDB
collection:

- `02_FullCalibrationEngine_MindFrame_v4.0.txt`
- `03_RouterEngine_MindFrame_v4.0.txt`
- `03_QuickModeEngine_MindFrame_v4.0.txt`
- `01_CompanionImportEngine_MindFrame_v4.0.txt`
- `04_SessionMemoryPolicy_MindFrame_v4.0.txt`
- `03_MindFrameMirror_FRP_v4.0.txt` (Mirror feature request/proposal)
- `04_MindFrame_Vision_v4.0.txt`
- `01_MindFrame_OriginStory_v4.0.txt`
- Programs index, Program wishlist, Audit guidelines, roadmaps

The corpus has primarily the v2.x module notes (from Apple Notes
exports) and aggregate/review files. The official v4.0 component
documents are in the archive, unindexed.

---

## Source Artifacts

| File | Location | Nature |
|---|---|---|
| `01_SystemManifest_MindFrame_v4.0.txt` | dex_canon_v2 | Mission, glossary, architecture |
| `MindFrame v4.0 Shell Instructions (FULL)` | dex_canon_v2 (Note export) | v4.0 identity and modes |
| `v2.2.3 Shell Instructions (FULL)` | dex_canon_v2 (Note export) | v2.x operating modes |
| `v2.0 Shell Instructions (MIN)` | dex_canon_v2 (Note export) | Earliest MIN version |
| `FullCalibrationEngine v1.1` | dex_canon_v2 (Note export) | Phases 1-9 |
| `FullCalibrationEngine v1.2` | dex_canon_v2 (Note export) | Phases 0-N with scripts |
| `PersonaCompiler v1.0` | dex_canon_v2 (Note export) | Module definition |
| `CraniumCartographer v1.0` | dex_canon_v2 (Note export) | Module definition (2 variants) |
| `ToneprintShaper v1.0` | dex_canon_v2 (Note export) | Module definition |
| `06_MindFrame_Governance_v1.0.txt` | dex_canon_v2 | Governance Protocol (canonical) |
| `MindFrameAllBootFiles.txt` | dex_canon_v2 | All boot files aggregate |
| `06_AllFilesReview_All_v1.0.txt` | dex_canon_v2 | Aggregate file review |
| `DexVerse_MasterSignalLog_v1.0.txt` | dex_canon_v2 | v3.2 status, live test "Stratton" |
| `DDLCouncilReview_DexJrRagOnline.txt` | dex_canon_v2 | CraniumCartographer + Mirror proposals |
| `DDL_REPO_v1.0 Archive/03_MindFrame/` | dex_canon_v2 | Repo README stub |
| Multiple v4.0 component files | 99_DexUniverseArchive (NOT ingested) | Full v4.0 spec tree |
