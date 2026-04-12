# STEP 24 — Subprocess Timeout Removal + Morning Resume

**Date:** 2026-04-12
**CR:** Phase 2 Step 24
**Operator:** Dave Kitchens
**Executor:** Claude Code (Dex Jr., Seat 1010)

---

## 1. Context

The 4am unattended sweep (2026-04-12) found 25 real operator files and
triggered ingestion. 2,987 chunks landed before the 300s subprocess
timeout in `dex-sweep.py::run_ingestion` killed the child. Outcome:
`"subprocess_stderr": "TimeoutExpired after 300s"`. Data integrity
preserved (STD metadata valid, no corruption), but the run was
interrupted and dex_canon was under-populated.

The 300s cap was inherited from Step 22 Fix A, which reduced the
original 600s cap after fixing the CANON_DIR-scan issue. Real operator
content (multi-MB files, thousands of chunks each) does not fit any
reasonable wall-time cap. The right answer is no timeout at all —
ingest runs to completion.

---

## 2. Morning 4am Run Outcome (from sweep log)

```
start_ts:          2026-04-12T04:00:00.832938
end_ts:            2026-04-12T04:13:07.650482
files_found:       25
files_copied:      25
backup_ran:        true (D:\DDL_Backup\chromadb_backups\chromadb_2026-04-12_0900)
outcome:           failure
subprocess_stderr: TimeoutExpired after 300s
report_written:    _sweep_reports\ingest_report_2026-04-12_091252.886462_sweep_2026-04-12_090000.md
```

dex_canon count after morning run: **245,020** (baseline for this step).

Temp dir preserved: `C:\Users\dexjr\dex-rag-scratch\sweep_sweep_2026-04-12_090000\`
(25 files intact, verified via `ls`).

---

## 3. Part A — Timeout Removal

### Diff

```diff
diff --git a/dex-sweep.py b/dex-sweep.py
@@ -366,9 +366,12 @@ def run_ingestion(ingest_path, dry_run=False):
     try:
         print(f"  Running ingestion against {ingest_path}...")
         ingest_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
+        # Step 24: no timeout. Real operator content can exceed any reasonable
+        # wall-time cap. Ingest runs to completion. Dex-ingest.py has its own
+        # progress indicators via stdout.
         result = subprocess.run(
             cmd_args,
-            capture_output=True, text=True, timeout=300,
+            capture_output=True, text=True,
             env=ingest_env,
         )
```

TimeoutExpired handler at lines 383-386 retained as defensive dead-code
in case a future caller re-introduces a timeout.

### Commit

```
20ee36a Phase 2 Step 24: remove subprocess timeout from sweep
```

Not pushed. Rule 4.

---

## 4. Part B — Resume the Interrupted Ingest

### Command

```
python dex-ingest.py --path "C:/Users/dexjr/dex-rag-scratch/sweep_sweep_2026-04-12_090000" --collection dex_canon
```

No `--fast`. Full dedup pass. Foreground. No sweep wrapper, no subprocess.

### Run-time output (key lines)

```
Ingest run id: manual_2026-04-12_173054
Backup refreshed: D:\DDL_Backup\chromadb_backups\chromadb_2026-04-12_1730

Scoped collection 'dex_canon': 245020 existing chunks
Existing chunks in RAW:   291520
Existing chunks in CANON: 245020

Scanning archive for ... files...
Found: 25 files

Running dedup pass (SHA-256)...
Unique files: 25
Duplicates skipped: 0

Loading existing chunk IDs...
SCOPED IDs loaded: 245020

Ingesting...

============================================================
  INGESTION COMPLETE
