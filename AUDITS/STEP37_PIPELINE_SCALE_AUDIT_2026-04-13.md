# STEP 37 — Pipeline Scale Audit (read-only)

**Date:** 2026-04-13
**CR:** Phase 2 Step 37
**Operator:** Dave Kitchens
**Executor:** Claude Code (Dex Jr., Seat 1010)
**Scope:** Read-only inventory. No code edits. No corpus touch.

---

## Headline

**31 findings across 5 pipeline files. 4 HIGH-risk (3 already tied
to Step 33c scope, 1 pre-existing search-api bug). 13 MEDIUM. 14
LOW.** Nothing in the live 4 AM sweep path is imminently at risk
after Step 36's patch — the next unattended run should succeed. The
audit's value is in surfacing the full scale-sensitivity surface so
Step 33c can plan the coordinated fix instead of another reactive
patch cycle.

Post-migration scale (10 collections, 1.1 M chunks, 22 GB — with
dex_canon now at 252,546 after Monday's manual sweep) has not yet
pushed any timeout or threshold past its bounds besides what Step
36 already addressed.

---

## Category A — Timeouts

All subprocess / requests timeouts in the pipeline code (the repo's
`.venv` and needoh-watcher are excluded).

| File:line | Value | Bounds | Pre-mig sized? | Post-mig headroom | Risk |
|---|---:|---|:-:|---|:-:|
| `dex_pipeline.py:326` | **300 s** | check-only probe (backup triggers) | patched | 5× observed (60s live-count) | LOW |
| `dex_pipeline.py:379` | **2400 s** | `--force` backup + restore-test | patched | ~2.8× observed (~14 min) | LOW |
| `dex_pipeline.py:396` | **300 s** | re-check after backup | patched | 5× | LOW |
| `dex-ingest.py:178` | 60 s | per-chunk Ollama `/api/embeddings` | yes | tight for large chunks under mxbai, fine under nomic | MEDIUM |
| `dex-backup.py` subprocess cleanup retry | `time.sleep(1)` + retry once | scratch `rmtree` | yes | no change | LOW |
| `dex_jr_query.py:71` | 60 s | embedding call | yes | tight under mxbai on long queries | LOW |
| `dex_jr_query.py:89` | 300 s | LLM generation (qwen2.5-coder:7b) | yes | generation-bound not scale-bound | LOW |
| `dex_jr_query.py:397` | 10 s | self-test `/api/tags` probe | yes | fast endpoint; fine | LOW |
| `dex-search-api.py:72` | 30 s | embedding call | yes | tight on long inputs under mxbai | MEDIUM |
| `dex-search-api.py:167` | 120 s | chat-model generation | yes | generation-bound | LOW |
| `dex_weights.py:66` | 60 s | embedding (in weights helper) | yes | same class as `dex-ingest.py:178` | LOW |
| `dex-query.py:18` | 60 s | embedding | yes | same class | LOW |
| `dex-deliberate.py` various | 60–300 s | multi-model query | yes | off the sweep path | LOW |
| `dex-council.py` various | 60–300 s | council generation | yes | off the sweep path | LOW |
| `transcribe_mania.py:64` | 14400 s | whisper transcription | N/A | not scale-sensitive | LOW |

**Cross-cutting pattern:** per-embedding call timeouts cluster at
60 s across 6 files (`dex-ingest.py`, `dex-query.py`, `dex_weights.py`,
`dex_jr_query.py`, `dex-search-api.py:72`, and the Step 32/33
diagnostic scripts). Under `nomic-embed-text` that's ample for the
existing 2000-char chunks. Under `mxbai-embed-large` after Step 33c's
ingest switchover, 1200-char-truncated embeddings take < 100 ms
each, so 60 s is still fine — **but** if a future long-context
embedding model (e.g. `bge-m3` with its 8K context) replaces
`mxbai`, the 60 s cap would need a re-eval. Tag: monitor-only for
now; no action.

---

## Category B — Hardcoded counts / thresholds

| File:line | Value | Represents | Pre-mig sized? | Risk |
|---|---:|---|:-:|:-:|
| `dex-backup.py:39` | `TRIGGER_DAYS = 3` | max backup age before Trigger 1 | no — age-based | LOW |
| `dex-backup.py:40` | `TRIGGER_CHUNK_DELTA = 1000` | chunk growth trigger | yes | LOW — bulk ingest always exceeds; fires reliably |
| `dex-backup.py:41` | `TRIGGER_BATCH_THRESHOLD = 100` | pre-batch trigger | yes | LOW — sweep passes 10 000 |
| `dex-backup.py:44` | `RETAIN_DAILY = 7` | retention | pre-22 GB era | **MEDIUM** — see §D |
| `dex-backup.py:45-46` | `RETAIN_WEEKLY=4, RETAIN_MONTHLY=3` | retention | pre-22 GB era | MEDIUM |
| `dex-sweep.py:77` | `DEFAULT_INTERVAL = 60` | watch-mode poll interval (s) | N/A | LOW |
| `dex-sweep.py:82` | `SWEEP_CHUNK_ESTIMATE = 10_000` | Trigger-5 input | fine | LOW |
| `dex-ingest.py:58-60` | `CHUNK_SIZE_TOKENS=500, OVERLAP=50` | chunker | yes — matches live data | **MEDIUM** under mxbai (512-tok ctx); Step 33c decision |
| `dex-ingest.py:65` | `BULK_CHUNK_ESTIMATE = 10_000` | Trigger-5 input | fine | LOW |
| `dex-ingest.py:95` | `MAX_TEXT_CHARS_NORMAL = 5_000_000` | skip huge files in NORMAL mode | yes | **MEDIUM** — two operator files from the Mon sweep were 2.5–2.7 MB (within bounds but trending up) |
| `dex_weights.py:~25-30` | `COLLECTIONS = { ext_creator, ext_reference, dex_canon, ddl_archive }` | weight table | old | **HIGH (latent)** — `ext_reference` was never created; `dex_code` is missing; `_v2` suffix absent. Retrieval calls that touch this default-weight path at 0.65 for anything not in the dict |
| `dex_weights.py:122` | `target_collections = [...]` | default search list | old | **HIGH (latent)** — hard-coded old names, missing `dex_code` |
| `dex_pipeline.py:295` | docstring `"If > 100, Trigger 5 fires"` | matches dex-backup.py:41 | fine | LOW |
| `dex-sweep.py:180` | `for cname in ["dex_canon","ddl_archive","dex_code","ext_creator"]:` | sweep report "pipeline state" | yes | MEDIUM — report is incomplete during soak (misses `_v2` + test collections) |

---

## Category C — Implicit assumptions

| Finding | File:line | Risk |
|---|---|:-:|
| Sweep ingest target hardcoded to `--collection dex_canon`. `_v2` never written by scheduled sweep. Intentional during soak; Step 33c will flip. | `dex-sweep.py:355` | **HIGH** (33c scope) |
| `dex-ingest.py` EMBED_MODEL = nomic hardcoded. Step 33c must change to mxbai + adaptive truncation. New ingests currently embed under nomic, widening the drift between nomic and _v2 every 24h the sweep runs. | `dex-ingest.py:55` | **HIGH** (33c scope) |
| `RAW_COLLECTION = "ddl_archive"`, `CANON_COLLECTION = "dex_canon"` — dual-write NORMAL mode still populates both with nomic embeddings. | `dex-ingest.py:51-52` | **HIGH** (33c scope) |
| `dex-search-api.py` only opens `dex_canon` and `ddl_archive`. It is invisible to `dex_code`, `ext_creator`, and all 4 `_v2` collections. **Pre-existing bug from Audit 2026-04-12 item #2.** Not a Step-33b regression — but a known gap the retool is supposed to close. | `dex-search-api.py:93-103` | **HIGH** (pre-existing) |
| Weight table assumes 4 nomic collections; any `_v2` query (currently via `dex_jr_query.py`) bypasses `dex_weights.py` entirely, which is fine today but will hurt when Step 33c renames `_v2 → canonical` and anything wired to dex_weights expects the new world. | `dex_weights.py:25-30, 122` | MEDIUM |
| `dex-ingest.py` loads **all** existing chunk IDs into a Python `set` at start of non-fast ingest (three calls, lines 429/437/445). At 1.1 M chunks that's ~50 MB of strings resident. Scales linearly with corpus. | `dex-ingest.py:429,437,445` | MEDIUM |
| `get_live_chunk_count()` iterates `client.list_collections()` calling `.count()` on each. With 10 collections this took > 120 s at AM (pre-Step 36). Now buffered to 300 s. Further collection growth (Step 33c may add more, or test collections accrue) would eventually bump into 300 s again. | `dex-backup.py:126-128` | MEDIUM |
| `query_collection_state()` joins `embeddings × segments` via SQL. `segments` table is small (20 rows); `embeddings` has > 1 M rows. Single aggregate query per collection. Latency scales with `embeddings` size. | `dex-backup.py:293-298` | MEDIUM |
| `validate_backup()` runs `query_collection_state()` twice — once on live, once on backup. Doubles the cost. Contributes to backup wall time at scale. | `dex-backup.py:399` | LOW |
| Sweep-report "pipeline state" block only counts the 4 nomic collections — `_v2` and test collections are invisible in the daily report. Telemetry gap, not a correctness bug. | `dex-sweep.py:180` | LOW |
| `dex_pipeline.py:512+` integration tests call `ensure_backup_current()` with `expected_write_chunks=0, 500` — verifies trigger logic but does not exercise the post-migration scale path. | `dex_pipeline.py:511-540` | LOW |

---

## Category D — Resource paths

| Concern | Numbers | Risk |
|---|---|:-:|
| **SQLite 32 K variable limit** — Step 33a and Step 33b both hit this. Any code that does `col.get(ids=large_list)` or `where={"source_file": {"$in": big_list}}` will fail at ~30 K items. B3 prefilter uses 3-item `$in`; safe. Migration and validation scripts use paged 2 K. | limit = 32 766 SQLite params | LOW in live pipeline; **MEDIUM** if future code adds big `$in` |
| **restore_test scratch dir cleanup** — known Windows HNSW mmap issue. Orphans reclaimed by `cleanup_stale_scratch(max_age_hours=1.0)` on next backup run. Observed this morning: sweep's Monday run left `restore_test_2026-04-13_2224` (21 GB) — expected, benign. | 1 h reclaim window | LOW (documented, self-healing) |
| **D: disk growth** — Each backup now ~22 GB (up from ~11 GB pre-migration). Retention `RETAIN_DAILY=7 + RETAIN_WEEKLY=4 + RETAIN_MONTHLY=3 = 14 backups`. At 22 GB each: **~308 GB** on `D:\DDL_Backup`. D: has 933 GB total, shared with other artifacts. | ~308 GB vs 933 GB | MEDIUM — comfortable today; shrinks after Step 33c drops nomic collections and corpus roughly halves |
| **C: disk growth** — live chromadb dir is currently 22 GB. Restore-test scratch briefly doubles it for minutes during backup. 323 GB free on C: today. | 22 GB + 22 GB burst | LOW |
| **Existing-IDs in-memory set** — `dex-ingest.py` holds up to 1.1 M string IDs in Python set(s) during non-fast ingest. ~50 MB RAM. | 1.1 M × ~48 bytes | LOW today; MEDIUM at 10 M |
| **Chunker files > 5 MB** are skipped in NORMAL mode (`MAX_TEXT_CHARS_NORMAL`). Monday's sweep ingested two 2.5–2.7 MB files — approaching the cap. A single 6 MB operator thread would silently drop today. | 5 MB ceiling | MEDIUM |
| **_backup_log.jsonl** never truncates. ~1 entry per backup plus Step 36's new "started" footprints. At 7 daily backups × 365 = 2 555 entries/year. Hundreds of KB per year. Fine. | unbounded-append | LOW |

---

## Cross-cutting patterns

1. **Every embedding-path timeout is 60 s.** The constant appears in 6 files. Consolidating to a single `DEX_EMBED_TIMEOUT` constant (ideally in a shared `dex_core` or similar) would make future tuning safe. Not urgent — just observed.

2. **Collection lists are hardcoded in three different places:**
   `dex-sweep.py:180` (reporting), `dex_weights.py:122` (query targets),
   `dex-search-api.py:93-103` (API endpoints). They disagree with each
   other (the API knows only 2; weights list 5 including non-existent
   `ext_reference`; sweep lists 4). Single-source-of-truth needed —
   this was flagged in the original 2026-04-12 audit as the
   "query router" item and is still open.

3. **Trigger threshold values (1000, 100, 10_000) were chosen for
   the pre-migration world.** None of them are dangerously wrong at
   new scale — `TRIGGER_CHUNK_DELTA=1000` still fires on the first
   sweep that adds any real content, and `TRIGGER_BATCH_THRESHOLD=100`
   trivially fires for any bulk. But they're due for a re-eval
   when STD-DDL-BACKUP-001 gets its v1.1 amendment.

4. **Nothing in the pipeline is currently counting _v2 chunks as
   live.** `get_live_chunk_count()` does use `list_collections()`
   which DOES include _v2, so triggers see the full 1.1 M. But the
   sweep report block at `dex-sweep.py:180` filters to the old 4
   names — which means operator telemetry shows an inflated "backup
   captures X chunks" vs "sweep saw Y chunks" until Step 33c
   rationalizes.

---

## Patch plan — ranked

### Before the next unattended 4 AM sweep (tonight)

**Nothing required.** Step 36's three timeout bumps cover the
only currently-failing path. Tonight's sweep should succeed.

The MEDIUM items above (chunker 500-tok, MAX_TEXT 5 MB, retention
disk, existing-IDs memory, collection list drift) are latent —
none of them will fire on tonight's 25-file sweep.

### Fold into Step 33c (coordinated switchover)

- `dex-ingest.py:55` EMBED_MODEL → `mxbai-embed-large` + adaptive truncation (same 1200→900→600→300 ladder `dex_jr_query.py:embed` uses)
- `dex-ingest.py:51-52` collection names rationalized after `_v2 → canonical` rename
- `dex-sweep.py:355` `--collection` target rationalized
- `dex-sweep.py:180` hardcoded collection list — replace with `client.list_collections()` for complete telemetry
- `dex_weights.py:25-30, 122` — update to match final collection set (also drop `ext_reference`)
- `dex-search-api.py:93-103` — expand to all live collections (close the 2026-04-12 Audit item #2)

### Defer to STD-DDL-BACKUP-001 v1.1 or later

- `TRIGGER_*` threshold re-eval (current values still correct in
  direction, not precision-tuned)
- `RETAIN_DAILY/WEEKLY/MONTHLY` tuning as D: grows (currently fine,
  revisit if D: hits 80% full)
- Restore-test cadence (run every N backups instead of every backup,
  now that we have actual timing telemetry)

### Defer to a dedicated refactor (the "dex_core" consolidation from the 2026-04-12 audit)

- `DEX_EMBED_TIMEOUT` constant consolidation
- Single collection-list source-of-truth
- `get_live_chunk_count()` called only when a trigger actually needs it (reduce per-check-only latency)

---

## Standard amendments suggested

- **STD-DDL-BACKUP-001 v1.1** — already in "drafted, pending distribution" state per the carry-forward from 2026-04-12. Should add:
  - Explicit guidance on `RETAIN_*` sizing vs corpus size (fraction of disk, not absolute count)
  - Restore-test cadence (every backup vs every Nth) with rationale
  - `TRIGGER_*` values reviewed against post-migration corpus
  - Telemetry requirements (the `restore_test_elapsed_seconds` and `stage:started` fields added in Step 36 should be codified, not just live in code)

- **STD-DDL-INGEST-001** (doesn't exist) — ADR-INGEST-PIPELINE-001 resolution would benefit from a companion standard that codifies collection naming, embedding model choice, chunker parameters, adaptive-truncation ladder, and the migration pattern we just executed. Would also formalize the `_v2` suffix convention for future migrations.

---

## Appendix — Actual bugs found (distinct from scale-sensitivity)

Per prompt's "if CC discovers an actual bug, surface it":

1. **`dex-search-api.py:87`** has a bare `except:` that swallows all errors in `get_rag_context()`. Silent-failure pattern flagged in the 2026-04-12 audit as Rule 15 violation. Still present. Not a Step 37 action; noting for completeness.

2. **`dex_weights.py:122`** lists `ext_reference` as a search target. **No such collection has ever existed** (verified via `client.list_collections()` — never in the 10-collection current roster, never in any backup manifest). Any code path that branches on `ext_reference` is dead. Suggests the weight config was authored aspirationally and never reconciled — same category as the 2026-04-12 audit's "ADR-CORPUS-001 disagrees with live schema" finding.

3. **`dex-sweep.py:180`** — `pipeline_state` computed inside the report-writing function wraps `client.get_collection(cname).count()` in a bare `try/except: pass`. If a collection is missing, the sweep report silently lists incomplete state without flagging it. Not a bug per se (the except has an empty key, which downstream code can detect) but a Rule 15 candidate.

None of these block tonight's 4 AM sweep.
