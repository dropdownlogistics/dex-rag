# Step 19: Mystery Scheduler Investigation

**Date:** 2026-04-11
**Auditor:** CC (executor) on behalf of Marcus Caldwell 1002 (advisor)
**Scope:** Identify the mechanism behind the daily 04:00:01 `dex-sweep-log.jsonl` entries discovered in Step 15
**Method:** Read-only. `schtasks /query` (281 tasks scanned), PowerShell `Get-ScheduledJob`, process listing (`ps -W`), startup folder inspection, crontab checks, script content analysis, full log entry analysis (48 entries). No modifications to any scheduler, registry, or file.

---

## Finding

### **PERSISTENT_WATCH_PROCESS (dead)**

The daily 04:00:01 entries are NOT from Windows Task Scheduler, PowerShell Scheduled Jobs, cron, or any startup-folder mechanism. They are from a **persistent `dex-sweep.py --watch` process** that the operator started manually, likely around 2026-03-15, and which has since **died** (no Python process is currently running).

The evidence for this is in the log's own temporal pattern:

1. **March 6 (first-ever entries):** 9 entries at exactly 30-minute intervals (20:36, 21:06, 21:36, ..., 23:36). This is unmistakably `dex-sweep.py --watch --interval 30`.
2. **March 7 (00:06–07:18):** the 30-minute watch continues (00:06), then a gap to 03:00 (machine slept or process was restarted), then 5 manual runs during the 07:00 morning session.
3. **March 14 (11:12–11:23):** 2 manual runs (governance doc ingest).
4. **March 15 onwards:** the pattern shifts to **once daily at exactly 04:00:01** (±10 minutes on days with actual files to process — the extra time is `copy_to_corpus()` latency; the log timestamp is captured at sweep-end, not sweep-start). This is consistent with `--watch --interval 1440` (24h = 1440 minutes) running continuously on a machine that doesn't sleep (Reborn).
5. **Sub-millisecond precision across days** (04:00:01.497911 → 04:00:01.498486 = 575μs drift over 24h) is consistent with `time.sleep(86400)` on a stable OS clock. A Windows Task Scheduler trigger would have ~1-second jitter; this is tighter than that, suggesting Python's internal sleep timer.
6. **No Task Scheduler entry found** (281 tasks scanned via `schtasks /query /fo list`, zero matches for python/dex/sweep/.py).
7. **No Python process currently running** (`ps -W | grep python` returns empty).

**The process is dead.** The last automated 04:00 entry was 2026-04-11T04:00:01.498486 (earlier today). No Python process is alive now. The process either (a) was killed by a machine reboot or sleep event after today's 04:00 run, or (b) crashed silently during or after today's run.

---

## Evidence

### A. Windows Task Scheduler — NO MATCH

```
MSYS_NO_PATHCONV=1 schtasks /query /fo list
→ 281 tasks across 1824 lines of output
→ grep -i "sweep|dex|python|\.py" → ZERO relevant matches
```

All 281 tasks are Windows system tasks (CloudRestore, OneDrive, NVIDIA, WD Device Agent, etc.) or Ollama. No user-created Python task.

### B. PowerShell Scheduled Jobs — EMPTY

`Get-ScheduledJob` returned no scheduled jobs (PowerShell scheduled-job infrastructure is separate from Task Scheduler).

### C. Startup folders — NO SWEEP

