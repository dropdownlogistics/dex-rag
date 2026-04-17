# WORLDBUILDER.md — WorldBuilder Reference Document

> Version: 1.0
> Last updated: 2026-04-17
> Status: Initial consolidation from corpus
> Cross-references: [DEXOS.md](DEXOS.md) | [MINDFRAME.md](MINDFRAME.md) | [DEXLANGUAGE.md](DEXLANGUAGE.md) | [DDL_SYSTEM.md](DDL_SYSTEM.md)

---

## Important Note on Scope

The prompt that triggered this consolidation described WorldBuilder as
"the methodology for constructing governed systems across domains" and
expected it to cover Chaos-to-Structured-to-Automated, star schema
thinking, Sibling Mandate, CathedralPlanned, BlueprintInversion, and
bundling architecture.

**The corpus disagrees.** Every source consistently defines WorldBuilder
as the **DexOS Universe OS for building fictional worlds** — TTRPG
campaigns, story canon, entities, factions, and timelines. The DDL
methodology concepts listed above exist in the corpus but are
**DDL-level** and **WorkBench platform** concepts, not WorldBuilder
concepts. They are documented in [DDL_SYSTEM.md](DDL_SYSTEM.md).

This document captures what WorldBuilder actually IS per the corpus.
See the "Methodology Concepts" section at the end for where those
other concepts live.

---

## Definition

WorldBuilder is the Universe OS of DexOS. It defines how fictional
worlds, entities, systems, timelines, and canon are created, evolved,
and governed.

> "WorldBuilder does NOT dictate story content; it manages the
> **structure** and **rules** that stories must respect."

From the boot prompt:

> "You are Worldbuilder v1.0, part of the MindFrame ecosystem. Your
> job: Help me design, clean up, and expand fictional worlds for
> campaigns and stories. Stay coherent, consistent, and
> system-agnostic (works with any TTRPG or format)."

---

## Purpose

1. Provide a structured environment for building and maintaining
   multiple fictional universes
2. Define consistent rules for:
   - World anatomy
   - Entities and factions
   - Physics / magic / tech systems
   - Timelines and events
   - Canon tracking and retcons
3. Integrate cleanly with MindFrame (cognitive engine), DexLanguage
   (prompt grammar), and DexHub (governance and file system)

---

## Eight Engines

| Engine | Function |
|---|---|
| **WorldSeedEngine** | Initial world generation — starting parameters, core identity |
| **RegionEngine** | Geographic and spatial structuring |
| **FactionEngine** | Organizations, groups, power structures |
| **CharacterEngine** | Individual entities, NPCs, player characters |
| **SystemEngine** | Physics, magic, technology, and rule systems |
| **TimelineEngine** | Temporal structuring, events, eras |
| **QuestEngine** | Mission and narrative arc structuring |
| **DrawingEngine** | Visual representation interfaces (six sub-engines) |

---

## Architecture

WorldBuilder follows a three-tier structure:

| Tier | Focus |
|---|---|
| **Conceptual** | World identity, themes, seed parameters |
| **Structural** | Regions, factions, systems, timelines |
| **Narrative** | Quests, characters, events, story arcs |

### Directory Structure

The canonical `05_Worldbuilder_v1.0` (or `04_WorldBuilder_v1.0` in
earlier numbering) contains:

```
01_CoreSpec/
02_Worldbuilder_System/
03_Worldbuilder_Modules/
04_Worldbuilder_Pipelines/
05_Worldbuilder_Playbook/
06_Worldbuilder_DemoWorld/
07_DrawingEngine/
```

### Demo World

**The Ember Coil** — a working demo world produced to prove the
system's viability. Demonstrates all eight engines in operation
against a single fictional universe.

---

## Integration with DexOS

WorldBuilder is an application-layer module within DexOS. In the
TestNet v2.0 three-layer architecture:

- **Compiler layer:** DPEG (intent to prompt)
- **OS layer:** DexHub (scheduling, resources, state)
- **Application layer:** MindFrame programs, **WorldBuilder worlds**

### Integration with MindFrame

