# Step 13: dex-acquire.py Path Typo Investigation

**Date:** 2026-04-11
**Auditor:** CC (executor) on behalf of Marcus Caldwell 1002 (advisor)
**Scope:** `dex-acquire.py` line 41 `CHROMA_PATH = r"C:\Users\dkitc.dex-jr\chromadb"` — missing backslash between `dkitc` and `.dex-jr`
**Predecessor:** CR-DEXJR-DDLING-001 Step 12 audit surprise #2

---

## Question

Does `C:\Users\dkitc.dex-jr\chromadb` exist as a shadow corpus containing quality-scored URL acquisitions, or has `dex-acquire.py` been silently failing since its initial commit?

---

## Finding

### **SCRIPT_DEAD**

`dex-acquire.py` was run **once** on 2026-03-23 06:16. The one execution opened a `chromadb.PersistentClient` at the typo path, which created a fresh empty Chroma DB file (`chroma.sqlite3`, 188 KB). The run failed somewhere before any collection was created or any chunk was written. The script has not been run successfully since, and there is **no data at the shadow path** that needs to be reconciled into the live corpus.

The typo path is harmless debris, not a shadow corpus. Nothing was lost because nothing was ever there.

---

## Evidence

### 1. Filesystem state at the typo path

```
C:\Users\dkitc.dex-jr\                          (dir, mtime 2026-03-23 06:16)
└── chromadb\                                   (dir, mtime 2026-03-23 06:16)
    └── chroma.sqlite3                          (188,416 bytes, mtime 2026-03-23 06:16:04.68)
```

- **No UUID segment directories** (a populated Chroma would have at least one HNSW segment dir per collection)
- **Single mtime** — nothing has touched the path since the initial creation moment
- **Total size: 184 KB** — this is consistent with Chroma's "schema only, no data" empty-DB state. For comparison, the legitimate live `chroma.sqlite3` is 8.7 GB.

### 2. SQLite schema + row counts (read-only query, no ChromaDB client)

Method: opened via `sqlite3.connect("file:.../chroma.sqlite3?mode=ro", uri=True)`. Ran `PRAGMA table_info` and `SELECT COUNT(*)` on every table. **No ChromaDB session was created against this file.**

Table row counts from the shadow sqlite:

| Table | Row count | Interpretation |
|---|---:|---|
| **`collections`** | **0** | **No collection was ever created** |
| **`embeddings`** | **0** | **No chunk was ever written** |
| **`segments`** | **0** | **No vector or metadata segment was ever allocated** |
| `embedding_metadata` | 0 | (consistent — no embeddings → no metadata) |
| `collection_metadata` | 0 | (consistent — no collections) |
| `segment_metadata` | 0 | (consistent — no segments) |
| `tenants` | 1 | Default tenant — Chroma creates this on schema init |
| `databases` | 1 | Default database — Chroma creates this on schema init |
| `migrations` | 18 | Chroma schema migrations ran to completion |
| `embeddings_queue_config` | 1 | Chroma internal queue config (schema default) |
| `embedding_fulltext_search_config` | 1 | FTS config (schema default) |
| `embedding_fulltext_search_data` | 2 | FTS internal bookkeeping (schema default, not user data) |
| `acquire_write` | 1 | Chroma write-lock bookkeeping (NOT related to dex-acquire.py — it's Chroma's own internal table) |
| all other tables | 0 | — |

### 3. Git history of the typo

```
git log --follow --format="%ai %h %s" -- dex-acquire.py
2026-03-14 20:02:59 -0500 0fa80e2 Initial commit — dex-rag v1.0

git blame -L 38,45 dex-acquire.py
^0fa80e2 (Dave Kitchens 2026-03-14 20:02:59 -0500 41) CHROMA_PATH = r"C:\Users\dkitc.dex-jr\chromadb"
```

The typo has been in the file since the **initial commit** on 2026-03-14 — not a recent regression, not introduced by any later edit. It shipped that way from day one.

The 9-day gap between file commit (2026-03-14) and shadow-path creation (2026-03-23) tells us dex-acquire.py was **not run immediately**. The operator committed the file, left it for 9 days, ran it once on the morning of 2026-03-23, and it presumably failed in a way that didn't leave an obvious trail.

