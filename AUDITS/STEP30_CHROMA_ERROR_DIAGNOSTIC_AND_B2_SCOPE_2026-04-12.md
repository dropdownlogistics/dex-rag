# STEP 30 — ChromaDB Error Diagnostic + B2 Scope

**Date:** 2026-04-12
**CR:** Phase 2 Step 30
**Operator:** Dave Kitchens
**Executor:** Claude Code (Dex Jr., Seat 1010)
**Scope:** Diagnosis + B2 scoping. No implementation of new retrieval features.

---

## Headline

**Finding 1** — The reported "hnsw segment reader: Nothing found on
disk" error was **not reproducible**. All queries against all 4
collections (with and without `--no-prefilter`, singly and merged)
succeed. Filesystem scan shows 7 orphan HNSW directories on disk
that are unreferenced by `segments` table — safe to leave, safe to
clean up. No corruption in live collections. No action required.

**Finding 2 — confirmed**. All three test identifiers
(`CR-OPERATOR-CAPACITY-001`, `ADR-INGEST-PIPELINE-001`,
`PRO-DDL-SPIRAL-001`) live as chunk **body** content in
`dex_canon`, not as standalone `{ID}.txt` files. B3's filename
prefilter correctly returns 0 hits for all three. **B2 is the fix**:
fallback `$contains` query when B3 misses. Proposed for Step 31.

---

## Part A — Finding 1 Diagnostic

### A1. Reproduction attempt

```
python dex_jr_query.py "What does CR-OPERATOR-CAPACITY-001 say?"
```

Ran clean. Retrieved 5 chunks across dex_canon + ddl_archive with
valid distances (219-243). No error, no traceback.

### A2. Narrowing

All variants succeeded:

| Variant | Result |
|---|---|
| default (all 4 collections, B3 on) | OK |
| `--no-prefilter` | OK |
| `--collection dex_canon` | OK |
| `--collection ddl_archive` | OK |
| `--collection dex_code` | OK |
| `--collection ext_creator` | OK |

**Conclusion: the error was transient.** Most likely cause: a race
with the 09:00 sweep that rebuilt the CANON_DIR HNSW segment, or a
short window where a write was in progress while a read was issued.
Not reproducible after settling. Not actionable as a code change.

### A3. Filesystem scan

