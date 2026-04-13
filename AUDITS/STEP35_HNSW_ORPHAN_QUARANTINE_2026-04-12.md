# STEP 35 — HNSW Orphan Directory Quarantine

**Date:** 2026-04-12 (spillover into 2026-04-13)
**CR:** Phase 2 Step 35
**Operator:** Dave Kitchens
**Executor:** Claude Code (Dex Jr., Seat 1010)
**Scope:** Filesystem cleanup. No ChromaDB API modification. No live-collection touch.

---

## Headline

7 orphan HNSW directories from Step 30 quarantined to
`C:\Users\dkitc\.dex-jr\chromadb_quarantine\`. Self-test confirms
all 10 ChromaDB collections (4 nomic + 4 _v2 + 2 test) open and
report counts cleanly post-move. Actual deletion deferred until
post-soak operator approval.

**One NEW orphan UUID surfaced** (`01bc5548-…`, 424 KB) that did
not exist at Step 30 time — almost certainly debris from the
Step 32/33a `delete_collection` + recreate pattern. Out of scope
for Step 35; flagged for operator decision.

---

## 1. Step 30 orphan UUIDs

Per `AUDITS/STEP30_CHROMA_ERROR_DIAGNOSTIC_AND_B2_SCOPE_2026-04-12.md` Appendix E, 7 orphan UUID directories were identified at Step 30 time, each exactly 321,700 bytes (empty-HNSW skeleton allocation: `data_level0.bin` 321,200 + `header.bin` 100 + `length.bin` 400 + `link_lists.bin` 0):

```
0b705eaf-e4e9-4f57-9bb1-5d32d068290e
15293f76-85e2-4ad2-9a48-2ddd3441db6e
42cf23b1-91bf-4529-bdf6-853620c8d670
af065713-9c5c-4bc5-bc00-4dbc304474c7
b2e6b7f8-0640-438a-931c-f1d4006498f3
f4df1db7-8cc8-4068-aac7-df483c0a3e69
fd9ae559-f423-4dbf-a636-98e8177b6068
```

## 2. Re-verification at Step 35 time

Cross-referenced against the current `segments` table in
`chroma.sqlite3`. The collection set has expanded since Step 30:
4 original nomic collections + 4 new `_v2` collections (Step 33b)
+ 2 test collections from Steps 32/33a = 10 collections, 20
segments referenced.

**All 7 Step 30 orphan UUIDs remain unreferenced.** Confirmed:
- None of them match a live VECTOR or METADATA segment
- None of them match the new `_v2` segment UUIDs

| UUID | Step 30 status | Step 35 status |
|---|---|---|
| 0b705eaf-…-5d32d068290e | orphan | still orphan |
| 15293f76-…-2ddd3441db6e | orphan | still orphan |
| 42cf23b1-…-853620c8d670 | orphan | still orphan |
| af065713-…-4dbc304474c7 | orphan | still orphan |
| b2e6b7f8-…-f1d4006498f3 | orphan | still orphan |
| f4df1db7-…-df483c0a3e69 | orphan | still orphan |
| fd9ae559-…-98e8177b6068 | orphan | still orphan |

## 3. UUIDs actually moved

All 7 UUIDs from §1 were `shutil.move`d from
`C:\Users\dkitc\.dex-jr\chromadb\` to
`C:\Users\dkitc\.dex-jr\chromadb_quarantine\`. Quarantine path
created on demand. **Move count: 7 / 7.** No partial moves, no
errors.

## 4. Post-quarantine collection self-test

Opened a fresh `chromadb.PersistentClient(path=...)` after the
moves. Listed collections, called `count()` on each:

| Collection | Count | Status |
|---|---:|---|
| ext_creator | 922 | OK |
| ext_creator_v2 | 922 | OK |
| dex_code | 20,384 | OK |
| dex_code_v2 | 20,384 | OK |
| dex_canon | 245,633 | OK |
| dex_canon_v2 | 245,633 | OK |
| ddl_archive | 291,520 | OK |
| ddl_archive_v2 | 291,520 | OK |
| dex_canon_mxbai_test | 2,500 | OK |
| dex_canon_mxbai_rechunk_test | 10,000 | OK |

**10 / 10 collections open and report counts. 0 failures.** Pre-
and post-quarantine counts identical.

## 5. Pre-quarantine vs post-quarantine collection count

Pre: 10 collections (verified just before quarantine).
Post: 10 collections (verified after quarantine).
Delta: 0.

## 6. Quarantine path for eventual deletion

```
C:\Users\dkitc\.dex-jr\chromadb_quarantine\
  0b705eaf-e4e9-4f57-9bb1-5d32d068290e\
  15293f76-85e2-4ad2-9a48-2ddd3441db6e\
  42cf23b1-91bf-4529-bdf6-853620c8d670\
  af065713-9c5c-4bc5-bc00-4dbc304474c7\
  b2e6b7f8-0640-438a-931c-f1d4006498f3\
  f4df1db7-8cc8-4068-aac7-df483c0a3e69\
  fd9ae559-f423-4dbf-a636-98e8177b6068\
```

Total ~2.2 MB. Future Step 36+ may delete the quarantine folder
after operator gives explicit approval and post-soak verification
confirms no regressions.

## 7. Flagged (Rule 6) — NEW orphan surfaced at Step 35

In addition to the 7 Step 30 orphans, the filesystem scan found
**one new orphan** that did not exist at Step 30 time:

```
01bc5548-54bb-4b15-a27f-509a817cfa46  size=424,100 bytes
```

Size differs from the Step 30 orphans (424 KB vs 322 KB) so it's
not the same kind of empty-skeleton allocation. Hypothesis: this
is the residue of a `client.delete_collection()` call in
`_step32_subset_build.py` or `_step33a_rechunk_builder.py` — both
scripts use a "drop if exists, then recreate" pattern, and Chroma's
delete may leave per-segment dirs unreferenced.

**Not moved in this step.** Step 35's prompt scope was the 7 Step
30 orphans only. The new orphan is similarly stable and similarly
small. Operator decision: include in a future cleanup, or leave.

## 8. Backup status

Most recent backup: `D:\DDL_Backup\chromadb_backups\chromadb_2026-04-12_1730`
(refreshed during Step 24, ~6h 23m old at the time of this step).
Within the prompt's 12h freshness window. No new backup forced.

If a rollback is needed for this step, the recovery is trivial:
```
move chromadb_quarantine\<uuid>\ chromadb\<uuid>\
```
No ChromaDB SQLite was touched; no segment table mutations
occurred. The 7 directories are recoverable in place by reversing
the move.

---

## Appendix A — Commands executed

```python
# Move
import shutil, os
src_root = r"C:\Users\dkitc\.dex-jr\chromadb"
quar = r"C:\Users\dkitc\.dex-jr\chromadb_quarantine"
os.makedirs(quar, exist_ok=True)
for u in [<7 step30 uuids>]:
    shutil.move(os.path.join(src_root, u), os.path.join(quar, u))
```

```python
# Self-test
import chromadb
c = chromadb.PersistentClient(path=r'C:\Users\dkitc\.dex-jr\chromadb')
for col in c.list_collections():
    col.count()  # all 10 succeeded
```

## Appendix B — Out of scope for Step 35

- The new orphan `01bc5548-…` (see §7)
- The two test collections themselves (`dex_canon_mxbai_test`,
  `dex_canon_mxbai_rechunk_test`) — these are scheduled for
  drop in Step 33c after soak
- The original 4 nomic collections — scheduled for drop in Step
  33c after soak
- Actual deletion of the quarantined dirs — deferred to a future
  step after operator confirms post-soak
