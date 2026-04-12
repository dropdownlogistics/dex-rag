# Step 12: Airtight Perimeter Audit

**Date:** 2026-04-11
**Auditor:** CC (executor) on behalf of Marcus Caldwell 1002 (advisor)
**Scope:** dex-rag repo, all .py files outside `.venv/`, `__pycache__/`, `.git/`, `dex-rag-scratch/`
**Authority:** STD-DDL-METADATA-001, STD-DDL-BACKUP-001 (Trigger 3), CLAUDE.md Rule 8
**Method:** Targeted ripgrep over 29 in-repo .py files for ChromaDB read/write method signatures, cross-referenced with `git log` mtimes, `import chromadb` presence, CLAUDE.md references, and docstring purpose

---

## Summary

| Metric | Count |
|---|---:|
| Total .py files scanned | **29** |
| Files importing `chromadb` directly | **14** |
| Files with write surfaces (direct) | **3** |
| Files with write surfaces (transitive via subprocess) | **1** |
| Files with read-only surfaces | **14** |
| Files with no ChromaDB interaction | **11** |
| **Currently gated by Trigger 3** (`ensure_backup_current`) | **1** |
| **Currently STD-compliant** (`build_chunk_metadata`) | **1** |
| Recommended WIRE | **3** |
| Recommended DEPRECATE | **0** |
| Recommended DELETE | **3** |
| Recommended KEEP_AS_IS | **12** |

**Perimeter verdict:** The airtight pipeline is **one airtight path out of four write paths**. Three write paths (including the nightly 3am sweep) are currently unguarded — no backup gating, no STD-DDL-METADATA-001 provenance metadata, no verification. Every sweep run at 3am writes chunks to `ddl_archive` and `dex_canon` ungated.

---

## Write Surfaces

### 1. `dex-ingest-text.py` ✅ AIRTIGHT REFERENCE

- **Path:** `dex-ingest-text.py`
- **Writes:** 1× `collection.add()` at line 164, 1× `client.get_or_create_collection()` at line 160
- **Target collections:** dynamic via `--collection` CLI flag (exercised against `dex_canon` in Step 6 for real, `dex_test` in smoke tests)
- **Gated (Trigger 3):** ✅ **YES** — `ensure_backup_current()` called at line 127-ish (Step 3.5, post-chunking pre-metadata)
- **STD metadata:** ✅ **YES** — uses `build_chunk_metadata()` via import from `dex_pipeline.py`
- **Purpose:** Plain-text ingest path for the airtight pipeline. Handles `.txt` and `.md` only. Bypasses `dex-convert.py` entirely.
- **Last modified:** 2026-04-11 (git-tracked)
- **Status:** ACTIVE (Phase 2 Step 5 + 6 + 9)
- **Recommendation:** **KEEP_AS_IS**
- **Notes:** This is the reference implementation. Every other write path should be evaluated against this as the target shape.

### 2. `dex-ingest.py` ⚠️ UNGATED, HIGH-TRAFFIC

- **Path:** `dex-ingest.py`
- **Writes:**
  - `client.delete_collection()` at line 253 (behind `--reset` flag — destructive)
  - 3× `client.get_or_create_collection()` at lines 257 (RAW), 260 (CANON), 268 (scoped)
  - 3× `collection.upsert()` at lines 435 (raw_col), 452 (canon_col), 469 (scoped_col)
- **Target collections:** `ddl_archive` (RAW), `dex_canon` (CANON), plus optional scoped collection via `--collection` flag
- **Gated (Trigger 3):** ❌ **NO**
- **STD metadata:** ❌ **NO** — writes chunks without `source_type`, `ingested_at`, `ingest_run_id`, `chunk_index`, `chunk_total`
- **Purpose:** Dual-collection (RAW + CANON) bulk filesystem ingestion. The legacy main ingest path. Filesystem scanner → chunker → Ollama embedder → upsert to RAW, conditional upsert to CANON.
- **Last modified:** 2026-03-14 (git-tracked)
- **Status:** ACTIVE (called by `dex-sweep.py` via subprocess every night at 3am per CLAUDE.md Rule 13; also invoked manually per CLAUDE.md Open Items)
- **Recommendation:** **WIRE** — highest-priority wiring target. This file is the bulk of the ungated perimeter.
- **Notes:**
  - CLAUDE.md Open Items #1 (critical bug, `dex-convert.py` silent-drop) and #3 (scoped+fast file-level skip broken at lines 370-374) both intersect with this file indirectly. Wiring Trigger 3 here does NOT fix those bugs — they stay independent.
  - Writes to 3 collections in a single run. Trigger 5 (>100 chunks) will fire on most runs.
  - The `--reset` flag calls `delete_collection()` on both RAW and CANON collections. This is the single most destructive operation in the repo. Rule 8 territory.
  - 562 lines total. Wiring this is the biggest refactor in the Step 13+ sequence.

