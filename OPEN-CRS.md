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

**Status:** CLOSED
**Opened:** 2026-04-16
**Closed:** 2026-04-16
**Resolution:** Step 50.2 (commit a11d661). Hard gate added at top of
`ingest()` in `dex-ingest.py`. Blocks any `--collection dex_dave*`
(covers `dex_dave`, `dex_dave_v2`, any future suffix). Fires before
backup check, collection access, or chunking. `sys.exit(1)` with clear
error. No bypass flags. `router_config.json` does not exist in the repo
— gate is enforced in code only.
**Source:** ADR-CORPUS-001 Rule 3

### Problem
`dex_dave` collection is HARD-GATED per ADR-CORPUS-001 Rule 3: "Never
ingest to dex_dave under any circumstance." Was unenforced in code.

---

## CR-DDL-SOAK-RENAME-001

**Status:** OPEN — Council review filed, verdicts due 2026-04-21
**Opened:** 2026-04-16
**Author:** Seat 1002 (Marcus Caldwell, LLMPM)
**Source:** Step 33c soak period governance
**Full document:** `prompts/CR-DDL-SOAK-RENAME-001.txt`

### Summary
Governs the retirement of the `_v2` collection suffix and deletion of
the legacy nomic-embed-text collections after the 14-day soak period
(target: 2026-04-28). Three paths evaluated: Path A (ChromaDB rename
in place), Path B (suffix flip, no rename), Path C (full rebuild).
Recommendation: Path A if ChromaDB `modify(name=)` is safe, Path B
otherwise.

### Scope
- ChromaDB collection rename or key update (4 live + 1 provisioned)
- Code updates across 8 files (suffix references)
- Ingest cache file rename
- Legacy nomic collection deletion (~11 GB disk recovery)
- CLAUDE.md, knowledge-vault, DDL site references

### Blocking prerequisites
- Soak period passes without retrieval quality complaints (14 days from 2026-04-14)
- Council verdicts on path selection (Q9a-Q9e)
- Pre-ceremony backup verified
- Path A viability confirmed (ChromaDB rename test on throwaway collection)
- Operator ceremony GO

### Timeline
- 2026-04-21: Council verdicts due
- 2026-04-21-27: Path A viability test
- 2026-04-28: Ceremony execution (if soak passes + council LOCK)
- 2026-04-29: First sweep on renamed collections = ceremony LOCK