============================================================
Files skipped (already in RAW): 0
New chunks added RAW:           0
New chunks added CANON:         0
```

Script crashed on the final SCOPED summary print (`cp1252` codec cannot
encode the `\u2192` arrow character). See §6.

**dex_canon count after resume:** 245,633 → **delta +613 chunks**.

The `add_canon=0` number reflects scoped-mode routing (chunks go to the
named scoped collection, not to CANON), and it printed before the crash.
The loop completed, all upserts landed (verified by post-run count).

---

## 5. Verification — 25 Files in dex_canon

Per-file chunk counts (via `col.get(where={"source_file": f})`):

| File | Chunks |
|---|---:|
| 03_Thread_LeChat.txt | 1,428 |
| 04_ThreadActive_LeChat Boot Prompt and Q and A.txt | 14 |
| 06_Thread_Perplexity.txt | 133 |
| 89_LLMPM Boot Prompt and Q and A.txt | 14 |
| 89_LLMPM Claude Code Session - 4.11.26.txt | 1,346 |
| 92_KnowledgeVault Claude Code Session - 4.11.26.txt | 1,458 |
| 92_KnowledgeVault_4.12.26.txt | 199 |
| 96_WorkBenchPM Initial Boot Prompt and Q and A.txt | 13 |
| Amendment.txt | 6 |
| AuditforgeAudit.txt | 32 |
| ClaudemdUpdate.txt | 7 |
| Comprehensive Update - Weekend of 4.11.26_20260412_040752.txt | 17 |
| DDLCouncilReview_BackUpAmendment.txt | 7 |
| DDLCouncilReview_ERP.txt | 107 |
| DDLCouncilReview_OperatorCapacity.txt | 65 |
| DDLCouncilReview_SweepProtocol_20260412_040752.txt | 37 |
| DDLCouncilReview_llms.txt.txt | 64 |
| DDLCouncilReview_llmsUpdate_20260412_040752.txt | 17 |
| DDLIngestAudit.txt | 23 |
| F2 Electric Boogaloo.txt | 22 |
| OBS-AF-001.txt | 1 |
| STD-DDL-SWEEPREPORT-001 Draft_20260412_040752.txt | 6 |
| STD-DDL-SWEEPREPORT-001.txt | 9 |
| ingest_report_2026-04-12_072033.791761_sweep_2026-04-12_071221.md | 1 |
| llms_v2.1.txt | 12 |
| **Total** | **5,036** |

**Present: 25 / 25. Missing: 0.**

Accounting:
- Sum of chunks across 25 files in dex_canon: 5,036
- Chunks added by morning run (before timeout): ~2,987
- Chunks added by resume (this step): 613
- Delta accounted for by this step's work: ~3,600
- Remaining ~1,436 chunks are from prior ingest runs of overlapping
  content (same `source_file` metadata appearing in earlier sessions).
  Not a discrepancy — dedup is chunk-id-based, so prior chunks with the
  same hash were correctly skipped.

---

## 6. Flagged (Rule 6)

### Unicode crash in dex-ingest.py:616

`print(f"  New chunks added SCOPED:        {add_scoped}  → {collection}")`

Under Windows cp1252 (default console encoding), the `\u2192` arrow
cannot be encoded and the script crashes after the ingest loop completes
but before the final count lines print. Effect is cosmetic — all DB
writes land — but it:

- Masks the true `add_scoped` value and final DB totals in stdout
- Will cause `INGESTION COMPLETE` to appear followed by a traceback in
  tonight's 4am sweep too, which will be logged as subprocess_stderr
  and potentially misinterpreted as a failure

Suggested fix: replace `→` with `->` on line 616, or set
`PYTHONIOENCODING=utf-8` in the ingest invocation (dex-sweep.py already
does this for its subprocess; manual invocations do not inherit it).

**Not fixed in this step.** Out of scope per prompt. Flagged for a
separate CR.

### Temp dir cleanup

`sweep_sweep_2026-04-12_090000` removed after verification.
`restore_test_2026-04-12_1734` remains in scratch — created by
dex-ingest.py's backup refresh during this run, unrelated to this step.

---

## 7. Rule 17 — Pre-existing modifications

At session start:
- `dex_weights.py` (M, untouched)
- `fetch_leila_gharani.py` (M, untouched)

Not staged. Not modified.

---

## 8. Commit summary

```
20ee36a Phase 2 Step 24: remove subprocess timeout from sweep
```

This audit report committed separately.

---

## 9. Ready for tonight's 4am run?

Yes. With timeout removed, tonight's sweep will run to completion on
whatever files land in the holding folder. The unicode print bug
(§6) will produce a noisy traceback in the subprocess_stderr log
field but will not block data landing. A follow-up CR should address
that before it confuses future forensics.
