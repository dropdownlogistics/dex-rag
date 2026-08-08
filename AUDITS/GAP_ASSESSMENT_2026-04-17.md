# GAP ASSESSMENT — Dex Jr. System Efficiency Audit

**Date:** 2026-04-17
**Executor:** Claude Code (Seat 1010 execution layer)
**Scope:** Full system audit after Steps 48-58
**Status:** Read-only assessment. No action taken.

---

## SYSTEM STATE SNAPSHOT

**Active tracked files:** 20 (root) + governance dirs
**Archived files:** 38 (in archive/)
**Corpus:** 566,804 chunks across 4 LIVE collections
**Models loaded (Reborn):** 9 (dexjr, mxbai-embed-large, llama3.1:8b,
qwen2.5-coder:7b, deepseek-r1:8b, gemma3:4b, phi3.5, llava, nomic)
**Models loaded (Gaming Laptop):** 4 (deepseek-r1:8b, gemma3:4b,
phi3.5, nomic)
**Hosts:** Reborn ONLINE, Gaming Laptop ONLINE
**Cloud APIs:** Gemini OK, Mistral OK
**Last sweep:** 2026-04-16 04:00 (skipped_report_only — only reports
in DDL_Ingest)
**Last backup:** 2026-04-15 09:01 (45h old, status success)
**Council log:** 22 runs, latest version 4.0
**Sweep log:** 64 entries

**Scheduled tasks (Task Scheduler):**
- DexSweep-NightlyIngest: daily 4:00 AM (sweep + ingest + backup)
- Note: `schtasks` query returned no results from this session (likely
  permission/encoding issue). Tasks confirmed via AUDITS/Step46 and
  sweep log evidence.

---

## A. CONTENT PIPELINE GAPS

### GAP A1: dex-convert.py silent data loss (CLAUDE.md Critical Bug #1)
**Status:** UNFIXED — 5 `except Exception:` blocks at lines 252, 355,
360, 374, 419 silently drop records during HTML/CSV/JSON/MBOX/VCF
conversion. Operator has zero visibility into how many documents have
been lost during ingest.
**Impact:** HIGH — every ingest run potentially loses data silently.
**Effort:** 1 CC session (add counters, log failures, flag-on-failure).
**Automation:** Once fixed, integrate into sweep pipeline for automatic
conversion of non-text formats.

### GAP A2: No PDF ingestion
**Status:** PHASE1_EXTENSIONS has 22 file types but NO `.pdf`. PDFs
dropped into DDL_Ingest are silently ignored by the sweep. dex-convert.py
doesn't handle PDF either.
**Impact:** MEDIUM — operator has PDF content (Leverage_Points.pdf in
repo root, likely others in DDL_Ingest).
**Effort:** 1 CC session (add PyPDF2/pdfplumber extraction to pipeline).
**Automation:** Add `.pdf` to PHASE1_EXTENSIONS + convert step.

### GAP A3: Council review content → corpus is manual
**Status:** Council runs saved to `council-runs/` folder (8 existing
folders). The `--ingest` flag on dex-council.py triggers auto-ingest of
the full transcript. But council runs initiated without `--ingest` stay
in `council-runs/` and never reach the corpus.
**Impact:** MEDIUM — 8 council run folders exist, representing weeks of
structured analysis that may not be in the corpus.
**Effort:** Quick win — add a `dex ingest-councils` command that scans
`council-runs/` and ingests any un-ingested transcripts.
**Automation:** Could be part of the nightly sweep.

### GAP A4: Bridge transcripts accumulate without cleanup
**Status:** `bridge-ingest/` dir gets a transcript per bridge query.
auto_ingest runs `--build-canon --fast` on the whole dir. Over time
this accumulates thousands of small files.
**Impact:** LOW — works but messy. No cleanup cadence.
**Effort:** Quick win — add post-ingest cleanup (delete after confirmed
ingest) or rotation.

