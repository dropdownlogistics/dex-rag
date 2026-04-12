# STEP 28 — Retrieval Quality Deep-Dive Audit

**Date:** 2026-04-12
**CR:** Phase 2 Step 28
**Operator:** Dave Kitchens
**Executor:** Claude Code (Dex Jr., Seat 1010)
**Scope:** Investigation only. No code changes, no re-embedding, no model swaps.

---

## Headline finding

**The `nomic-embed-text` tokenizer collapses DDL identifiers
(`STD-DDL-*-001`, `CR-*`, `ADR-*`) to indistinguishable token
sequences.** Two distinct identifiers —`STD-DDL-SWEEPREPORT-001` and
`STD-DDL-BACKUP-001`— embed to the **same vector** (cosine distance =
0.0000). A query containing the identifier therefore has zero
identifier-derived signal; retrieval must rely on surrounding English
prose. This is the root cause of the retrieval failure reported
against `dex_jr_query.py`.

The corpus is intact. The chunker is working. The stored embeddings
are not corrupt. The embedding model is simply not preserving the
signal that DDL governance queries depend on.

---

## Evidence

### Correction to prompt's premise

The prompt said "STD-DDL-SWEEPREPORT-001.txt IS in dex_canon (5
chunks)." Actual count in `dex_canon`: **9 chunks** (verified via
`col.get(where={"source_file": ...})`). All chunks present, all
readable, embeddings stored. Not a corpus integrity issue.

Chunk 0 head:
```
===================================================================
STD-DDL-SWEEPREPORT-001 v1.0 — Sweep Report Protocol
Ratified: 2026-04-12 via CR-SWEEP-REP...
```

### A1 — Direct proximity test

Five queries, each embedded via `nomic-embed-text`, compared against
all 9 stored chunks of `STD-DDL-SWEEPREPORT-001.txt` using both the
raw L2² metric (Chroma's default) and cosine distance. Also the top-20
native Chroma query to see where the target file actually ranks
across the full 245,633-chunk collection.

| Query label | Query text | Best L2² to target | Best cos to target | Target rank in top-20 | Chroma top-1 dist |
|---|---|---:|---:|---|---:|
| id_only | `"STD-DDL-SWEEPREPORT-001"` | **383.96** | 0.4274 | **NOT IN TOP 20** | 185.67 |
| key_phrase | `"classification predicate ingest report"` | 293.74 | 0.3443 | positions 7, 12 | 263.31 |
| conceptual | `"sweep report protocol"` | **282.02** | **0.3322** | position 16 | 244.61 |
| exact_quote | `"A file is an ingest report IF AND ONLY IF"` | 240.77 | 0.2883 | **NOT IN TOP 20** | 218.76 |
| colloquial | `"skip-if-reports-only logic"` | 381.18 | 0.4871 | **NOT IN TOP 20** | 335.16 |

**The exact-quote query — text lifted verbatim from chunk 2 of the
target file — does not retrieve the target in the top 20.** Best L2²
to target is 240.77; Chroma's top-1 sits at 218.76 (from some
unrelated chunk). That's 22 distance units of gap between the query
and its own source document, while 20 unrelated chunks score closer.

This is not a merge-logic bug in `dex_jr_query.py`. Bypassing the
top-k merge and querying Chroma directly gives the same answer: the
embedding model does not place the target chunks near the query in
vector space.

Conceptual and key-phrase queries do slightly better because they use
normal English words the model's training captured. The identifier
itself is dead weight.

### A2 — Embedding model sanity check

| Pair | L2² | L2 | Cosine distance |
|---|---:|---:|---:|
| `"the cat sat on the mat"` vs `"the cat was on the mat"` | 75.24 | 8.67 | 0.0773 |
| `"STD-DDL-SWEEPREPORT-001"` vs `"STD-DDL-SWEEPREPORT-001"` | 0.0 | 0.0 | 0.0000 |
| `"STD-DDL-SWEEPREPORT-001"` vs `"STD DDL SWEEPREPORT 001"` | 47.56 | 6.90 | 0.0452 |
| **`"STD-DDL-SWEEPREPORT-001"` vs `"STD-DDL-BACKUP-001"`** | **0.0** | **0.0** | **0.0000** |
| `"STD-DDL-SWEEPREPORT-001"` vs `"Sweep Report Protocol"` | 304.19 | 17.44 | 0.2912 |

**Row 4 is the smoking gun.** Two completely different DDL
identifiers produce bit-identical embeddings. The model is working
(row 1: cat/mat distance is sensibly small). The self-identity test
(row 2) passes. The dash-vs-space test (row 3) shows minor variation,
so the tokenizer isn't fully stripping punctuation. But across
different `STD-DDL-*-001` identifiers the output is identical —
which means whatever token sequence survives normalization is the
same for both inputs. The identifier conveys no signal to the model.

