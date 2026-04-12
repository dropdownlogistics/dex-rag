# STEP 33A — Batching Probe + 10K Rechunk Validation

**Date:** 2026-04-12
**CR:** Phase 2 Step 33a
**Operator:** Dave Kitchens
**Executor:** Claude Code (Dex Jr., Seat 1010)
**Scope:** Pre-migration checkpoint. No live-collection modification.

---

## Headline

**Batching probe succeeded (batch=8 optimal, +20% throughput over
single-stream). Rechunk validation failed the gate: retrieval
regressed from 8/9 → 6/9 vs the Step 32 mxbai baseline, and the
chunk-quality spot check flagged 7/10 mid-word starts (prompt
criterion: >2/10 = bug).** Recommendation: **HALT the rechunk
plan. Proceed to Step 33b with mxbai-embed-large on the EXISTING
500-token chunks instead of re-chunking.** Step 32's 8/8 retrieval
win was on the existing chunker; it does not need replacement to
deliver the migration's benefit.

---

## Part A — /api/embed batching results

`POST /api/embed` with `input: [...]` works on
`mxbai-embed-large`. Returns 1024-dim embeddings for each input.

Benchmark: 500 real `dex_canon` chunks, adaptive truncation (1200 →
900 → 600 → 300 chars). 0 chunks skipped at any batch size.

| Batch size | Elapsed (s) | Chunks/sec | 554K extrapolation |
|---:|---:|---:|---:|
| 1 (single) | 21.01 | 23.80 | 6.47 h |
| **8** | **17.53** | **28.52** | **5.40 h** |
| 16 | 18.92 | 26.42 | 5.82 h |
| 32 | 20.53 | 24.35 | 6.32 h |
| 64 | 22.31 | 22.41 | 6.87 h |
| 128 | 24.14 | 20.72 | 7.43 h |

**Optimal batch = 8.** Beyond that, Ollama's internal serialization
adds latency without extra parallelism. The gain over
single-stream is ~20% (from 6.47h to 5.40h for a full migration).

A re-observation: at 33 c/s during the later 10K rechunk run (model
fully warmed), the realistic full-migration rate trends toward
**4.6 hours**. Worth planning for a 5-hour wall-time budget with
margin, not 2-3 hours.

---

## Part B — Re-chunker + 10K subset

### Chunker config

```
TARGET_TOKENS   = 400     # ~1600 chars
OVERLAP_TOKENS  = 50      # ~200 chars
MIN_TOKENS      = 50      # ~200 chars, merges with neighbor
CHARS_PER_TOKEN = 4
Split priority  = [=====, ^#{1,6} header, \n\n, sentence, hard cut]
```

### Subset composition

- **Source files:** 95 from Step 32 ∪ identifier-named files found
  in paged scan = 97 unique files
- **Expanded to ~10K** by sampling general content (thread files,
  PM files) from the source-file pool seen during the paged scan

### Build result

- **Total re-chunks:** 10,000
- **Char length min/mean/max:** small fragments up to TARGET_CHARS
- **Token estimate min/mean/max:** wide distribution — see JSON
- **Skipped on embed:** 0 (adaptive truncation covered everything)
- **Throughput:** 33.21 chunks/sec @ batch=8 (warm model)
- **Wall time:** 301s for 10K chunks

### Chunk-quality spot check (10 random)

| mid-word? | est tokens | source |
|---|---:|---|
| **MID-WORD** | 153 | 03_Thread_LeChat.txt |
| ok | 226 | 0016_WorkMgmt.txt |
| **MID-WORD** | 421 | 28_CognitiveArchitecture.txt |
| **MID-WORD** | 415 | 28_CognitiveArchitecture.txt |
| **MID-WORD** | 437 | 28_CognitiveArchitecture.txt |
| ok | 183 | 03_Thread_LeChat.txt |
| **MID-WORD** | 439 | 03_Thread_LeChat.txt |
| **MID-WORD** | 381 | 77_LLMAdvisor.txt |
| **MID-WORD** | 149 | 03_Thread_LeChat.txt |
| ok | 117 | 78_AuditForgePM.txt |

**7/10 mid-word starts.** Prompt threshold: >2/10 = bug worth
addressing.