### 3. `dex-acquire.py` ⚠️ UNGATED, LOW-TRAFFIC

- **Path:** `dex-acquire.py`
- **Writes:** 1× `collection.add()` at line 245, 1× `client.get_or_create_collection()` at line 58
- **Target collections:** dynamic via `--collection` CLI flag (docstring example: `ext_canon`)
- **Gated (Trigger 3):** ❌ **NO**
- **STD metadata:** ❌ **NO**
- **Purpose:** Batch URL acquisition with quality gate. Fetch → evaluate with `dexjr` model → score → auto-ingest if >= 7/10 OR flag for review if 5-6 OR skip if <5. Governance-layer URL ingestor.
- **Last modified:** 2026-03-14 (git-tracked)
- **Status:** ACTIVE (referenced in docstring examples for `ext_canon` — one of the three missing-collection targets from Phase 1)
- **Recommendation:** **WIRE**
- **Notes:**
  - 488 lines. Smaller and cleaner than `dex-ingest.py` — easier wiring target and good second candidate after `dex-ingest.py`.
  - Has its own `get_collection()` helper at line 55 that creates-on-demand. When wired, this helper should also enforce STD compliance.
  - Hardcoded `CHROMA_PATH = r"C:\Users\dkitc.dex-jr\chromadb"` on line 41 — **NOTE: typo, missing backslash between `dkitc` and `.dex-jr`.** This path as written resolves to `dkitc.dex-jr\chromadb` (a single dotted folder name), NOT to the live ChromaDB at `C:\Users\dkitc\.dex-jr\chromadb`. This is a **latent bug** — dex-acquire.py has been writing to a different path than everything else, or failing silently. Flagging loudly.

### 4. `dex-sweep.py` ⚠️ TRANSITIVE WRITER, AUTOMATED, UNGATED

- **Path:** `dex-sweep.py`
- **Writes:** **Indirect** — subprocess invokes `python dex-ingest.py ...` at line 141. Variable hardcoded at line 56: `INGEST_SCRIPT = r"C:\Users\dexjr\dex-rag\dex-ingest.py"`. No direct ChromaDB method calls in this file.
- **Target collections:** whatever `dex-ingest.py` writes to → `ddl_archive`, `dex_canon`, + any `--collection` scoped target
- **Gated (Trigger 3):** ❌ **NO**
- **STD metadata:** ❌ **NO** (inherits from dex-ingest.py)
- **Purpose:** Auto-sweep. Watches drop folders (`C:\Users\dkitc\OneDrive\DexJr`, `DDL_Ingest`, `Downloads\DDL_Ingest`, iCloud `04_DDL_Ingest`) → copies new files to canon dir → moves originals to `_processed` → invokes `dex-ingest.py`. Can run once (`python dex-sweep.py`) or continuously (`--watch --interval N`).
- **Last modified:** 2026-03-14 (git-tracked)
- **Status:** **ACTIVE + LIVE INFRASTRUCTURE** (CLAUDE.md Rule 13: "The 3am sweep is not test code. It runs against the real corpus on a schedule using `--fast` mode"). Per CLAUDE.md Open Items, also affected by scoped+fast bug.
- **Recommendation:** **WIRE** — specifically: add its own `ensure_backup_current()` call BEFORE invoking dex-ingest.py, sized via estimated `--expected-chunks` from the file count × rough per-file chunk average. Trigger 5 (>100 chunks) will reliably fire on sweep runs that touch more than a handful of files.
- **Notes:**
  - **This is the biggest perimeter hole.** It runs automatically, unattended, at 3am, against the live corpus, with no Trigger 3 gate and no post-run report. Any corruption introduced by this path goes undetected until the next manual audit.
  - When dex-ingest.py is wired (step above), each inner per-file call will individually fire Trigger 3. That's good but redundant-per-file. Better pattern: have dex-sweep.py fire ONE Trigger 3 upfront with `expected_write_chunks=estimated_total`, then let dex-ingest.py skip its own check via an env flag or CLI bypass. This avoids 30 backup checks per sweep run.
  - Sweep writes nothing on its own but is the de-facto entry point for all nightly writes. Any airtight perimeter discussion MUST consider the sweep as first-class.
  - 260 lines. Wiring is small if dex-ingest.py is wired first.