`C:\Users\dkitc\.dex-jr\chromadb\` contents:

- `chroma.sqlite3` — **9.34 GB** (healthy, grows with corpus)
- 11 UUID directories

Of those 11 UUID directories:
- **4 match live `VECTOR` segments** (one per collection) — healthy,
  sizes match expected chunk counts
- **7 are orphans** — not referenced in `segments` table

### A5. Segment UUID cross-reference

From `chroma.sqlite3` `segments` table:

| Segment UUID | Collection | Scope | On disk? |
|---|---|---|---|
| `927ef2f1-…-16a05160e201` | ext_creator | VECTOR | YES (321 KB) |
| `29dca8d3-…-19caeb59acda` | ext_creator | METADATA | no (expected) |
| `6cc8e21b-…-27225c3a80fd` | dex_code | VECTOR | YES (64.7 MB) |
| `a7c6a0d8-…-d83e6bedb06e` | dex_code | METADATA | no (expected) |
| `c99ad37a-…-67cc69d22c85` | dex_canon | VECTOR | YES (787 MB) |
| `f5b9c720-…-e494d01d84bd` | dex_canon | METADATA | no (expected) |
| `dc4f170f-…-d57a6a1a52bc` | ddl_archive | VECTOR | YES (936 MB) |
| `a657a589-…-b4e6ef68fb57` | ddl_archive | METADATA | no (expected) |

All 4 `METADATA` segments are `urn:chroma:segment/metadata/sqlite`
→ their data lives inside the central `chroma.sqlite3`, not in a
per-segment directory. "Not on disk" is normal for this segment
type. **Not corruption.**

**Orphan dirs on disk, 7 total, all exactly 321,700 bytes:**

```
0b705eaf-e4e9-4f57-9bb1-5d32d068290e
15293f76-85e2-4ad2-9a48-2ddd3441db6e
42cf23b1-91bf-4529-bdf6-853620c8d670
af065713-9c5c-4bc5-bc00-4dbc304474c7
b2e6b7f8-0640-438a-931c-f1d4006498f3
f4df1db7-8cc8-4068-aac7-df483c0a3e69
fd9ae559-f423-4dbf-a636-98e8177b6068
```

321,700 bytes = default empty-HNSW allocation (`data_level0.bin`
321,200 + `header.bin` 100 + `length.bin` 400 + `link_lists.bin` 0).
These are the skeletal indexes of collections that were created and
then either dropped or superseded during the six months of iteration.
They are unreferenced; Chroma does not open them; they cost ~2.2 MB
of disk total.

Two of them (`f4df1db7-…`, `af065713-…`) match UUIDs flagged in
earlier audits as "orphan segments." They've been stable for months.

### A4. Backup cross-reference

Most recent backup: `D:\DDL_Backup\chromadb_backups\chromadb_2026-04-12_1730`
(refreshed during Step 24 manual ingest). Earlier backups from
sweep runs (`_0712`, `_0900`) also present. STD-DDL-BACKUP-001's
Trigger 6 (restore test) has been firing successfully. Backup
surface is healthy.

### A6/A7 — Disposition

**No fix required, no halt needed.** The error was transient. The
orphan dirs are cosmetic debt, not a correctness issue. The operator
may choose to:

- **Leave as-is** (recommended): 2.2 MB is negligible; removing
  them risks a mistake that breaks a live segment by fat-finger
- **Clean up in a future step**: move them to a quarantine dir
  under `D:\DDL_Backup\orphan_segments\` first, verify collections
  still query clean, then delete

No operator decision is urgent.

---

## Part B — Finding 2 & B2 Scope

### B1. Body-content verification (chroma `$contains`)

Ran `col.get(where_document={"$contains": ident})` for each of the
three identifiers against each of the 4 collections:

| Identifier | dex_canon hits | ddl_archive | dex_code | ext_creator | source_files containing identifier |
|---|---:|---:|---:|---:|---|
| `CR-OPERATOR-CAPACITY-001` | 5 | 0 | 0 | 0 | `89_LLMPM Boot Prompt and Q and A.txt` |
| `ADR-INGEST-PIPELINE-001` | 5 | 0 | 0 | 0 | `89_LLMPM Boot Prompt and Q and A.txt`, `89_LLMPM Claude Code Session - 4.11.26.txt` |
| `PRO-DDL-SPIRAL-001` | 5 | 0 | 0 | 0 | `83_MarcusCaldewellPM.txt`, `DDLCouncilReview_SpiralProtocol.txt` |

For comparison, B3 source_file prefilter:

| Identifier | `{ID}.txt` / `.md` / `Draft.txt` matches |
|---|---:|
| `CR-OPERATOR-CAPACITY-001` | **0** |
| `ADR-INGEST-PIPELINE-001` | **0** |
| `PRO-DDL-SPIRAL-001` | **0** |

**Confirmed: the content exists, but not under the identifier's
filename.** It lives inside thread files and council review
transcripts. B3 alone cannot reach it. B2 would.

ChromaDB `1.5.2` — `where_document.$contains` is supported and
returned results cleanly above. Case-sensitive on substring match.

### B2. Design proposal

**Name:** B2 — body-contains fallback prefilter.

**Trigger:** query contains one or more identifiers (same regex as
B3) AND B3's source_file prefilter returns 0 chunks for that
identifier.

**Behavior:** for each unmatched identifier, run
`col.get(where_document={"$contains": identifier}, limit=BODY_MATCH_PER_COL)`
against each searched collection. Surface hits between B3 (which
returned nothing for these idents) and the vector results. Tag
hits as `retrieval_source: "prefilter_body_match"` so markdown
output can show `[BODY MATCH]` distinct from `[PREFILTER MATCH]`.

**Per-collection limit:** `BODY_MATCH_PER_COL = 3` (configurable).
Prevents flood when an identifier is referenced in many files
(e.g., `STD-DDL-LOG-001` cross-referenced everywhere).

**Ordering in merged output:**
1. B3 filename-match chunks
2. B2 body-match chunks
3. Vector-search chunks
- Dedupe by `(collection, chunk_id)` (already implemented).

**Case sensitivity:** governance identifiers are ALL-CAPS by
convention. `$contains` is case-sensitive. Pass identifier as
extracted (uppercase). If the corpus happens to have lowercase
mentions the user wanted, that's an open question — current
recommendation is to stay case-sensitive to avoid surfacing
spurious matches like "adr-ingest-pipeline-001" buried in code
comments or emails.

**LOC estimate:** ~40 lines in `dex_jr_query.py`:
- a `body_match_prefilter()` helper modeled on
  `prefilter_by_source_file()`
- one call site in `run_query()` between the existing B3 block and
  the vector search, guarded by `if idents and not prefilter_hits`
  (or more surgically per-identifier if the operator wants mixed
  B3+B2 on the same query)
- a new `--no-body-match` flag if testing needs it
- markdown output extension to show `[BODY MATCH]`
- one self-test canary assertion

**Open questions for Step 31:**
1. Should B2 fire for identifiers that B3 *partially* matched (e.g.
   B3 finds `STD-DDL-SWEEPREPORT-001.txt` but the operator also
   wants to see every other file that cites it)? Proposal: no —
   B3 hits suppress B2 for that identifier. Keep behavior
   predictable.
2. How aggressive should the per-collection limit be? Proposal: 3.
   Revisit after real-workflow testing.
3. Should the B2 body-match tag the *matched identifier* separately
   from the filename-match? Proposal: yes — add `matched_identifier`
   field, mirroring B3.
4. Case sensitivity policy — stay case-sensitive (proposed) or
   lowercase-normalize? Proposal: stay case-sensitive; governance
   identifiers are capitalized, lowercasing invites false positives.

### B3. Recommendation

**Step 31:** Implement B2 as scoped above. ~40 LOC. Pure retrieval
layer. No corpus changes. Reversible via `git revert`. Covers the
broad class of "operator queries an identifier that's discussed in
many files but not filed under its own name" which is the dominant
failure mode after B3.

No new investigation prerequisites. Ship.

---

## Appendix A — Reproduction commands

```bash
# A2 narrowing
python dex_jr_query.py "What does CR-OPERATOR-CAPACITY-001 say?"
python dex_jr_query.py "What does CR-OPERATOR-CAPACITY-001 say?" --no-prefilter
python dex_jr_query.py "What does CR-OPERATOR-CAPACITY-001 say?" --collection dex_canon
# ... etc per collection
```

All returned exit code 0 with markdown output.

## Appendix B — SQLite introspection

```sql
SELECT id, collection, scope, type FROM segments ORDER BY collection;
SELECT id, name FROM collections;
```

Outputs captured inline in §A5.

## Appendix C — Body-contains raw output

See §B1 table. Raw pull script is inline in the session log.

## Appendix D — ChromaDB version

`chromadb 1.5.2` — supports `where_document.$contains`. No caveats
observed during this investigation.

## Appendix E — Orphan dir disposition draft

If the operator wants the 7 orphan directories cleaned up later,
proposed steps (NOT executed in this step):

1. Create `D:\DDL_Backup\orphan_segments\` if absent
2. For each of the 7 UUID dirs: `mv <dir> D:\DDL_Backup\orphan_segments\`
3. Run `python dex_jr_query.py --self-test` — must still pass
4. Run a handful of real queries across all 4 collections — must
   succeed
5. If good after a day or two of use, delete the quarantine dir
6. If any failure: move them back, halt, investigate

This is a cleanup-hygiene step, not a correctness fix.
