# Step 47 — Orphan backup directory cleanup (PRE-DELETION — awaiting GO)

**Date:** 2026-04-14
**Mode:** Read-only inventory. Nothing deleted yet.

## Inventory

| Name | Size | Age | LastWrite | Origin |
|---|---:|---:|---|---|
| `chromadb_2026-04-13_0900_INCOMPLETE` | **21.3 GB** | 37.8 h | 4/13 04:00:10 | Residue from 2026-04-13 4 AM sweep: both concurrent backup PIDs timed out (120 s check-only + 900 s force), leaving a partial copy. Known flagged item. |
| `chromadb_2026-04-14_2140_FAILED` | **21.6 GB** | 1.1 h | 4/14 16:40:38 | This session's backup validate-step failure (`dex_canon_v2 src=253979 dst=253978` — the 1-chunk delta was from this session's smoke-test chunk being deleted mid-backup). Data-wise redundant: the prior `chromadb_2026-04-14_2130` completed 10 min earlier successfully. |

Total reclaim: **~42.9 GB**.

## Note on new auto-cleanup policy (commit 88d23c3)

The `cleanup_dead_letter_backups()` helper added in Step 47 commit 1
would, on the next backup run, auto-delete `_INCOMPLETE` at age 37.8 h
(exceeds the 24 h safety window). It would **keep** the `_FAILED` dir
because age 1.1 h < 24 h — the safety window is there to protect against
racing concurrent-PID siblings that look like dead letters but aren't.

This one-time manual cleanup removes both **now**, ahead of the 24 h
window, because the operator can confirm both are truly dead letters
(the _FAILED race was already root-caused to the smoke-test cleanup and
there is no concurrent PID writing to this directory).

## Recommendation

**DELETE BOTH.** Both are confirmed dead letters:

1. `chromadb_2026-04-13_0900_INCOMPLETE` — yesterday's crash, can't be
   revived (ChromaDB segment dirs were in mid-copy when killed).
2. `chromadb_2026-04-14_2140_FAILED` — this session's validate failure,
   superseded by the successful `chromadb_2026-04-14_2130` sibling
   written 10 minutes earlier.

Each removal will be logged to `_backup_log.jsonl` with
`{"action":"manual_cleanup","path":...,"reason":"<pattern>","age_hours":N}`.

## Result — quarantined (not deleted) per operator revision

Both directories moved via `shutil.move()` to
`D:\DDL_Backup\chromadb_backups_quarantine\`. Each move logged to
`_backup_log.jsonl` with `{"action":"quarantine","from":...,"to":...,"reason":...}`.

Post-move:
- Active dead-letters in `D:\DDL_Backup\chromadb_backups\`: **0**
- Quarantine contents: both moved directories present.

Going forward, `perform_backup()` auto-quarantines new dead letters
and GCs the quarantine dir at a 30-day cadence (see commit `c52b698`).
This manual move only handled the two that pre-existed the fix.