### GAP A5: No .docx / .pptx / .xlsx content extraction
**Status:** dex-xlsx.py (now in archive/) handled .xlsx. No .docx or
.pptx support. These are common operator content formats.
**Impact:** LOW (most operator content is .txt/.md from LLM exports).
**Effort:** Medium — python-docx / python-pptx extraction.

---

## B. RETRIEVAL QUALITY GAPS

### GAP B1: "F-codes" query returns embedding float data
**Status:** The query "What are the F-codes?" retrieves ChatGPT export
chunks containing literal floating-point embedding values (e.g.,
`4.29907516e-02f`). The word "f" in "F-codes" partially matches these
numeric patterns in vector space.
**Impact:** HIGH — common operator query returns garbage.
**Effort:** Quick win — the fix is corpus hygiene: these ChatGPT export
chunks contain raw JSON/binary data that should never have been ingested
as text. A cleanup pass to identify and quarantine binary-content chunks
would fix this class of issue permanently.
**Automation:** Add a chunk quality filter in dex-ingest.py that detects
and skips chunks with >50% non-readable characters.

### GAP B2: "Sibling Mandate" requires qualification
**Status:** "What is the Sibling Mandate?" returns family text messages
(siblings texting). "What is the Sibling Mandate in DDL architecture?"
returns the correct answer from the primer. The primer knowledge is
present but the model prioritizes retrieved chunks over it.
**Impact:** MEDIUM — workaround exists (qualify the query), but the
operator shouldn't have to.
**Effort:** Medium — options: (a) boost primer weight in prompt
instruction, (b) add a pre-retrieval classifier that detects DDL-term
queries and injects primer context more aggressively, (c) re-rank
results that conflict with primer definitions.

### GAP B3: 39% of migrated chunks have truncated embeddings
**Status:** Step 33c flagged ~3,274 chunks whose embedding prompts were
progressively truncated to fit mxbai's 512-token context. These chunks
have slightly degraded retrieval precision.
**Impact:** LOW — retrieval works, just not optimal for those chunks.
**Effort:** Medium — re-chunk those specific files with proper token
limits. The ingest cache (Step 48) makes this safe (re-chunk triggers
on modified content).

### GAP B4: No retrieval quality benchmarks
**Status:** No automated retrieval quality testing. Step 28 did a
one-time audit. No recurring check that key queries return expected
documents.
**Impact:** MEDIUM — retrieval quality could degrade without notice.
**Effort:** 1 CC session — build a benchmark suite of 10-20 known
query→expected_source pairs. Run weekly.
**Automation:** Schedule weekly via Task Scheduler.

---

## C. AUTOMATION GAPS

### GAP C1: Health check not verified as scheduled
**Status:** The prompt says health check runs at 4:15 AM daily, but
no Task Scheduler entry was visible. If it's not scheduled, it's not
running.
**Impact:** HIGH — the entire health monitoring layer may not be active.
**Effort:** Quick win — verify/create Task Scheduler entry for
`python dex_health.py --json >> health_log.jsonl`.
**Automation:** Already designed for automation. Just needs scheduling.

### GAP C2: No git auto-push
**Status:** Every session requires manual `git push`. The operator
has to remember, and tonight's push hit GitHub 500s requiring manual
intervention.
**Impact:** LOW (commits are safe locally, push is ceremony not safety).
**Effort:** Quick win — add `git push origin main` to the post-sweep
or post-health-check pipeline. Or schedule separately.
**Risk:** Auto-push could push unintended commits. Safer as a
scheduled daily push (e.g., 5:00 AM after sweep completes).

