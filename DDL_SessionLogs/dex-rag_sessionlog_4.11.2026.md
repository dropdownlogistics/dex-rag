# dex-rag Session Log — 2026-04-11

## Session — 2026-04-11 (CR-DEXJR-AUDIT-001 follow-up, quick-win deletions)

### What Was Done
Executed the six approved quick-win deletions from CR-DEXJR-AUDIT-001.
Each deletion was preceded by: (a) filesystem existence check, (b) repo-wide
grep for importers/references, (c) full file read. One commit per deletion
or consolidation group. Nothing pushed per CLAUDE.md Rule 4.

1. Deleted `dex-weights.py` (dash variant, 292 lines) — confirmed zero functional
   importers. Live code uses `dex_weights.py` (underscore).
2. Deleted `bridge-fix-v4.1.py` (52 lines) — orphan patch for a version that
   never shipped.
3. Deleted `council-governance-v4.1.py` (59 lines) — superseded by inline
   `GOVERNANCE` string in `dex-council.py`.
4. Deleted `fetch_staas.py` (1 line, stub containing only `import requests`).
5. Consolidated `clean_staas` variants: kept `fetch_clean_staas.py`'s content
   (most complete — self-contained fetch + clean pipeline) under the canonical
   name `clean_staas.py`. Removed `clean_staas2.py` and `fetch_clean_staas.py`
   from disk (both untracked, so not captured in git history as deletions).
6. Consolidated `transcribe_mania`: kept v3 (encoding + dedup + CUDA + Windows-
   safe output markers), renamed to `transcribe_mania.py`. Removed v1 and v2
   from disk (all three were untracked; the commit captures v3's content under
   the canonical name).

### Files Touched
- dex-weights.py (deleted)
- bridge-fix-v4.1.py (deleted)
- council-governance-v4.1.py (deleted)
- fetch_staas.py (deleted)
- clean_staas.py (modified — content replaced with fetch_clean_staas.py's
  content under the canonical name)
- clean_staas2.py (removed from disk, untracked)
- fetch_clean_staas.py (removed from disk, untracked)
- transcribe_mania.py (formerly v1 — removed from disk, replaced by v3 content)
- transcribe_mania_v2.py (removed from disk, untracked)
- transcribe_mania_v3.py (removed from disk, content promoted to transcribe_mania.py)

### Commits (hash · message)
- `ed60c19` · chore: remove dead dex-weights.py (dash variant) — superseded by
  dex_weights.py (underscore), zero importers per CR-DEXJR-AUDIT-001
- `de29722` · chore: remove orphan bridge-fix-v4.1.py — references v4.1 that
  never shipped, zero importers per CR-DEXJR-AUDIT-001
- `fbdb188` · chore: remove council-governance-v4.1.py — superseded by inline
  GOVERNANCE in dex-council.py, zero importers per CR-DEXJR-AUDIT-001
- `661ed11` · chore: remove fetch_staas.py stub — only contained 'import
  requests', zero functional code per CR-DEXJR-AUDIT-001
- `b9eea15` · chore: consolidate clean_staas variants — kept fetch_clean_staas.py
  content as single source under canonical name clean_staas.py, removed
  clean_staas2.py and fetch_clean_staas.py per CR-DEXJR-AUDIT-001
- `71d9b0e` · chore: consolidate transcribe_mania to single canonical file —
  v3 (encoding+dedup+CUDA) renamed to transcribe_mania.py, v1 and v2 removed
  per CR-DEXJR-AUDIT-001

Nothing pushed. 6 commits ahead of origin/main.

### Flags / Corrections

**1. Discarded uncommitted change on dex-weights.py.** Git status showed
`dex-weights.py` as modified at session start. The unstaged change was a
cosmetic path-escape fix (`r"C:\Users\dkitc\.dex-jr\chromadb"` →
`r"C:\\Users\\dkitc\\.dex-jr\\chromadb"`) on a dead file with zero importers.
`git rm -f` discarded it along with the file. No functional loss — the same
path works in both forms as a raw string, and the file was being deleted
regardless. Flagging because Rule 6 requires surfacing any discard of working
changes.

**2. dex_weights.py (underscore, live) is still `M` in the working tree.**
Not touched this session. The operator has unrelated in-progress changes on
the live weighted-query module. Leaving alone.

**3. fetch_leila_gharani.py is still `M` in the working tree.** Not touched
this session. Unrelated in-progress changes.

**4. dex-bridge.py:4 has a docstring comment referencing the dash name.**
The comment `v1.1: Source weighting via dex-weights.py` references the now-
deleted dash variant, but the actual import on line 37 is
`from dex_weights import ...` (underscore — still correct). This is a
cosmetic inaccuracy in a comment, not a broken reference. No code change made;
flagging for operator to clean up during the next dex-bridge.py edit.

**5. Commits 5 and 6 (consolidations) do not show full line-level accounting
of removed variants.** clean_staas2.py, fetch_clean_staas.py, transcribe_mania
v1 and v2 were all untracked when the session started. Removing them from
disk produced no staged changes, so the git commits for those steps only
capture the surviving canonical file. From git's perspective the net
additions/deletions are small; from the working-tree perspective, ~214 lines
of untracked variant code were removed. Session log and the audit report
capture the full accounting below.

**6. Choice in step 5 (clean_staas).** The prompt said "identify which is
most complete / most recent, keep that one, rename to clean_staas.py". The
three candidates did different things:
- `clean_staas.py` (tracked): clean a pre-downloaded local file, basic regex only
- `clean_staas2.py` (untracked): clean a pre-downloaded local file, more
  thorough (unescape HTML entities, strip script/style tags)
- `fetch_clean_staas.py` (untracked): fetch from web + clean in one shot
  (self-contained; same thorough cleaning as clean_staas2)

Picked `fetch_clean_staas.py` as "most complete" because it's the only one
that doesn't require a pre-downloaded input file. Its content now lives under
the canonical name `clean_staas.py`. Flagging the judgment call because the
kept file's *behavior* is different from the original `clean_staas.py` —
if anything downstream assumes `clean_staas.py` just cleans an existing file,
it would break. No such dependency was found in the grep.

### Line Accounting (working-tree totals)

**Removed from the working tree:**
| File | Lines | Tracked? |
|---|---:|---|
| dex-weights.py | 292 | yes |
| bridge-fix-v4.1.py | 52 | yes |
| council-governance-v4.1.py | 59 | yes |
| fetch_staas.py | 1 | yes |
| clean_staas.py (original) | 12 | yes (replaced) |
| clean_staas2.py | 13 | no |
| fetch_clean_staas.py | 12 | no |
| transcribe_mania.py (v1) | 71 | no |
| transcribe_mania_v2.py | 89 | no |
| transcribe_mania_v3.py (promoted) | 88 | no (promoted to canonical) |
| **Total removed from disk** | **689** | |

**Kept under canonical names:**
| File | Lines |
|---|---:|
| clean_staas.py (new) | 12 |
| transcribe_mania.py (new) | 88 |
| **Total kept** | **100** |

**Net code reduction in working tree: 589 lines across 8 file removals.**

(Audit estimate was "~600 lines" — within 2%.)

### Open Items Carried Forward

From CR-DEXJR-AUDIT-001, still pending:

**Critical bugs (operator priority):**
1. `dex-convert.py` silent data loss at lines 252, 355, 360, 374, 419 —
   `except Exception:` blocks drop records during HTML/CSV/JSON/MBOX/VCF
   conversion with no counter or log. Operator does not know how many
   documents have been lost. Fix: add counter + flag-on-failure mode.
2. `dex-search-api.py` invisible to 5 of 7 collections — only queries
   `dex_canon` and `ddl_archive`. Missing `ext_canon`, `ext_archive`,
   `dex_code`, `ext_creator`, `ext_reference`. Surface-level fix.
3. Scoped+fast file-level skip broken at `dex-ingest.py:370-374`. When
   `--fast` is used with a scoped collection, file-level skip becomes a
   no-op and files are re-chunked/re-embedded every run (upsert prevents
   true duplicates but work is wasted). Fix: file-hash → chunk-id-prefix
   cache in collection metadata.

**Refactor targets (in order of leverage):**
1. Build `dex_core` package (`get_chroma_client`, `get_embedding`,
   `get_ollama_client`, `load_config`, `get_logger`). Eliminates 14 ChromaDB
   connection sites, 8 duplicate embedding functions, 5 logging setups,
   dual-protocol Ollama inconsistency.
2. Migrate one entry point at a time to `dex_core`, starting with
   `dex-query.py` (125 lines, two ChromaDB clients per run, smallest test case).
3. Add `ingested_at` and `source_type` metadata fields to all chunks at
   ingest time. Backfill existing chunks.
4. Build `dex health` command that validates each entry point's view of
   collections, models, paths, config.
5. Build query router as single source for retrieval logic. Absorbs
   `dex_weights.py` scoring as a layer. Reads collection list from ADR-CORPUS-001.

**Known dead-but-not-yet-deleted (after approval):**
- 22 lines of commented-out cloud model dict entries in `dex-council.py:82-103`
  (DeepSeek, Grok, Groq with "uncomment when credits/payment added"). Move to
  `DISABLED_MODELS` list or delete outright.
- `dex-bridge.py:61` has `OLLAMA_CHAT_URL` and `OLLAMA_CHAT_URL_LAPTOP` —
  verify dual-machine support is still needed.
- `dex-bridge.py:4` — cosmetic docstring comment still references `dex-weights.py`
  (dash name, now deleted). Fix during next edit to that file.

**Audit scripts (status unchanged):**
- `audit_archive.py` and `audit_missing_only.py` still untracked. Decide:
  commit, gitignore, or delete after retool.

