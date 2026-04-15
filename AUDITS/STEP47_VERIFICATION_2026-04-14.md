# Step 47 — Verification run

**Date:** 2026-04-15 (UTC) / 2026-04-14 late evening local
**Purpose:** Confirm the new naming scheme and quarantine model work end-to-end.

## Run command

    python dex-backup.py --force --skip-restore-test

(Restore test skipped for speed; naming/quarantine changes are independent
of restore-test behavior.)

## Result

- Backup directory: `chromadb_2026-04-15_001923_48976`
  - **New format verified:** `YYYY-MM-DD_HHMMSS_<PID>` (date + time-to-second + PID)
  - No `FileExistsError`. Clean `mkdir(exist_ok=False)`.
- Duration: 425.2 s (~7 min). Consistent with prior runs (no overhead introduced).
- Manifest written. 1,133,612 chunks. Validation: OK.
- Dead-letter cleanup step: zero active dead-letters to move (expected —
  the two pre-existing orphans were manually quarantined in commit `a7e15cf`).

## Log schema verification

Recent `_backup_log.jsonl` tail:

    {"timestamp":"2026-04-15T00:18:06Z","action":"quarantine",
     "from":"D:\\DDL_Backup\\chromadb_backups\\chromadb_2026-04-13_0900_INCOMPLETE",
     "to":"D:\\DDL_Backup\\chromadb_backups_quarantine\\chromadb_2026-04-13_0900_INCOMPLETE",
     "reason":"_INCOMPLETE"}
    {"timestamp":"2026-04-15T00:18:06Z","action":"quarantine",
     "from":"...\\chromadb_2026-04-14_2140_FAILED",
     "to":"...\\chromadb_2026-04-14_2140_FAILED","reason":"_FAILED"}
    {"timestamp":"2026-04-15T00:19:23Z","stage":"started","pid":48976,
     "backup_path":"...\\chromadb_2026-04-15_001923_48976"}
    {"timestamp":"2026-04-15T00:28:02Z","result":"success",
     "backup_path":"...\\chromadb_2026-04-15_001923_48976",
     "duration_seconds":425.22,"total_size_bytes":22686267402,
     "total_chunk_count":1133612,"triggers":["force"],
     "rotation_pruned":0,"restore_test_elapsed_seconds":null}

Schema confirmed: `action:quarantine` records show `from`/`to`/`reason`;
`stage:started` captures PID; `result:success` unchanged from prior.

## Directory state post-verification

- Active `D:\DDL_Backup\chromadb_backups\`: no `_INCOMPLETE` or `_FAILED` dirs.
- Quarantine `D:\DDL_Backup\chromadb_backups_quarantine\`: 2 dirs
  (both pre-existing orphans, awaiting 30-day GC).

Step 47 end-to-end verified.