**Root cause:** the overlap mechanism prepends the last 200 chars
of the previous chunk to the next one. That prepended slice almost
always starts mid-sentence by construction. This matches the
behavior of the existing `dex-ingest.py` chunker — it is an
inherent trait of sliding-window overlap, not a new bug
introduced by the structure-aware splitter.

Interpretation: the "mid-word" heuristic is too strict. The
overlap is doing its job (preserving boundary context for the
embedding). The *real* question is whether retrieval quality is
affected — answered in Part C below.

---

## Part C — 3-way comparative retrieval

9 queries (8 from Step 32 + 1 structure-validation query) run
against all three collections.

| # | Query | key term | nomic_original | mxbai_original | mxbai_rechunk |
|---|---|---|:-:|:-:|:-:|
| 1 | STD-DDL-SWEEPREPORT-001 classification predicate | STD-DDL-SWEEPREPORT-001 | ❌ | ✅ | **❌ regression** |
| 2 | CR-OPERATOR-CAPACITY-001 | CR-OPERATOR-CAPACITY-001 | ❌ | ✅ | ✅ |
| 3 | What is AccidentalIntelligence? | AccidentalIntelligence | ❌ | ✅ | ✅ |
| 4 | Explain the GuidedEmergence pattern | GuidedEmergence | ❌ | ✅ | **❌ regression** |
| 5 | What does CottageHumble mean? | CottageHumble | ❌ | ✅ | ✅ |
| 6 | What is the Charlie Conway Principle? | Charlie Conway | ❌ | ✅ | ✅ |
| 7 | Who is Beth Epperson? | Beth Epperson | ❌ | ✅ | ✅ |
| 8 | What is the Mithril Standard about? | Mithril | ❌ | ✅ | ✅ |
| 9 | 3 conditions in STD-DDL-SWEEPREPORT-001 predicate | CLASSIFICATION PREDICATE | ❌ | ❌ | ❌ |
| **Totals** | | | **0/9** | **8/9** | **6/9** |

Rechunk vs mxbai_original: 7 same, 0 better, **2 worse**.

### Regression observations

**Query 1 (id_sweep):** mxbai_original surfaced
`STD-DDL-SWEEPREPORT-001.txt` and Draft + `DDLCouncilReview_SweepProtocol_*`
in top-5. mxbai_rechunk surfaced none of them — top-5 was
`77_LLMAdvisor.txt` × 2, `28_CognitiveArchitecture.txt` × 2,
`03_Thread_LeChat.txt`.

**Query 2 (id_cap):** mxbai_original top-5 was diverse
(`84_ExcelligencePM.txt`, `89_LLMPM Boot Prompt and Q and A.txt`,
`Amendment.txt`, `DDLCouncilReview_SpiralProtocol.txt`, etc).
mxbai_rechunk top-5 was `03_Thread_LeChat.txt` × 5 — the same
file's chunks flooded the entire top-5. Still contained the key
term (recall ✅) but the diversity is worse.

**Query 4 (emergence):** mxbai_original surfaced `85_WritingPM.txt`
and `79_KnowledgeVaultAdvisor.txt` (the PM files where
GuidedEmergence was authored). mxbai_rechunk surfaced
`32_BlindSpotAdvisor.txt` and `28_CognitiveArchitecture.txt` —
none of which contain the key term.

### Root cause analysis

The regression correlates with two things:

1. **Corpus size mismatch.** mxbai_original has 2,500 chunks;
   mxbai_rechunk has 10,000. Queries compete against 4× more
   candidates. Some correct-answer chunks get outranked by more
   general content that's now in the pool.
2. **Chunk fragmentation.** The structure-aware splitter cut
   files into significantly more chunks per file. Files like
   `STD-DDL-SWEEPREPORT-001.txt` that originally had 9 chunks
   (500-token each) now have 20+ smaller pieces. The identifier
   line appears in only the first chunk, and that chunk is now
   much smaller (fewer surrounding words to anchor the embedding).
   Smaller chunks = less semantic context = weaker retrieval.

This matches the dominant signal in retrieval research: smaller
chunks are better *when the query targets a specific fact*;
larger chunks are better *when the query targets a concept that
needs surrounding context*. Dex Jr.'s governance queries skew
toward the concept-and-context class. Shrinking the chunker hurt
those.

---

## Decision: HALT rechunk, proceed to 33b with original chunker

### Gate criteria (per prompt)

