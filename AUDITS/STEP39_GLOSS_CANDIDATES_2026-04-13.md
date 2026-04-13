# STEP 39A — Gloss-Candidate Inventory

**Date:** 2026-04-13
**CR:** Phase 2 Step 39A
**Operator:** Dave Kitchens
**Executor:** Claude Code (Dex Jr., Seat 1010)
**Scope:** Read-only. No corpus modification. No artifact authoring.

---

## Headline

**44 terms checked. 36 have no canonical definition file.** Of
those, **11 exceed 500 chunks of corpus density** with no gloss —
the class Marcus called "definition-thin." Top candidates by
impact × feasibility are `CottageHumble`, the F-code family
(F1–F6), and the operator's own profile (`Dave Kitchens`). Beth
Epperson and Charlie Conway remain flagged. One surprise:
`Emily` is actually the densest term in the corpus (21,993 chunks)
and already has a definition file — no action needed.

---

## Full inventory (sorted by chunk density)

Ordering is chunk-count descending. `def?` = filename match
against known artifact patterns (`{term}.*`, `STD-DDL-<term>-*`,
`CR-*<term>*`, `PROFILE-DDL-<term>-*`, `GLOSS-DDL-<term>-*`).

| # | Term | Type | `dex_canon_v2` | `ddl_archive_v2` | Total | Def? | Recommended |
|---|---|---|---:|---:|---:|:-:|:-:|
| 1 | Emily | entity | 10,576 | 11,417 | **21,993** | YES | — |
| 2 | Dave Kitchens | entity | 2,896 | 3,139 | **6,035** | no | **PROFILE** |
| 3 | F1 | fcode | 2,151 | 2,927 | 5,078 | no | **GLOSS** |
| 4 | F5 | fcode | 2,076 | 2,831 | 4,907 | no | **GLOSS** |
| 5 | **CottageHumble** | canon | 2,384 | 2,127 | 4,511 | no | **GLOSS** |
| 6 | F4 | fcode | 1,714 | 2,185 | 3,899 | no | **GLOSS** |
| 7 | F2 | fcode | 1,720 | 2,095 | 3,815 | no | **GLOSS** |
| 8 | F3 | fcode | 1,693 | 2,108 | 3,801 | no | **GLOSS** |
| 9 | F6 | fcode | 1,497 | 1,701 | 3,198 | no | **GLOSS** |
| 10 | Connor | entity | 1,490 | 1,471 | 2,961 | YES | — |
| 11 | GK | entity | 803 | 1,677 | 2,480 | no | PROFILE |
| 12 | Beth Epperson | entity | 860 | 810 | **1,670** | no | **PROFILE** |
| 13 | AutoCouncil | canon | 861 | 765 | 1,626 | YES | — |
| 14 | MDN | canon | 881 | 247 | 1,128 | no | GLOSS |
| 15 | GroundTune | canon | 501 | 261 | 762 | no | GLOSS |
| 16 | CoherentVelocity | canon | 274 | 248 | 522 | no | GLOSS |
| 17 | Clayton Hotze | entity | 237 | 249 | 486 | no | PROFILE |
| 18 | Bryce | entity | 224 | 206 | 430 | YES | — |
| 19 | GuidedEmergence | canon | 240 | 130 | 370 | no | GLOSS |
| 20 | OccamsOpposite | canon | 239 | 78 | 317 | no | GLOSS |
| 21 | AccidentalInsight | canon | 166 | 144 | 310 | no | GLOSS |
| 22 | AcceptableArrogance | canon | 163 | 137 | 300 | no | GLOSS |
| 23 | Jennifer Parker | entity | 144 | 134 | 278 | no | PROFILE |
| 24 | ModelCourtesy | canon | 225 | 35 | 260 | no | GLOSS |
| 25 | TrustANDVerify | canon | 162 | 86 | 248 | no | GLOSS |
| 26 | SideDoor | canon | 66 | 96 | 162 | no | GLOSS |
| 27 | AccidentalIntelligence | canon | 121 | 40 | 161 | no | GLOSS |
| 28 | Graph Holds | canon | 72 | 69 | 141 | no | GLOSS |
| 29 | ExpertiseInvisibility | canon | 38 | 40 | 78 | no | GLOSS |
| 30 | Cara Borkowski | entity | 31 | 29 | 60 | no | PROFILE |
| 31 | Charlie Conway | canon | 23 | 24 | **47** | no | **GLOSS** |
| 32 | OBS-DJ-004 | obs | 23 | 24 | 47 | no | STD |
| 33 | HYFS | canon | 34 | 0 | 34 | no | GLOSS |
| 34 | MetaMeta | canon | 8 | 12 | 20 | no | GLOSS |
| 35 | OBS-DJ-001 | obs | 5 | 13 | 18 | no | STD |
| 36 | OBS-AF-001 | obs | 9 | 0 | 9 | YES | — |
| 37 | WanderingDirection | canon | 2 | 0 | 2 | no | GLOSS |
| 38 | AppeaseMent | canon | 0 | 0 | 0 | no | — (unused) |
| 39 | CathedralPlanned | canon | 0 | 0 | 0 | no | — |
| 40 | SessionAsExemplar | canon | 0 | 0 | 0 | no | — |
| 41 | BringYourData | canon | 0 | 0 | 0 | no | — |
| 42 | AccidentalEntity | canon | 0 | 0 | 0 | no | — |
| 43 | PortableRecord | canon | 0 | 0 | 0 | no | — |
| 44 | AuditorsEye | canon | 0 | 0 | 0 | no | — |

