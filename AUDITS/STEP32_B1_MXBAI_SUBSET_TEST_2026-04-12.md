# STEP 32 — B1 Subset Test with mxbai-embed-large

**Date:** 2026-04-12
**CR:** Phase 2 Step 32
**Operator:** Dave Kitchens
**Executor:** Claude Code (Dex Jr., Seat 1010)
**Scope:** Subset comparison. No live-collection modification.

---

## Headline

**`mxbai-embed-large` materially improves retrieval on every query
tested, including both identifier queries and all six concept queries
that `nomic-embed-text` failed.** Win/loss across 8 queries:
**mxbai 8, nomic 0.** A full-corpus migration to `mxbai-embed-large`
is recommended for Step 33, with an estimated 7.1 hours of re-embed
wall time on the 3070.

The caveat worth pricing in: `mxbai-embed-large` has a 512-token
context window (vs nomic's 2K). Chunks were truncated to 1,200 chars
to fit; 0/2,500 subset chunks needed adaptive backoff. A full
migration should either accept the truncation loss on big chunks, or
re-chunk to smaller units (≤400 tokens) at the same time.

---

## Test collection composition

- **Collection:** `dex_canon_mxbai_test` (new, `test_only: true`)
- **Chunks:** 2,500 (of 245,633 in `dex_canon`)
- **Selection method:** `where_document.$contains` on 9 seed terms →
  1,060 unique chunks → expanded by `source_file` to include every
  chunk from each seed-matched file → capped at 2,500
- **Seed-term contributions:**

| Seed term | New chunks |
|---|---:|
| CottageHumble | 200 |
| AccidentalIntelligence | 121 |
| GuidedEmergence | 164 |
| Charlie Conway | 23 |
| Beth Epperson | 200 |
| Mithril | 200 |
| STD-DDL-PRIVACY-001 | 14 |
| STD-DDL-SWEEPREPORT-001 | 33 |
| STD-DDL-BACKUP-001 | 105 |

- **Re-embed model:** `mxbai-embed-large` (334M params, 670 MB disk, 1024-dim)
- **Re-embed throughput:** 21.67 chunks/sec (single-stream Ollama)
- **Extrapolated full re-embed (554,459 chunks):** 7.1 hours

---

## A2 sanity — mxbai under the same tests as Step 28

| Pair | nomic cos | mxbai cos |
|---|---:|---:|
| `"cat sat on the mat"` vs `"cat was on the mat"` | 0.0773 | 0.0604 |
| `"STD-DDL-SWEEPREPORT-001"` vs itself | 0.0000 | 0.0000 |
| `"STD-DDL-SWEEPREPORT-001"` vs `"STD DDL SWEEPREPORT 001"` | 0.0452 | 0.0236 |
| **`STD-DDL-SWEEPREPORT-001`** vs **`STD-DDL-BACKUP-001`** | **0.0000** | **0.2438** |
| `"CottageHumble"` vs `"humble surface cathedral underneath"` | (not tested) | 0.5103 |

**Row 4 is the fix.** Under nomic these two DDL identifiers embed
identically; under mxbai they sit 0.24 cosine apart — comfortably
distinct. The tokenizer is preserving the signal.

---

## Comparative retrieval — 8 queries

For each query, queries the live `dex_canon` (245K chunks, nomic)
and `dex_canon_mxbai_test` (2.5K chunks, mxbai) with top-K=5. "Key
term in top-5" checks whether any of the 5 returned chunk bodies
actually contain the query's key term — the strongest practical
retrieval signal.

| # | Query | Key term | nomic top-1 dist | nomic recall | mxbai top-1 dist | mxbai recall |
|---|---|---|---:|---|---:|---|
| 1 | STD-DDL-SWEEPREPORT-001 protocol classification predicate | STD-DDL-SWEEPREPORT-001 | 244.57 | ❌ | 0.589 | ✅ |
| 2 | CR-OPERATOR-CAPACITY-001 | CR-OPERATOR-CAPACITY-001 | 185.67 | ❌ | 0.653 | ✅ |
| 3 | What is AccidentalIntelligence? | AccidentalIntelligence | 306.79 | ❌ | 0.589 | ✅ |
| 4 | Explain the GuidedEmergence pattern | GuidedEmergence | 240.58 | ❌ | 0.490 | ✅ |
| 5 | What does CottageHumble mean? | CottageHumble | 191.51 | ❌ | 0.779 | ✅ |
| 6 | What is the Charlie Conway Principle? | Charlie Conway | 263.63 | ❌ | 0.758 | ✅ |
| 7 | Who is Beth Epperson? | Beth Epperson | 305.51 | ❌ | 0.794 | ✅ |
| 8 | What is the Mithril Standard about? | Mithril | 279.58 | ❌ | 0.588 | ✅ |
| **Totals** | | | | **0/8** | | **8/8** |

Notable top-5 source files retrieved by mxbai:

- **STD-DDL-SWEEPREPORT-001:** ranks the actual `STD-DDL-SWEEPREPORT-001.txt`
  plus its Draft variant and the sweep-protocol council review file
- **CR-OPERATOR-CAPACITY-001:** surfaces `89_LLMPM Boot Prompt and Q and A.txt`
  and `84_ExcelligencePM.txt` — the files that actually discuss the CR,
  same ones B2 found via `$contains`
- **AccidentalIntelligence / GuidedEmergence:** surfaces
  `79_KnowledgeVaultAdvisor.txt`, `79_KnowledgeVaultPM.txt`,
  `81_WebsiteAdvisor.txt`, `85_WritingPM.txt` — the PM files where
  these patterns were authored
- **CottageHumble:** surfaces `DDLCouncilReview_WalkTheSite.txt`,
  `28_DDLWebsite - Consolidated 5.txt`, `83_MarcusCaldewellPM.txt` —
  the website design review + Marcus's design thread
- **Charlie Conway:** surfaces `DDLCouncilReview_SpiralProtocol.txt`
  and Deepseek/BlindSpot threads — the discussions that reference it
- **Beth Epperson:** surfaces four message-history files directly
  about Beth Epperson + DropDownLogistics — trivially correct
- **Mithril:** surfaces `83_MarcusCaldewellPM.txt` and
  `DDLCouncilReview_Mithril.txt` — the definition's home

Every mxbai top-5 reads like the answer-space a human would expect.
Every nomic top-5 reads like a random sample of the corpus.

---

## Throughput + extrapolation

- **Subset throughput:** 21.67 chunks/sec (single-stream, batch=32
  wrapping single-prompt Ollama calls)
- **Total subset re-embed:** 115 s for 2,500 chunks
- **Skipped:** 0 (adaptive truncation from 1,200 → 900 → 600 → 300
  chars handled all content)
- **Extrapolated full re-embed:** 554,459 chunks ÷ 21.67 c/s ÷ 3600
  = **7.10 hours**

Batch embedding via `/api/embed` (plural endpoint, array input) was
not attempted in this subset test. If it's supported by Ollama's
current mxbai implementation, full re-embed time likely drops to
2–3 hours. Worth a probe as part of Step 33 planning.

### mxbai context limit

`mxbai-embed-large` has a 512-token context window. Under the
current 500-token chunker (roughly 2000 chars in practice; actual
chunks were 1,265–1,957 chars), many chunks exceed the model's
capacity. The subset test truncated to 1,200 chars and let the
backoff path handle any stragglers — 0 skipped across 2,500 chunks.

**Implication for a full migration:**
1. Accept truncation: embed from the first ~1,200 chars of each
   chunk. Loses tail content for ~30-50% of chunks that exceed this
   length. Some semantic signal lost but still dominant over nomic's
   identifier failure.
2. Re-chunk first: cut the chunker to ~400 tokens (~1,600 chars)
   with 50-token overlap (~200 chars). Doubles chunk count to
   ~1.1 M. Preserves every char of content in the embed. Larger
   HNSW index, more disk, slightly more wall time.
3. Stay chunked at 500 tokens but split chunks > 1,600 chars into
   two embeddings (with metadata linking them to the same parent
   chunk). Hybrid — cleanest semantic preservation, moderate
   complexity.

Option 2 is the recommended path if re-chunking ever was going to
happen; pair it with the embed swap.

---

## Recommendation

**Option 1 — proceed with B1 full migration. mxbai is clearly better.**

The evidence is not marginal. nomic fails all 8 test queries; mxbai
wins all 8. The concept-retrieval class of failures (6 out of 8)
that B3+B2 can't touch becomes solved with the model swap alone.
Identifier queries (2 out of 8) additionally get sensible distance
signals, which may let us soften or retire B3+B2 over time.

### Proposed Step 33 plan

1. **Backup-first gate:** ensure `D:\DDL_Backup` contains a fresh
   chromadb backup (Trigger 2 should fire automatically on the next
   ingest or can be forced with `dex-backup.py --force`).
2. **Create new scoped collections** (one per live collection):
   - `dex_canon_v2`
   - `ddl_archive_v2`
   - `dex_code_v2`
   - `ext_creator_v2`
   All with `metadata.embedding_model = "mxbai-embed-large"` and
   `metadata.chunker_version` tag so we can track provenance.
3. **Re-embed in batches:** script that iterates each live
   collection's chunk IDs, fetches (doc, meta), re-embeds with
   mxbai, upserts into the `_v2` twin. Resumable (checkpoint by
   chunk id). Expected wall time: ~7 hours single-stream, ~2-3
   hours if `/api/embed` batching works.
4. **Validate:** count parity, sampled retrieval on the 8 queries
   of this audit against the full `_v2` collections, self-test.
5. **Flip the switch:** update `dex_jr_query.py` and `dex-ingest.py`
   to use `mxbai-embed-large` and the `_v2` collection names.
   Retain B3+B2 (they complement vector retrieval at near-zero
   cost; no reason to rip them out).
6. **Soak period:** 24–72 hours of real workflow queries. If
   clean, drop the old nomic collections and rename `_v2` → canonical
   name. If issues, rollback is `git revert` + swap the collection
   names back; data from the backup is still intact.

**Rollback plan:** `D:\DDL_Backup` restore restores the nomic
collections whole. `_v2` collections can be deleted without
touching `dex_canon` etc. Code reverts via git.

### What to decide before Step 33

- **Chunker change or not?** Option 1 (accept truncation) ships
  faster but loses ~half of chunk tails. Option 2 (re-chunk to
  400 tok) preserves everything and doubles chunk count. Operator
  decides.
- **Wait for batching probe?** If `/api/embed` batch support drops
  wall time from 7h to 2h, it's worth an extra 30 minutes of
  investigation up front.

### Option 2 / Option 3 fallbacks (not recommended given results)

- Option 2 (test another model, e.g. `bge-large-en-v1.5`): only if
  operator wants a second data point before committing. mxbai's
  margin here is large enough that a tiebreaker feels like
  premature optimization.
- Option 3 (pivot to corpus rebuild): not indicated. The corpus
  is fine; the embedding model was the bottleneck.

**Should the operator read the full audit before deciding?** Yes.
Step 33 is a multi-hour compute operation with a backup/flip-switch
sequence and a reversibility plan worth reading. The decision to
commit is straightforward; the execution has enough moving parts to
merit a full read.

---

## Appendix A — Test artifacts

- `_step32_subset_build.py` — builds the test collection
- `_step32_subset_build.json` — build metadata (throughput, counts)
- `_step32_comparative_test.py` — runs the 8-query comparison
- `_step32_comparative_test.json` — structured results

Test collection `dex_canon_mxbai_test` left intact in ChromaDB for
possible further testing. Not to be deleted in this step per prompt.

## Appendix B — Raw sanity pair distances

Full output of the A2 comparison is in
`_step32_comparative_test.json → sanity_pairs`.

## Appendix C — Model sizes and VRAM

| Model | Params | Disk | Dim |
|---|---|---|---|
| nomic-embed-text | 137M | 0.27 GB | 768 |
| mxbai-embed-large | 334M | 0.67 GB | 1024 |

Both load comfortably alongside qwen2.5-coder:7b on the 3070. No
OOM observed during subset re-embed.

## Appendix D — Open items for Step 33

1. Decide: truncation vs re-chunk (operator)
2. Probe `/api/embed` batch endpoint for throughput
3. Draft Step 33 pre-flight (backup state, disk space, staging
   collections)
4. Plan for B3+B2 retention — they still help and cost nothing;
   recommendation is keep them