### 4. No operator-facing artifacts

- No `dex-acquire-log.jsonl` anywhere in `C:\Users\dexjr\dex-rag\`, `C:\Users\dkitc\`, or `C:\Users\dkitc.dex-jr\`
  (`dex-acquire.py:51` defines `LOG_FILE = "dex-acquire-log.jsonl"` — a relative path written to the process cwd. If the script had reached its logging path, this file would exist somewhere reachable. It does not.)
- No `acquisition-plan.json` (docstring example suggests this as a `--from-plan` input) in any known project directory
- No evidence of `dex-acquire.py` being referenced by any other script, any sweep, any cron, or any session log

### 5. Cross-reference with legitimate path

- **Legitimate live corpus:** `C:\Users\dkitc\.dex-jr\chromadb\` — 8.7 GB sqlite + 9 UUID segment dirs, 542,914 chunks across 4 collections, actively written to (most recently by Phase 2 Step 6 at 2026-04-11 21:27)
- **Shadow typo path:** `C:\Users\dkitc.dex-jr\chromadb\` — 184 KB sqlite, 0 UUID dirs, 0 chunks, last touched 2026-03-23 06:16

The two paths are completely disjoint. `dex_weights.py:21` uses the legitimate path `C:\Users\dkitc\.dex-jr\chromadb` — that's why every other script that relies on `dex_weights.get_client()` hit the real corpus, and only `dex-acquire.py` (which has its own hardcoded `CHROMA_PATH` at line 41, not imported from `dex_weights`) ended up at the typo path.

### 6. Why the PersistentClient opened but no collection was written

Tracing the call path:

`dex-acquire.py:55-61`:
```python
def get_collection(name: str):
    client = chromadb.PersistentClient(path=CHROMA_PATH)    # line 56 — creates the DB file
    try:
        return client.get_or_create_collection(name=name)   # line 58 — creates the collection
    except Exception as e:
        print(f"  [ERROR] ChromaDB collection '{name}': {e}")
        sys.exit(1)