---

## Notes on the top 5 candidates

Drafting-challenge typology per CC's earlier framing:
- **Summarize-existing** — material is in the corpus; operator can collapse it into a definition with editorial judgment, no new content
- **Articulate-implicit** — term is used constantly but its meaning lives in the operator's head; requires externalization, not summarization
- **Create-new** — principle is referenced but undefined; operator must author from scratch

| Rank | Term | Density | Challenge | Notes |
|---|---|---:|---|---|
| 1 | **CottageHumble** | 4,511 | **Articulate-implicit** | Highest-density canon term without a def. Samples show it described as "intentional, not insecurity" / "a feature, not a bug" / paired with "Graph Holds™." Operator-internal communication style, never serialized. Short standalone paragraph would fix retrieval for the entire class. |
| 2 | **F-code family (F1–F6)** | ~20,700 combined | **Summarize-existing** | Each F-code fires frequently in session logs and CLAUDE.md. The meanings ARE in the operator manifest and CLAUDE.md F-code section. The issue is those live as bulleted lists inside larger docs; extracting into `GLOSS-DDL-FCODES-001.txt` would give B3 a filename to catch. Single combined gloss, not six separate files. |
| 3 | **Dave Kitchens** | 6,035 | **Summarize-existing** | Operator's own profile. 6K chunks of message history, decisions, standards. A `PROFILE-DDL-DAVE-KITCHENS-001.txt` with role, responsibilities, operating principles, typical workflows would anchor Dex Jr.'s self-understanding of who it reports to. |
| 4 | **Beth Epperson** | 1,670 | **Summarize-existing** | Business partner. Chunks are pure message history + Nueterra demo context. `PROFILE-DDL-BETH-EPPERSON-001.txt` with role, relationship, business context. |
| 5 | **Charlie Conway Principle** | 47 | **Create-new** | Genuinely thin. Always appears as `"… MetaMeta™, Charlie Conway Principle (D-034) …"`. Has a decision number (D-034) but no content in the corpus. Operator must author the principle itself, not summarize existing material. |

---

## Recommendation

**Ship 1–3 first draft artifacts, ranked by impact × feasibility:**

1. **`GLOSS-DDL-FCODES-001.txt`** — combined F1–F6 entry. Highest
   impact: affects 6 distinct terms at ~3,000–5,000 chunks each.
   Lowest cost: meanings already exist in CLAUDE.md; this is
   extraction, not authorship. Single file. Unblocks all
   F-code-related queries immediately via B3.

2. **`GLOSS-DDL-COTTAGEHUMBLE-001.txt`** — articulate-implicit.
   One short paragraph defining the term, citing one or two
   representative uses. Mid cost (operator externalization),
   high impact (densest undefined canon term).

3. **`PROFILE-DDL-DAVE-KITCHENS-001.txt`** — the operator profile.
   High cost (it's an identity document, requires care), highest
   impact (anchors Dex Jr.'s understanding of its reporting
   structure). Can also be summarize-existing if the operator
   approves draft-and-revise from corpus material.

Beth and Charlie are second-wave. Charlie is the hardest
(create-new, principle undefined) and should probably wait for
operator-authored D-034 expansion.

**Rule-17 note:** none of these artifacts currently exist; no
conflict. The operator authors them in OneDrive or a working
folder, drops into DDL_Ingest, and the nightly sweep lands them
in `dex_canon`. B3 will catch them on the first query against
the ingested filename.

---

## Surprises

- **Emily at 21,993 chunks** is the densest term in the entire
  corpus. Already has a definition file (`Excerpt_30_emily.txt`).
  Not an issue — but worth noting that corpus density is wildly
  uneven; Emily alone is ~2% of all chunks.
- **8 operator terms have zero chunks** (AppeaseMent,
  CathedralPlanned, SessionAsExemplar, BringYourData,
  AccidentalEntity, PortableRecord, AuditorsEye, plus
  WanderingDirection with only 2). These are operator-internal
  language that never made it into a document. Not candidates
  for gloss; candidates for the operator to either start using
  them in drafted material or to retire them.
- **F-code density (~20K combined) suggests F-codes are the
  operator's dominant feedback mechanism** — by volume, more
  prevalent than any single canon term. Worth a dedicated
  governance artifact even beyond a gloss.
- **OBS-AF-001 has a file** (ingested this weekend via sweep)
  but OBS-DJ-001 and OBS-DJ-004 don't. Operator-observation
  artifacts need consistent filename discipline to be
  retrievable via B3.

---

## Appendix — script

`_step39_inventory.py` and `_step39_inventory.json` left
untracked as diagnostic artifacts (same pattern as Steps 28,
30, 32, 33).
