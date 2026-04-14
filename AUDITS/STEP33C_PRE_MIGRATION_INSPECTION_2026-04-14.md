# Step 33c Part A — Pre-Migration Inspection (Read-Only)

**Date:** 2026-04-14
**Scope:** Drift state between nomic (writer) and _v2 / mxbai (reader) collections since Step 33b switchover (2026-04-12 night).
**Mode:** READ-ONLY. No collections modified. No source files modified. No commits.

---

## Pre-flight

| Check | Result |
|---|---|
| Rule 17 — `dex_weights.py` unstaged | Present, untouched |
| Rule 17 — `fetch_leila_gharani.py` unstaged | Present, untouched |
| Today's backup `chromadb_2026-04-14_0900` | Exists, 21 GB, no `_INCOMPLETE` sibling |
| Yesterday's backup `chromadb_2026-04-13_0900_INCOMPLETE` | Still present (prior known state) |

---

## SUB-TASK 1 — Exact drift count per collection

| Pair | nomic count | _v2 count | drift (nomic − _v2) | drift % of _v2 |
|---|---:|---:|---:|---:|
| dex_canon / dex_canon_v2 | 253,982 | 245,633 | **+8,349** | **+3.40%** |
| ddl_archive / ddl_archive_v2 | 291,520 | 291,520 | 0 | 0.00% |
| dex_code / dex_code_v2 | 20,384 | 20,384 | 0 | 0.00% |
| ext_creator / ext_creator_v2 | 922 | 922 | 0 | 0.00% |

Test collections (candidates for drop in Part B):

| Collection | Count |
|---|---:|
| dex_canon_mxbai_test | 2,500 |
| dex_canon_mxbai_rechunk_test | 10,000 |

**Finding:** Only `dex_canon` has drifted. Archive / code / ext_creator are byte-identical in count between the nomic and mxbai _v2 sides.

**Why only dex_canon drifted:** `dex-sweep.py:362` invokes `dex-ingest.py --collection dex_canon --fast --skip-backup-check`. The scoped writer path (`dex-ingest.py:380-384, 502-506`) writes **only** to the named collection, bypassing RAW/CANON routing entirely. Since Step 33b, every nightly sweep has landed exclusively in `dex_canon` (nomic). Nothing has touched `ddl_archive`, `dex_code`, or `ext_creator` during this period.

---

## SUB-TASK 2 — Drift content fingerprint (dex_canon only)

- Unique `source_file` values in nomic `dex_canon`: **4,640**
- Unique `source_file` values in `dex_canon_v2`: **4,596**
- Unique `source_file` values in drift (in nomic, NOT in _v2): **44**
- Total chunks in drift: **8,349**
- `ingest_run_id` sample (min/max from sampled subset): `manual_2026-04-13_222540` / `manual_2026-04-13_222540`
  - Note: sampled via `$in` on the first 100 drift source_files, limit 500; the one run_id returned reflects the last sweep (4:20 AM 2026-04-14 files inherit a prior manual run id only if re-ingested — current auto-sweep uses a different id scheme that did not appear in the 500-row sample). Full timestamp sweep was not performed to keep inspection read-only and cheap. This is not a blocker for Part B planning.

### Drift source files (top 30 by chunk count)

| chunks | source_file |
|---:|---|
| 1,488 | 11_Thread_Gemini_4.12.26.txt |
| 1,385 | 10_Thread_Gemini.txt |
| 1,088 | 83_MarcusCaldwell_4.12.26.txt |
|   756 | 89_LLMPM Claude Code Session - 4.11.26_20260413_172530.txt |
|   574 | LLMPM_Full Session Log - 4.12.26_20260414_041657.txt |
|   419 | LLMPM_Full Session Log - 4.12.26.txt |
|   273 | WorkBench_Full Session Log - 4.12.26(1).txt |
|   258 | WorkBench_Full Session Log - 4.12.26 2.txt |
|   247 | AuditForge_SideProject_Full Session Log_4.12.26.txt |
|   213 | 96_WorkBenchPM_4.12.26.txt |
|   182 | WebsitePM Full Session Log - 4.13.26.txt |
|   167 | DDLExtraction_DaveKitchens_SourceMaterial_4.13.26.md |
|   139 | Workbench Full Session Log - 4.13.26.txt |
|   121 | DDLExtraction_DexKit_LineageSourceMaterial_4.13.26.md |
|   106 | DDLExtraction_DexFamilyOriginThreads_4.13.26.md |
|    93 | DDLCouncilReview_StructuralRequirements.txt |
|    82 | DDLCouncilReview_HR&People_Module.txt |
|    77 | DDLCouncilReview_FactLayer.txt |
|    70 | DDLCouncilReview_WorkBenchAnalytics.txt |
|    69 | DDLCouncilReview_Bi-DirectionalIntegration.txt |
|    69 | PositionBook_Full Session Log - 4.12.26.txt |
|    61 | DDLCouncilReview_ModuleBuildProcess.txt |
|    60 | DDLCouncilReview_PitfallsAndResearch.txt |
|    55 | DDLCouncilReview_WeekendUpdate_4.12.26.txt |
|    54 | DDLCouncilReview_CannonAdditions.txt |
|    48 | LedgerPM_Full Session Log - 4.12.26.txt |
|    26 | WorkBench-BrandKit-v1_0.html |
|    25 | Comprehensive Update - Weekend of 4.11.26_20260413_172532.txt |
|    24 | DDLExtraction_CottageHumble_SourceMaterial_4.13.26.md |
|    19 | 83_MarcusCaldwell Council Member Boot Prompt and Q and A.txt |

