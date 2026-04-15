# OPEN-CRS.md

Tracking file for open Change Requests (CRs) in dex-rag.
Each CR is a queued governance/implementation item awaiting a dedicated
session. Pre-flight plan + operator approval required before execution
per CLAUDE.md Rule 5 and Rule 10 as applicable.

---

## CR-DDL-INGEST-FAST-SCOPED-001

**Status:** Queued — approved for dedicated session
**Opened:** 2026-04-15
**Source:** SWEEP_INGESTION_AUDIT_2026-04-15.md §9
**Related:** CLAUDE.md Open Items → Critical Bug #3 (scoped+fast file skip)

### Problem
When `dex-ingest.py` is invoked with both `--fast` and a non-default
`--collection` (e.g., `dex_canon_v2`, `dex-bridge`, `dex-council`, `dex-sweep`,
`fetch_ext_creators`), the file-level skip at `dex-ingest.py:370-374` becomes
a no-op. Entire files are re-chunked and re-embedded on every run.

Upsert against deterministic chunk IDs prevents duplicate rows, so the corpus
stays clean — but GPU time, embedding budget, and sqlite I/O are burned on
every nightly sweep. The 2026-04-15 sweep is the reference case: 6 files
re-processed, 0 net chunk delta, sqlite modified.

### Proposed fix
File-hash → chunk-id-prefix cache in collection metadata. On `--fast` scoped
runs, look up the file hash in the collection's metadata map; if present with
a matching chunk-id-prefix, skip. On miss, process and record.

### Scope (pre-flight not yet written)
- Touches `dex-ingest.py` (ingest pipeline — Rule 5 sensitive)
- Affects ChromaDB collection metadata (data layer — Rule 5 + Rule 8 sensitive)
- Affects sweep behavior (live infrastructure — Rule 13)
- Requires backup verification before first live run

### Blocking prerequisites
- Pre-flight plan (Template 3) drafted and approved
- Dry-run on a test collection with representative files
- Backup verified at `D:\DDL_Backup` before first live run
- Verification of next sweep's `chunks_written` and sqlite mtime

### Notes
- Cosmetic drift to clean up opportunistically on next `dex-sweep.py` edit:
  line 6 docstring says `--collection dex_canon`, actual code passes
  `dex_canon_v2`. No standalone commit for this.
