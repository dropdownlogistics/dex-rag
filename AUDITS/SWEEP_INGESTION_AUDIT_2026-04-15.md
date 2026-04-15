# SWEEP INGESTION AUDIT — 2026-04-15

**Scope:** Read-only diagnosis of why 6 swept files produced 0 new chunks
during the 4 AM sweep `sweep_2026-04-15_090001` (UTC 09:00 = 04:00 local).
**Rule 17:** `dex_weights.py` and `fetch_leila_gharani.py` untouched.
**No pipeline edits. No ChromaDB writes. No commits.**

---

## 1. Current chunk counts vs yesterday's baseline

From the 4 AM sweep report (`ingest_report_2026-04-15_111207.346316_sweep_2026-04-15_090001.md`),
live pipeline state post-sweep:

| Collection     | Post-sweep (2026-04-15) | Baseline (CLAUDE.md / b9fc28c) | Delta |
|---|---:|---:|---:|
| dex_canon      | 253,982 | — (v1, not in CLAUDE.md table) | n/a |
| dex_canon_v2   | 253,978 | 253,978 | **0** |
| ddl_archive    | 291,520 | — | n/a |
| ddl_archive_v2 | 291,520 | 291,520 | **0** |
| dex_code       |  20,384 | — | n/a |
| dex_code_v2    |  20,384 |  20,384 | **0** |
| ext_creator    |     922 | — | n/a |
| ext_creator_v2 |     922 |     922 | **0** |

All four live v2 collections are **unchanged**. Confirmed. Not a display issue.

Side note: `dex_canon` (v1, old) is 4 higher than `dex_canon_v2`. That gap is
pre-existing — unrelated to today's sweep. Flagging but not investigating.

---

## 2. ChromaDB sqlite mtime check

```
-rw-r--r-- 18,341,908,480 bytes  Apr 15 08:24  chroma.sqlite3
```

sqlite was modified at **08:24 local** (after the 04:00 sweep start and after
subprocess finish around 06:12). **Something WAS written.** Ingest was not a
complete no-op at the storage layer — ChromaDB absorbed writes, but the net
chunk count is identical. This is the signature of **upsert-on-same-IDs**:
chunks were re-computed, re-embedded, and upserted into existing IDs.

---

## 3. The 4 AM ingest_report contents

File: `C:\Users\dkitc\OneDrive\DDL_Ingest\_sweep_reports\ingest_report_2026-04-15_111207.346316_sweep_2026-04-15_090001.md`

```
ingest_run_id: sweep_2026-04-15_090001
triggered_at:  2026-04-15T09:00:01 UTC
outcome:       success
files_ingested: 6
chunks_written: 0
errors: 0
backup_ran: True
```

All six files listed:
- AuditForge Full Session Log - 4.14_.txt (279,521)
- KnowledgeVault and DexJr Audit - 4.14.26.txt (173,741)
- KnowledgeVault Full Session Log - 4.14.26.txt (803,666)
- LLMPM Full Session Log 4.14.26.txt (674,613)
- WebsitePM Full Session Log - 4.14.26.txt (951,601)
- ingest_report_2026-04-14_214740.406061_sweep_2026-04-14_213022.md (1,116)

Report narrative says *"6 file(s) ingested into dex_canon, producing 0 chunk(s)"*
— docstring still says "dex_canon" but code passes `dex_canon_v2` (see §4).
Report-narrative string is cosmetic drift only.

`chunks_written=0` is **parsed from dex-ingest.py stdout** at
`dex-sweep.py:199-205` — it scans for `"New chunks added SCOPED:"` /
`"New chunks added CANON:"` lines. If dex-ingest printed `0` for both, that's
what we get. So the 0 is authoritative *from dex-ingest's own perspective*.

---

## 4. Sweep → ingest argument tracing

`dex-sweep.py:361-362`:
```python
cmd_args = ["python", INGEST_SCRIPT, "--path", str(ingest_path),
            "--collection", "dex_canon_v2", "--fast", "--skip-backup-check"]
```

`dex-ingest.py:54`: `CANON_COLLECTION = "dex_canon_v2"` (Step 33c flip).
`dex-ingest.py:651,692`: CLI `--collection` flag is parsed and passed through
to the ingest function as `args.collection`, overriding the constant when
provided.

**Trace: sweep passes `--collection dex_canon_v2` → dex-ingest writes to
`dex_canon_v2`.** Target collection is correct. Not a misrouting bug.

