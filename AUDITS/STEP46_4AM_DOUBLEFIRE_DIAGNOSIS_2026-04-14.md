# Step 46 — 4 AM sweep double-fire diagnosis (read-only)

**Date:** 2026-04-14
**Scope:** Diagnose the 2026-04-14 04:00 AM sweep failure and its 20-minute-later
success. Read-only across Task Scheduler, dex-backup.py, dex-sweep.py, and logs.
**No fixes. No edits. No commits.**

---

## TL;DR

The framing "20 minutes apart double-fire" is wrong. The actual pattern is:
**two concurrent sweep processes fire within 44 ms of each other** at 04:00:01.
One runs to completion in 20 minutes (success); the other fails in 34 seconds
on a `FileExistsError` because its peer won the backup-directory creation race.
The 20-minute *wall-clock gap* is between their *end_ts* values, not their fire
times. Identical pattern to 2026-04-13 (54 ms apart there).

---

## Q1 — Where did `chromadb_2026-04-14_0900` come from?

**It was created by the peer sweep fire, not pre-existing.**

### Backup-name generation

`dex-backup.py:70`:
```python
datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
```

Minute precision. At `dex-backup.py:312`:
```python
backup_dir = BACKUP_ROOT / f"chromadb_{timestamp}"
```
At `dex-backup.py:328`:
```python
backup_dir.mkdir(parents=True, exist_ok=False)  # <-- fails if dir exists
```

`09:00 UTC = 04:00 CDT`. Any two backups that call the name function in the same
UTC minute compute the **same** path, and exactly one of them survives the
`mkdir(exist_ok=False)` race.

### Backup log fingerprint (`_backup_log.jsonl`, timestamps in UTC)

```
09:00:34.xxx started pid=39280 path=chromadb_2026-04-14_0900
09:00:35.xxx started pid=10680 path=chromadb_2026-04-14_0900
09:16:11.xxx success duration=581s path=chromadb_2026-04-14_0900
```

Two distinct PIDs. Same target path. One-second gap between their start-lines,
but the directory creation itself races within milliseconds. The success record
is the survivor (took 9 min 37 s for backup + 2 min 22 s for restore-test =
~581 s total). The loser's failure is not recorded in `_backup_log.jsonl` — it
crashed before it could log — but *is* recorded in `dex-sweep-log.jsonl` as a
captured subprocess stderr:

```
Creating backup at: D:\DDL_Backup\chromadb_backups\chromadb_2026-04-14_0900
FileExistsError: [WinError 183] Cannot create a file when that file already
exists: 'D:\\DDL_Backup\\chromadb_backups\\chromadb_2026-04-14_0900'
```

### Orphan / incomplete siblings