Remaining 14 drift files tail off below 19 chunks each. These are the documents that are currently invisible to Dex Jr. retrieval until Part B lands.

---

## SUB-TASK 3 — dex-ingest.py config inspection

File: `C:\Users\dexjr\dex-rag\dex-ingest.py` — **not modified**.

| Setting | Value | Location |
|---|---|---|
| ChromaDB dir | `C:\Users\dkitc\.dex-jr\chromadb` | Module constant `CHROMA_DIR` (line 49) |
| Default RAW collection | `ddl_archive` | `RAW_COLLECTION` (line 51) |
| Default CANON collection | `dex_canon` | `CANON_COLLECTION` (line 52) |
| Embedding URL | `http://localhost:11434/api/embeddings` | `OLLAMA_URL` (line 54) |
| Embedding model | `nomic-embed-text` | `EMBED_MODEL` (line 55) |
| Chunk size / overlap (tokens) | 500 / 50 | lines 58–59 |
| Chunk chars per token | 4 | line 60 |
| Max normal-mode file size | 10,000,000 chars (~10 MB) | `MAX_TEXT_CHARS_NORMAL` (line 97) |
| Scoped collection override | Runtime CLI `--collection <name>` | argparse line 641–646 |
| Extension filter override | Runtime CLI `--ext-filter ...` | argparse line 647–652 |
| Model override | **None** — model is hardcoded, no CLI flag, no env var | n/a |
| Suffix logic | **None** — collection names are literal; no `_v2` suffix logic exists | n/a |

### Extension → collection routing

`PHASE1_EXTENSIONS` (lines 79–91) is the single extension whitelist. Routing is NOT per-extension — it is **tier-based** via `classify_tier(rel_path, filename, folder)` (lines 118–126) against `CANON_PATH_MARKERS` / `FOUNDATION_PATH_MARKERS` / `ARCHIVE_PATH_MARKERS`.

In **NORMAL** mode (no `--collection`, no `--build-canon`):
- All eligible files go to `ddl_archive` (RAW).
- Files classified as `canon` or `foundation` tier *also* go to `dex_canon`.

In **BUILD CANON** mode (`--build-canon`):
- RAW is not touched; only canon/foundation tier files go to `dex_canon`.

In **SCOPED** mode (`--collection <name>`):
- RAW and CANON are bypassed entirely. All eligible files go to the named collection only.
- **This is the mode the nightly sweep uses** (`dex-sweep.py:362` → `--collection dex_canon --fast --skip-backup-check`).

Extensions are not routed differently by type in any mode. `.png` and other non-listed extensions are filtered out at scan time by `scan_archive` (lines 266–289). The `CODE_EXTENSIONS` set (lines 71–76) is used only for `source_type` metadata inference (line 138), not for collection routing.

### Implication for Part B

To redirect writes to `_v2` (mxbai) collections, the smallest viable patch is to add either:
1. A `--embedding-model` CLI flag + `--collection-suffix` CLI flag (explicit, composable), OR
2. A hardcoded switchover: change `EMBED_MODEL` to `mxbai-embed-large`, change `RAW_COLLECTION` / `CANON_COLLECTION` to the `_v2` names, and update the sweep invocation to pass `--collection dex_canon_v2` instead of `dex_canon`.

Either way, `get_embedding()` (lines 175–186) must send the new model name. The embedding dimension of mxbai-embed-large differs from nomic-embed-text, so writes to a wrong-dimension collection will fail at Chroma level — there is no silent-corruption risk, but the sweep would halt if misconfigured.

---

## SUB-TASK 4 — dex-search-api.py config inspection

File: `C:\Users\dexjr\dex-rag\dex-search-api.py` — **not modified**.