Row 5 confirms the corollary: when the same concept is expressed in
English prose, the embedding is distinct from the identifier (cos
0.29). The model can talk about sweep reports; it just can't read
`STD-DDL-SWEEPREPORT-001` as a name.

### A3 — Chunker inspection

Chunker at `dex-ingest.py:190` (`chunk_text`):

- `CHUNK_SIZE_TOKENS = 500`, `CHUNK_OVERLAP_TOKENS = 50`, `CHARS_PER_TOKEN = 4`
- Effective: ~2000 char chunks with ~200 char overlap
- Prefers paragraph (`\n\n`) then sentence boundaries in the back
  half of the window; falls back to hard cut otherwise

Actual chunks of `STD-DDL-SWEEPREPORT-001.txt`:

| idx | len | head (first 80 chars) |
|----|----:|---|
| 0 | 1935 | `===== STD-DDL-SWEEPREPORT-001 v1.0 — Sweep Report Protocol Ratified` |
| 1 | 1938 | `what happened. ===== REPORT LOCATION All reports...` |
| 2 | 1898 | `b_2026-04-13_0401. No errors." SECTION 3. Files ingested...` |
| 3 | 1957 | `n seconds SECTION 8. Next scheduled sweep ISO timestamp...` |
| 4 | 1823 | `folder would grow indefinitely with reports about reports...` |
| 5 | 1937 | `n Section 6. The report write itself is not gated by...` |
| 6 | 1914 | `to stderr with full error context - Continue execution — do NOT...` |
| 7 | 1847 | `ed during the v1.0 council review but deferred to keep v1.0...` |
| 8 | 1265 | `acceptable triggers. ===== VERSION HISTORY v0.1 (2026-04-12)...` |

Observations:
- The title + identifier appear **only in chunk 0**. Every other
  chunk has its identifier-free body.
- Chunks start mid-word or mid-sentence in most cases (e.g. chunk 2
  begins `"b_2026-04-13_0401..."` — a backup-dir fragment carried
  across a boundary).
- The corpus uses `=====` lines as section separators. A
  semantic-aware chunker could split cleanly on those and produce
  chunks that start with a section header plus body, which would
  measurably help retrieval even with the current embedding model.

The chunker is not catastrophic, but it is not exploiting the
structure the governance docs provide.

---

## Candidate fixes

### B1 — Swap embedding model

| Candidate | Params | Disk | Dim | Via Ollama | Notes |
|---|---|---|---|---|---|
| current: nomic-embed-text | 137M | 0.27 GB | 768 | yes | broken on identifiers |
| mxbai-embed-large | 335M | ~670 MB | 1024 | yes (`ollama pull mxbai-embed-large`) | strong on identifiers per public benchmarks |
| bge-large-en-v1.5 | 335M | ~1.3 GB | 1024 | yes | strong general-purpose |
| bge-m3 | 568M | ~2.3 GB | 1024 | yes | multilingual + long context |

**Feasibility:** high — any of these pull into Ollama in minutes.
**Cost to test on subset:** trivial — embed ~1000 chunks, re-run the
A1 diagnostic against the same target, compare distances. <10 min.
**Cost to commit full re-embed:** 554,459 chunks across 4 live
collections. At a conservative 40 ms/embed single-stream on the 3070,
≈6.2 hours. Batchable through Ollama (`/api/embed` supports arrays) —
could fall to 1–2 hours with batch=32.
**VRAM:** current `qwen2.5-coder:7b` + `nomic-embed-text` fit together.
mxbai-embed-large is ~2× the embed model size. Probably still fits on
the 3070 with qwen loaded; worth measuring.
**Chroma compatibility:** dim change (768→1024) **requires
re-creating collections** (you cannot add 1024-d vectors to a
768-d collection). Backup exists. Rollback = restore backup.
**Reversibility:** medium. Destructive to existing collections but
fully recoverable from `D:\DDL_Backup`.

### B2 — Hybrid retrieval (semantic + keyword substring)

Detect identifier-like tokens in the query via regex
(`\bSTD-[A-Z]+-[A-Z0-9]+-\d+\b`, `\bCR-[A-Z0-9-]+\b`,
`\bADR-[A-Z0-9-]+\b`, `\bPRO-[A-Z0-9-]+\b`, `\bOBS-[A-Z0-9-]+\b`). For
each match, run a direct Chroma `get(where_document={"$contains": tok})`
(or the `$and` combination with a `where` on `source_file` for best
coverage) and surface hits at rank 0 before the vector results.

**Feasibility:** high — implementable in `dex_jr_query.py` in under
100 lines.
**Cost:** ~20 ms extra per query for the substring lookup. No
re-embed. No re-index.
**Expected improvement:** large for governance queries that include
an identifier; neutral for queries that don't.
**Reversibility:** trivial — revert `dex_jr_query.py`.

