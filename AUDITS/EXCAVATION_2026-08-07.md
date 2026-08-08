# EXCAVATION — dex-rag, 2026-08-07

**Trigger:** Operator: *"dream job protocol, do whatever you want, just
document it... this is exactly why I've never been able to trust dexjr, and
you're gonna excavate."*
**Executor:** Claude Code (Silas Reeve context, dream-job mode)
**Method:** Nothing in this document is trusted from the April audits without
independent re-measurement today. Where a April finding is repeated, it is
because it was re-verified live, not because it was assumed still true.

---

## The starting point: an unread folder

`AUDITS/` holds 32 files (31 from April, plus this one), dated April 11-17,
2026.

**Correction made before this document was committed, not after:** the first
draft of this section claimed all 31 were uncommitted. That was wrong, and I
caught it only because I checked `git status` before staging rather than
after. **The 25 sequential `STEP*` audits and two `.xml` files have been
tracked in git since 2026-04-11.** They were never at risk.

**Six files were genuinely uncommitted, all synthesis-level documents, not
step logs:**

```
CORPUS_AUDIT_2026-04-17.csv
CORPUS_RECLASSIFICATION_2026-04-17.md
DDL_INGEST_CLEANUP_2026-04-14.md
GAP_ASSESSMENT_2026-04-17.md
_classification_summary.json
_corpus_sources_raw.json
```

Six files, not thirty-one -- but they are the six that mattered most: every
synthesis document that turned the 25 raw step-audits into a decision (the
corpus reclassification recommendation, the ranked gap list) was the part
sitting exposed. `dex-rag/CLAUDE.md` has listed "a second audit pass over
non-.py files" as queued since April 16 and never closed the loop on any of
this.

That correction is itself the first finding, twice over: **this is precisely
the failure mode Reed Vane named org-wide tonight in a different repo** — work
that existed and wasn't reachable by anyone else, except this instance
predates the warning by sixteen weeks -- **and it is exactly the pattern this
whole excavation is about: a number that sounds alarming ("31 files never
committed") dissolving under one more check (git status), the same way the
40% garbage corpus dissolved under measurement below.**

---

## Finding 1 — The corpus reclassification was already fixed. Nobody said so.

**April 17 claim** (`CORPUS_RECLASSIFICATION_2026-04-17.md`): `dex_canon_v2`
was 40.4% garbage — 104,364 chunks of raw ChatGPT export data (literal
embedding floats) sitting at 0.90 weight next to governance documents.
Status: **AWAITING OPERATOR GO.** Never actioned in the record.

**Measured today, live, direct ChromaDB connection:**

```
dex_canon_v2 total:           67,093 chunks   (April: 258,492)
garbage-pattern source files:      0 / 67,093 (April: 104,364)
distinct source files:         3,882          (April: 4,683)

"What are the F-codes?" query, top result:
  April:  literal embedding-float garbage (the documented bug)
  today:  "...F-Codes when the model violates a constraint..." / STD-FCODE-...
```

**The reclassification happened.** Not via the documented Option A/B/C — most
likely as a side effect of the unrelated `_v2` embedding-model rebuild
(mxbai-embed-large, 1024-dim) that occurred sometime after April 17, which
re-ingested from clean source directories and simply never re-included the
garbage export files. **Nobody verified this, closed the finding, or updated
the record.** The April document still reads as an open decision awaiting you,
four months after the problem it describes stopped existing.

**This is marked CLOSED below**, by measurement, not by inference from the
rebuild's existence.

---

## Finding 2 — Repo backups have been silently failing for at least 3 weeks. Fixed.

`dex-repo-backup-log.jsonl`: **every single run since at least 2026-07-19**
— three consecutive complete failures, 11/11 repos, every time:

```
fatal: detected dubious ownership in repository at 'D:/DDL_Backup/repos/...'
```

Git's own dubious-ownership guard, triggered because the backup volume's
filesystem doesn't record ownership. **Root cause confirmed, fix applied and
verified live:**

```powershell
git config --global --add safe.directory "D:/DDL_Backup/repos/*"
```

Re-tested against `dex-rag.git`: `git fetch origin` now succeeds and pulled
real updates (`459a861..c9781bc`). **All 11 repos can back up again.** This
had nothing to do with the code being backed up — it was a permissions
allowlist, global and reversible.

---

## Finding 3 — ChromaDB backups: no verified backup in ~47 days, and the sweep has been silently erroring every night

**`dex_health.py`'s own last run, decoded** (see Finding 4 — the log was
unreadable as filed):