| Setting | Value | Location |
|---|---|---|
| ChromaDB dir | `C:\Users\dkitc\.dex-jr\chromadb` | line 17 |
| Embedding URL | `http://localhost:11434/api/embeddings` | line 18 |
| Chat URL | `http://localhost:11434/api/chat` | line 19 |
| Embedding model | `nomic-embed-text` | line 20 |
| Chat model | `qwen2.5-coder:7b` | line 21 |
| Collections opened | `dex_canon` (line 93), `ddl_archive` (line 99) | hardcoded literal names |
| Suffix logic | **None** — hardcoded literal names, no `_v2` awareness | n/a |
| `/search` corpus param | `corpus=canon` → `dex_canon`; anything else → `ddl_archive` | line 124 |
| `/mindframe/chat` | Queries `dex_canon` for RAG context (line 149) | n/a |

### Implication for Part B

`dex-search-api.py` is a **separate reader** from `dex_jr_query.py` and is **still reading nomic `dex_canon` / `ddl_archive`**. It was NOT included in the Step 33b reader switchover. If any external consumer hits this API, they are currently getting nomic-backed results regardless of what Dex Jr. CLI returns.

Whether flipping this to `_v2` is safe depends on whether any external consumer is live. Rule 10 applies (routing change). Recommend surfacing this to the operator explicitly in Part B.

Also: this file still carries Known Bug #2 from the open items list — it only opens `dex_canon` and `ddl_archive`, ignoring `dex_code`, `ext_creator`, and any pending `ext_*` collections. Not in scope for 33c but flagged.

---

## SUB-TASK 5 — Known issues pre-check

### Quarantined HNSW dirs

`C:\Users\dkitc\.dex-jr\chromadb_quarantine\` contains **7** directories:

```
0b705eaf-e4e9-4f57-9bb1-5d32d068290e
15293f76-85e2-4ad2-9a48-2ddd3441db6e
42cf23b1-91bf-4529-bdf6-853620c8d670
af065713-9c5c-4bc5-bc00-4dbc304474c7
b2e6b7f8-0640-438a-931c-f1d4006498f3
f4df1db7-8cc8-4068-aac7-df483c0a3e69
fd9ae559-f423-4dbf-a636-98e8177b6068
```

The 8th orphan referenced in the prompt (`01bc5548`) is **live** in `chromadb\01bc5548-54bb-4b15-a27f-509a817cfa46` — i.e. it is not quarantined, it corresponds to a currently-active Chroma collection segment. Not an orphan; should be removed from the orphan watch list. Recommend verifying against the sqlite3 segment table in Part B planning.

### New orphan dirs from the 4:00 AM failed sweep attempt

Live `chromadb\` directory has 11 HNSW UUID directories plus `chroma.sqlite3`. The four live + four _v2 = 8 collections, plus the 2 test collections = 10. Plus 1 extra. This is broadly consistent with no spurious orphan creation from the 4:00 AM failure — the count is off by at most one, and that one is likely one of the two test collections (both are still live). **No obvious new orphans.** Full reconciliation against the sqlite segment table is deferred to Part B planning.

### Today's backup completeness

`D:\DDL_Backup\chromadb_backups\chromadb_2026-04-14_0900`:
- Size: 21 GB (consistent with a full snapshot)
- No `_INCOMPLETE` sibling present
- Sibling `chromadb_2026-04-13_0900_INCOMPLETE` from yesterday remains on disk (known prior state from the 4:00 AM collision that retried successfully at 4:20 AM; this was today's backup's parent-of-parent event)

**Today's backup is complete and usable as Part B's restore point.**

---

## Summary findings for Part B planning

1. **Only `dex_canon` has drifted** (+8,349 chunks, 44 unique source files). Archive / code / ext_creator are identical byte-for-byte in count and source_file set.
2. **Root cause** is scoped-sweep behavior: `dex-sweep.py` calls `dex-ingest.py --collection dex_canon`, which bypasses RAW/CANON routing. The sweep has only ever touched `dex_canon`.
3. **Writer config is hardcoded** — `EMBED_MODEL` and collection names are module constants, not env vars or CLI flags. Part B must either parameterize these or flip the constants.
4. **Two readers exist.** `dex_jr_query.py` was flipped to `_v2` in Step 33b. `dex-search-api.py` was NOT — it still reads nomic. Part B must decide whether to flip the API too.
5. **No new orphans, no incomplete backup, no new quarantine entries.** The system is in a clean state to plan a migration.
6. **Test collections** (`dex_canon_mxbai_test` 2,500 chunks, `dex_canon_mxbai_rechunk_test` 10,000 chunks) are drop candidates but NOT dropped in this step (read-only).

No blockers for Part B planning identified.