### B3 — Metadata pre-filter on `source_file`

Before the vector search, run a cheap `col.get(where={"source_file":
{"$eq": <token>}})` for any identifier detected in the query whose
shape resembles a filename stem (e.g., `STD-DDL-SWEEPREPORT-001`
matches `STD-DDL-SWEEPREPORT-001.txt`). Surface those chunks first.

Subset of B2; even simpler. Limited to the case where the identifier
matches the filename of the source document. Covers a large fraction
of real governance queries.

**Feasibility:** trivial.
**Cost:** negligible.
**Expected improvement:** the specific failure case in this audit
would return chunk 0 at rank 0 instantly.
**Reversibility:** trivial.

### B4 — Chunking changes

- Smaller chunks (250 tok): higher semantic density, ~2× chunk
  count. Requires full re-embed.
- Larger overlap (200+ tok): reduces boundary effects. Requires
  full re-embed.
- **Structure-aware split** on `=====` separators + markdown
  headers: for the DDL-standards corpus this is a natural fit.
  Chunks would start with an identifier + title line, which even
  under the broken tokenizer gives the remaining English words a
  fighting chance. Requires re-ingest (re-chunk + re-embed).

Any chunker change is paired with re-embedding. Defer until B1 is
decided.

### B5 — Distance metric

Live collections have `metadata: {"description": "Dex Canon"}` with
no `hnsw:space` key → Chroma default is squared L2. Modern embedding
models are typically evaluated under cosine. Switching to cosine
requires creating new collections (Chroma stores the metric in HNSW
index metadata). Effect on retrieval quality is second-order compared
to the tokenizer issue and would not, by itself, fix the identifier
collapse problem.

Defer. Pair with B1 if/when a re-embed happens.

---

## Recommendation

**Step 29 path: B3 first, then B2, then evaluate B1 on a test subset.**

Ranked by (impact × reversibility) / cost:

1. **B3 — source_file pre-filter in `dex_jr_query.py`**
   - Impact: directly fixes the failing case in this audit
   - Cost: <50 lines of Python
   - Reversibility: trivial
   - Ship as Step 29.

2. **B2 — full hybrid retrieval with identifier-regex substring match**
   - Impact: covers the broader class of DDL-identifier queries
     beyond filename matches
   - Cost: ~100 lines
   - Reversibility: trivial
   - Ship as Step 30 (or bundle with Step 29).

3. **B1 — embedding model subset test with `mxbai-embed-large`**
   - Test plan:
     - `ollama pull mxbai-embed-large`
     - Script: embed the same 5 A1 queries + the 9 target chunks
       via mxbai, compute the same distance table, compare.
     - Also run the A2 sanity pairs (cat/mat, identifier pairs).
     - If the identifier-pair distance is meaningfully non-zero
       AND the conceptual/exact-quote queries now hit the target
       in top-5, proceed.
   - Commit plan (if test passes):
     - Backup current live collections (existing Trigger-2 gate).
     - Create new collections `dex_canon_v2`, `ddl_archive_v2`,
       `dex_code_v2`, `ext_creator_v2` with `mxbai-embed-large`.
     - Re-embed in batches. Validate counts against originals.
     - Swap `dex_jr_query.py` and `dex-ingest.py` defaults.
     - Retire old collections after a soak period.
   - Rollback plan: restore from `D:\DDL_Backup`; revert code.
   - Cost: ~6h wall time plus validation. Biggest swing but
     highest ceiling on quality.

B4 (structure-aware chunking) and B5 (cosine metric) should be
folded into the B1 migration if it goes ahead. They are not worth
doing in isolation.

**Should the operator read the full report before deciding?**
Yes — B1 is a significant operation. B3 is safe to ship immediately
on the operator's approval without further reading.

---

## Appendix A — Raw A1 distance table (full 9 chunks)

Full per-chunk distances produced by `_step28_diagnostic.py`, archived
in `_step28_diagnostic.json`. Best row per query highlighted above.

## Appendix B — Chunker config (current)

```
CHUNK_SIZE_TOKENS    = 500      # ~2000 chars
CHUNK_OVERLAP_TOKENS = 50       # ~200 chars
CHARS_PER_TOKEN      = 4
```

Splits at paragraph / sentence boundaries in the back half of the
window, hard cut otherwise. Source: `dex-ingest.py:57-60, 190-236`.

## Appendix C — Collection metadata

All 4 live collections expose metadata of the form `{"description":
"..."}`. None set `hnsw:space`. Chroma default distance metric is
squared L2.

## Appendix D — Diagnostic artifacts

- `_step28_diagnostic.py` — standalone, read-only. Uses the live
  Ollama instance and the live Chroma directory. Safe to re-run.
- `_step28_diagnostic.json` — structured output of the run.

Both are untracked and should remain so; they are one-off
investigation tooling, not production code.