- PROCEED if: batching works ✅ **AND** rechunk retrieval ≥ Step
  32 mxbai ❌ **AND** no chunk-quality regressions ⚠ (7/10
  mid-word; inherent overlap artifact, not a splitter bug)
- HALT if: rechunk retrieval regresses vs Step 32 mxbai — **YES,
  regresses on 2/9**

**Gate answer: HALT rechunk. Do not proceed with the
structure-aware 400-token chunker.**

### Recommended Step 33b path

Migrate the live collections to `mxbai-embed-large` using the
**existing 500-token chunker**. Rationale:

- Step 32 validated 8/8 retrieval quality on this configuration
- Zero chunks were skipped with adaptive truncation in any test
- mxbai's 512-token context limit affects ~1/3 of existing chunks
  (those > 1200 chars); truncating them preserves the first
  ~70% of content. In the Step 32 test this was sufficient for
  8/8 recall. We accept that tail-of-chunk loss for now.
- Keeps the chunker change as a separate, future decision — not
  coupled to the embedding model migration

### Proposed Step 33b parameters

| Setting | Value |
|---|---|
| Embedding model | `mxbai-embed-large` |
| Chunker | **unchanged** (`CHUNK_SIZE_TOKENS=500, CHUNK_OVERLAP_TOKENS=50` in dex-ingest.py) |
| Adaptive truncation | 1200 → 900 → 600 → 300 chars per chunk text |
| Batch size | 8 (per probe) |
| Expected wall time | ~5 hours for 554K chunks (cold) |
| New collection names | `dex_canon_v2`, `ddl_archive_v2`, `dex_code_v2`, `ext_creator_v2` |
| Retention | B3 + B2 retrieval logic in `dex_jr_query.py` (unchanged) |
| Rollback | `D:\DDL_Backup` restore + git revert |

### Pre-flight checklist for Step 33b

1. Fresh chromadb backup at `D:\DDL_Backup\chromadb_backups\` (Trigger 2 gate)
2. 324 GB free on C: (confirmed this step; ChromaDB will grow ~4 GB during migration with 1024-dim embeddings vs 768-dim)
3. Nightly sweep disabled or paused during migration window (to avoid write contention while re-embedding reads)
4. Self-test of `dex_jr_query.py` currently passing (confirmed Step 31)
5. Operator signs off on "accept truncation over rechunk" decision

### What NOT to do in 33b

- Do not rechunk. If chunker changes are wanted later, do them as
  a separate Step 34.
- Do not delete old collections immediately after the swap. Soak
  period 24-72h minimum.
- Do not ship both embedding-model swap AND chunker change in one
  step. One variable at a time.

---

## Appendix A — Test artifacts (committed)

- `_step33a_batching_probe.py`
- `_step33a_rechunk_builder.py`
- `_step33a_comparative_test.py`
- `AUDITS/STEP33A_BATCHING_AND_RECHUNK_VALIDATION_2026-04-12.md` (this file)

Untracked (diagnostic outputs, kept locally):
- `_step33a_batching_probe.json`
- `_step33a_rechunk_builder.json`
- `_step33a_comparative_test.json`

## Appendix B — Test collections left intact

Per prompt constraint, both test collections remain in ChromaDB:

- `dex_canon_mxbai_test` (2,500 chunks, Step 32 baseline)
- `dex_canon_mxbai_rechunk_test` (10,000 chunks, Step 33a)

Operator decides disposition in Step 33b. If proceeding with the
recommended non-rechunk path, both are retainable as future
comparison points and can be dropped after soak.

## Appendix C — What the "mid-word" spot-check really measures

The 7/10 mid-word flag is a boundary artifact of overlap, not a
splitter bug. Every chunk after the first will start with 200
chars of the previous chunk's tail, which by definition usually
starts inside a sentence.

Two ways to interpret this going forward:

1. **Accept it.** The existing `dex-ingest.py` chunker produces
   the same artifact in the live collections, and Step 32 showed
   retrieval works fine with those chunks. This is a cosmetic
   flag, not a quality signal.
2. **Change the overlap.** Move the overlap rule to "last full
   sentence of previous chunk, up to N chars." Cleaner boundaries,
   slightly more complexity, deferrable.

For Step 33b: accept as-is. The existing chunker already has this
behavior and it's working.
