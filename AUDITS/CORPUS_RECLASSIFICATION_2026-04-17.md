# CORPUS RECLASSIFICATION — dex_canon_v2

**Date:** 2026-04-17
**Current state:** 258,492 chunks, 4,683 unique source files
**Executor:** Claude Code
**Status:** AWAITING OPERATOR GO

---

## RECLASSIFICATION SUMMARY

| Target | Files | Chunks | % of corpus |
|---|---:|---:|---:|
| stays in dex_canon | 3,315 | 58,919 | 22.8% |
| → ddl_archive | 1,124 | 94,795 | 36.7% |
| → dex_code | 54 | 414 | 0.2% |
| → ext_creator | 0 | 0 | 0.0% |
| → DELETE | 190 | 104,364 | 40.4% |
| **TOTAL** | **4,683** | **258,492** | **100%** |

**40% of dex_canon is garbage.** ChatGPT export chunks with raw
binary/embedding data (104K chunks) rank at 0.90 weight alongside
ratified governance documents.

**37% is misrouted archive.** Text messages, thread exports, session
logs — all personal/historical content that belongs in ddl_archive
at 0.65 weight, not dex_canon at 0.90.

**Only 23% is actual canon.** Council reviews, governance artifacts,
council threads, cognitive architecture docs, standards, protocols.

---

## DELETE BREAKDOWN (104,364 chunks — 40.4%)

| Reason | Chunks |
|---|---:|
| ChatGPT raw export (conversations_chunk_*.txt) — binary/embedding data | 43,671 |
| ChatGPT raw export (chat_chunk_*.txt) | 39,619 |
| Reddit/XLSX comment exports — noise | 15,426 |
| ChatGPT group chat exports (group_chats_chunk_*.txt) | 5,648 |

These are the source of the "F-codes" garbage results. The ChatGPT
export chunks contain literal floating-point embedding arrays that
were chunked as text.

---

## → ddl_archive (94,795 chunks — 36.7%)

Top categories:
- **Text message exports** (Messages - *.txt): ~25K chunks across
  ~35 contacts. Personal conversations at 0.90 weight.
- **Thread exports** (*_Thread*.txt): ~30K chunks. PM sessions,
  LLM threads, work project discussions.
- **Session logs** (*Session*.txt): ~15K chunks. CC/PM session
  transcripts.
- **Numbered PM exports** (NN_Name.txt): ~10K chunks.
- **iOS notes, converted exports**: ~5K chunks.

These are valuable historical context but NOT governed canon.
Moving to ddl_archive drops their weight from 0.90 to 0.65.

---

## stays in dex_canon (58,919 chunks — 22.8%)

Top content:
- Council thread compilations (CouncilThreads_*.txt): ~5K chunks
- Cognitive architecture docs: ~5K chunks
- DDLCouncilReview_*.txt: ~3K chunks (the actual reviews)
- Governance artifacts (STD-, PRO-, ADR-, CR-): ~1K chunks
- Bridge/AutoCouncil transcripts: ~2K chunks
- Boot prompts, profiles, handoffs: ~1K chunks
- Unclassified .txt/.md (conservative keep): ~40K chunks

Note: ~40K chunks classified as "conservative keep" may include
further archive material. The operator can review the full CSV
for these.

---

## → dex_code (414 chunks — 0.2%)

54 Python/JS/CSS files that got ingested into dex_canon instead
of dex_code. Small impact but wrong collection.

---

## REBUILD OPTIONS

### Option A: Full Rebuild (recommended)

1. Backup current state
2. Empty dex_canon_v2 completely
3. Re-ingest all source files from CANON_DIR with proper
   --collection routing based on classification
4. DELETE targets are simply not re-ingested
5. Rebuild ingest cache

**Pro:** Cleanest result. Every chunk re-embedded with current
model. No orphan metadata.
**Con:** ~60 min on RTX 3070 for 58K chunks. Requires all source
files to still exist on disk in CANON_DIR.

**Risk:** Source files that were ingested but never saved to
CANON_DIR (e.g., early manual ingests) would be lost. Need to
verify file availability before emptying.

### Option B: Surgical Delete

1. Delete the 104K DELETE chunks by source_file
2. Delete the 95K ddl_archive chunks by source_file
3. Delete the 414 dex_code chunks by source_file
4. Don't re-ingest — those chunks just leave dex_canon
5. ddl_archive and dex_code don't grow (those files may
   already be in ddl_archive_v2)

**Pro:** Fast (~5 min). No re-embedding. No file dependency.
**Con:** Doesn't fix the conservative-keep bucket. Doesn't
re-embed with current model.

### Option C: Surgical Delete + Selective Re-ingest

1. Delete the 104K DELETE chunks
2. Move the 95K archive chunks to ddl_archive_v2 (copy then delete)
3. Move the 414 code chunks to dex_code_v2
4. Leave canon chunks untouched

**Pro:** Preserves existing embeddings. Proper collection routing.
**Con:** Complex. Chunk copy between collections requires
re-embedding (different collection = different index).

---

## RECOMMENDATION

**Option B (Surgical Delete)** for tonight. Remove the 104K garbage
chunks immediately — that's 40% of the corpus polluting every query.
The archive misrouting (36.7%) affects ranking but doesn't produce
garbage results like the binary data does.

Schedule Option A (Full Rebuild) for a weekend session when the
operator can monitor the 60-min re-embed.

**Immediate impact of Option B:**
- dex_canon_v2: 258,492 → ~154,128 chunks
- "F-codes" query: no more float data
- "Sibling Mandate" query: family texts still present (archive
  misrouting not fixed) but less noise overall

---

## FILES

- Full audit: `AUDITS/CORPUS_AUDIT_2026-04-17.csv` (4,683 rows)
- Raw source data: `AUDITS/_corpus_sources_raw.json`
- This report: `AUDITS/CORPUS_RECLASSIFICATION_2026-04-17.md`

**AWAITING OPERATOR GO BEFORE ANY ACTION.**
