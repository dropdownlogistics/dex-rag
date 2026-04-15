# dex-rag session log — 2026-04-14

Status: Final. Captures the full 2026-04-14 session across Step 33c
(drift migration), Step 46 (4 AM race diagnosis), Step 47 (race fix),
CLAUDE.md numeric refresh, and the DDL_Ingest pre-sweep cleanup.

---

## Morning verification (Step 45)

- Confirmed 4:00 AM sweep attempt failed on backup collision, retried
  successfully at 4:20 AM.
- 19 files ingested into nomic `dex_canon` (+1,436 chunks → 253,982).
- `_v2` collection baselines all unchanged from Step 44 baseline.
- Smoke: PROFILE-DDL-DAVE-KITCHENS-001 present in `dex_canon` (5 chunks)
  and **ZERO** in `dex_canon_v2`. The drift-accumulation symptom was real.

## Step 33c Part A — Pre-migration inspection (read-only)

Report: `AUDITS/STEP33C_PRE_MIGRATION_INSPECTION_2026-04-14.md`

Findings:
- **Drift isolated to `dex_canon`**: +8,349 chunks / +3.40% vs `_v2`.
  `ddl_archive`, `dex_code`, `ext_creator` were byte-identical to their
  `_v2` twins. Root cause: `dex-sweep.py:362` was running
  `dex-ingest.py --collection dex_canon` (scoped mode), which bypasses
  tier routing — only `dex_canon` (nomic) ever received writes.
- Writer config was hardcoded: `EMBED_MODEL = "nomic-embed-text"` and
  `RAW_COLLECTION`/`CANON_COLLECTION` constants. No CLI/env overrides.
- `dex-search-api.py` was never flipped in Step 33b — still reading
  nomic on both `/search` (dex_canon, ddl_archive) and `/mindframe/chat`
  (dex_canon).
- Test collections present: `dex_canon_mxbai_test` (2,500),
  `dex_canon_mxbai_rechunk_test` (10,000) — drop candidates.
- Today's backup complete (21 GB, no `_INCOMPLETE` sibling).

Flagged (correction surfaced later): Part A claimed
`01bc5548-54bb-4b15-a27f-509a817cfa46` was a live segment dir. **That
was wrong.** See Part B sub-task 3.

## Step 33c Part B pre-flight — Drift source file list

Report: `AUDITS/STEP33C_PART_B_DRIFT_SOURCE_FILES_2026-04-14.md`

- 44 source_files / 8,349 chunks ✅ matches Part A.
- Extension breakdown: 34 .txt / 7 .md / 3 .html / 1 .jsx.
- Ingest-run breakdown: 26 files from Sunday manual (6,580 chunks),
  18 files from this morning's sweep (1,769 chunks).
- All 7 expected-shape classes confirmed present (4 extractions, 3
  governance, 3 profiles, 1 synthesis, brand kit, session logs, Monday
  remnants).
- 6 non-blocking flags surfaced; operator reviewed and approved scope.
- Scope change from operator: exclude 2 ingest_report_*.md files from
  migration AND from scanner going forward (pipeline feedback loop).

## Step 33c Part B execution

### Commit 1/3 — config flip (0fe2abb)
- `dex-ingest.py`: EMBED_MODEL → mxbai-embed-large; collections →
  `_v2` variants; new `SKIP_FILENAME_PREFIXES = ("ingest_report_",)`
  enforced in `scan_archive`.
- `dex-search-api.py`: model + both collection references → mxbai / `_v2`.
- `dex-sweep.py:362`: scoped collection flag → `dex_canon_v2`.
- Self-test: all three files parse clean.

### Commit 2/3 — drift migration (b89d543)
- Pre `dex_canon_v2`: 245,633
- Post `dex_canon_v2`: 253,978 (+8,345) ✅ expected exactly
- 42 source_files migrated (44 − 2 ingest_report exclusions).
- Wall time: 15.3 min (within 10–15 min estimate).
- **~3,274 chunks (39%) required progressive truncation** to fit mxbai's
  512-token context. Original chunks were sized at 500 tokens assuming
  4 chars/token; real tokenization ran longer. **Flag: embedding quality
  on these chunks may be slightly degraded vs a full-chunk embedding.
  Document text is preserved in destination; only the embedding prompt
  was truncated.**