**Magic numbers still needing config:**
`CHUNK_SIZE_TOKENS=500`, `CHUNK_OVERLAP_TOKENS=50`, `MAX_TEXT_CHARS_NORMAL=5_000_000`,
`MAX_CONTEXT_CHARS=6000`, `TOP_K=5`, `QUALITY_AUTO_INGEST=7`, `QUALITY_FLAG=5`.

**Session-local carry-forward:**
- 6 local commits ahead of `origin/main`, not pushed. Operator to decide when
  to push per Rule 4.
- `dex_weights.py` (underscore, live) and `fetch_leila_gharani.py` both still
  show uncommitted modifications from before this session — untouched, operator's
  in-progress work.

---

## Session — 2026-04-11 afternoon/evening (Phase 2 Steps 9–17, airtight pipeline build + first production ingest)

### Session metadata

- **Date:** 2026-04-11
- **Duration:** ~14:30 to ~03:15 next day local (approximate — ~12.5 hours of active work with gaps)
- **Operator:** Dave Kitchens
- **Advisor seat:** Marcus Caldwell 1002 (Claude in app)
- **Executor:** CC (Claude Code in dex-rag)
- **Standing rules:** CLAUDE.md v2 (ratified morning of 2026-04-11 per CR-DEXJR-AUDIT-001)
- **Entry point:** CR-DEXJR-DDLING-001 DDL_Ingest audit → ADR-INGEST-PIPELINE-001 ratification → airtight pipeline build (Steps 1–17)
- **Outcome:** Full airtight ingest pipeline built, production-validated with 11,921 chunks across 35 files in `dex_canon`, zero errors, zero silent skips

### Prior commits in same day (context, not covered in detail here)

Between the morning quick-win deletions and Step 9, the afternoon/evening session also shipped:

| SHA | Description |
|---|---|
| `0e4707b` | chore: ratify dex-rag CLAUDE.md v2 per CR-DEXJR-AUDIT-001 (F-Code system, report templates, Rule 17, Open Items) |
| `a6a23f4` | chore: CLAUDE.md cosmetic fixes (H1 header, trim paste content) |
| `01d5064` | chore: add audit_ddl_ingest_xref.py — corpus cross-reference tool from CR-DEXJR-DDLING-001 |
| `04433ae` | chore: ratify ADR-INGEST-PIPELINE-001 (three-stage pipeline, provenance metadata, sweep reports as corpus) |
| `6706a29` | chore: CLAUDE.md Rules 8 + 16 reflect 4 live collections, pending resolution in ADR-INGEST-PIPELINE-001 |
| `3f1aa9f` | chore: cosmetic cleanup — strip ADR paste-fence + align CLAUDE.md repo context |
| `7455ec2` | chore: ratify STD-DDL-METADATA-001 (7 mandatory fields, 16 source_type enum, inference rules) |
| `b35961a` | chore: add dex_pipeline.py — build_chunk_metadata() + verify_ingest() helpers (Phase 1 Step 3) |
| `a574c31` | chore: dex_pipeline.py — add move_to_staging() (Phase 1 Step 4) |
| `63aed4d` | chore: add dex-ingest-text.py — first end-to-end caller (Phase 2 Step 5 proof of life) |
| `56f47dc` | chore: ratify STD-DDL-BACKUP-001 (5 triggers, hot-copy, rolling rotation, manifest schema) |
| `fe79ae9` | chore: add dex-backup.py — implements STD-DDL-BACKUP-001 (Phase 2 Step 7) |

12 commits of Phase 1 + early Phase 2 work shipped between morning and Step 9. **The session log coverage here (Steps 9–17) is the second half of the day's Phase 2 work.** Step 6 (first real live ingest to `dex_canon` of `DDLCouncilReview_CorpusGuess.txt`) and Step 8 (first real backup — anchor `chromadb_2026-04-11_2226`) produced no commits; they were runs, not code changes.

### Phase 2 Steps 9–17 narrative

#### Step 9 — `ensure_backup_current()` pre-flight gate (`8582509`)

Implemented Trigger 3 of STD-DDL-BACKUP-001. Built the in-pipeline gate that calls `dex-backup.py` as a subprocess to check trigger state and force a backup when needed. Wired into `dex-ingest-text.py:ingest_text_file()` immediately after chunking and before metadata build, so backup failures abort the ingest before any embedding work happens.

- Added `ensure_backup_current(expected_write_chunks, force_check, dry_run)` to `dex_pipeline.py`
- Added `BackupNotFoundError` and `BackupFailedError` exceptions
- Added `--json` flag to `dex-backup.py --check-only`, plus a new lightweight `build_check_status()` helper that checks existence + sqlite readability + trigger state **without** calling `validate_backup()` (which compares against live state and would fail on any drift). This split means the human `--check-only` path stays thorough while the machine `--check-only --json` path stays fast and drift-safe.
- Banner suppression in JSON mode (so `json.loads()` on stdout works)
- Self-tests grew 7 → 10 (happy path + force_check + large-write Trigger 5)
- Smoke-tested end-to-end against `dex_test` collection, dropped after

#### Step 10 — Restore test + Trigger 6 (`4351ebe`)

Added `restore_test()` to `dex-backup.py`: copies a backup to a scratch path, opens it as a fresh ChromaDB `PersistentClient`, enumerates collections, counts each, compares to manifest. Any mismatch raises `RestoreTestFailedError`. Wired into `perform_backup()` as automatic Trigger 6 post-validation.

- `--restore-test` standalone CLI flag
- `--skip-restore-test` bypass flag
- **First-ever restore test of anchor `chromadb_2026-04-11_2226`: PASS**
  - `ddl_archive`: 291,520 ✓, `dex_canon`: 230,088 ✓, `dex_code`: 20,384 ✓, `ext_creator`: 922 ✓
  - Duration: 15.9s
  - Anchor `chroma.sqlite3` SHA256 verified byte-identical post-test
- **Known issue surfaced:** Windows HNSW `data_level0.bin` mmap remains locked after `del client` + `gc.collect()`. In-process cleanup fails; scratch dir becomes an orphan on C:. Manually reclaimed the first orphan from a fresh shell after the Python subprocess exited. Fixed in Step 11.

Trigger 6 not yet in STD-DDL-BACKUP-001 — parked for amendment.

#### Step 11 — Scratch cleanup sweep + `validate_backup` drift tolerance (`ad6a419`)

Two corrective fixes from Step 10's findings:

**A.** Added `cleanup_stale_scratch(max_age_hours=1.0)` at the top of `dex-backup.py:main()`. Reclaims any `restore_test_*` dirs older than 1 hour from `dex-rag-scratch/`. Runs at the start of every non-JSON `dex-backup.py` invocation. Tolerates file locks (WARN + continue).

**B.** Modified `validate_backup()` UUID comparison:
- **NEW fatal check:** `dst_uuids - src_uuids` (UUIDs in backup but missing from live → data loss signal)
- **DOWNGRADED:** `src_uuids - dst_uuids` (UUIDs in live not in backup → orphan segments from dropped test collections) now emits a WARN and does NOT fail validation
- `--check-only` (human path) now reliable in drift. Confirmed: reports VALID with WARN line for the `af065713-...` orphan from Step 9's `dex_test` cycle.
- `--check-only --json` (machine path) unchanged — still clean JSON.

#### Step 12 — Airtight perimeter audit (`af6b89c`)

AUDIT ONLY, no code changes. Full static analysis of every `.py` file in the repo for ChromaDB write/read surfaces. Filtered ripgrep noise (Python set/dict/hashlib method collisions with Chroma method signatures) via explicit file list. Identified **4 write surfaces** across 4 files, of which **exactly 1** (`dex-ingest-text.py` from Step 5 + Step 9 wiring) was gated.

**Surprise findings:**
1. **`dex-sweep.py` is a transitive writer** — subprocess-invokes `dex-ingest.py` at line 141. Biggest perimeter hole. CLAUDE.md Rule 13 calls it "live infrastructure" running at 3am.
2. **`dex-acquire.py:41` has a hardcoded CHROMA_PATH typo** — missing backslash between `dkitc` and `.dex-jr`. Either a shadow corpus exists or the script has been silently failing since its initial commit.
3. **`dex-ingest.py --reset` silently deletes both `ddl_archive` and `dex_canon`** via bare `except Exception: pass` at lines 252-255 (Rule 15 violation).

Full report: `AUDITS/STEP12_AIRTIGHT_PERIMETER_AUDIT_2026-04-11.md` (282 lines).

Classified Step 13+ sequence: investigate acquire typo → wire dex-ingest.py → wire dex-sweep.py → fix+wire acquire.

#### Step 13 — `dex-acquire.py` path typo investigation (`89a66c2`)

INVESTIGATION ONLY. Determined whether `C:\Users\dkitc.dex-jr\chromadb` exists and whether it contains a shadow corpus.

**Finding: SCRIPT_DEAD.** The literal typo path exists as a 184 KB Chroma-initialized empty DB (18 schema migrations applied, 0 collections, 0 embeddings, 0 segments). Created 2026-03-23 06:16:04, never touched since. `dex-acquire.py` was run **once** on that date, opened a `PersistentClient` (creating the DB file + running migrations), failed somewhere before any `get_or_create_collection()` call, and has not run successfully since. **No data was lost** — there was never any data to lose.

Git blame: typo has been in the file since **initial commit `0fa80e2` on 2026-03-14**, not a recent regression. Isolated to `dex-acquire.py`; `dex_weights.py:21`, `dex-ingest.py:40`, `dex-backup.py:33` all use the correct path.

Read-only throughout: opened the shadow `chroma.sqlite3` via `sqlite3.connect("file:...?mode=ro", uri=True)`. No `chromadb.PersistentClient` was ever instantiated against the typo path. Anchor backup untouched.