```

`get_collection()` is called from `dex-acquire.py:210` inside the ingest path. If the operator ran `dex-acquire.py --review-only` (the default per the docstring), the ingest path may not have been reached. But the shadow sqlite proves `PersistentClient()` WAS opened at least once. The most likely story:
- Operator ran `dex-acquire.py` with some args that caused `get_collection()` to be called at line 210
- Line 56 `PersistentClient()` initialized the DB → 18 migrations ran → sqlite file created, tenants/databases populated
- Something crashed BEFORE line 58 completed, OR the script exited between lines 56 and 58 (non-exception flow)
- Alternative: the script ran, reached line 58, but the collection creation itself raised → caught at line 59 → `sys.exit(1)` → but that would leave NO row in `collections`, which matches what we see

Any of those paths produces the observed state. The specific crash reason is unknowable from the evidence; what matters is that **no user data ever landed** and **no data-loss risk exists**.

---

## Recommendation

### **FIX_THEN_WIRE** (not DELETE, not WIRE)

Don't delete `dex-acquire.py`. The script has a clear and reasonable design:
- URL batch acquisition
- Per-URL fetch with polite throttling (1.5s delay)
- Quality gate via the `dexjr` local eval model (auto-ingest ≥7/10, flag-for-review 5-6, skip <5)
- Per-decision logging with reasoning
- Source-attribution header prepended to every ingested document

These are all features that would be useful in a properly-wired airtight pipeline. The only things wrong with the file are:
1. **The path typo** (one-character fix at line 41)
2. **No Trigger 3 gating** (needs `ensure_backup_current()` call before the `.add()`)
3. **No STD-DDL-METADATA-001 compliance** (needs `build_chunk_metadata()` for every chunk)
4. **Own `get_collection()` helper** duplicates `dex_pipeline`/`dex_weights` patterns — should be collapsed into the shared helpers when dex_core lands

The fix in a future Step 16 is:
1. Change line 41 to `CHROMA_PATH = r"C:\Users\dkitc\.dex-jr\chromadb"` (or, better, import `get_client` from `dex_weights` and remove the hardcoded path entirely — matches the pattern in `dex-ingest-text.py`)
2. Add `ensure_backup_current(expected_write_chunks=chunk_total)` after chunking
3. Replace manual chunk dict construction with `build_chunk_metadata()` calls
4. Test against a single URL with `--auto-ingest --collection dex_test`, drop `dex_test`, commit

**Cleanup of the shadow directory** (`C:\Users\dkitc.dex-jr\`) is a separate, optional step. It's 184 KB of inert debris. Can be deleted safely since we've now proven it contains zero data. But per the operator's governance principle ("nothing is ever deleted"), the safer play is to rename it to something like `C:\Users\dkitc.dex-jr.EMPTY_SHADOW_FROM_STEP13` and leave it as a historical marker. Either is fine; flagging for operator decision.

---

## Implications for Step 16

**Classification: `dex-acquire.py` → NEEDS_FIX_THEN_WIRE**

- **Risk of data loss from the typo:** **NONE.** The shadow path contains no chunks.
- **Risk of running the typo'd script as-is:** Low. If the operator reruns dex-acquire.py today without fixing line 41, the shadow path gets more Chroma activity but still writes to the wrong place. No harm to the legitimate corpus. But the time investment is wasted.
- **Blocker for Step 16 wiring:** Path typo fix must land BEFORE any wiring work, or the wiring work is wasted on the wrong DB.
- **Dependency:** None — the fix is standalone. Can be done at any time.
- **Sequence impact:** My Step 12 recommendation was "do Step 15 (investigate) before Step 16 (wire)." Step 13 closes Step 15. Step 16 (wire dex-acquire.py) is now unblocked whenever the operator chooses.

---

## Additional observations (non-blocking)

- **The shadow path `C:\Users\dkitc.dex-jr\` was created on 2026-03-23 06:16.** Interestingly, this is the same date and very close to the same time as the existing 19-day-old legitimate-path backup at `D:\DDL_Backup\chromadb\chroma.sqlite3` (mtime `2026-03-23 06:08:52`). These two events are ~8 minutes apart. The operator may have been doing some kind of "morning run" on 2026-03-23 that exercised multiple scripts; dex-acquire.py was one of them and failed quietly. Worth knowing for reconstructing the session history.
- **The typo is the result of a raw string + escape interaction** that Windows users hit regularly. In Python, `r"C:\Users\dkitc\.dex-jr\chromadb"` is correct (raw string, backslash preserved), but a typo swallowed the backslash. Not a Python language issue — just a manual typo during file authoring.
- **Other files that hardcode `CHROMA_PATH`:**
  - `dex_weights.py:21` — `r"C:\Users\dkitc\.dex-jr\chromadb"` — CORRECT
  - `dex-acquire.py:41` — `r"C:\Users\dkitc.dex-jr\chromadb"` — TYPO
  - `dex-ingest.py:40` — `CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"` — CORRECT
  - `dex-backup.py:33` — `LIVE_CHROMADB = Path(r"C:\Users\dkitc\.dex-jr\chromadb")` — CORRECT
  - `dex-search-api.py` — didn't audit, but uses CHROMA_DIR internally
  
  The typo is isolated to `dex-acquire.py`. No other file has the same issue. Confirmed via the Grep call during investigation (`CHROMA_PATH|dkitc\.dex-jr|dex-acquire` scoped to *.py files).

---

## Methodology notes

- **All SQLite access was read-only** via `file:...?mode=ro` URI. No ChromaDB PersistentClient was opened against the typo path (would have mutated mtimes + potentially triggered migrations/writes).
- **Temp script `_tmp_shadow_sqlite_probe.py`** was created in the repo, run once, and deleted. Confirmed deleted via post-run `ls` check (exit code 2 on the expected "No such file or directory").
- **No files at the shadow path were touched.** `chroma.sqlite3` mtime remains `2026-03-23 06:16:04.68` post-investigation (not re-verified after the read, but SQLite read-only mode does not update mtimes).
- **No live corpus reads or writes.** The investigation touched only (a) the shadow path on disk, (b) git history via `git log`/`git blame`, (c) dex-rag repo files via Read/Grep.

---

**End of STEP13 investigation report.**