---

## Read Surfaces

All files below touch ChromaDB read-only. Per the operator's instruction, these don't need gating, but listing for completeness of the perimeter picture.

| File | Path | Reads | Target collections | Purpose | Last mod | Status |
|---|---|---|---|---|---|---|
| `dex-query.py` | root | `.count()`, `.query()`, `get_collection()` | `dex_canon`, `ddl_archive`, `ext_canon?`, `ext_archive?` | Interactive query CLI with optional external collections | 2026-03-14 | ACTIVE |
| `dex-search-api.py` | root | `.query()`, `.count()`, `get_collection()` | `dex_canon`, `ddl_archive` | FastAPI HTTP server. CLAUDE.md Open Items #2 flagged: invisible to 5 of 7 collections. | 2026-03-14 | ACTIVE |
| `dex-bridge.py` | root | `get_collection()`, `.query()` | `RAW_COLLECTION` (hardcoded) | Bridge query path per v1.1 source-weighting. Imports `dex_weights`. | 2026-03-14 | ACTIVE |
| `dex-council.py` | root | `get_collection()`, `.query()` | dynamic via `col_name` var | Council deliberation query path. | 2026-03-14 | ACTIVE |
| `dex-deliberate.py` | root | `get_collection()`, `.query()` | `RAW_COLLECTION` or `CANON_COLLECTION` | Dex Jr. deliberation path (switchable RAW/CANON). | 2026-03-14 | ACTIVE |
| `dex-fetch.py` | root | `get_collection()`, `.query()` | `CANON_COLLECTION` | Fetch with dedup check against canon. | 2026-03-14 | ACTIVE |
| `dex_weights.py` | root | `get_collection()`, `.query()` | 4 live + 3 missing per `COLLECTIONS` dict | **Shared library.** Weighted retrieval scoring. `get_client()` is reused across pipeline. | 2026-03-14 | ACTIVE. **Rule 17 WIP** (unstaged mods). |
| `dex_pipeline.py` | root | `get_collection()`, `.get(where=)` | dynamic | `verify_ingest()` read helper for the airtight pipeline. | 2026-04-11 | ACTIVE (airtight helper library) |
| `dex-backup.py` | root | `list_collections()`, `get_collection()`, `.count()`, raw SQLite read | all 4 live | Backup executable. Reads to build manifests and validate. | 2026-04-11 | ACTIVE (infrastructure) |
| `morning_check.py` | root | `get_collection()`, `.count()` | hardcoded list | Daily diagnostic count across collections. | UNTRACKED | ACTIVE? (operator uses interactively) |
| `audit_ddl_ingest_xref.py` | root | `get_collection()`, `.get(where=)`, `.query()` | all 7 documented (only 4 exist) | DDL_Ingest ↔ corpus cross-reference audit tool. Phase 1. | 2026-04-11 | ACTIVE (committed Phase 1 tool) |
| `audit_archive.py` | root | `get_collection()`, `.count()` | hardcoded list | One-off archive count audit. | UNTRACKED | STALE — flagged in CLAUDE.md Open Items |
| `audit_missing_only.py` | root | `get_collection()`, `.count()` | hardcoded list | One-off missing-file audit. | UNTRACKED | STALE — flagged in CLAUDE.md Open Items |
| `check_file.py` | root | `get_collection()` | dynamic | 14-line one-liner to check a file. | UNTRACKED | STALE |