- First live attempt errored on chunk `c22` of 11_Thread_Gemini with a
  500 from Ollama (`input length exceeds the context length`). Resume
  logic + progressive-truncation fallback added to the script; 22
  already-written chunks from that first attempt were picked up as
  idempotent skips on re-run.
- Spot-checks: PROFILE-DDL-DAVE-KITCHENS-001.txt (19), STD-FCODE-001.txt
  (6), GLOSS-DDL-COTTAGEHUMBLE-001.txt (10) — all present post-migration.

### Commit 3/3 — test collection drop + Part A correction (fab6ac0)
- `dex_canon_mxbai_test` dropped (was 2,500).
- `dex_canon_mxbai_rechunk_test` dropped (was 10,000).
- 8 collections remain (4 nomic + 4 `_v2`).
- **Part A correction:** `01bc5548-…` IS an orphan after all. Verified
  via sqlite segment query (10 segment rows vs 11 live dirs). STEP35
  quarantine audit was right; Part A was wrong. Watch list unchanged.
- Orphan watch list now expects 2 additional transient orphans from the
  dropped test collections until Chroma compaction removes them.

### Sub-task 4 — Ingest smoke test
- Drop file `_33c_smoke_test.txt` into `OneDrive\DDL_Ingest`.
- Sweep ran cleanly (no errors).
- Result: `dex_canon_v2` +1 (253,979); `dex_canon` unchanged (253,982). ✅
- Chunk retrievable via direct vector query at distance 0.628 when
  scoped to source_file. Sentinel phrase less selective under
  unscoped top-K against 254K chunks; this is expected and not a
  migration defect.
- Cleaned up: chunk deleted, file removed from `_processed` and
  `CANON_DIR`. `dex_canon_v2` back to 253,978.

### Sub-task 5 — Retrieval smoke test (dex_jr_query.py --raw)
| Query | Top-1 hit | Distance | Collection |
|---|---|:---:|---|
| "CottageHumble canonical definition" | GLOSS-DDL-COTTAGEHUMBLE-001.txt | 0.5979 | dex_canon_v2 |
| "Dave Kitchens UMB Commission Analyst" | 28_CognitiveArchitectureHandoff.txt | 0.5512 | dex_canon_v2 |
| "Platinum Bounce recovery protocol" | ClaudemdUpdate.txt (then PRO-DDL-PLATINUM-BOUNCE-001.txt @ 0.5979 at rank 2) | 0.5674 | dex_canon_v2 |

All three: top hit in `dex_canon_v2`, distance ≤ 0.60. The two migrated
governance artifacts (GLOSS-DDL-COTTAGEHUMBLE-001, PRO-DDL-PLATINUM-BOUNCE-001)
both surface in the top-3 of their respective queries. Retrieval quality
broadly consistent with the Step 39B Q5 baseline — no obvious degradation.

## What's now retrievable that wasn't before

All 42 drift source_files — 8,345 chunks — including the governance,
profile, extraction, and synthesis artifacts authored during the
4.12–4.13 weekend and the 4.14 morning retry. Highest-leverage additions:

- PROFILE-DDL-DAVE-KITCHENS-001, -OPERATOR-001, -EXTERNAL-001
- STD-FCODE-001, PRO-DDL-PLATINUM-BOUNCE-001, GLOSS-DDL-COTTAGEHUMBLE-001
- All 4 DDLExtraction_* source materials
- DDLSynthesis_WorkBenchWeekend_4.12.26
- 10 DDLCouncilReview_* artifacts from the weekend council run

## Pre-existing uncommitted modifications (Rule 17)

- `dex_weights.py` — operator WIP, untouched
- `fetch_leila_gharani.py` — operator WIP, untouched

## Open items carried forward

- **Truncated-embedding hot-spots**: ~3,274 migrated chunks were embedded
  against progressively-truncated prompts. Re-chunking these files to
  respect mxbai's actual token limit (not the nominal 4-char-per-token
  assumption) would improve retrieval precision on those chunks. Not
  urgent — retrieval works — but a known quality caveat.
- **Dropped test collection segment dirs**: 2 transient orphans expected
  until Chroma compaction; add to next orphan sweep, not quarantined here.