- `C:\Users\dkitc\...\Startup\`: `Ollama.lnk`, `desktop.ini` only
- `C:\Users\dexjr\...\Startup\`: directory does not exist

### D. crontab — NOT APPLICABLE

No crontab files found at `~/.crontab` or `/var/spool/cron/crontabs/`. WSL cron would require WSL to be running, which is unlikely as the primary runtime for a Windows Python script.

### E. PowerShell wrapper scripts — NO SWEEP INVOCATION

- `dex.ps1`: simple query wrapper (`python dex-query.py "$q"`)
- `dex-run-canon.ps1`: canon backfill runner invoking `dex-ingest.py --build-canon` — NOT sweep
- No `.bat` files exist in the repo

### F. Process listing — NO PYTHON PROCESSES

```
ps -W | grep -i python → (empty)
ps -W | grep -i pythonw → (empty)
```

Zero Python or pythonw processes running on Reborn at investigation time (~22:55 local).

---

## Full log analysis (48 entries)

### Timeline narrative

| Phase | Dates | Entries | Pattern | Interpretation |
|---|---|---:|---|---|
| **Initial `--watch --interval 30`** | 2026-03-06 20:35 – 2026-03-07 00:06 | 9 | 30-min intervals, `files_found=0` | Operator started watch mode manually for the first time |
| **Morning manual runs** | 2026-03-07 03:00 – 07:18 | 6 | irregular, manual invocations | Operator testing, ingested 3+19 files across 3 successful runs |
| **Sporadic manual runs** | 2026-03-14 11:12 – 11:23 | 2 | manual | Governance doc ingest (CR-CORPUS-NOMINATIONS, STD-VAULT-002) |
| **`--watch --interval 1440` starts** | 2026-03-15 04:10 onwards | 28 | daily at 04:00:01 (±10 min on busy runs) | Persistent process, 24h sleep interval |
| **Files found in early auto runs** | 2026-03-15 – 03-23 | 5 of 8 | 4–169 files found per run | Drop folders had content; sweep copied but **ingestion failed every time** |
| **Long empty streak** | 2026-03-24 – 04-05 | 13 | daily 04:00:01, `files_found=0` | Drop folders emptied by prior copies; no new content dropped |
| **Single auto find** | 2026-04-06 | 1 | 04:10, 1 file found | `audit.txt` — ingestion failed |
| **Final auto streak** | 2026-04-07 – 04-11 | 5 | daily 04:00:01, `files_found=0` | Empty drop folders |
| **Step 15 dry-run** | 2026-04-11 20:42 | 1 | manual | My Layer 1 test (127 files, DRY_RUN=true) |

### Critical log entries (files_found > 0)

| Date | Found | Copied | Ingested? | Files (sample) |
|---|---:|---:|:---:|---|
| 2026-03-07 07:03 | 3 | 3 | ✅ | DDLCouncilReview_GradeTheQuery, LocalAI, WebsiteDeployment |
| 2026-03-07 07:18 | 19 | 19 | ❌ | Profile docs, conversation exports |
| 2026-03-14 11:12 | 2 | 2 | ✅ | CR-CORPUS-NOMINATIONS-001, STD-VAULT-002 |
| **2026-03-16 04:10** | **169** | **169** | **❌** | **Major sweep: 169 files copied, ingestion FAILED** |
| 2026-03-22 04:10 | 93 | 93 | ❌ | 93 files copied, ingestion FAILED |
| 2026-03-23 04:00 | 50 | 0 | ❌ | 50 found but ZERO copied (copy failures?) |
| 2026-04-06 04:10 | 1 | 1 | ❌ | audit.txt, ingestion FAILED |
| 2026-04-11 20:42 | 127 | 127 | ✅ | My Step 15 dry-run (DRY_RUN flag) |

**Out of 12 entries with files_found > 0, only 2 had `ingestion_success: true`** (the two manual morning runs on 2026-03-07 and 2026-03-14). **Every automated nightly run that found files FAILED the ingestion subprocess.** This is a consistent ingestion-failure pattern on the 3am path.

Possible cause: the `run_ingestion()` subprocess runs `dex-ingest.py --build-canon --fast` in a context where either (a) Ollama isn't accessible at 04:00 (embedding calls fail), or (b) the `--build-canon` tier filter causes a "no files ingested" outcome that doesn't contain the "INGESTION COMPLETE" string, so the success check fails. (Note: this is the SAME `--build-canon` silent-skip issue identified in Step 17's pre-flight.)

### 04:00:01 vs 04:10:01 split (explained)

The `log_sweep()` function (pre-Step-15) captures `datetime.datetime.now()` at **sweep completion**, not sweep start. When `copy_to_corpus()` processes 100+ files, it takes ~10 minutes. So:

- `files_found=0` → sweep completes in ~1s → timestamp 04:00:01
- `files_found=169` → copy takes ~10 min → timestamp 04:10:02

The underlying trigger fires at exactly 04:00 every day. The 10-minute offset is copy latency, not a different schedule.

### Entry frequency

| Hour (local) | Entries |
|---:|---:|
| 04:00 | **28** (the daily auto pattern) |
| 07:00 | 5 (manual morning runs on 2026-03-07) |
| 20:00 | 4 (first-ever --watch + my Step 15 test) |
| 23:00 | 2 (March 6 --watch continuation) |
| Other hours | 9 (various manual runs + watch continuation) |

---

## Implications for tomorrow's 04:00 run

**No Python process is alive. Tomorrow's 04:00 run will NOT happen** unless:

1. The operator manually restarts `dex-sweep.py --watch --interval 1440` tonight
2. The operator creates a Task Scheduler task to invoke it (not yet done)
3. Some hidden mechanism I couldn't find (e.g., a service, a remote trigger) restarts it

If the process IS somehow restarted (or if I'm wrong and it's still alive in a session I can't see), the new Step 15 wiring would fire:
- `scan_drop_folders()` would print WARN for any unreachable drop folder (new Rule 15 fix)
- If files ARE found: `ensure_backup_current()` would trigger (Trigger 5, SWEEP_CHUNK_ESTIMATE=10000) → new backup created → then `dex-ingest.py --build-canon --fast --skip-backup-check` subprocess runs
- The `--build-canon` tier filter issue from Step 17 pre-flight would still apply: non-council-review files would be silently skipped
- Log entry would have the new 13-field schema including `start_ts`, `end_ts`, `backup_ran`, `recovery_hint`

---

## Recommendations for Step 20 (do NOT execute — proposal only)

### Option A: Let the persistent process stay dead (RECOMMENDED)

Don't restart `--watch`. The persistent-process-as-scheduler approach is fragile:
- Dies on reboot without restart
- Dies on machine sleep
- No monitoring or recovery
- No log rotation
- Failed 100% of automated ingestions that found files

Instead, move to a proper Task Scheduler entry created in a dedicated Step 20 that:
1. Runs `dex-sweep.py` (no `--watch`, single-run mode) via Task Scheduler at 04:00 local daily
2. Runs as the correct user context (whichever user has the drop folders visible)
3. Logs output to a sidecar file for post-mortem
4. Does NOT pass `--build-canon` — uses `--collection dex_canon` (or NORMAL mode) based on the Step 17 tier-filter findings

### Option B: Restart the persistent watch process (NOT recommended)

Restart `dex-sweep.py --watch --interval 1440` in a background terminal. Quick fix but same fragility. Would need to also decide on `--build-canon` vs alternative routing.

### Option C: Disable everything until sweep is fully validated

Leave the persistent process dead. Don't create a Task Scheduler task yet. Manual `dex-sweep.py` runs only, under explicit operator GO per Rule 5. Most conservative.

---

## Methodology notes

- Windows Task Scheduler queried via `MSYS_NO_PATHCONV=1 schtasks /query /fo list` (required MSYS path-conversion bypass; git bash mangles `/query` into `C:/Program Files/Git/query` without it)
- Process listing via `ps -W` (MSYS ps with Windows process table flag)
- Log analysis via Python: loaded all 48 JSON lines, computed per-date counts, time-of-day distribution, gap analysis, files_found > 0 filtering
- Script content analysis via Read tool: inspected `dex.ps1` and `dex-run-canon.ps1` for sweep invocations (none found)
- Startup folder inspection via `ls` on both user profiles' Startup dirs
- crontab check via `ls` on standard crontab locations (none exist)
- **No modifications made to any scheduler, registry, file, or process.**

---

**End of STEP19 investigation report.**