```
Ollama reachable ................ PASS
ChromaDB integrity ............... PASS  (404,540 chunks / 4 live collections
                                           -- matches an independent live
                                           count exactly: 20,416 + 922 +
                                           67,093 + 316,109 = 404,540)
Embedding smoke test .............. PASS
Retrieval smoke test .............. PASS
Weighted retrieval ................ PASS
Ingest cache health ............... PASS
Backup currency ................... FAIL  1128.2 hours old (~47 days),
                                           latest: chromadb_pre_mindframe_
                                           ingest_20260718, status unknown
Last sweep health ................. FAIL  "Last sweep errored:
                                           BackupFailedError: Most recent
                                           backup sqlite is unreadable: unknown"
```

**The corpus itself is healthy — six of eight checks pass, and the count
cross-validates independently.** The problem is entirely in the backup layer:
the most recent ChromaDB backup snapshot's SQLite file is corrupted or
unreadable, and the nightly sweep's internal verification step throws that
error **every night** — while `DexSweep-NightlyIngest`'s own scheduled-task
exit code reports `LastResult=0` (success). **The failure is real and is being
swallowed at the process-exit boundary.**

**Not fixed here, deliberately.** Per Rule 8, corpus/backup data is not mine to
remediate unilaterally, and I don't yet know whether the safe fix is "delete
the corrupted snapshot and let the next scheduled run regenerate cleanly" or
something that risks masking a deeper storage problem. **This needs your
decision, not my guess.** The last known-good, verified backup is
`chromadb_2026-05-31_090035_44748` or `chromadb_2026-06-07_090035_97748` —
both logged full success with a completed restore test.

---

## Finding 4 — The health log itself is UTF-16, and every downstream reader expects UTF-8

`dex-health-log.jsonl` — despite the extension, is not line-delimited UTF-8
JSON. It is UTF-16LE, growing at ~3,000+ "lines" per run because it's also
pretty-printed multi-line JSON rather than one compact object per line.

**Root cause found exactly:** the scheduled task invokes
`powershell.exe -Command "... >> dex-health-log.jsonl"`. Windows PowerShell's
`>>` is `Out-File -Append`, whose default encoding is UTF-16LE. This is the
same class of bug ddl-org's own `CLAUDE.md` documents as "Trap A" — a
different repo, an identical mechanism, independently produced.

**Attempted fix, blocked by permissions, documented instead of forced:**

```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument `
  '-ExecutionPolicy Bypass -Command "cd C:\Users\dexjr\dex-rag; python dex_health.py --json 2>&1 | Out-File -FilePath C:\Users\dexjr\dex-rag\dex-health-log.jsonl -Append -Encoding utf8"'
Set-ScheduledTask -TaskName "DexHealthCheck" -Action $action
```

`Set-ScheduledTask` returned `Access is denied` — modifying a scheduled task
needs elevation this session doesn't have, and forcing that is a system-
settings change that is yours to run, not mine. **The command above is ready
to paste into an elevated PowerShell prompt.** Nothing else needs to change;
`dex_health.py` itself was verified to already open its OWN reads with
`encoding="utf-8"` — it never wrote the file in UTF-16 itself, the wrapper
redirection did.

---

## Finding 5 — GAP D1 (April: "no external content pipeline") is stale. It was built.

`DexExternalFetch` is a live scheduled task, ran successfully today
(`LastResult=0`). The April gap assessment's #3-ranked high-impact
recommendation has already shipped, sometime in the four months since. The
April document should not be read as current backlog without this correction.

---

## What is CLOSED, SUPERSEDED, or STILL LIVE — reconciling the April audit batch

| April finding | File | Status today |
|---|---|---|
| 40% corpus garbage, awaiting go | `CORPUS_RECLASSIFICATION_2026-04-17.md` | **CLOSED** — measured resolved, Finding 1 above |
| "F-codes" returns embedding floats | `GAP_ASSESSMENT` GAP B1 | **CLOSED** — same measurement |
| `dex-convert.py` silent data loss | `CLAUDE.md` Critical Bug #1 | **CLOSED 2026-08-04** — already recorded in current `CLAUDE.md`, predates this excavation |
| No external content pipeline | `GAP_ASSESSMENT` GAP D1 | **CLOSED** — `DexExternalFetch` live and passing |
| No health check scheduling verified | `GAP_ASSESSMENT` GAP C1 | **SUPERSEDED** — it is scheduled and running; the real live issues are Findings 3 and 4 above, neither of which April could have found |
| Repo backup reliability | *(not in April scope at all)* | **NEW, found today, FIXED** — Finding 2 |
| ChromaDB backup corruption / silent sweep error | *(not in April scope at all)* | **NEW, found today, OPEN — needs your decision** |
| No PDF ingestion (GAP A2), no retrieval benchmarks (GAP B4), no primer freshness check (GAP C4), log rotation (GAP C3), auto-classification (GAP G1), drift detection (GAP G3) | `GAP_ASSESSMENT` | **UNVERIFIED today, not re-measured** — plausible these are still open, but this excavation did not re-check each one individually. Treat as a starting list for a future pass, not a current fact. |

---

## Part 2 -- reconciling the rest of GAP_ASSESSMENT_2026-04-17.md

Continued on the same instruction ("dig in, tokens authorized"). Same rule:
nothing below is trusted from April without live re-verification today.

### GAP A2 (PDF ingestion) -- CONFIRMED STILL OPEN

`dex-convert.py` has zero references to PDF, pdfplumber, or PyPDF anywhere in
the file. The single PDF-related hit anywhere in the ingest path is a comment
about the sequestration exclusion gate, unrelated to extraction. Exactly as
April found it. No drift, no partial progress.

### GAP B4 (retrieval quality benchmarks) -- MIXED: the right tool got built,
### the wrong thing got scheduled, and it has probably never once succeeded

`dex-eval-retrieval.py` exists, dated **2026-08-04** -- three days before this
excavation, not April. It runs and produces real output:

```
dex_canon_v2  (67,093 chunks)
  on vs off-domain   gap +0.083   SEPARABLE
  on vs degenerate   gap -0.082   OVERLAPPING
  at the LIVE MAX_DISTANCE = 0.62:
    real questions REFUSED    2/10
    greetings ACCEPTED        4/10
    off-domain ACCEPTED       0/6