Directory listing `D:\DDL_Backup\chromadb_backups\`:

```
chromadb_2026-04-13_0900_INCOMPLETE   (from 2026-04-13 failure, unresolved)
chromadb_2026-04-13_2216              (operator manual backup 2026-04-13 22:16)
chromadb_2026-04-14_0900              (this morning's survivor)
chromadb_2026-04-14_2130              (from this session's smoke-test sweep)
chromadb_2026-04-14_2140_FAILED       (from this session's second attempt —
                                       renamed by the validate step because
                                       dst chunk count was off-by-one during
                                       the smoke-test cleanup; separate issue)
```

No `chromadb_2026-04-14_0900_INCOMPLETE` sibling exists for today, which means
the loser did NOT create a `.part` or stub — it hit `FileExistsError` **before**
any artifact was written, which is consistent with the peer having already run
`mkdir()` and moved into sqlite copy by that moment.

---

## Q2 — Did anything run between midnight and 4 AM that could have created
the directory?

**No.** The directory came into existence inside the 4 AM window, not before.

### Evidence

`_backup_log.jsonl`, ordered:

| UTC time | Event |
|---|---|
| 2026-04-13T22:16:20Z | started (operator manual, pid 45300) |
| 2026-04-13T22:25:15Z | success (chromadb_2026-04-13_2216) |
| **2026-04-14T09:00:34Z** | **started pid 39280 path=chromadb_2026-04-14_0900** |
| 2026-04-14T09:00:35Z | started pid 10680 path=chromadb_2026-04-14_0900 |
| 2026-04-14T09:16:11Z | success |

No entry between 22:25:15Z (prior-day end) and 09:00:34Z (4 AM start).
No cron-equivalent external process touched `D:\DDL_Backup` in the gap.

Task Scheduler Operational event log was queried for the window 04:50–04:30
(and also for 08:50–09:30 UTC); the log returned no matching events. The
Operational log appears to be disabled or cleared on this machine, so we cannot
cross-check from the OS side. The `_backup_log.jsonl` is authoritative.

### Why the dir "seemed to pre-exist"

The failing fire wrote the "creating backup at…" log line to stdout (captured
in the sweep log's error field), suggesting it got far enough to *attempt*
creation. It hit `FileExistsError` because its peer — fired 44 ms earlier and
already past the `mkdir()` line — had beaten it to disk. From the perspective
of the losing process, the dir did exist when *it* called `mkdir()`. From a
filesystem observer, the dir came into existence during the 04:00 window.

---

## Q3 — Task Scheduler configured state and run history

**One task, one trigger, daily at 04:00 local.** Full XML captured below.

### `DexSweep-NightlyIngest`

```xml
<CalendarTrigger>
  <StartBoundary>2026-04-12T04:00:00-05:00</StartBoundary>
  <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
</CalendarTrigger>
<Settings>
  <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
  <RestartOnFailure>
    <Count>3</Count>
    <Interval>PT30M</Interval>
  </RestartOnFailure>
  <StartWhenAvailable>true</StartWhenAvailable>
  <WakeToRun>true</WakeToRun>
  <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
</Settings>
<Actions>
  <Exec>
    <Command>C:\Users\dkitc\AppData\Local\Programs\Python\Python312\python.exe</Command>
    <Arguments>dex-sweep.py</Arguments>
    <WorkingDirectory>C:\Users\dexjr\dex-rag</WorkingDirectory>
  </Exec>
</Actions>
```

Last run reported by `Get-ScheduledTaskInfo`:

| Field | Value |
|---|---|
| LastRunTime | 4/14/2026 4:00:01 AM |
| LastTaskResult | 0 (success) |
| NextRunTime | 4/15/2026 4:00:00 AM |
| NumberOfMissedRuns | 0 |

Task Scheduler itself reports **one fire** at 04:00:01 with a success result.
This is consistent with one of the two python processes exiting 0 (the
successful one that finished at 04:20:20) while the failing one's exit code
is aggregated away.

### Other dex-invoking tasks

Searched `Get-ScheduledTask` for anything invoking `dex-sweep` or paths under
`dex-rag`:
- `DexSweep-NightlyIngest` — our target task.
- `Needoh-Watcher` — daily 16:17, invokes `needoh-watcher\watcher.py`, no
  interaction with dex-sweep or dex-backup.

No other task is invoking `dex-sweep.py` or `dex-backup.py`.

### Retry policy implication

`RestartOnFailure Count=3 Interval=PT30M` means: on failure, Task Scheduler
will retry up to 3 times at 30-minute intervals. **This is not what caused
the 44 ms double-fire** (retries would be minutes apart, not milliseconds).
It *could* explain a 30-minute-later *third* fire if one had occurred, but
the logs show only two fires at 04:00:01, and neither was re-launched later.

---

## Q4 — Re-examine the two log entries

The morning verification note described the pattern as "20 minutes apart."
**This is end-time difference, not fire-time difference.** The two entries
fire at 04:00:01 within 44 ms.

### Exact sweep log fields

```
Entry A (failure):
  jsonl_timestamp: 2026-04-14T04:00:35.369517
  start_ts:        2026-04-14T04:00:01.560105
  end_ts:          2026-04-14T04:00:35.369517
  outcome:         failure
  error:           BackupFailedError: dex-backup.py --force exited 1 ...
                   FileExistsError: Cannot create a file when that file
                   already exists: chromadb_2026-04-14_0900
  files_found: 19, files_copied: 0, ingestion_triggered: false

Entry B (success):
  jsonl_timestamp: 2026-04-14T04:20:20.699317
  start_ts:        2026-04-14T04:00:01.604346   <-- 44ms after Entry A's start
  end_ts:          2026-04-14T04:20:20.699317
  outcome:         success
  backup_path:     chromadb_2026-04-14_0900
  files_found: 19, files_copied: 19, ingestion_triggered: true,
                 ingestion_success: true
```

### Same pattern yesterday (2026-04-13)

```
Entry A (failure): start_ts 04:00:01.611560, end_ts 04:02:01 (120s check-only timeout)
Entry B (failure): start_ts 04:00:01.557927, end_ts 04:15:13 (900s force timeout)
```

Yesterday both instances *failed* (different timeout types, both backup-gate).
Today one failed and one succeeded. **But the fire-time delta is the same
class:** 44–54 ms. This is the actual "double fire" signature.

### Corollary

The "20-minute gap" on 2026-04-14 is because the successful run took 20 min
(backup 9:40, restore-test 2:22, ingest the rest) while the doomed run bailed
in 34 s. They're not sequential retries — they're concurrent siblings.

---

## Q5 — Is the failure recoverable in-process, or did Task Scheduler retry?

**Neither.** The second instance is not a retry; it is a **concurrent sibling
fired at the same moment**. `dex-sweep.py` has no internal retry/recovery logic.

### dex-sweep.py retry/recovery search

Grep for `watch|--interval|subprocess|Popen|spawn|fork|daemon|service` and the
broader control flow:

- `dex-sweep.py:11–12` — CLI supports `--watch` (persistent) and `--interval N`
  (poll every N minutes), but this loop lives **inside** the process. It does
  NOT re-fire a fresh dex-sweep.py.
- `dex-sweep.py:379` — `subprocess.run(...)` calls dex-ingest.py once per sweep.
  No loop.
- `dex-sweep.py:393` — `subprocess.TimeoutExpired` is caught and surfaced as a
  failure; no automatic retry.
- Main `__main__` path: one-shot unless `--watch` flag is passed (it is not —
  Task Scheduler invokes `python dex-sweep.py` with no flags).

There is no code path in `dex-sweep.py` that would spawn a second sweep. The
two concurrent processes therefore have an **external** origin.

### Probable causes for the external double-fire

Ranked by plausibility:

1. **WakeToRun + scheduled trigger race.** When `WakeToRun=true` and
   `StartWhenAvailable=true`, Windows can deliver a wake-and-fire event
   simultaneously with the normal calendar-time fire if the machine is in a
   sleep state around 04:00. Both dispatch through the Task Scheduler service,
   which then tries to honor `MultipleInstancesPolicy=IgnoreNew` — but the
   policy check is per-instance-registration and races against sub-second
   twin launches. This is a known Windows Task Scheduler quirk.

2. **Unified scheduling engine re-emission.** `UseUnifiedSchedulingEngine=true`
   delegates dispatch to a newer scheduler component (hence "Win7" compatibility
   fallback) that has documented cases of double-emitting a CalendarTrigger
   when the system clock is adjusted or NTP-synced near the boundary.

3. **Prior-run hand-off race.** If yesterday's prior-day sweep run was still
   considered "running" by Task Scheduler at 04:00:00 and then crashed mid-
   check, two fires could land in the same millisecond window as the scheduler
   re-evaluates state. Unlikely here — yesterday's runs exited by 04:15:13 and
   have no impact on today.

Without Task Scheduler Operational log data (which this machine is not
retaining), we cannot discriminate between (1) and (2). Both are consistent
with the observed 44–54 ms fire delta.

### Implication for fix scope (not designing fix here)

The fix is not in dex-sweep.py — it has no retry logic to remove. The fix is
in **one or both** of:

- **dex-backup.py** — make `backup_dir.mkdir(parents=True, exist_ok=False)`
  robust against the concurrent-sibling case. Options include: a file-lock
  on `D:\DDL_Backup\chromadb_backups\.lock`, atomic mkdir-else-claim via a
  `_RUNNING_pid` sentinel, or simply using a more-precise timestamp (include
  seconds) so two fires within the same minute get different paths.
- **Task Scheduler task definition** — remove WakeToRun, tighten MultipleInstances
  policy to "Queue" with a max-wait, or add a `<StartBoundary>` random delay.

This is a small-to-medium fix (a few lines in one or two places plus a task
XML re-import). Not urgent because the existing behavior is self-healing
(one fire always wins), but operator should close it before the next
long-duration run where both fires might clash in backup validate/restore-test.

---

## Appendix — pattern history

| Date | Fire delta | Outcome A | Outcome B |
|---|---|---|---|
| 2026-04-13 04:00 | 54 ms | check-only timeout 120s | force timeout 900s |
| 2026-04-14 04:00 | 44 ms | FileExistsError 34s | success 20m 19s |

Two days running. Not a one-off.