Note: `dex-sweep.py:6` docstring still reads *"ingestion via dex-ingest.py
--collection dex_canon"* — stale docstring from before Step 33c. Cosmetic.
Fix on next dex-sweep.py edit, no standalone commit.

---

## 5. Hash check on the 5 session logs

**Skipped per operator decision** — evidence from §1, §2, §3 is sufficient.
The observable chain is:

- All 6 files processed with `errors=0`.
- dex-ingest returned `INGESTION COMPLETE`.
- Net chunk count delta: 0 across *every* collection.
- sqlite was modified (writes happened) but count is static.

Operative mechanism: **upsert on deterministic chunk IDs** combined with the
known `--fast` + scoped-collection bug (CLAUDE.md Open Item #3). When
`--fast` is used with a non-default `--collection`, the file-level skip
becomes a no-op. Files get re-chunked and re-embedded every run, but each
chunk's ID is stable (filename + offset), so upsert overwrites in place →
net zero.

This is the documented bug behaving exactly as documented. Not a new bug.

---

## 6. DDL_Ingest folder state

**The prompt's premise is incorrect: the top level of `DDL_Ingest` has NO
loose files.** It contains only 4 subfolders:
```
_duplicates/   _processed/   _review/   _sweep_reports/
```

All 6 files from this morning's sweep are in `_processed/`:
- AuditForge Full Session Log - 4.14_.txt ✓
- KnowledgeVault and DexJr Audit - 4.14.26.txt ✓
- KnowledgeVault Full Session Log - 4.14.26.txt ✓
- LLMPM Full Session Log 4.14.26.txt ✓
- WebsitePM Full Session Log - 4.14.26.txt ✓
- (ingest_report_*.md swept from `_sweep_reports/`)

`_processed/` currently holds **71 files** — normal accumulation from prior
sweeps.

**The sweep DOES move files on success.** `dex-sweep.py:343` performs
`shutil.move(f["source"], processed)` after copying to CANON_DIR + temp dir.
Workflow is option (a) from the prompt. No OneDrive re-sync battle.

---

## 7. _review/ and _duplicates/ state (OneDrive resurrection check)

**No resurrection.** Yesterday's manual tidy still intact:
- `_review/`:    8 files (SVG/PNG graphics)
- `_duplicates/`: 8 files (prior-day session logs + HTML/JSX duplicates)

Neither folder has lost entries, and the top level has no resurrected copies.
OneDrive is behaving.

---

## 8. Root-cause diagnosis

**Answer: (a), via the Open-Item-#3 mechanism.**

- Files were read and chunked by dex-ingest.
- Chunks were embedded (GPU time burned — the known waste).
- Chunks were upserted into `dex_canon_v2` against their deterministic IDs.
- Net chunk count delta: 0 across all collections.
- sqlite mtime confirms writes occurred; counts confirm no new IDs.

This is the **documented scoped+fast bug**, not a new failure. The five
.txt session logs were already in `dex_canon_v2` (almost certainly ingested
during the Step 33c rechunk / Step 46 / Step 47 work), so an upsert with
identical IDs produces no delta. The `ingest_report_*.md` was also in scope
but is small (1,116 bytes) and likely yielded no new chunks.

Rejected alternatives:
- **(b) wrong collection** — ruled out, §4 trace confirms `dex_canon_v2`.
- **(c) silent downstream failure** — ruled out, sqlite was modified and
  dex-ingest returned `INGESTION COMPLETE`.
- **(d) only the .md was ingested** — ruled out, all 6 appear in files_processed
  and `_processed/`.

---

## 9. Recommended fix scope

**Severity: routine — no bug fix required today.** The sweep worked as
designed given the known bug. The corpus is intact. No data loss. No
misrouting. OneDrive is not fighting the pipeline.

**Follow-up actions (approved):**

1. **CR-DDL-INGEST-FAST-SCOPED-001 (Step 48, queued):** fix CLAUDE.md Open
   Item #3 — scoped+fast file-level skip. Implementation per CLAUDE.md:
   file-hash → chunk-id-prefix cache in collection metadata. Payoff: sweep
   stops burning GPU on re-embedding identical content every night.
   Governance / weights-adjacent → requires pre-flight plan and operator
   approval before touching `dex-ingest.py`. **Not today. Dedicated session.**
2. **Cosmetic:** update `dex-sweep.py:6` docstring from
   `--collection dex_canon` → `--collection dex_canon_v2` on next edit to
   that file. No standalone commit.

**Declined:**
- Hash-verify diagnostic on the 5 .txt files — skipped, evidence sufficient.
