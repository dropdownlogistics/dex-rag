# Step 33c Part B — Test collection drop + Part A correction

**Date:** 2026-04-14
**Scope:** Destructive DB op on two test collections. No code changes.

## Test collections dropped

| Collection | Pre-drop count | Post-drop |
|---|---:|---|
| `dex_canon_mxbai_test` | 2,500 | gone (NotFoundError on get) |
| `dex_canon_mxbai_rechunk_test` | 10,000 | gone (NotFoundError on get) |

Remaining collections (8): `ddl_archive`, `ddl_archive_v2`, `dex_canon`,
`dex_canon_v2`, `dex_code`, `dex_code_v2`, `ext_creator`, `ext_creator_v2`.

## Part A correction — 01bc5548 IS an orphan

STEP33C Part A (this morning's inspection report) claimed that HNSW
directory `01bc5548-54bb-4b15-a27f-509a817cfa46` in `C:\Users\dkitc\.dex-jr\chromadb\`
was a "currently-active Chroma collection segment" and recommended
removing it from the orphan watch list.

**That claim was wrong.** Verification via direct sqlite query:

```sql
SELECT id, collection FROM segments  -- 10 segment rows
SELECT id, name FROM collections     -- 10 collection rows
-- 11 live dirs in chromadb\ vs 10 segment ids => 1 orphan
-- 01bc5548 is the dir with NO matching segment id
```

STEP35 (`STEP35_HNSW_ORPHAN_QUARANTINE_2026-04-12.md`) correctly
identified `01bc5548-…` as an orphan. It remains an orphan. **The orphan
watch list is unchanged.** Part A's recommendation is hereby superseded.

Part A also noted that the live dir count (11) was "broadly consistent
with no spurious orphan creation from the 4:00 AM failure" — that framing
was correct; the error was only in calling `01bc5548` live.

## Post-drop live-dir state

- Live dirs: 11 (unchanged pre vs post drop — Chroma's `delete_collection`
  marks segments as inactive in sqlite but does not immediately remove
  segment directories from disk; they persist until next compaction)
- Collection rows in sqlite: 8 (10 − 2 dropped)
- Segment rows in sqlite: need re-verification after next compaction
- Expect 2 additional orphan dirs (the 2 dropped test collections' segment
  dirs) to appear on the filesystem until Chroma cleans them up. These
  should be added to a follow-up orphan sweep, not quarantined here
  (quarantining a segment while it's still sqlite-referenced risks
  corrupting the live DB).