### Reader verdict

All readers are correctly classified as **KEEP_AS_IS** except three untracked one-offs (`audit_archive.py`, `audit_missing_only.py`, `check_file.py`) which are **DELETE** or **commit** candidates per CLAUDE.md Open Items. They don't affect the airtight perimeter either way.

---

## Non-ChromaDB files (11)

Classified for completeness — these don't touch ChromaDB at all (verified by absence from both read and write greps and from the `import chromadb` list). No action needed from a perimeter standpoint.

| File | Purpose | Last mod | Status |
|---|---|---|---|
| `clean_staas.py` | STAAS fetch+clean | 2026-04-11 | ACTIVE (consolidated in the 2026-04-12 cleanup session) |
| `dex-convert.py` | Format converter (HTML/CSV/PDF/MBOX → txt). **Writes to filesystem, not ChromaDB.** CLAUDE.md critical bug #1 (silent drops). | 2026-03-14 | ACTIVE |
| `dex-ocr.py` | OCR | 2026-03-14 | ACTIVE? |
| `dex-setup.py` | One-time setup script | 2026-03-14 | ACTIVE? (93 lines) |
| `dex-whisper.py` | Whisper transcription | 2026-03-14 | ACTIVE? |
| `dex-xlsx.py` | XLSX converter | 2026-03-14 | ACTIVE? |
| `extract.py` | 6-line one-off PDF→text for Leverage_Points.pdf | 2026-03-14 | **STALE** (committed but clearly one-off) |
| `fetch_ext_creators.py` | URL fetcher for external creators | UNTRACKED | ACTIVE? |
| `fetch_leila_gharani.py` | URL fetcher. **Rule 17 WIP** (unstaged mods). | 2026-03-18 | UNKNOWN — operator work-in-progress |
| `fetch_simon_willison.py` | URL fetcher | UNTRACKED | ACTIVE? |
| `transcribe_mania.py` | Mania transcription (consolidated 2026-04-11) | 2026-04-11 | ACTIVE |

---

## Surprise Findings — Flag Loudly

### ⚠️ Surprise #1: `dex-sweep.py` is an automated ungated writer

The nightly sweep at 3am writes to `ddl_archive` + `dex_canon` every run, via subprocess to `dex-ingest.py`. **Zero backup gating. Zero STD metadata. Zero post-run report.** Runs unattended. No one watches it. Any silent corruption from its writes is invisible until a manual audit or a restore test.

**This is the single highest-risk item in the entire perimeter.** Rule 13 of CLAUDE.md explicitly calls it "live infrastructure." Wiring Trigger 3 into this path — either directly in dex-sweep.py or transitively via dex-ingest.py — is the most important follow-up of this audit.

### ⚠️ Surprise #2: `dex-acquire.py` has a typo in its hardcoded ChromaDB path

Line 41: `CHROMA_PATH = r"C:\Users\dkitc.dex-jr\chromadb"`

Notice the missing backslash between `dkitc` and `.dex-jr`. This path as written points to a single dotted folder name `dkitc.dex-jr`, not to the live ChromaDB at `C:\Users\dkitc\.dex-jr\chromadb`.

**Either:**
- dex-acquire.py has been silently writing to a different (non-corpus) ChromaDB path since 2026-03-14, and the "quality-gated URL acquisitions" the operator thinks were ingested never landed in the real corpus, OR
- dex-acquire.py has been raising on every run (empty path resolves to no-such-dir) and the operator hasn't used it recently

I did NOT run `dex-acquire.py` to verify which case applies. Flagging for operator investigation. **If the former, there may be a parallel shadow corpus somewhere on this machine containing quality-scored URL acquisitions that were never in `dex_canon`.**

### ⚠️ Surprise #3: `dex-ingest.py` has a `--reset` flag that deletes `ddl_archive` and `dex_canon`

Line 247 checks an `if reset:` condition and calls `client.delete_collection(cname)` on both RAW and CANON collections (lines 251-255). This is the single most destructive path in the repo. Currently the `delete_collection` is wrapped in `except Exception: pass` — a Rule 15 silent-failure anti-pattern that would hide a partial-delete state.