- **dex-search-api.py still missing 5/7 collections bug**: only opens
  dex_canon_v2 + ddl_archive_v2; still invisible to dex_code_v2,
  ext_creator_v2, and any future `ext_*`. Pre-existing known bug, not
  introduced by 33c; deferred.
- **`scoped+fast` re-chunk bug** (Open Item #3): untouched by this step.
- **ingest_report feedback loop prevention**: guarded at the ingest scanner
  now, but the sweep's `classify_scanned_files` already had this concept
  — root cause of why reports still ended up in `dex_canon` deserves a
  follow-up (likely: the sweep copies reports to `CANON_DIR`, and some
  earlier path walked CANON_DIR). Not blocking.

## Metrics

- Files touched (code):   3 (dex-ingest.py, dex-search-api.py, dex-sweep.py)
- Files created (scripts): 3 (_step33c_inspect, _step33c_partb_drift, _step33c_migrate_drift)
- Audit reports:          3 (Part A, Part B pre-flight, test-drop + Part A correction)
- Commits:                3 (0fe2abb, b89d543, fab6ac0) — local only, not pushed
- Chunks migrated:        8,345
- Chunks dropped (test):  12,500 (2,500 + 10,000)
- Net dex_canon_v2 delta: +8,345
- Wall time (migration):  15.3 min

## Next logical step

- Operator reviews this log and the audit reports.
- Subsequent sessions will tackle the `scoped+fast` bug or begin the
  `dex_core` refactor. See Next logical step at end of log.

---

## Step 46 — 4 AM sweep double-fire diagnosis (read-only)

Report: `AUDITS/STEP46_4AM_DOUBLEFIRE_DIAGNOSIS_2026-04-14.md`

Prompted by the morning 4 AM sweep log pattern (one 34s failure +
one 20m success against the same backup path). Investigation
determined:

- The "20 minutes apart" framing was wrong. Two sweep PIDs actually
  fire within **44 ms** of each other at 04:00:01 (this morning) and
  **54 ms** apart yesterday. Identical signature both days.
- Root cause pair:
  1. `dex-backup.py` uses minute-precision UTC timestamp for the
     backup directory name, so two sibling PIDs in the same minute
     compute the same path and race on `mkdir(exist_ok=False)`.
  2. Windows Task Scheduler configured `MultipleInstancesPolicy=IgnoreNew`,
     but that check races against sub-second twin launches — the OS
     dispatches both before the already-running check lands. Likely
     `WakeToRun + StartWhenAvailable + UnifiedSchedulingEngine` race.
- `dex-sweep.py` has NO internal retry. Both fires are external.

Push of Step 33c + prior unpushed work happened mid-step: 23 commits
pushed to origin (`3efb6a4..fab6ac0`) after a pre-push scan for
secrets/oversize/scope-foreign additions surfaced nothing blocking.
`needoh-watcher/` confirmed as operator side-project co-located here.

## Step 47 — Fix 4 AM sweep double-fire race

Five commits (all pushed to origin):

### Commit 88d23c3 — dex-backup.py naming + cleanup helper
- `utc_now_compact()` now includes seconds (`%Y-%m-%d_%H%M%S`).
- `perform_backup()` appends `os.getpid()` → dir names like
  `chromadb_2026-04-15_001923_48976`. Concurrent siblings get
  distinct paths; `mkdir(exist_ok=False)` no longer races.
- First-pass dead-letter cleanup helper added (later revised — see below).
- `--skip-cleanup` CLI flag.
- Also commits the Step 46 audit alongside the fix.

### Commit c51908f — Task Scheduler XML: IgnoreNew → Queue
- Single-line XML change: `<MultipleInstancesPolicy>IgnoreNew</...>`
  → `<MultipleInstancesPolicy>Queue</...>`.
- All other task settings preserved (trigger, RestartOnFailure,
  WakeToRun). Under Queue, a second dispatch waits for the first to
  finish instead of racing.
- Applied via `Set-ScheduledTask`.
- BEFORE/AFTER XML captured in `AUDITS/DexSweep-NightlyIngest_{BEFORE,AFTER}.xml`.

### Commit c52b698 — revision: quarantine-model dead-letter handling
Operator revision: instead of deleting dead letters, MOVE them to
`D:\DDL_Backup\chromadb_backups_quarantine\` and GC the quarantine
at a 30-day cadence.

- New `quarantine_dead_letter_backups()` — `shutil.move()` `_INCOMPLETE`/
  `_FAILED` dirs to `QUARANTINE_ROOT`. No age threshold (OS file lock
  protects in-flight siblings from being moved mid-write).
- New `cleanup_quarantine()` — GC entries older than 30 days.
- Log schema: `action:quarantine` (move) + `action:quarantine_gc`
  (delete).

### Commit a7e15cf — one-time manual quarantine of existing orphans
- `chromadb_2026-04-13_0900_INCOMPLETE` (21.3 GB, 37.8h) → quarantine
- `chromadb_2026-04-14_2140_FAILED` (21.6 GB, 1.1h) → quarantine
- Each move logged to `_backup_log.jsonl`.

### Commit a847f56 — verification run
- `python dex-backup.py --force --skip-restore-test` ran clean.
- New backup dir: `chromadb_2026-04-15_001923_48976` (format confirmed).
- Duration 425s (consistent with baseline). 1,133,612 chunks.
- Log schema entries for `quarantine` + `started` + `result:success`
  all present with expected fields.

## CLAUDE.md refresh — commit b9fc28c

Four numeric-only lines updated post-Step-33c:
- `Last audit: 2026-04-12 (CR-DEXJR-AUDIT-001)` → `Last audit: 2026-04-14 (post-Step-33c drift migration)`
- `~542K chunks` → `~566K chunks` (two occurrences)
- `` `dex_canon`    (230,082 chunks) `` → `` `dex_canon`    (253,978 chunks) ``

Sum check: 253,978 + 291,520 + 20,384 + 922 = **566,804** ✓.
Pushed to origin.

## DDL_Ingest pre-sweep cleanup

Report: `AUDITS/DDL_INGEST_CLEANUP_2026-04-14.md`
Action log: `_ddl_ingest_cleanup_actions.json`

Inspected 22 top-level files in `C:\Users\dkitc\OneDrive\DDL_Ingest\`.

Executed 17 actions after operator GO:
- **Deleted 1**: `AuditForge Full Session Log - 4.14.26.txt` (202,966 B
  partial browser save; superseded by 279,521 B complete version).
- **Moved 8 → `_review/`**: all unsupported extensions (7 × PNG + 1 SVG,
  including 3 `(2)` double-save pairs).
- **Moved 8 → `_duplicates/`**: all files whose SHA-256 first-16-char
  `file_hash` matched an existing chunk in `dex_canon_v2`. 0 matched
  `ddl_archive_v2` (expected — sweep writes only to `dex_canon_v2`).

Final top-level inventory: **5 novel `.txt` files (2.74 MB)** ready
for the next 4 AM sweep. These are the 4.14 session logs from
AuditForge, KnowledgeVault (x2), LLMPM, and WebsitePM PMs.

## Pre-existing uncommitted modifications (Rule 17 running total)

Unchanged across the entire session:
- `dex_weights.py` — operator WIP, untouched
- `fetch_leila_gharani.py` — operator WIP, untouched

## Open items carried forward (consolidated)

### From Step 33c
- **Truncated-embedding hot-spots**: ~3,274 migrated chunks embedded
  against progressively-truncated prompts. Re-chunking these files
  to respect mxbai's actual token limit would improve retrieval
  precision. Not urgent.
- **Dropped test collection segment dirs**: 2 transient orphans in
  the live Chroma dir until compaction.
- **`dex-search-api.py` still 2/4 collections**: only opens
  `dex_canon_v2` + `ddl_archive_v2`; invisible to `dex_code_v2`,
  `ext_creator_v2`.
- **`scoped+fast` re-chunk bug** (Open Item #3 from CLAUDE.md): untouched.

### Newly surfaced or confirmed this session
- **Task Scheduler Operational event log disabled**: could not
  cross-check 4 AM dispatch events from the OS side. Not blocking —
  `_backup_log.jsonl` is authoritative for PID-level forensics.
- **`01bc5548-…` orphan HNSW dir** still in the live Chroma folder
  (not quarantined). STEP35 audit was correct; Step 33c Part A's
  contrary claim was wrong and has been retracted in commit `fab6ac0`.
- **ingest_report feedback loop**: guarded at the `dex-ingest.py`
  scanner now (`SKIP_FILENAME_PREFIXES`), but the deeper root
  (something walks CANON_DIR where the reports live) deserves a
  follow-up.
- **Quarantine GC not yet exercised**: `cleanup_quarantine()` will
  first trigger at the 30-day mark for the two dirs quarantined
  today. Worth a manual check on 2026-05-13 ± a few days that the
  GC runs as expected.

---

## Operator Status Report (end-of-session summary)

**Status:** Full 2026-04-14 session — Complete.

**Done:**
- Step 33c Part A (read-only drift inspection)
- Step 33c Part B pre-flight (drift source_file enumeration)
- Step 33c Part B execution: writer+search-api flipped to mxbai+_v2,
  8,345 drift chunks migrated, 12,500 test-collection chunks dropped,
  Part A orphan-claim corrected (3 commits pushed to origin)
- Step 46 4 AM double-fire diagnostic (1 audit report)
- Step 47 race fix: dex-backup.py naming + quarantine model, Task
  Scheduler XML, one-time quarantine of 2 existing orphans,
  verification run (5 commits pushed to origin)
- CLAUDE.md post-33c numeric refresh (1 commit pushed)
- Pre-push scan of 23-commit batch for secrets/scope/size (PASS)
- Pre-sweep DDL_Ingest cleanup (1 delete, 16 moves, 5 novel files remain)

**Flagged (Rule 6):**
- Step 33c Part A mis-identified `01bc5548-…` as a live segment dir —
  corrected in commit `fab6ac0`. STEP35 audit stands.
- First drift-migration attempt failed on an mxbai 512-token context
  limit; added progressive truncation (1500 → 1000 → 600 chars) and
  resume logic. ~39% of migrated chunks needed truncation.
- Two `AuditForge Full Session Log - 4.14*.txt` variants had different
  SHA-256 (one was a partial browser save); operator chose delete vs
  retain on the partial.
- Push to origin was 23 commits (not the 3 Step 33c ones), because
  prior sessions never pushed. Pre-push scan surfaced needoh-watcher
  as operator side-project co-located in the repo — not a secret leak
  or scope surprise; operator OK'd all 23.
- A mid-session `chromadb_2026-04-14_2140_FAILED` backup was produced
  by the smoke-test concurrency with a manual dex-backup invocation
  (`dex_canon_v2 src=253979 dst=253978`, the 1-chunk delta was my
  smoke-test chunk being deleted mid-backup). Quarantined in the
  manual one-time cleanup.

**Pending:**
- Next 4 AM sweep (2026-04-15 04:00 local) is the first in-production
  test of the Step 47 race fix. Will ingest the 5 novel .txt files
  left in DDL_Ingest after today's cleanup.
- 30-day quarantine GC first-fire window: ~2026-05-13.

**Decisions needed:**
- None.

**Metrics (full day):**
- Commits:            10 (all pushed to origin; 3 × Step 33c, 5 × Step 47,
                         1 × CLAUDE.md refresh, 1 × verification note)
- Files touched (code): 4 (dex-ingest.py, dex-search-api.py, dex-sweep.py,
                         dex-backup.py)
- Task Scheduler:     1 setting flipped (IgnoreNew → Queue)
- Audit reports:      6 (STEP33C Part A / Part B pre-flight / Part B drop,
                         STEP46, STEP47 orphan + verification,
                         DDL_INGEST_CLEANUP)
- Scratch scripts:    4 (_step33c_inspect, _step33c_partb_drift,
                         _step33c_migrate_drift, _ddl_ingest_inspect)
- Chunks migrated to dex_canon_v2: 8,345 (42 source_files)
- Chunks dropped (test collections): 12,500
- DDL_Ingest top-level cleanup: -1 delete / -16 moves / 5 files remain
- Backup quarantine: 2 dead-letter dirs moved (~42.9 GB)

**Next logical step:**
Watch the 2026-04-15 04:00 sweep. If the Step 47 fix holds (single clean
fire, new naming scheme, 5 novel files ingested into `dex_canon_v2`), the
race is closed. The next workstream-level choice is between (a) fixing the
`scoped+fast` file-level-skip bug in `dex-ingest.py:370-374` (narrow, CLAUDE.md
Open Item #3) or (b) starting the `dex_core` package refactor (broad,
CLAUDE.md Refactor Target #1).
