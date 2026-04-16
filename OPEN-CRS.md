# OPEN-CRS.md

Tracking file for open Change Requests (CRs) in dex-rag.
Each CR is a queued governance/implementation item awaiting a dedicated
session. Pre-flight plan + operator approval required before execution
per CLAUDE.md Rule 5 and Rule 10 as applicable.

---

## CR-DDL-INGEST-FAST-SCOPED-001

**Status:** CLOSED
**Opened:** 2026-04-15
**Closed:** 2026-04-16
**Resolution:** Step 48 (commits b62e67e, 823daf0, 6bd5c73, efccab4).
Ingest cache with SHA-256 content hashing replaces deterministic ID skip
logic. Per-collection JSON cache enables true file-level deduplication
(content-aware, not ID-aware). Corpus can grow on next sweep.
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

---

## CR-DDL-WEIGHTS-SYNC-001

**Status:** CLOSED
**Opened:** 2026-04-15
**Closed:** 2026-04-16
**Resolution:** Verified during Step 49. ext_creator base_weight was
already 0.85 at time of verification. No code change needed.

---

## CR-DDL-WEIGHTS-INTEGRATION-001

**Status:** CLOSED
**Opened:** 2026-04-15
**Closed:** 2026-04-16
**Resolution:** Step 49 (commits a50b7e3, b3a1aa0, fe44fa8).
dex_weights.py modernized (mxbai-embed-large, _v2 suffix, phantom
collections ext_canon/ext_archive removed) and wired into
dex_jr_query.py. Retrieval now ranked by weighted_score. Self-test
passes, standalone query works.

---

## CR-DDL-DEXDAVE-GATE-001

**Status:** OPEN
**Opened:** 2026-04-16
**Source:** ADR-CORPUS-001 Rule 3

### Problem
`dex_dave` collection is HARD-GATED per ADR-CORPUS-001 Rule 3: "Never
ingest to dex_dave under any circumstance." Currently unenforced in code.
Nothing prevents `python dex-ingest.py --collection dex_dave_v2 --path ...`
from writing to a collection that should never receive automated ingest.

### Required fix
Add a hard gate at the top of the `ingest()` function in `dex-ingest.py`
that checks the `--collection` argument against `dex_dave*` patterns and
exits with `sys.exit(1)` before any DB access occurs.

### Notes
- `router_config.json` does not exist in the repo. The gate must be
  enforced in code, not configuration.