I did NOT search for where `--reset` is invoked from (is it only manual? is there an automated path?). Worth checking before wiring.

### ⚠️ Surprise #4: `check_file.py` exists and is completely undocumented

14 lines, untracked, not in CLAUDE.md Open Items list of audit scripts. Doesn't show up anywhere else. Probably a one-off diagnostic the operator ran once and forgot. **Candidate for immediate deletion.**

### Non-surprise: 3 of 7 collections still missing from live

`dex_weights.py` still defines the full 7-collection dict at `COLLECTIONS` (lines 25-33) including `ext_canon`, `ext_archive`, `ext_reference` which don't exist in the live DB. This is the same drift-between-code-and-reality finding from CR-DEXJR-DDLING-001. Not new. Already tracked in ADR-INGEST-PIPELINE-001 §"Pending decisions".

---

## Top 3 WIRE candidates by risk

Ordered by combined signal of (active usage) × (ungated) × (recently exercised):

### 1. `dex-ingest.py` — highest priority
- Bulk ingest path with 3 upsert targets
- Called transitively by `dex-sweep.py` every 3am
- 562 lines — biggest refactor in the wire-up sequence
- Writes to 3 collections with no STD metadata

### 2. `dex-sweep.py` — highest urgency (even if lowest LOC)
- Runs unattended and invisibly
- Needs its own Trigger 5 (>100 chunks) check upfront rather than relying on per-file checks inside dex-ingest.py
- Transitively fixed by wiring dex-ingest.py, but that's 30 per-file backup checks per sweep run — wasteful
- Best pattern: sweep fires ONE Trigger 3 with estimated total → passes bypass env var to dex-ingest.py → dex-ingest.py's per-file check becomes a no-op during sweep invocations

### 3. `dex-acquire.py` — lowest urgency but needs the path typo investigated first
- Single `collection.add()` at line 245
- Smaller refactor than dex-ingest.py
- **Do not wire until the line-41 path typo is understood and resolved** — otherwise we'd be wiring a broken path

---

## Top 3 DELETE candidates