### GAP C3: No log rotation
**Status:** 6 JSONL log files growing indefinitely:
- dex-bridge-log.jsonl (149KB, growing per bridge query)
- dex-council-log.jsonl (19KB, 22 entries)
- dex-sweep-log.jsonl (37KB, 64 entries)
- dex-fetch-log.jsonl (50KB, historical)
- dex-deliberation-log.jsonl (2KB, historical)
- dex-xlsx-log.jsonl (25KB, historical)
**Impact:** LOW (won't be a problem for months at current growth).
**Effort:** Quick win — archive logs older than 90 days.
**Automation:** Add to sweep or weekly schedule.

### GAP C4: No automatic primer freshness check
**Status:** DDL_PRIMER.md is manually maintained. If products change,
council seats change, or architecture changes, the primer goes stale
and Dex Jr. gives wrong answers from deterministic knowledge.
**Impact:** MEDIUM — primer is the ground truth layer. Stale primer =
confidently wrong answers.
**Effort:** Quick win — add a primer freshness check to dex_health.py
(file age, hash comparison against a known-good hash).
**Automation:** Flag in health check if primer is >30 days old.

---

## D. EXTERNAL CONTENT GAPS

### GAP D1: No external content pipeline (operator's top ask)
**Status:** Two archived scripts partially implement this:
- `dex-fetch.py` — single URL fetch, HTML strip, optional ingest.
  Uses nomic-embed-text (stale). Targets dex_canon (wrong collection).
  Otherwise functional.
- `dex-acquire.py` — batch URL acquisition with quality evaluation
  (7+/10 auto-ingest, 5-6 flag, <5 skip). Uses nomic (stale), wrong
  CHROMA_PATH. Has BeautifulSoup HTML parsing, polite crawling delays,
  source attribution headers. Well-designed but needs rewiring.
**Impact:** HIGH — the operator wants this and has working foundations.
**Effort:** 1-2 CC sessions to modernize (rewire to dex_core, add
CSV/spreadsheet input, target ext_creator/ext_reference, add scheduling).
**Automation:** Task Scheduler weekly run.

### GAP D2: No RSS/Atom feed monitoring
**Status:** No feed reader. Industry publications, audit standard
updates, and competitor blogs all publish via RSS.
**Impact:** LOW (nice-to-have, not blocking).
**Effort:** Medium — feedparser library + ingest pipeline.

### External Content Pipeline Design (Phase 4)

See dedicated section below.

---

## E. SCHEDULING GAPS

### Current schedule:
| Time | Task | Status |
|---|---|---|
| 4:00 AM | Sweep + ingest + backup | CONFIRMED (sweep log active) |
| 4:15 AM | Health check | UNVERIFIED (no schtasks evidence) |
| Sunday 1 AM | Weekly council evaluation | UNVERIFIED |

### Recommended additions:
| Time | Task | Effort |
|---|---|---|
| 4:20 AM | `git push origin main` (daily) | Quick win |
| 5:00 AM Sunday | Retrieval quality benchmark (weekly) | 1 session |
| 6:00 AM Monday | External content refresh (weekly) | 1-2 sessions |
| 1st of month | Log rotation (monthly) | Quick win |
| 1st of month | Primer freshness check (monthly) | Quick win |

---

## F. TOOL GAPS

### GAP F1: No `dex dashboard` command
**Status:** No single-glance view of system state. Operator must run
`dex health`, `dex log`, `dex hosts`, `dex weights` separately.
**Impact:** MEDIUM — on a phone, 4 commands is 4 too many.
**Effort:** Quick win — composite command that runs health (quick) +
last sweep status + last council run + corpus total in one output.

### GAP F2: No `dex stats` command
**Status:** `dex status` runs `dex_health.py --quick` (infrastructure).
No command shows corpus stats (collection counts, chunk growth trend,
cache entries, last ingest time).
**Impact:** LOW — `dex health` shows collection counts.
**Effort:** Quick win — add `dex stats` that queries collection counts +
cache stats + last sweep result.

### GAP F3: No `dex fetch` command in router
**Status:** dex-fetch.py is in archive/. When modernized for the
external content pipeline, it should get a `dex fetch` / `dex f`
subcommand.
**Impact:** Blocked on GAP D1 (external pipeline rebuild).

### GAP F4: No `dex convert` command in router
**Status:** dex-convert.py is an active file (imported by
dex-ingest-text.py) but not in the dex.ps1 router.
**Impact:** LOW — rarely called directly.
**Effort:** Quick win — add to router.

---

## G. INTELLIGENCE GAPS

### GAP G1: No auto-classification of incoming files
**Status:** The sweep ingests everything into dex_canon_v2 regardless
of content type. Council reviews, session logs, governance docs, and
casual notes all get the same treatment.
**Impact:** MEDIUM — source_type metadata is inferred by filename
pattern (infer_source_type in dex-ingest.py), but this is a heuristic.
**Effort:** Medium — add an LLM classification step that reads the
first 500 chars of each new file and assigns a source_type before
chunking. Would improve retrieval weighting accuracy.
**Automation:** Add to sweep pipeline before ingest.

### GAP G2: No daily digest
**Status:** No automatic summary of what entered the corpus overnight.
The sweep report shows file names and chunk counts but not content
summaries.
**Impact:** LOW — operator can check sweep reports.
**Effort:** Medium — have Dex Jr. summarize new chunks from the last
24h and write a 5-line digest.

### GAP G3: No drift detection between primer and corpus
**Status:** If the primer says "11 seats" but the corpus contains
references to "10 seats" from older documents, Dex Jr. may give
conflicting answers depending on which context dominates.
**Impact:** MEDIUM — primer/corpus conflicts are a known source of
confused responses.
**Effort:** Medium — build a drift detector that queries known primer
facts against the corpus and flags contradictions.

### GAP G4: No anomaly detection in logs
**Status:** Sweep and backup logs exist but nobody reads them unless
something breaks. Patterns like "3 consecutive failures" or "chunk
count dropped" go unnoticed.
**Impact:** LOW — health check catches most issues.
**Effort:** Quick win — add anomaly checks to health check (e.g.,
"last 3 sweeps all failed" or "backup >96h old").

---

## PHASE 4: EXTERNAL CONTENT PIPELINE DESIGN

### Architecture

**Input:** `ext_sources.csv` in repo root.

```csv
url,source_name,category,frequency,target_collection,active
https://simonwillison.net/atom/everything/,Simon Willison,technology,weekly,ext_creator,true
https://www.auditboard.com/blog/,AuditBoard Blog,audit,monthly,ext_reference,true
```

**Processing script:** `dex-acquire.py` (modernized from archive):

1. Read `ext_sources.csv`
2. For each active source:
   a. Check last-fetch timestamp in `ext_fetch_cache.json`
   b. If due (based on frequency), fetch URL
   c. Strip HTML (BeautifulSoup), extract text
   d. Quality gate: score 1-10 via Dex Jr. (existing dex-acquire logic)
   e. If quality >= 7: chunk and ingest into target collection
   f. If quality 5-6: flag for operator review
   g. If quality < 5: skip, log reason
   h. Update fetch cache with timestamp + hash

3. **PDF support:** Add pdfplumber extraction path for URLs ending
   in .pdf or returning application/pdf content-type.

4. **Dedup:** Use the ingest cache (Step 48) — if content hash matches
   previous fetch, skip.

**Governance:**
- New URLs require operator approval (add to CSV manually or via
  `dex add-source <url> --category <cat> --collection <target>`)
- ext_creator: operator-approved external creator content (blogs,
  publications by known authors)
- ext_reference: vetted reference material (standards bodies, industry
  publications)
- ADR-CORPUS-001 governs collection assignment

**CLI integration:**
```
dex fetch                    # run all due sources
dex fetch --url <url>        # one-off fetch
dex fetch --list             # show all sources + last fetch
dex fetch --add <url>        # add a new source (operator approval)
```

**Scheduling:** Task Scheduler weekly (Monday 6:00 AM).

### Existing foundations to modernize:
- `archive/standalone-utils/dex-fetch.py` — HTML stripping, sitemap
  crawling, save/ingest modes. Needs: dex_core rewire, mxbai embeddings,
  _v2 collections.
- `archive/standalone-utils/dex-acquire.py` — Quality gate (7/5 thresholds),
  batch URL processing, source attribution headers. Needs: dex_core rewire,
  mxbai embeddings, correct CHROMA_PATH, BeautifulSoup already imported.
- `fetch_ext_creators.py` — exists in repo root (active, untracked).
  Fetches specific creator URLs. Could be the starting point.
- `fetch_simon_willison.py` — exists in repo root (untracked). Single-
  creator fetcher. Merge into the CSV-driven pipeline.

### Effort estimate: 2 CC sessions
- Session 1: Modernize dex-acquire.py, add CSV input, wire to dex_core
- Session 2: Add PDF support, scheduling, CLI integration

---

## RANKED RECOMMENDATIONS

| # | Gap | Impact | Effort | Ratio | Recommendation |
|---|---|---|---|---|---|
| 1 | C1 | HIGH | Quick win | **BEST** | Verify/create health check Task Scheduler entry |
| 2 | A1 | HIGH | 1 session | HIGH | Fix dex-convert.py silent data loss (5 except blocks) |
| 3 | D1 | HIGH | 2 sessions | HIGH | Build external content pipeline (CSV-driven dex-acquire) |
| 4 | B1 | HIGH | Quick win | HIGH | Corpus hygiene: quarantine binary-content chunks |
| 5 | F1 | MED | Quick win | HIGH | Add `dex dashboard` composite command |
| 6 | B4 | MED | 1 session | MED | Build retrieval quality benchmark suite |
| 7 | C4 | MED | Quick win | HIGH | Add primer freshness check to health check |
| 8 | A2 | MED | 1 session | MED | Add PDF ingestion support |
| 9 | A3 | MED | Quick win | HIGH | Add `dex ingest-councils` for uningested council runs |
| 10 | G1 | MED | Medium | MED | Auto-classification of incoming files |
| 11 | B2 | MED | Medium | MED | Primer-aware retrieval re-ranking |
| 12 | G3 | MED | Medium | MED | Primer/corpus drift detection |
| 13 | C2 | LOW | Quick win | MED | Daily git auto-push (5:00 AM) |
| 14 | C3 | LOW | Quick win | MED | Log rotation (90-day archive) |
| 15 | A4 | LOW | Quick win | MED | Bridge transcript cleanup |
| 16 | B3 | LOW | Medium | LOW | Re-chunk truncated-embedding files |
| 17 | G2 | LOW | Medium | LOW | Daily corpus digest |
| 18 | G4 | LOW | Quick win | MED | Anomaly detection in health check |

**Top 5 quick wins (operator could ship tonight):**
1. Verify health check is scheduled (C1)
2. Quarantine binary-content chunks (B1)
3. Add `dex dashboard` command (F1)
4. Add primer freshness to health check (C4)
5. Add `dex ingest-councils` (A3)

**Top 3 high-impact sessions (schedule with PM thread):**
1. Fix dex-convert.py silent data loss (A1)
2. Build external content pipeline (D1)
3. Build retrieval quality benchmarks (B4)

---

## APPENDIX: FILES NOT AUDITED

The following untracked files exist in the repo root but were not part
of this audit (they're not tracked in git):

```
_check_profiles.py, _ddl_ingest_inspect.py, _step28_diagnostic.py,
_step39_inventory.py, _step41_write.py, _step42_extract.py,
_step43_dexkit.py, _step44_threads.py, audit_archive.py,
audit_missing_only.py, check_file.py, fetch_ext_creators.py,
fetch_simon_willison.py, morning_check.py, dex-run-canon.ps1,
show-rag-folder.ps1, various .txt/.md/.jsonl files
```

These should be reviewed in a future cleanup pass: commit, archive,
or gitignore.