```

**This is a live, current, measurable retrieval-quality problem**, not an
April leftover: at the threshold actually in production, one in five
legitimate questions gets refused, while four in ten greetings get accepted
as though they were on-domain content. **Not touched.** `MAX_DISTANCE` is a
routing/scoring parameter -- Rule 10 requires operator approval before any
change, and this is squarely that.

**Separately, `DexWeeklyEval` -- the scheduled task that should be running
retrieval quality checks -- does not call this script at all.** It runs:

```
python dex-council.py --from-file prompts\EVAL-WEEKLY.txt --all --rag --save council-runs\eval-2026-04-17 --ingest
```

**`--rag` is not, and has never been, a valid flag on `dex-council.py`.**
Confirmed from the script's own `--help`: RAG is on by default, disabled only
via `--no-rag`. `--rag` does not exist in the argument parser. Running the
exact scheduled command live reproduces the failure immediately:

```
dex-council.py: error: unrecognized arguments: --rag
```

**This fails at argument parsing, before a single line of output is
produced.** `council-runs/eval-2026-04-17/` does not exist on disk, confirming
the task has never gotten far enough to write anything. Given the flag has
apparently never been valid, `DexWeeklyEval` has likely **never once
succeeded** since it was scheduled -- not "stopped working," never worked.

**Secondary defect in the same command, lower priority:** the save path is
hardcoded to `eval-2026-04-17` rather than a dynamic date. Even with `--rag`
removed, every future weekly run would write into the same April-dated folder,
mixing or overwriting each week's output. Worth fixing in the same pass as the
flag, not separately.

**Fix identified, attempted, blocked by the same permission wall as
Finding 4:**

```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument '-ExecutionPolicy Bypass -Command "cd C:\Users\dexjr\dex-rag; python dex-council.py --from-file prompts\EVAL-WEEKLY.txt --all --save council-runs\eval-<DATE> --ingest"'
Set-ScheduledTask -TaskName "DexWeeklyEval" -Action $action
```

`Set-ScheduledTask` returned `Access is denied`, identical to Finding 4.
**Both scheduled-task fixes need the same elevated session to apply** -- worth
doing together rather than two separate elevation requests.

### GAP C3 (log rotation) -- CONFIRMED STILL OPEN

No rotation logic in any `.py` file. Current sizes, largest first:
`dex-health-log.jsonl` 160,852 bytes, `dex-bridge-log.jsonl` 149,095,
`dex-sweep-log.jsonl` 73,611, `dex-repo-backup-log.jsonl` 60,026 (this one
will keep growing now that Finding 2 is fixed and backups run again),
`dex-fetch-log.jsonl` 55,460. None yet large enough to be a performance
problem, exactly as April assessed. Still nobody's problem until it is.

### GAP C4 (primer freshness check) -- CONFIRMED STILL OPEN

Zero references to primer age, freshness, or hash comparison anywhere in
`dex_health.py`. Not attempted, not partial. `DDL_PRIMER.md` can go stale with
nothing to notice.

### GAP G1 (auto-classification) -- CONFIRMED STILL OPEN, unchanged from April

`infer_source_type()` and `classify_tier()` in `dex-ingest.py` are exactly as
April described them: filename-pattern heuristics, no content-based or
LLM-based classification step. Still true today, word for word.

### GAP G3 (drift detection) -- CONFIRMED STILL OPEN

No file, function, or reference matching drift detection anywhere in the repo
root. Never started.

### Updated reconciliation

| April finding | Status after Part 2 |
|---|---|
| GAP A2 -- PDF ingestion | **STILL OPEN**, unchanged |
| GAP B4 -- retrieval benchmarks | **PARTIALLY BUILT, SCHEDULED WRONG.** The eval tool exists and works; the scheduled job runs a different, permanently-broken command. Also revealed a live, unrelated retrieval-quality problem (2/10 real questions refused at the current threshold) that April could not have found because the tool didn't exist yet. |
| GAP C3 -- log rotation | **STILL OPEN**, unchanged |
| GAP C4 -- primer freshness | **STILL OPEN**, unchanged |
| GAP G1 -- auto-classification | **STILL OPEN**, unchanged |
| GAP G3 -- drift detection | **STILL OPEN**, unchanged |

Every remaining item in `GAP_ASSESSMENT_2026-04-17.md` has now been
individually re-verified against live state. None of it should be re-read as
current fact without this reconciliation from this point forward.

---

## Why this matters more than any single bug

**You said this is exactly why you've never been able to trust Dex Jr.** The
mechanism, precisely: a real, serious-sounding finding (40% garbage corpus)
got written up in detail, correctly diagnosed, given a clear remediation plan
— and then **the loop never closed.** It sat as "AWAITING OPERATOR GO" for
four months while something else silently fixed it, and nothing in the system
ever told you it was fixed. If you'd asked Dex Jr. "is my corpus clean?" any
time in that window, the honest answer required someone to actually query the
live database rather than trust the last document written about it — and nothing
in the pipeline does that automatically.

**The backup and health-check findings are the same mechanism at smaller
scale.** A scheduled task can report `LastResult=0` while the thing it was
supposed to verify has been broken for 47 days, because the failure was
recorded in a log nobody reads in a format nothing else can parse.

**The fix that matters isn't any one of tonight's three patches. It's GAP G4
from April, still unactioned:** anomaly detection in the health check — "3
consecutive sweep failures" or "backup >96h old" should be loud, not something
that requires a human to decode a UTF-16 file to discover.

---

## Actions taken tonight (reversible, documented, low-risk per the operator's
authorization — none touch corpus data)

1. `git config --global --add safe.directory "D:/DDL_Backup/repos/*"` —
   fixes repo backup, verified working.
2. This document, plus a session log entry (see
   `~/DDL_SessionLogs/dex-rag_sessionlog_8.7.2026.md`).
3. The six genuinely-uncommitted synthesis documents committed to git for
   the first time -- four months of findings that existed only on one disk
   now have history. (Corrected count -- see above. The other 25 files in
   this folder were already safe.)

## Actions NOT taken, and why

1. **ChromaDB backup corruption (Finding 3) — not touched.** Corpus/backup
   data per Rule 8. Needs your call on whether to delete the corrupted
   snapshot or investigate further first.
2. **Health log encoding fix (Finding 4) — command prepared, not executed.**
   Blocked by permissions, and modifying a scheduled task is a system setting
   change that should be yours to run.
3. ~~The rest of the April `GAP_ASSESSMENT` backlog — not re-verified
   item by item.~~ **DONE in Part 2, same session.** All six remaining items
   individually re-checked against live state. Four confirmed unchanged
   (A2, C3, C4, G3, G1). One found partially built and wrongly scheduled
   (B4). See Part 2 below for the full reconciliation.
4. **`MAX_DISTANCE` retrieval threshold — not touched.** Rule 10. `dex-eval-
   retrieval.py`'s live output (2/10 real questions refused, 4/10 greetings
   accepted at the current threshold) is a scoring/routing finding, and
   changing it is an operator decision, not an execution one.
5. **`DexWeeklyEval`'s broken command — not fixed.** Same permission wall as
   Finding 4; both scheduled-task fixes are ready for the same elevated
   session.

---

*Filed per dex-rag CLAUDE.md Template 1 (Audit Report) in spirit, restructured
around what changed since April rather than a fresh full-repo pass. Every
number in Findings 1–5 above was measured against the live system on
2026-08-07, not carried forward from April.*