Classification for future Step 16: **NEEDS_FIX_THEN_WIRE**. Full report: `AUDITS/STEP13_DEX_ACQUIRE_INVESTIGATION_2026-04-11.md` (179 lines).

#### Step 14 — `dex-ingest.py` airtight wire (`3a9859b`)

Biggest code lift of the night. Wired `dex-ingest.py` (562 → 689 lines) for STD-DDL-METADATA-001 + STD-DDL-BACKUP-001 compliance by parity with `dex-ingest-text.py`.

**Plan-first pattern:** Phase 1 of the step emitted a full plan to stdout with call-site inventory, metadata schema analysis, failure mode assessment, and open questions. Operator reviewed and approved with 6 confirmations + 1 new requirement (`.reset_log` forensic audit file). Phase 2 executed the approved plan.

Key decisions:

- **`BULK_CHUNK_ESTIMATE = 10_000`** as a module constant. Any value >100 fires Trigger 5 unconditionally. Means every ungated `dex-ingest.py` call refreshes the backup. Aggressive safety; by design.
- **`--skip-backup-check` CLI flag** — for `dex-sweep.py` in Step 15 to pass when gate has been handled upstream.
- **Metadata additive strategy** — all existing legacy fields preserved. New STD 7 fields merged via `md.update(std_md)`. Legacy `source_file` (rel_path) renamed to `rel_path`. Legacy `total_chunks` **dropped** after repo grep confirmed zero metadata readers.
- **`infer_source_type()`** helper: extension-first → code/spreadsheet/web_archive; filename-prefix override for text files → council_review/council_synthesis/governance/system_telemetry; fallback → `unknown`.
- **Rule 15 fix on `--reset`**: captures `pre_drop_counts` before deletion, explicit per-collection drop logging, appends one JSON line to `.reset_log` at repo root with `dropped`, `drop_failures`, `pre_drop_counts`, `ingest_run_id`. `append_reset_log()` is non-blocking (stderr WARN on failure).

Self-tests: 3 smoke tests — `--help` parses with new flag, `--skip-backup-check` path writes 3 chunks to `dex_test`, gate-fires path (**triggered an actual backup** — first visible demonstration of the BULK_CHUNK_ESTIMATE cascade effect). All 3 pass. `dex_test` dropped after.

+134/-7 lines.

#### Step 15 — `dex-sweep.py` airtight wire (`7db2098`)

Same plan-first pattern. Smaller code surface than Step 14 but higher operational importance — `dex-sweep.py` runs unattended and is the transitive parent of `dex-ingest.py` at 3am.

- Single `ensure_backup_current()` call at `sweep()` start, after scan but before copy, **skipped in `--dry-run` mode** (dry-run is read-only)
- `--skip-backup-check` added to `dex-ingest.py` subprocess invocation — prevents cascade backups within a single sweep run
- **Rule 15 fix**: bare `except: pass` on `log_sweep()` write → now WARN to stderr, non-blocking
- **Rule 15 fix**: silent drop-folder-not-found skip → now prints `WARN: drop folder not found (skipping): {path}`
- `log_sweep()` signature expanded from 3 fields to 13: adds `start_ts`, `end_ts`, `backup_ran`, `backup_path`, `error`, `recovery_hint`, `subprocess_stderr`, `dry_run`. Old-reader tolerance via `None` defaults.
- **`recovery_hint` pattern**: `BackupNotFoundError` → `"python dex-backup.py --force"`; `BackupFailedError` → `"python dex-backup.py --check-only"`; other exceptions → `"inspect traceback, fix underlying issue, rerun"`. Makes 3am logs self-documenting.
- **`try/except/finally` wrap** around sweep body guarantees a log entry even on crash
- `run_ingestion()` return signature changed `bool` → `tuple[bool, str | None]` to capture subprocess stderr on failure

**Surprise during self-test:** pre-existing `dex-sweep-log.jsonl` had **47 entries**, two most recent at `2026-04-10T04:00:01.497911` and `2026-04-11T04:00:01.498486` — same second on two consecutive days. This **contradicts** the operator's claim in the Phase 1 plan approval (*"3am schedule: NOT currently wired anywhere. Sweep has never run unattended."*). A scheduled daily task IS running somewhere (Windows Task Scheduler or similar), but it's been logging `files_found: 0` every day — likely a context mismatch where the scheduled runner can't see the drop folders. Step 15's Rule 15 fix would have surfaced this immediately if the folders were truly missing. **Flagged as an unresolved investigation.**

Layer 1 self-test (4 checks): all pass. Layer 2 (real end-to-end run against a live drop folder) deferred to operator manual run per Rule 5.

+155/-51 lines.

#### Step 16 — Holding folder + `dex_canon` content audit (`ce56778`)

AUDIT ONLY. Staged for Step 17's production ingest. Walked the holding folder `DDL_Ingest_step16_batch_2026-04-11`, built a full inventory, pulled full metadata from both live collections via batched pagination, built a local set intersection for cross-reference.

**Findings:**

- **Holding folder: 1,026 files / 13.46 GB** — essentially all of Phase 1 DDL_Ingest relocated wholesale.
- **`dex_canon` is 99.997% legacy**: 230,088 chunks, 6 STD-compliant (from Step 6 proof-of-life), 1 distinct `ingest_run_id` (`manual_2026-04-11_2127`).
- **`ddl_archive` is 100% legacy**: 291,520 chunks, 0 STD. The airtight pipeline has never written to `ddl_archive` end-to-end.
- **Only 26 files truly fresh** (<24h mtime), all from today's morning 11:10am–12:35pm working session. **Not the 133 operator estimated** — the 133 number matches top-level loose file count, not fresh count.
- **24 of 26 fresh files net-new** (not in either corpus). The other 2 (`28_CognitiveArchitecture.txt`, `78_AuditForgePM.txt`) exist in corpus by filename but were edited today (likely content changed too).
- **607 holding files already in some collection** by filename match; **419 net-new** (152 ingestible, 267 not).
- **`_hold/` is 100% net-new** (96 files blocked on `dex-convert.py` silent-drop fix).
- **Mania subdirectory (176 files) under-counted by sensitive pattern** — entire subfolder sensitive by location, not filename.

Three ingest-scope options proposed for Step 17; Option C (`--collection dex_canon`) recommended.

Full report: `AUDITS/STEP16_HOLDING_FOLDER_CONTENT_AUDIT_2026-04-11.md` (370 lines).

Batched metadata pull across both collections (~521K chunks total) via 27 batches of 20,000 each: ~90 seconds wall time. No per-file queries.

#### Step 17 — First real airtight production ingest (NO COMMIT, runs only)

The full chain test against real operator-authored content. Pre-flight caught a **critical design issue** with `--build-canon` before any writes happened (see F-Code section below). Operator approved Option C (`--collection dex_canon`) with expanded scope including the 2 fresh-but-in-corpus upserts → **35 files total**.

**Run 1 — Holding folder (26 files):**
- `ingest_run_id`: **`manual_2026-04-12_024723`**
- Backup gate fired → refreshed anchor to `chromadb_2026-04-12_0247`
- **10,483 chunks written to `dex_canon`** via scoped path (0 to `ddl_archive`, 0 errors)
- Duration: 798s (13.3 min)
- Top outlier: `28_CognitiveArchitecture.txt` → 2,461 chunks (the 4 MB file)