1. **`check_file.py`** — 14 lines, untracked, undocumented, not referenced anywhere, no `.chunks()` or similar that would indicate active usage. Safe to delete with operator OK.
2. **`audit_archive.py`** — 66 lines, untracked, explicitly flagged as "one-off" in CLAUDE.md Open Items. Operator asked "Either commit, gitignore, or delete after retool." Delete recommendation: after the retool consolidates into `dex_core`, this one-off logic is absorbed into a general `dex health` command (CLAUDE.md refactor target #4) and the standalone file has no home.
3. **`audit_missing_only.py`** — same as above, 79 lines. Same recommendation.

Low-confidence DELETE candidate (don't delete without investigation):
- **`extract.py`** — 6-line PDF→text one-off for `Leverage_Points.pdf`. The file `Leverage_Points.pdf` is in the untracked repo root. Could be deleted or committed as a sibling to the audit scripts, but no urgency. Operator call.

---

## Ambiguous / goes-to-Marcus for judgment

- **`fetch_leila_gharani.py`** — Rule 17 WIP. Operator is actively working on this. Not mine to classify or touch. Listed for completeness.
- **`fetch_ext_creators.py`, `fetch_simon_willison.py`** — untracked URL fetchers. Don't touch ChromaDB (confirmed). Look like they write converted text files somewhere that `dex-ingest.py` then picks up. Status ACTIVE but not part of the airtight perimeter since they write filesystem, not DB. Listed for perimeter completeness, no action.
- **`morning_check.py`** — untracked diagnostic, likely active. The operator runs it interactively based on its name. Not in CLAUDE.md but clearly useful. Commit candidate for later cleanup. No action now.
- **`dex-ocr.py`, `dex-whisper.py`, `dex-xlsx.py`** — file-converter utilities. Don't touch ChromaDB. Probably invoked by `dex-convert.py` or by the operator manually. Not airtight perimeter. Listed for completeness.

---

## Recommended Step 13+ Sequence

Each step sized to one CC session (~200 LOC of changes, one commit, testable in isolation).

### Step 13 — Wire `dex-ingest.py` (biggest lift)
- Add `ensure_backup_current()` call after chunk count is known but before the first upsert
- Replace manual metadata dict construction (if any) with `build_chunk_metadata()` calls for every chunk
- Add a `--skip-backup-check` bypass flag for when sweep invokes it (Step 14 uses this)
- Self-test: dry-run against a known small corpus subset, compare pre/post chunk counts
- Gate against operator GO before any live run (the scoped+fast bug intersects here)
- **Prerequisite decision:** what `source_type` inference rule applies to legacy ingest targets? (filesystem scan finds `.py`, `.md`, `.html`, `.jsx`, `.jpg` (NO), etc. — needs an extension → source_type map)

### Step 14 — Wire `dex-sweep.py`
- Add one `ensure_backup_current()` call at sweep start, sized via estimated chunks from file count × avg per-file chunk estimate
- Pass `--skip-backup-check` env var or CLI flag to dex-ingest.py invocation so per-file checks become no-ops
- Add a minimal sweep report per ADR-INGEST-PIPELINE-001 §"Sweep report format" — even a stub is valuable
- First real exercise: operator approves a manual dry-run against a small DDL_Ingest subset

### Step 15 — Investigate and fix `dex-acquire.py` path typo
- Confirm whether line 41's `C:\Users\dkitc.dex-jr\chromadb` resolves to an actual directory on this machine
- If yes: investigate what's in it, potentially re-ingest via the airtight path
- If no: fix the typo to match everything else, verify nothing was lost
- Separate commit, separate pre-flight

### Step 16 — Wire `dex-acquire.py`
- Add `ensure_backup_current()` call before the `.add()` at line 245
- Replace its own `get_collection()` helper with calls into `dex_pipeline`-style helpers
- Test against a small URL list with quality gate intact

### Step 17 — STD amendment + cleanup pass
- STD-DDL-BACKUP-001 amendment: formalize Trigger 6 and `--skip-restore-test`
- Cosmetic fences on STD-DDL-BACKUP-001
- Delete `check_file.py`, `audit_archive.py`, `audit_missing_only.py` per operator OK
- CLAUDE.md Open Items housekeeping pass — mark Phase 2 items as done, update Open Items list

### Later — not sized as single-session
- `move_to_archive()` helper + wiring (DDL_Staging → DDL_Archive leg)
- Phase 3 sweep report full builder
- Backfill operation per STD-DDL-METADATA-001 §"Backfill operation" (touches 542K chunks — multi-session)

---

## Methodology notes

- **Grep scope:** Targeted grep over explicit list of 29 in-repo .py files (not recursive with exclusions, to avoid .venv/chromadb internal noise). See Bash output `grep -HnE '...' audit_*.py check_*.py clean_*.py dex-*.py dex_*.py extract.py fetch_*.py morning_*.py transcribe_*.py` at the repo root.
- **Write patterns:** `\.add\(`, `\.upsert\(`, `\.delete\(`, `\.update\(`, `create_collection\(`, `delete_collection\(`, `get_or_create_collection\(`. Filtered for ChromaDB-specific signatures vs Python set/dict/hashlib noise via context review.
- **Read patterns:** `\.query\(`, `\.count\(\)`, `\.get\(`, `list_collections\(`, `get_collection\(`. Filtered to Chroma-specific patterns.
- **Import gate:** `import chromadb`, `from chromadb`, `PersistentClient`. 14 files directly import chromadb. Plus `dex-ingest-text.py` uses `dex_weights.get_client` indirectly (not a direct chromadb import).
- **Transitive write detection:** Grep for `subprocess`, `Popen`, `os.system`, `dex-ingest`, `dex-acquire`, `dex-convert` in files that otherwise don't import chromadb. `dex-sweep.py` is the only positive hit.
- **No scripts were run that touched live ChromaDB.** Audit was pure static analysis + docstring reading.
- **No code modifications.** Per operator instruction: "This is an audit, not a fix."

---

**End of STEP12 audit report.**