MindFrame runs Programs that create, modify, and explore worlds.
WorldBuilder schemas serve as the data model for MindFrame's
universe-building operations. MindFrame provides the cognitive
engine; WorldBuilder provides the domain-specific structure.

### Integration with DexLanguage

DexLanguage defines the grammar for describing world changes and
queries:

> "Prompts become predictable world operations instead of free-form
> chaos."

WorldBuilder operations are expressed in DexLanguage prompt shapes
(see [DEXLANGUAGE.md](DEXLANGUAGE.md)).

### Integration with DexHub

DexHub tracks WorldBuilder files and versions, maintains the world
list, monitors health (QC status), and manages integration status
across the DexOS ecosystem.

---

## Version History

| Version | Date | Notes |
|---|---|---|
| v1.0 | ~November 2025 | Initial system with 8 engines, demo world (The Ember Coil) |
| v2.0 | ~February 2026 | Exists on filesystem (`04_WorldBuilder_All_v2.0.txt`), not separately retrieved |

---

## What WorldBuilder Is NOT

WorldBuilder is not DDL's general methodology for constructing
governed systems. That methodology has no single name — it is
distributed across several concepts:

- **Chaos-to-Structured-to-Automated** — the DDL core operational loop
- **Star schema / dimensional modeling** — the architectural primitive
- **Sibling Mandate** — the WorkBench module composition pattern
- **Bundling** — the commercial packaging architecture
- **CathedralPlanned / BlueprintInversion** — canon candidates for
  governance-first vs. build-first approaches

These are documented in [DDL_SYSTEM.md](DDL_SYSTEM.md) under
"Methodology and Architecture."

---

## AI Review Summary

From the Cognitive Architecture Handoff:

> "You've essentially built a mini operating system for fictional
> universes, with modular engines, syntax conventions, and pipelines
> that can be orchestrated through DexLanguage. Strengths: Clear
> tiering (Conceptual to Structural to Narrative); Eight functional
> engines; Five practical workflows; A working demo world (The Ember
> Coil); DrawingEngine counterpart with six sub-engines."

---

## Source Artifacts

| File | Location | Nature |
|---|---|---|
| `04_BootFiles_WorldBuilder_All_v1.0.txt` | dex_canon_v2 | Boot files aggregate |
| `06_AllFilesReview_All_v1.0.txt` | dex_canon_v2 | File review (includes WorldBuilder) |
| `DexLanguageMerged.txt` | dex_canon_v2 | CorePrinciples (references WorldBuilder) |
| `Note - Worldbuilder v1.0` | dex_canon_v2 (Note export) | Boot prompt definition |
| `OCR_IMG_0302.txt` | dex_canon_v2 | Screenshot of file listing |
| `28_CognitiveArchitectureHandoff.txt` | dex_canon_v2 | AI review of WorldBuilder |
| `28_CognitiveArchitecture.txt` | dex_canon_v2 | Earlier cognitive architecture |
| `03_Worldbuilder_AI_Review.txt` | 99_DexUniverseArchive (NOT ingested) | Multi-model AI review |
| `Worldbuilder Engine v1.0.txt` | 99_DexUniverseArchive (NOT ingested) | Engine definition |
| `27_Worldbuilder_Architecture_v1.0.txt` | 99_DexUniverseArchive (NOT ingested) | Architecture spec |
| `Project Directive — WorldBuilder_v1.0.txt` | 99_DexUniverseArchive (NOT ingested) | Project directive |
| `NewThreadPrompt — WorldBuilder_v1.0.txt` | 99_DexUniverseArchive (NOT ingested) | New thread prompt |
| `ContinuingThreadPrompt — WorldBuilder_v1.txt` | 99_DexUniverseArchive (NOT ingested) | Continuing thread prompt |
| `01_ProjectInfo_01_WorldBuilder.txt` | 99_DexUniverseArchive (NOT ingested) | Project info |
| `04_WorldBuilder_All_v2.0.txt` | 99_DexUniverseArchive (NOT ingested) | v2.0 aggregate |
| `DDL_REPO_v1.0 Archive/04_WorldBuilder/` | 99_DexUniverseArchive (NOT ingested) | Repo archive directory |