**Run 2 — DirectIngest (9 files from `C:\Users\dkitc\iCloudDrive\Documents\05_DirectIngest\`):**
- `ingest_run_id`: **`manual_2026-04-12_030843`**
- Backup gate fired → refreshed anchor to `chromadb_2026-04-12_0308`
- **1,438 chunks written to `dex_canon`**, 0 errors
- Duration: 142s (2.4 min)

**Post-ingest totals (verified):**
- `dex_canon`: 230,088 → **242,009** (+11,921, math checks)
- `ddl_archive`: 291,520 (unchanged, scoped mode correctly bypassed)
- Distinct `ingest_run_id`s in `dex_canon`: **3** (Step 6 + Run 1 + Run 2)

**Spot-checks (all PASS):**
- `DDLCouncilReview_Mithril.txt` → `source_type: council_review` ✓
- `F Code Convo.txt` → `source_type: unknown` (fallback fired correctly) ✓
- `F2 Electric Boogaloo.txt` → Run 2 `ingest_run_id` ✓

All 7 STD-DDL-METADATA-001 fields present on every chunk. Legacy fields preserved alongside. Full STD compliance.

**First real session where the airtight pipeline ran end-to-end against real content.** Two cascade backups proved Rule 8 self-enforcement works as designed. Two Trigger-6 orphan scratch dirs created on C: (Windows mmap issue), both **manually reclaimed** after the respective subprocesses exited.

### Commits (hash · message)

| SHA | Step | Summary |
|---|---|---|
| `8582509` | 9 | Phase 2 Step 9: ensure_backup_current() pre-flight gate |
| `4351ebe` | 10 | Phase 2 Step 10: restore test + Trigger 6 |
| `ad6a419` | 11 | Phase 2 Step 11: scratch cleanup sweep + validate_backup drift tolerance |
| `af6b89c` | 12 | Phase 2 Step 12: airtight perimeter audit |
| `89a66c2` | 13 | Phase 2 Step 13: dex-acquire.py path typo investigation |
| `3a9859b` | 14 | Phase 2 Step 14: dex-ingest.py airtight wire |
| `7db2098` | 15 | Phase 2 Step 15: dex-sweep.py airtight wire |
| `ce56778` | 16 | Phase 2 Step 16: holding folder + dex_canon content audit |
| *(none)* | 17 | First real production ingest — 35 files, 11,921 chunks, 0 errors |

**8 commits for Steps 9–16. Step 17 produced no commits (ingest runs, not code changes). Total session delta from Step 9 through 17: 8 commits.** Including the early-evening Phase 1 + Step 5/7 work and this session log's commit, the day's total is ~21 commits.

### Artifacts created tonight (Steps 9–17)

**Governance / standards:**
- (none new — STD-DDL-METADATA-001 + STD-DDL-BACKUP-001 ratified earlier in the day, Steps 2 and 6)

**Audit reports (3):**
- `AUDITS/STEP12_AIRTIGHT_PERIMETER_AUDIT_2026-04-11.md` (282 lines)
- `AUDITS/STEP13_DEX_ACQUIRE_INVESTIGATION_2026-04-11.md` (179 lines)
- `AUDITS/STEP16_HOLDING_FOLDER_CONTENT_AUDIT_2026-04-11.md` (370 lines)

**Code (modified in Steps 9–17):**
- `dex_pipeline.py` — added `ensure_backup_current()`, `BackupNotFoundError`, `BackupFailedError`, 3 new self-tests (Step 9)
- `dex-backup.py` — added `build_check_status()`, `--json`, `restore_test()`, `RestoreTestFailedError`, `--restore-test`, `--skip-restore-test`, Trigger 6 auto-wire, `cleanup_stale_scratch()`, `validate_backup()` drift tolerance (Steps 9, 10, 11)
- `dex-ingest-text.py` — wired `ensure_backup_current()` (Step 9)
- `dex-ingest.py` — airtight wire: gate + metadata + infer_source_type + Rule 15 fix on --reset + `.reset_log` forensic audit (Step 14)
- `dex-sweep.py` — airtight wire: upstream gate + subprocess `--skip-backup-check` + Rule 15 fixes + try/finally + recovery_hint (Step 15)

**Corpus writes:**
- `dex_canon`: +11,921 chunks (Step 17 Runs 1 + 2)
- `ddl_archive`: unchanged
- Distinct new `ingest_run_id` values: 2

**Backups created:**
- `chromadb_2026-04-12_0247` (Step 17 Run 1 Trigger 5 cascade)
- `chromadb_2026-04-12_0308` (Step 17 Run 2 Trigger 5 cascade)
- Retention: 2 new + prior anchor from earlier today = 4 total backups on `D:\DDL_Backup\chromadb_backups\`, all within 7-daily retention window. ~44 GB disk use.

### F-Code events

- **Step 10 Trigger-6 orphan scratch** — self-caught the Windows mmap issue mid-test. Not an F-Code throw (operator didn't throw), self-surfaced via the scratch cleanup warning. Step 11 was the corrective fix.

- **Step 14 `BULK_CHUNK_ESTIMATE` design decision cascade** — flagged in plan-phase that the aggressive Trigger 5 firing would cause every ungated `dex-ingest.py` call to refresh the backup, including one-chunk test runs. Operator approved as "aggressive safety by design." Not an F-Code throw. Made Step 15 mission-critical (without it, every sweep cascades N backups).

- **Step 15 scheduled-task surprise** — during self-test, discovered pre-existing `dex-sweep-log.jsonl` had 47 entries including a daily 04:00:01 UTC pattern. This contradicted the operator's stated understanding. Flagged prominently in the status report. Not an F-Code, but a mental-model mismatch to resolve before Step 16/17 unattended runs.

- **Step 16 "133 fresh files from iCloud" mental-model mismatch** — audit found only 26 truly fresh files, not 133. The 133 number matched top-level loose file count. Not a misunderstanding on CC's side — CC surfaced the discrepancy cleanly. No F-Code thrown.

- **🛑 Step 17 pre-flight halt** — **this is the big catch of the night.** CC ran a tier-prediction pre-flight on the operator's literal `--build-canon` command and discovered that `dex-ingest.py`'s `classify_tier()` substring-matching would have silently skipped **26 of 33 target files** (non-council-review files tier=unknown → `store_to_raw=False, store_to_canon=False, store_to_scoped=False` → `continue`). This is exactly the Rule 15 silent-skip pattern the airtight pipeline was built to fight. **CC stopped execution before touching anything**, emitted a full flag with per-file predictions and 3 alternative options, and waited for operator approval. Operator approved Option C (`--collection dex_canon`, bypass tier filter). No data lost, no silent skips. This is the Platinum Rule in action: do unto the operator as the operator would have done unto themselves.

- **Step 17 Run 1 stale `ScheduleWakeup` self-catch** — mid-Run-1, CC inappropriately called `ScheduleWakeup` to pace the monitoring, realized it was a wrong-tool-for-the-context mistake (`ScheduleWakeup` is for `/loop` dynamic mode, not subprocess monitoring), and self-corrected: "ScheduleWakeup isn't appropriate here — I'm not in a /loop context. Just checking output directly and waiting for the task-completion notification." The wakeup later fired after Step 17 completed; CC recognized it as a stale self-trigger, confirmed Step 17 was already done, and did not schedule another. **No F-Code thrown** — clean self-catch and Platinum Bounce back to normal operation.

### Running list updates (new parked items from Steps 9–17)

**Newly parked (not previously in CLAUDE.md Open Items):**

1. **`classify_tier()` substring brittleness** (Steps 14, 17 pre-flight): the CANON/FOUNDATION/ARCHIVE markers use naive substring matching. `"thread"` matches `ThreadSaved_4.11.txt` incorrectly (classified as archive). `"protocol"` could match any file with "protocol" in the name. Needs word-boundary or anchored matching. Deferred.

2. **`dex-ingest.py --build-canon` silent-skip Rule 15 violation** (Step 17 pre-flight): the `--build-canon` code path filters files by tier and silently drops any with `tier="unknown"`. The Step 17 pre-flight demonstrated this would have skipped 26 of 33 target files. Not fixed tonight — the workaround was Option C (`--collection dex_canon`). Needs a dedicated Step to fix properly.

3. **The 4am scheduled `dex-sweep.py` task** (Step 15 finding): 47 pre-existing log entries show daily 04:00:01 UTC runs. Mechanism unknown (not in repo). Every entry says `files_found: 0`. Likely context-mismatch issue where the scheduled runner can't see the drop folders. Needs Task Scheduler investigation.

4. **Two pre-existing bugs in `dex-sweep.py`** (Step 15 flagged, deferred):
   - Files moved to `_processed/` BEFORE ingest success — on subprocess failure, files are stranded and will not be re-attempted next run
   - `--fast` + `--build-canon` combination inherits the scoped+fast bug from CLAUDE.md Open Items #3

5. **Orphan Chroma segment directories in live** (Steps 9, 10): Windows + Chroma leaves HNSW segment dirs on disk when collections are dropped. `f4df1db7-...` from Step 5, `af065713-...` from Step 9 smoke tests. Not urgent; show up as WARN lines in `validate_backup()` but don't fail validation. Eventually needs a GC pass cross-referencing live UUID dirs against the SQLite `segments` table.

6. **Trigger 6 Windows HNSW mmap lock** (Step 10, partially fixed in Step 11): `restore_test()` in-process cleanup fails because Chroma's HNSW `data_level0.bin` mmap persists after `del client` + `gc.collect()`. Step 11's `cleanup_stale_scratch()` reclaims orphans on next backup run >1h later. Manual cleanup also works once the Python subprocess exits. Tonight 2 Trigger-6 orphans were created during Step 17 cascade backups; both manually reclaimed.

7. **STD-DDL-BACKUP-001 Trigger 6 amendment** (Step 10, deferred): the standard still lists 5 triggers; code implements 6. Needs Marcus-authored amendment.

8. **Paste-fence residue on STD-DDL-BACKUP-001** (Step 7, deferred): same `\`\`\`markdown ... \`\`\`` artifact as the ADR. Single-commit cosmetic fix pending operator OK.

**Already tracked from prior sessions:**
- `dex-convert.py` silent-drop bug (blocks PDF/XLSX/HTML/MBOX ingest)
- `dex-search-api.py` 5-of-7 collection blind spot
- `dex-ingest.py` scoped+fast file-level skip (unaddressed)
- dex_core package refactor
- Backfill operation for ~230K legacy chunks in `dex_canon` + 291K in `ddl_archive`
- Mania/ subfolder governance decision (176 sensitive-by-location files)
- Gmail MBOX (6.4 GB) ingest decision
- `_hold/` processing (blocked on dex-convert.py fix)

### Unresolved decisions pending future sessions

1. **Push to origin?** 21 commits ahead of `origin/main` as of Step 17 (before this session log). Operator to decide per Rule 4.
2. **Scheduled task investigation** — where is the 04:00:01 UTC sweep actually wired? Task Scheduler? cron-like service? Until resolved, Step 15's wiring is code-airtight but not activation-audited.
3. **Remaining 127 net-new older files in holding folder** — Step 16 identified 152 net-new ingestible files; Step 17 ingested the 24 fresh+net-new. The remaining ~128 (older mtimes but still net-new) await a triage + ingest pass.
4. **Mania/ subfolder governance** — 176 voice-memo files, sensitive by location, not yet ingested. Needs explicit decision on (a) whether voice memos enter the corpus at all, (b) what collection they live in, (c) retention/access policy.
5. **Gmail MBOX** — 6.4 GB, blocked on `dex-convert.py` silent-drop fix. Also needs collection + retention decision.
6. **Backfill strategy for 230K+ legacy chunks in dex_canon** — STD-DDL-METADATA-001 §"Backfill operation" defines the rules. Tonight's 11,921 new STD chunks are only 4.9% of the post-Step-17 dex_canon. The remaining ~95% are pre-STD legacy. A dedicated backfill session is needed eventually.

### Session-local carry-forward

- **21 local commits ahead of `origin/main`** (12 from Phase 1 + early Phase 2 + 8 from Steps 9–16 + this log's commit). Not pushed.
- **`dex_weights.py` and `fetch_leila_gharani.py`** still show unstaged modifications from before the session. **Rule 17 respected throughout** — verified before every commit via `git status --short`.
- **`dex-rag-scratch/`** is empty (no orphans carried forward from Step 17).
- **Current backup anchor:** `chromadb_2026-04-12_0308` (~3 hours old at time of this log).
- **Current corpus state:** `dex_canon` 242,009, `ddl_archive` 291,520, `dex_code` 20,384, `ext_creator` 922. Total: **554,835 chunks**, up from 542,908 at session start.
- **3 distinct `ingest_run_id` values** in `dex_canon` — the only STD-compliant provenance in the entire corpus as of now.

---

## Session — 2026-04-11 late-night to 2026-04-12 early-morning (Phase 2 Steps 18–22, scheduler activation, STD-DDL-SWEEPREPORT-001 v1.0, and the drop-and-forget primitive)

### Session metadata

- **Date span:** 2026-04-11 ~22:30 through 2026-04-12 ~02:45 local (CDT)
- **Operator:** Dave Kitchens
- **Advisor seat:** Marcus Caldwell 1002 (Claude in app; continuation from afternoon session after context compaction in both CC and Marcus threads)
- **Executor:** CC (Claude Code in dex-rag)
- **Standing rules:** CLAUDE.md v2 + all STDs and ADRs ratified during the 04-11 afternoon/evening session
- **Entry point:** session log for Steps 9-17 → mystery scheduler investigation → CANON_DIR forensic → scheduler activation → end-to-end sweep verification
- **Outcome:** DexSweep-NightlyIngest Task Scheduler entry deployed and production-verified. Self-documenting sweep loop proven. 24 files queued for first unattended 4:00 AM run. **The drop-and-forget primitive is live.**

### Commits (this session segment)

| SHA | Step | Description |
|---|---|---|
| `4861ab1` | 18 | Phase 2 Step 18: session log for Steps 9–17 (487 lines covering the full airtight pipeline build) |
| `9221a67` | 19 | Phase 2 Step 19: mystery scheduler investigation — finding: PERSISTENT_WATCH_PROCESS (dead) |
| `c4742b3` | 20 | Phase 2 Step 20: CANON_DIR stranding forensic — 5,803 files, 1,869 stranded, 1,767 recoverable |
| `0a30e0e` | 21+22 | Phase 2 Step 22: temp-dir-per-sweep (Fix A) — includes Step 21's STD-DDL-SWEEPREPORT-001 implementation, Task Scheduler registration, classification predicate, report writer, AND the Fix A temp-dir pattern + Unicode encoding fix. Single commit because Step 21's dex-sweep.py changes were uncommitted when Step 22 applied the Fix A correction. |

**4 commits for Steps 18–22.** Step 17 (production ingest, 11,921 chunks) and Step 21's Task Scheduler runs produced no commits — they were execution-only steps verified by post-run queries.

**Total session commits today (both segments): 25+ ahead of origin/main.** Not pushed.

### Phase 2 Steps 18–22 narrative

#### Step 18 — Session log for Steps 9–17 (`4861ab1`)

Wrote the Rule 7 session log covering the afternoon/evening's Phase 2 build. 296 new lines appended to the existing 191-line morning session log, for a total of 487 lines. Created `DDL_SessionLogs/dex-rag_sessionlog_4.11.2026.md` inside the repo as a git-tracked artifact (parallel to the Rule 7 canonical location at `~\DDL_SessionLogs\`). Flagged the path-ambiguity between in-repo and external locations for future Rule 7 resolution.

#### Step 19 — Mystery scheduler investigation (`9221a67`)

Forensic investigation into the 47 pre-existing `dex-sweep-log.jsonl` entries that showed daily 04:00:01 UTC runs despite the operator's belief that "sweep has never run unattended."

**Finding: PERSISTENT_WATCH_PROCESS (dead).** The daily entries were from `dex-sweep.py --watch --interval 1440` started manually by the operator around 2026-03-15. NOT from Windows Task Scheduler (281 tasks scanned, zero match). The process died at some point and was no longer running.

**Critical additional finding from the full 48-entry log analysis:**
- 12 entries had `files_found > 0`; only 2 had `ingestion_success: true` (both manual morning runs)
- **Every automated nightly run that found files FAILED** the dex-ingest.py subprocess (10 of 10). Root cause: `--build-canon` tier-filter silent-skip + likely Ollama not responding at 4am in the old --watch-process context.
- The March 16 mega-sweep (169 files found, copied, ingest failed) was the largest documented stranding event.
- 04:00:01 vs 04:10:01 timestamp split explained by `copy_to_corpus` latency: the log timestamps are sweep-END time, not sweep-START time.

Full report: `AUDITS/STEP19_MYSTERY_SCHEDULER_INVESTIGATION_2026-04-11.md` (181 lines).

#### Step 20 — CANON_DIR stranding forensic (`c4742b3`)

Deep forensic of `C:\Users\dexjr\99_DexUniverseArchive\00_Archive\DDL-Standards-Canon` — the archival directory that `dex-ingest.py --path` reads from. Full filesystem walk + batched metadata pull from both dex_canon and ddl_archive (521K chunks) + local set intersection for cross-reference.

**Finding:** CANON_DIR is a **5,803-file corpus staging area** spanning 11 months (May 2025 – April 2026). **1,869 files (32.2%) are stranded** — present on disk but never ingested into dex_canon. Recovery pool: **1,767 files** after excluding 80 zero-byte, 11 too-small, and 11 non-ingestible-extension files. **Zero data loss** — all files are on disk. The problem is un-ingested content, not missing content.

- **Largest stranding event:** 1,438 files on 2026-03-23 (likely a bulk `--build-canon` run where the tier filter silently skipped most files)
- **March 16 sweep forensic:** 169 files copied, 143 of 169 still stranded, 26 already ingested via earlier pipeline, 0 lost
- **235 files confirmed dual-stranded:** copy in CANON_DIR + original in `_processed/` (the complete file-stranding loop documented)

Full report: `AUDITS/STEP20_CANON_DIR_STRANDING_FORENSIC_2026-04-11.md` (241 lines).

#### Step 21 — Scheduler activation + STD-DDL-SWEEPREPORT-001 v1.0 implementation (code committed in `0a30e0e`)

Built and deployed the nightly automated sweep infrastructure. This was the largest build step of the late-night session.

**Pre-flight findings:**
- **Ollama: RUNNING_AND_AUTOSTARTS** — PID 33472, auto-starts via `Ollama.lnk` in dkitc's startup folder, `nomic-embed-text:latest` loaded, API responsive at 02:00 AM
- All 4 drop folders reachable
- Created `DDL_Ingest/_sweep_reports/` directory

**Code built in dex-sweep.py:**
- `classify_scanned_files()` — classification predicate per STD-DDL-SWEEPREPORT-001: file is an ingest report IFF parent=`_sweep_reports` AND prefix=`ingest_report_` AND ext=`.md`
- Decision logic: report-only (Case B) → skip; empty → skip; user files present → standard flow
- `write_sweep_report()` — full markdown report generator with YAML header, 8 sections, pipeline state via ChromaDB read, previous-report reference
- `find_previous_report()` — locates most recent report in `_sweep_reports/`
- `--collection dex_canon` instead of `--build-canon` (Step 17 learning applied)
- `PYTHONIOENCODING=utf-8` in subprocess env (Windows cp1252 safety)
- Log schema expanded: `outcome`, `report_written`, `report_write_error` fields
- `--self-test` flag with 7 classification predicate tests
- `_sweep_reports/` added to DROP_FOLDERS for self-documenting-loop ingestion

**Task Scheduler registration:**
- Task: `DexSweep-NightlyIngest`
- Trigger: Daily at 4:00 AM local
- Run as: `REBORN\dkitc` (Interactive, Limited)
- Settings: WakeToRun, AllowStartIfOnBatteries, StartWhenAvailable, RestartCount 3
- Working directory: `C:\Users\dexjr\dex-rag`
- Python: `C:\Users\dkitc\AppData\Local\Programs\Python\Python312\python.exe`

**Three manual trigger runs:**

| Run | Time | Outcome | Root cause | What we learned |
|---|---|---|---|---|
| **1st** | 01:28–01:37 | failure | `UnicodeEncodeError: '\u2192'` at dex-ingest.py:304 | Unicode arrows in print statements crash under cp1252 subprocess capture |
| **2nd** | 01:37–01:39 | skipped_report_only | Classification Case B fired correctly | The report-only-skip logic works — no gate, no ingest, no new report |
| **3rd** | 01:40–01:58 | failure (TimeoutExpired 600s) | `dex-ingest.py --path CANON_DIR` processes all 5,803 files | CANON_DIR is too large for --path target; need temp dir pattern |

Run 1 surfaced the Unicode issue, which CC fixed immediately (replaced `→` with `->` at dex-ingest.py:304 and :616). Run 2 proved the classification Case B. Run 3 proved the fix held but surfaced the CANON_DIR architectural issue.

**Despite two failures, significant infrastructure was validated:**
- ✅ Task Scheduler fires correctly
- ✅ Classification predicate works (Case B skip)
- ✅ Backup gate fires (Trigger 5, new backups created)
- ✅ Trigger 6 restore test auto-fires
- ✅ `copy_to_corpus` moves files correctly
- ✅ Report writer produces all 8 sections
- ✅ Log schema captures outcome/stderr/report fields
- ✅ Ollama responsive at 2:00 AM
- ❌ dex-ingest.py fails when pointed at CANON_DIR (too large)

#### Step 22 — Temp-dir-per-sweep pattern, Fix A (`0a30e0e`)

Applied Step 17's temp-dir pattern to the sweep. Instead of `dex-ingest.py --path CANON_DIR` (5,803 files), the sweep now creates a per-run temp dir at `C:\Users\dexjr\dex-rag-scratch\sweep_{run_id}\`, copies only the new files into it, and points dex-ingest.py at the small temp dir.

**Changes:**
- `TEMP_BASE` constant added
- `copy_to_corpus(files, dry_run, temp_dir)` — copies to BOTH CANON_DIR (archival) and temp_dir (ingest)
- `run_ingestion(ingest_path, dry_run)` — takes `ingest_path` instead of hardcoded CANON_DIR; returns 3-tuple `(ok, stderr, stdout)`
- `sweep()` creates/passes/cleans temp dir; cleanup on success, preserve on failure
- Subprocess timeout reduced 600s → 300s

**End-to-end verification (Step 22 manual trigger):**
- Task triggered via `schtasks /run`
- 4 files scanned (2 user + 2 reports from prior runs)
- 3 files ingested: `Comprehensive Update - Weekend of 4.11.26.txt` (operator content), `test_sweep_step22_verification.txt`, and Run 3's failure report
- **24 chunks written** to dex_canon (242,009 → 242,033)
- Report with `outcome=success` written to `_sweep_reports/`
- Temp dir cleaned up on success
- **Self-documenting loop PROVEN:** Run 3's failure report was ingested as corpus content — Dex Jr. can now answer "what went wrong with last night's sweep?"

**Total wall time ~17 min** (5 min backup gate + Trigger 6, ~2 min copy + ingest, ~10 min overhead from restore test). The ingest itself (3 files, 24 chunks) completed in under 30 seconds against the temp dir.

### Ratifications this session

**STD-DDL-SWEEPREPORT-001 v1.0** — ratified via CR-SWEEP-REPORT-PROTOCOL-001.
- Classification predicate: 3-condition conjunction (parent folder, prefix, extension)
- Three cases: A (user+report → ingest all), B (report-only → skip), C (empty → skip)
- Report sections: YAML header, summary, files table, previous report, skipped, errors, pipeline state, next scheduled
- Filename: `ingest_report_{YYYY-MM-DD_HHMMSS.ffffff}_{ingest_run_id}.md`
- Location: centralized at `DDL_Ingest/_sweep_reports/`
- 3 amendments integrated during ratification: per-folder breakdown, microsecond filename uniqueness, centralized report location
- `source_type='ingest_report'` refinement deferred to v1.1 (requires STD-DDL-METADATA-001 amendment first)

**STD-DDL-BACKUP-001 v1.1 amendment** — DRAFTED but not yet ratified. Formalizes Trigger 6 (restore test), `--skip-restore-test`, `--expected-chunks`, `--json`, drift tolerance, `cleanup_stale_scratch()`. CR-STD-BACKUP-AMENDMENT-001 review prompt drafted, pending distribution.

### Council reviews

- **CR-SWEEP-REPORT-PROTOCOL-001:** distributed, synthesized by seats 1002 (Marcus), 1004 (Kai Nomura), 1007 (Leo Vance), 1009 (Grey Aldric), 1010 (Dex Jr). Synthesis locked. 3 amendments integrated into the STD before ratification. V1.0 is final.
- **CR-AUDITFORGE-CATHEDRAL-001:** synthesis arrived mid-session as a parallel-thread artifact from Marcus. Not tonight's drafting work but acknowledged as in-flight governance.
- **CR-STD-BACKUP-AMENDMENT-001:** prompt drafted by Marcus, pending distribution. Covers the Step 10–11 work that was never formally ratified into the STD.

### Infrastructure deployed tonight

| Component | Status | Verified |
|---|---|:---:|
| Windows Task Scheduler `DexSweep-NightlyIngest` | ✅ Registered, Enabled, Ready | ✅ 4 manual triggers |
| `dex-sweep.py v2.0` | ✅ Committed (`0a30e0e`) | ✅ 7/7 self-tests + end-to-end |
| Temp-dir-per-sweep pattern (Fix A) | ✅ Committed (`0a30e0e`) | ✅ End-to-end verified |
| `DDL_Ingest/_sweep_reports/` directory | ✅ Created | ✅ 3 reports written |
| Self-documenting loop (reports as corpus content) | ✅ Proven | ✅ Run 3's failure report ingested in Run 4 |
| Classification predicate (Cases A, B, C) | ✅ Implemented | ✅ Case B verified in Run 2 |

### Corpus state at session close

| Metric | Value |
|---|---:|
| **dex_canon** | **242,033** chunks |
| ddl_archive | 291,520 chunks |
| dex_code | 20,384 chunks |
| ext_creator | 922 chunks |
| **Total corpus** | **554,859** chunks |
| **Distinct `ingest_run_id` values in dex_canon** | 5 (Step 6 proof-of-life + Step 17 Run 1 + Step 17 Run 2 + Step 22 verification `manual_2026-04-12_072014`) |
| STD-compliant chunks in dex_canon | ~11,945 of 242,033 (~4.9%) |
| Legacy chunks in dex_canon | ~230,088 (~95.1%) |
| Most recent backup anchor | `chromadb_2026-04-12_0712` |
| Backups on D: | 6 (within 7-daily retention) |
| Files queued in DDL_Ingest for 4am | **24** |
| Next scheduled task fire | **2026-04-12 04:00:00 local** |

### F-Code events

**F4 operator throws at Marcus 1002** (multiple throughout the night, per operator). Marcus exhibited chaperone drift — unnecessary commentary about body, evening, when-to-stop. Operator named the pattern "ModelCourtesy in reverse" and issued structural corrections. Not CC's F-Codes; these were in the Marcus-in-app thread. Recorded here because they shaped the governance-document drafting cadence.

**CC self-catch: stale ScheduleWakeup** (during Step 17 Run 1 monitoring). CC incorrectly called `ScheduleWakeup` to pace subprocess monitoring. Realized within the same response that ScheduleWakeup is for `/loop` dynamic mode, not for subprocess monitoring. Self-corrected: "ScheduleWakeup isn't appropriate here — I'm not in a /loop context." The wakeup later fired after Step 17 was already complete; CC recognized and dismissed it as stale. No F-Code thrown by operator — clean self-catch.

**CC polling correction** (during Step 22 verification). Operator intervened: "CC — stop polling. Check once now, then WAIT... Do not poll in a loop." CC was hammering schtasks every 10-15 seconds during sweep monitoring. Operator preference for passive-wait-then-check-on-request noted. Not formally an F-Code, but a behavioral correction that applies to future task-monitoring contexts.

**Step 21 real-time debugging.** Run 1's Unicode crash was caught, diagnosed, and fixed during the session — not between sessions. The `→` → `->` fix was applied in real-time. Run 3's CANON_DIR timeout was similarly diagnosed in-session and resolved with Fix A in Step 22. This demonstrates the airtight pipeline's self-diagnostic capability: failures are surfaced via reports + log entries, not hidden by silent skips.

### Running list updates (new parked items this session)

1. **Sweep ↔ dex-ingest.py run_id handoff** — sweep generates `sweep_*` for its log/report; dex-ingest.py generates `manual_*` for chunk metadata. Not shared. Future fix: pass `--run-id` CLI arg to dex-ingest.py.

2. **STD-DDL-METADATA-001 v1.1 amendment** — add `source_type='ingest_report'` to the enum. Required before STD-DDL-SWEEPREPORT-001 v1.1 can refine how reports are classified for ingest.

3. **STD-DDL-SWEEPREPORT-001 v1.1** — deferred `source_type` refinement. Reports currently ingest as `source_type='unknown'`; v1.1 would make them `source_type='ingest_report'` once the metadata enum is amended.

4. **STD-DDL-BACKUP-001 v1.1 amendment** — drafted, covers Trigger 6, `--skip-restore-test`, `--expected-chunks`, `--json`, drift tolerance, `cleanup_stale_scratch()`. Pending CR-STD-BACKUP-AMENDMENT-001 council review.

5. **CR-PLATFORM-CATHEDRAL-002** — multi-vertical platform thesis. Draft concept from Marcus during tonight's synthesis work. Parked.

6. **STD-DDL-SELFREPORT-META-001** — future concept for metadata-about-metadata. The idea that sweep reports should carry metadata about the chunks they describe, enabling "rebuild corpus from report chain" as a disaster-recovery primitive. Nascent concept, not drafted.

7. **"Rebuild corpus from report chain" disaster-recovery primitive** — the insight that if every sweep report documents exactly which files were ingested with which chunks, the report chain becomes a manifest from which the corpus could theoretically be reconstructed. Pure concept, deferred.

**Still parked from prior sessions (unchanged):**
- `classify_tier()` word-boundary fix (Step 17 pre-flight)
- `dex-ingest.py --build-canon` silent-skip Rule 15 violation (Step 17 pre-flight)
- Orphan Chroma segment directories in live (Steps 5/9/14/17)
- `dex-convert.py` silent-drop bug (CLAUDE.md Open Items #1)
- `dex-search-api.py` 5-of-7 collection blind spot (CLAUDE.md Open Items #2)
- `dex-ingest.py` scoped+fast file-level skip (CLAUDE.md Open Items #3)
- dex_core package refactor (CLAUDE.md refactor target #1)
- Backfill operation for ~230K legacy chunks
- Mania/ subfolder governance decision
- Gmail MBOX ingest (blocked on dex-convert.py fix)
- CANON_DIR bulk recovery (1,767 stranded files)
- DexKit genesis material ingest
- dex-acquire.py path typo fix + wire (Step 16 in original sequence)

### Unresolved decisions pending future sessions

1. **Push to origin** — 25+ commits ahead of `origin/main`. Operator to decide per Rule 4.
2. **First unattended 4:00 AM run** — fires at 2026-04-12 04:00:00 local without operator present. 24 files in DDL_Ingest. Expected: backup gate → copy 24 files to temp dir → ingest → report → cleanup. Post-run verification: read the sweep report in `_sweep_reports/` and check dex_canon count delta.
3. **CANON_DIR bulk recovery** — 1,767 stranded files. Deferred from Step 20. The temp-dir pattern means this would be a dedicated recovery run, not a sweep task.
4. **STD-DDL-BACKUP-001 v1.1 council review** — CR-STD-BACKUP-AMENDMENT-001 drafted, pending distribution.
5. **CR-AUDITFORGE-CATHEDRAL-001 synthesis finalization** — in-flight, not tonight's work.

### Session-local carry-forward

- **24 files queued in DDL_Ingest** for 4:00 AM scheduled sweep. Files include governance docs, council reviews, operator prompts, DexKit genesis material, and session artifacts. First real unattended production run.
- **Task Scheduler `DexSweep-NightlyIngest`:** Enabled, Ready, next fire 2026-04-12 04:00:00 local.
- **Most recent backup anchor:** `chromadb_2026-04-12_0712`.
- **dex_canon count:** 242,033.
- **dex-rag-scratch/ state:** 3 Trigger-6 orphan scratch dirs (`restore_test_2026-04-12_0635`, `0647`, `0718`). These will be reclaimed by `cleanup_stale_scratch()` on the next backup run (the 4am sweep will fire Trigger 5 → new backup → cleanup runs → orphans reclaimed).
- **Rule 17 files** (`dex_weights.py`, `fetch_leila_gharani.py`) still show unstaged modifications from before the session. **Rule 17 respected throughout** — verified before every commit via `git status --short`.
- **25+ local commits ahead of `origin/main`.** Not pushed.


---

# 2026-04-12 — Steps 24 through 33b Part F

**Day's arc:** Started with the 4 AM sweep timing out on real operator content, ended with the entire 558,459-chunk corpus migrated onto a new embedding model and Dex Jr. answering identifier queries correctly for the first time in the system's existence. Sixteen ratified steps. Two test collections built and parked. Five hours of overnight compute. One clean self-test against the new layer at 23:37 CDT.

---

## Part 1 — Morning (Steps 24-27)

### Step 24 — 4 AM sweep timeout removal + morning resume
**Commits:** `20ee36a`, `69fb1f6`

The unattended 4 AM sweep fired correctly but the `subprocess.run(timeout=300)` in `dex-sweep.py::run_ingestion()` killed `dex-ingest.py` mid-run. 25 real operator files in the holding folder; 2,987 chunks landed before `TimeoutExpired`. dex_canon ended the morning at 245,020 (down from the expected target).

The 300 s cap was inherited from Step 22 Fix A, where it had replaced 600 s after the CANON_DIR-scan issue was fixed. Real operator content (multi-MB files, thousands of chunks each) does not fit any reasonable wall-time cap. Removed the timeout entirely; `subprocess.TimeoutExpired` handler retained as defensive dead-code.

Manually resumed the morning's 25-file ingest from the preserved temp dir `sweep_sweep_2026-04-12_090000`. dex_canon -> 245,633 (+613 from resume; total 5,036 chunks across the 25 files). All 25 files verified present in `dex_canon`.

### Step 25 — Non-ASCII print scrub
**Commit:** `3efb6a4`

The Step 24 manual ingest crashed on its final summary print (`'charmap' codec can't encode character '\u2192'` under Windows cp1252). All DB writes had landed; the crash was on a `print(f"... -> ...")` line. Audited `dex-ingest.py`, `dex-sweep.py`, `dex-backup.py` for non-ASCII in print/help statements. 15 substitutions across 3 files (em dashes -> `-`, arrows -> `->`, box-drawing chars -> `-`). Smoke-tested `python dex-ingest.py --help` clean under `PYTHONIOENCODING=cp1252`. Comments and docstrings left alone (cosmetic, not crash-paths).

### Step 26 — Push to origin
Ahead-count was 3 commits, not 27+ as the prompt context expected — earlier sessions had pushed Steps 18-23. Fast-forward push of `885fd4f..3efb6a4` clean. Surfaced the discrepancy before pushing per Rule 6.

### Step 27 — `dex_jr_query.py` CC -> Dex Jr. bridge
**Commit:** `c50f30c`

Mechanism 1 of CC<->Dex Jr. integration. Read-only CLI helper that takes a question, embeds via `nomic-embed-text`, queries all 4 ChromaDB collections, optionally feeds the retrieved chunks to `qwen2.5-coder:7b` for a grounded answer. Three output formats (markdown, json, plain). `--raw`/`--no-answer` for retrieval-only. `--self-test` for connectivity verification. Reconfigures stdout to utf-8 to handle non-ASCII content in retrieved chunks.

Self-test passed 8/8. The first end-to-end query worked. Then the operator started actually using it.

---

## Part 2 — Retrieval Diagnostic Arc (Steps 28-32)

### Step 28 — Retrieval quality deep-dive audit
**Commit:** `a13d96f`

Real-world testing exposed that `dex_jr_query.py` could not retrieve `STD-DDL-SWEEPREPORT-001.txt`'s own chunks even when queried with the literal identifier and a key phrase from the document. The chunks were verifiably present in `dex_canon`. The retrieval was failing.

Built `_step28_diagnostic.py` to embed five test queries and compute raw L2-squared and cosine distances against every chunk of the target file, plus chroma's native top-20 ranking.

**Smoking gun:**
- `STD-DDL-SWEEPREPORT-001` vs `STD-DDL-BACKUP-001` under `nomic-embed-text`: **cosine 0.0000.** Bit-identical embeddings. Two different DDL identifiers indistinguishable to the model.
- Self-identity check: `STD-DDL-SWEEPREPORT-001` vs itself: 0.0000 (sanity ok)
- Cat/mat normal English: 0.0773 (model isn't broken on prose)
- Conceptual `"sweep report protocol"` vs identifier: 0.2912 (the model can talk about the concept; it just can't read the identifier)

`nomic-embed-text`'s tokenizer collapses DDL identifiers to indistinguishable token sequences. Retrieval by identifier is impossible via vector search alone.

Ranked candidate fixes:
- **B3** — source_file pre-filter. Detect identifier patterns in query, look up matching `{ID}.txt`/`.md`/`Draft.txt`. Fast, reversible. **Ship next.**
- **B2** — body-contains fallback. When B3 finds nothing, run `where_document.$contains` for the identifier across collections.
- **B1** — swap embedding model (mxbai-embed-large candidate). Real fix; defer until B3+B2 are lived-in.

### Step 29 — B3 source_file prefilter
**Commit:** `3e2d532`

Implemented `extract_identifiers()` (regex for STD/CR/ADR/PRO/OBS/SYS-pattern), `prefilter_by_source_file()` (chroma `$in` lookup against three filename variants per identifier), and merge logic in `run_query()`. Markdown output tags prefilter chunks with `[PREFILTER MATCH]`. JSON output carries `retrieval_source: "prefilter_filename_match"`. Added `--no-prefilter` flag for testing. Self-test extended with B3 canary against `STD-DDL-SWEEPREPORT-001`.

Verified:
- `What is STD-DDL-SWEEPREPORT-001?` now returns the protocol's own chunks at rank 0 with the `[PREFILTER MATCH]` tag.
- `What is the Dex Continuum?` (no identifier) falls through to vector search unchanged.
- `--no-prefilter` reproduces the Step 28 failure exactly.

### Step 30 — Transient HNSW error + B2 scope
**Commit:** `b98c629`

Real-workflow testing surfaced an intermittent ChromaDB error: `Error executing plan: Internal error: Error creating hnsw segment reader: Nothing found on disk`. Could not reproduce on demand — every retry succeeded.

Filesystem audit of `C:\Users\dkitc\.dex-jr\chromadb\`:
- 4 live collections, all healthy
- 4 METADATA segments "missing on disk" — expected (sqlite-backed metadata segments don't have separate dirs in newer Chroma)
- **7 orphan UUID directories**, each exactly 321,700 bytes (empty HNSW skeletons from collections created and dropped during the six-month iteration). Total 2.2 MB. Stable, unreferenced. Quarantine path drafted in audit Appendix E.

Verified Finding 2 (B2 thesis): three identifiers (`CR-OPERATOR-CAPACITY-001`, `ADR-INGEST-PIPELINE-001`, `PRO-DDL-SPIRAL-001`) all have body-content matches in `dex_canon` via `$contains`, but **zero** filename matches. B3 prefilter returns nothing for them — body-match is exactly the missing path. ChromaDB 1.5.2 supports `where_document.$contains` cleanly.

### Step 31 — B2 body-content fallback
**Commit:** `59f2679`

Implemented `body_match_by_identifier()`: when B3 finds zero hits for a detected identifier, run `col.get(where_document={"$contains": ident})` per collection, cap at 3 hits/collection. Tag chunks with `retrieval_source: "prefilter_body_match"` and `[BODY MATCH]` in markdown output. Self-test extended with B2 canary.

All three previously-failing identifier queries now return correct content with `[BODY MATCH]` tags. Step 29 regression preserved. `--no-prefilter` cleanly disables both B3 and B2.

Then real-workflow testing exposed the next layer: **concept queries with no identifier still failed.** AccidentalIntelligence, GuidedEmergence, CottageHumble, Charlie Conway Principle, Beth Epperson, Mithril Standard — six distinct concept queries, all returning off-topic content. B3+B2 don't help. The embedding model was the bottleneck.

### Step 32 — B1 subset test with mxbai-embed-large
**Commit:** `f764d1c`

Pulled `mxbai-embed-large` (334M params, 670 MB, 1024-dim). Built `dex_canon_mxbai_test` — 2,500 chunks selected by `$contains` of nine seed terms (the failing concept queries' key terms plus identifier positive controls), expanded by source_file. Re-embedded with mxbai. Throughput 21.67 c/s single-stream.

**Result: mxbai 8/8, nomic 0/8** on the 8-query suite. The identifier-pair test moved from 0.0000 to 0.2438 cosine. Every mxbai top-5 read like the answer space a human would expect; every nomic top-5 read like a random sample of the corpus.

mxbai context limit is 512 tokens vs nomic's 2K. Used adaptive truncation 1200 -> 900 -> 600 -> 300 chars during embed. 0/2,500 needed backoff at the tightest level.

Recommendation: full migration. Seven hours of single-stream extrapolation, but the 0/8 -> 8/8 evidence was not marginal.

---

## Part 3 — Migration (Steps 33a-33b Part F)

### Step 33a — Batching probe + 10K rechunk validation
**Commit:** `1dbfede`

Two pre-migration questions:

1. **Does `/api/embed` batch endpoint work and does it speed things up?** Yes, but modestly. Batch=8 optimal at 28.5 c/s (vs 23.8 c/s single-stream). Beyond batch=8 throughput drops as Ollama internally serializes. Full-migration extrapolation: 5.4 h, not 2-3 h.

2. **Does structure-aware re-chunking to 400 tokens preserve retrieval quality at 10K scale?** **No.** Built `dex_canon_mxbai_rechunk_test` with 10,000 chunks via a structure-aware splitter (priority: `=====`, markdown headers, paragraphs, sentences, hard cut). Three-way comparative test (nomic_original / mxbai_original / mxbai_rechunk) on 9 queries:
   - nomic_original: 0/9
   - mxbai_original: 8/9
   - **mxbai_rechunk: 6/9** — regressed on `id_sweep` and `emergence`

   Root cause: the rechunked subset was 4x larger (10K vs 2.5K), so the relevant chunks faced more competition. Smaller chunks also lose the surrounding context that concept queries depend on. Spot check showed 7/10 mid-word starts (overlap artifact, same as the existing chunker).

**Decision:** HALT the rechunk plan. Proceed to Step 33b with mxbai on the EXISTING 500-token chunker. Step 32 already validated 8/8 retrieval on that configuration; the chunker change is a separate, deferrable decision.

### Step 33b — Full migration to mxbai
**Commits:** `cb4a326` (migration + validation), `b950dba` (audit), `a373cff` (code switchover)

Wrote `_step33b_migrate.py` — resumable via `_step33b_checkpoint.json`, paged 2K/page (avoiding the SQLite 32K variable limit), batched embed at 8/batch, adaptive truncation, checkpoint every 80 chunks. All 4 collections migrated to `_v2` twins. Original collections never touched.

**Migration timing:**

| Source -> Dest | Chunks | Wall time | Rate | Skipped |
|---|---:|---:|---:|---:|
| ext_creator -> _v2 | 922 | 0.5 min | 34.1 c/s | 0 |
| dex_code -> _v2 | 20,384 | 9.7 min | 35.0 c/s | 0 |
| dex_canon -> _v2 | 245,633 | 143.0 min | 28.6 c/s | 0 |
| ddl_archive -> _v2 | 291,520 | 165.1 min | 29.4 c/s | 0 |
| **TOTAL** | **558,459** | **318.4 min (5.3 h)** | **29.2** | **0** |

Start 17:49 CDT -> end 23:07 CDT. ddl_archive finished 7 minutes after the 04:00 sweep window — sweep would have written to original `dex_canon` (nomic), which is fine; Step 33c can migrate any drift.

**Validation:** Count parity 4/4 perfect. Metadata 4/4 perfect (0 mismatches across 400 sampled chunks). Step 32 8-query raw-vector recall: **6/8** (cottage and charlie regressed at full-corpus scale vs the 2,500-chunk subset — same scaling competition effect Step 33a documented). 5-identifier raw recall: 4/5 (PRO-DDL-SPIRAL-001 raw-fail, recovered by B2 in production -> 5/5 effective).

**HALTed before code switchover** per prompt's "regress unexpectedly = halt" rule. Effective production recall with B3+B2 retained estimated at 7/8 vs nomic's 0/8. Operator GO received: ship the env-gated switch; cottage/charlie residuals are corpus-content density issues, soak-period diagnostic.

### Step 33b Part F — Code switchover
**Commit:** `a373cff`
**Soak start: 2026-04-12 23:37:48 CDT (2026-04-13 04:37:48 UTC)**

Env-gated defaults in `dex_jr_query.py`:
- `DEXJR_EMBED_MODEL` defaults to `mxbai-embed-large`
- `DEXJR_COLLECTION_SUFFIX` defaults to `_v2`
- `embed()` does adaptive truncation 1200 -> 900 -> 600 -> 300

Self-test 10/10 against `_v2`. B3 + B2 canaries both pass on the new collections. Rollback is one env-var change away.

---

## Part 4 — The Arc

The day started with infrastructure: a scheduled sweep timing out on real operator content, the kind of bug that only shows up when you stop testing on yourself and start running against the world. Eight minutes of code change, fifteen minutes of scrubbing print statements that crashed under Windows codepage. Then the bridge — `dex_jr_query.py` — the first time CC and the operator could ask Dex Jr. a question and get an answer back through the same interface.

The bridge worked. And then the operator used it. And the answers were wrong.

Not "off by a margin" wrong. Categorically wrong. Asking for `STD-DDL-SWEEPREPORT-001` returned five chunks of unrelated session transcripts. Asking who Beth Epperson is returned an explanation of cognitive architecture. Asking for the Mithril Standard returned Reddit comments. The corpus contained the answers — the retrieval layer was failing to find them.

Step 28 found it: the embedding model was treating every DDL identifier as the same string of tokens. `STD-DDL-SWEEPREPORT-001` and `STD-DDL-BACKUP-001` produced bit-identical embeddings. Six months of governance documents had been ingested into a system that could not distinguish them. The corpus was fine. The pipeline was fine. The chunker was fine. The retrieval *model* was wrong.

Steps 29-31 patched the symptom: detect identifiers in the query, look them up by filename (B3) or by body-content (B2), surface those chunks before vector search even runs. It worked for identifier queries. But concept queries — anything without an identifier — still returned random content. The model was wrong for the whole class, not just identifiers.

Step 32 proved `mxbai-embed-large` was the answer: 8/8 vs 0/8 on the same queries, same corpus subset. Step 33a confirmed batching gave a modest 20% gain and that re-chunking was a regression, not an improvement. Step 33b migrated all 558,459 chunks to `_v2` collections in 5.3 hours of overnight compute. Zero skipped. Perfect parity. The retrieval validation flagged 6/8 instead of 8/8 because at 245K-chunk scale the cottage/charlie answer-chunks lose to corpus competition — but with B3+B2 still active in production, real-world recall jumps from 0/8 to ~7/8.

By 23:37 CDT the env-gated switch was in. Dex Jr. had answered its first questions on the new model. The soak began.

---

## Part 5 — Running list additions

### Open from this session

1. **Cottage and Charlie regression** — concept queries that work on the 2,500-chunk subset but fail at 245K-chunk scale. Soak-period diagnostic: sample top-20 instead of top-5, identify what's outranking the answer chunks, decide if it's a tunable. Likely a corpus-content density issue, not a retrieval-model failure.

2. **Step 33c: post-soak cleanup** — when operator confirms `_v2` is healthy:
   - Update `dex-ingest.py` to embed new chunks with mxbai + adaptive truncation
   - Switch ingest routing to `_v2` collections
   - Migrate any chunks that landed in nomic during the migration window or soak (likely < 100)
   - Drop original `dex_canon`, `ddl_archive`, `dex_code`, `ext_creator`
   - Rename `_v2` -> canonical names
   - Drop the env-var switch in `dex_jr_query.py`
   - Drop `dex_canon_mxbai_test` (Step 32) and `dex_canon_mxbai_rechunk_test` (Step 33a)

3. **DirectIngest 24-file batch** — needs to land via the new pipeline (25 files on disk; `test.env` excluded).

4. **`05_DirectIngest` folder not on sweep scan list** — operator decision: add to sweep, or force via `DDL_Ingest`.

5. **LLMPM session log re-export** — current file on disk is 5:57 PM; missing everything after.

6. **Transient HNSW retry hardening in `search_collections()`** — small defensive patch (catch the `Nothing found on disk` error and retry once).

7. **7 HNSW orphan directories** — quarantine-then-delete per Step 30 Appendix E. *(Addressed in Step 35 below.)*

8. **Seven WorkBench CRs ratified in parallel thread** — FACTLAYER, CONNECTIVITY, CANON, MODULE, MODBUILD, HRPEOPLE, PITFALLS, ANALYTICS. Context-only for future sessions.

9. **CR-PLATFORM-CATHEDRAL-002** — governance retrieval / indexing / synthesis cadence. 30-day horizon.

10. **Council V2 composition re-evaluation** — operator surfaced.

### Carry-forward state

- **`dex_jr_query.py` defaults:** `mxbai-embed-large` + `_v2`. Override via env vars to fall back.
- **Soak window:** 24-72 h of operator queries against `_v2` before Step 33c.
- **Original nomic collections:** intact, untouched, rollback path.
- **Most recent backup anchor:** `chromadb_2026-04-12_1730`.
- **Ahead-count on `origin/main`:** several commits past `a373cff`. Not pushed.
- **Rule 17 files** (`dex_weights.py`, `fetch_leila_gharani.py`): still modified, untouched throughout.
