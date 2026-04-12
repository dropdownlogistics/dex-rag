# Step 22: Temp-Dir-Per-Sweep Pattern (Fix A)

**Date:** 2026-04-12
**Auditor:** CC (executor) on behalf of Marcus Caldwell 1002 (advisor)
**Scope:** Fix the CANON_DIR timeout from Step 21, implement temp-dir-per-sweep pattern, end-to-end verify via Task Scheduler manual trigger

---

## What Step 21 shipped and what ran tonight

Step 21 registered `DexSweep-NightlyIngest` Task Scheduler entry (daily at 4:00 AM, REBORN\dkitc Interactive). Three manual triggers were fired:

| Run | Time | Files | Outcome | Root cause |
|---|---|---:|---|---|
| 1st | 01:28–01:37 | 3 | failure | `UnicodeEncodeError` — `→` arrow in cp1252 subprocess capture |
| 2nd | 01:37–01:39 | 0 user, 1 report | skipped_report_only | Classification Case B fired correctly |
| 3rd | 01:40–01:58 | 2 | failure | `TimeoutExpired after 600s` — CANON_DIR has 5803 files, scoped+fast re-embeds all |

## Root cause: CANON_DIR size + scoped+fast bug

`dex-ingest.py --path CANON_DIR --collection dex_canon --fast` scans ALL 5803 files in CANON_DIR. With `--fast` on a scoped collection, the file-level skip check (CLAUDE.md Open Items #3) is a no-op — every file is re-chunked and re-embedded even if chunks already exist. At ~50ms per embedding × ~100K chunks = far beyond the 600s subprocess timeout.

**The fix is architectural, not timeout-based.** Point `dex-ingest.py` at a temp dir containing ONLY the new files, not at the 5803-file archival directory.

## Fix A implementation

**Pattern:** same as Step 17's manual ingest — create a per-run temp dir, copy only the new files into it, run `dex-ingest.py --path <temp_dir>` instead of `--path CANON_DIR`.

**Changes to `dex-sweep.py`:**

1. **`TEMP_BASE` constant** — `C:\Users\dexjr\dex-rag-scratch`
2. **`copy_to_corpus(files, dry_run, temp_dir)`** — accepts optional `temp_dir`. Files are copied to BOTH CANON_DIR (archival) and temp_dir (ingest). Originals still move to `_processed/`.
3. **`run_ingestion(ingest_path, dry_run)`** — takes `ingest_path` parameter instead of hardcoded CANON_DIR. Returns 3-tuple `(ok, stderr, stdout)` for report chunk-count extraction.
4. **`sweep()`** — creates `sweep_{ingest_run_id}` temp dir before copy, passes to both functions, cleans up on success (preserves on failure for forensics).
5. **Subprocess timeout reduced** from 600s to 300s (5 min). Typical sweep of 3-30 files should complete in under 1 min.

**Also preserved:** Unicode encoding fix from Step 21 Run 1 debugging (`→` replaced with `->` in `dex-ingest.py:304,616`). Plus `PYTHONIOENCODING=utf-8` in subprocess env.

## End-to-end verification (Step 22 manual trigger)

| Check | Result |
|---|---|
| Task triggered | ✅ `schtasks /run /tn "DexSweep-NightlyIngest"` |
| Task completed | ✅ Status: Ready (~17 min total, ~5 min backup + ~12 min overhead) |
| Files scanned | 4 (2 user + 2 reports from prior runs' `_sweep_reports/`) |
| Files classified | 2 user, 1 report ingested (3 total in temp dir) |
| Backup gate | ✅ Trigger 5 fired, new anchor `chromadb_2026-04-12_0712` |
| Ingest outcome | ✅ **success** |
| Chunks written | **24** to dex_canon |
| dex_canon delta | 242,009 → **242,033** (+24) ✅ |
| Chunk run_id | `manual_2026-04-12_072014` (dex-ingest.py's own ID) |
| Source files in chunks | `Comprehensive Update - Weekend of 4.11.26.txt`, `test_sweep_step22_verification.txt`, `ingest_report_...065841...md` |
| Report written | ✅ `ingest_report_2026-04-12_072033...sweep_2026-04-12_071221.md` |
| Report outcome field | `success` |
| Report chunk count | 24 ✅ |
| DDL_Ingest empty | ✅ (user files moved to `_processed/`) |
| CANON_DIR has archived copies | ✅ |
| Temp dir cleaned up | ✅ (no `sweep_*` dirs in dex-rag-scratch) |
| Self-documenting loop | ✅ **Run 3's failure report ingested as corpus content** |

## Self-documenting loop proven

The previous sweep run (Run 3, which timed out) wrote a failure report at `_sweep_reports/ingest_report_2026-04-12_065841...md`. This run's scan found that report alongside the 2 new user files. All 3 were copied to the temp dir and ingested. The failure report now exists as chunks in dex_canon — Dex Jr. can answer "what went wrong with last night's sweep?" by retrieving the report.

## Known gaps (deferred)

1. **Sweep run_id vs ingest run_id mismatch** — sweep generates `sweep_*` for its log/report; dex-ingest.py generates `manual_*` for chunk metadata. They're correlated by time but not by a shared ID. Future fix: pass run_id to dex-ingest.py via CLI arg.
2. **3 Trigger-6 orphan scratch dirs** on C: — `restore_test_2026-04-12_0635`, `0647`, `0718`. These accumulate per backup. `cleanup_stale_scratch()` reclaims them on the next backup >1h later.
3. **Operator file `Comprehensive Update - Weekend of 4.11.26.txt`** was real content the operator dropped tonight. It was ingested with `source_type=unknown` — no naming convention match for council_review/governance/etc. If the operator wants a specific type, they need to name the file with a recognized prefix.
4. **Only 1 of 2 prior reports was ingested** — the Run 1 report may have been in `_sweep_reports/_processed/` from the second trigger's copy cycle.

---

**End of STEP22 report.**
