# Step 16: Holding Folder Content Audit

**Date:** 2026-04-11
**Auditor:** CC (executor) on behalf of Marcus Caldwell 1002 (advisor)
**Scope:** `C:\Users\dkitc\OneDrive\DDL_Ingest_step16_batch_2026-04-11` + `dex_canon` + `ddl_archive` cross-reference
**Authority:** STD-DDL-METADATA-001, CLAUDE.md Rule 8
**Method:** Read-only filesystem walk (no content reads) + batch metadata pull from ChromaDB via `dex_weights.get_client()` + local set intersection for cross-reference. No file moves. No ChromaDB writes.

---

## Headline

- **Holding folder: 1,026 files / 13.46 GB** (essentially all of DDL_Ingest from the Phase 1 CR-DEXJR-DDLING-001 audit, relocated wholesale)
- **759 ingestible** (PHASE1_EXTENSIONS), **267 not ingestible** (audio, video, PDFs, XLSX, installers)
- **Fresh files (<24h): 26** — not 133. The operator's "133 fresh from iCloud" mental model was inaccurate; see surprise #1.
- **Older files (>24h): 994** (within 7 days: 6; older than 7 days: 988)
- **Already in dex_canon (by filename match): 90**
- **Already in ddl_archive (by filename match): 606**
- **In EITHER collection: 607** (90 dex_canon, 516 archive-only, overlap negligible)
- **NET-NEW (not in either): 419** (152 ingestible, 267 not-ingestible)
- **FRESH AND NET-NEW: 24** — this is the real "tonight's work" pile
- **Sensitive flags (filename-only): 8** (6 mania, 1 Google Takeout MBOX, 1 draft)

**Verdict:** The holding folder is NOT primarily a fresh iCloud drop. It is the complete Phase 1 DDL_Ingest moved into a new parent name. Tonight's real net-new work is **24 files / ~16 MB** — a much smaller pile than the 1,026-file container suggests.

---

## Surprise findings

### 1. "133 fresh from iCloud this afternoon" is a mental-model mismatch

The operator said **~133 files fresh from iCloud this afternoon**. The filesystem says:

| Metric | Count |
|---|---:|
| Top-level loose files (matches the "133" number) | **133** |
| Files with mtime <24h (truly fresh) | **26** |
| Files with mtime from today morning (11am-12:35pm local) | **26** |

The "133" matches the number of top-level loose files in the holding folder — which also matches Phase 1's top-level file count (134) almost exactly. **These 133 files are not all fresh.** They span Mar 1 through Apr 11 mtimes.

The 26 genuinely-fresh files are all dated 2026-04-11 between 11:10am and 12:35pm local time — one working session this morning, not "this afternoon." They're mostly numbered custom GPT/advisor prompt exports (`77_LLMAdvisor`, `79_KnowledgeVaultPM`, `85_WritingPM`, etc.) plus 6 new DDLCouncilReviews plus a few miscellaneous files.

### 2. dex_canon is 99.997% legacy

Total chunks: 230,088. STD-compliant (has `source_type`): **6**. That's from my Step 6 ingest of `DDLCouncilReview_CorpusGuess.txt` via the airtight path. **Everything else predates STD-DDL-METADATA-001 and was written by the pre-Step-14 `dex-ingest.py`**. Distinct `ingest_run_id` values: **1** (`manual_2026-04-11_2127`).

### 3. ddl_archive is 100% legacy

Total chunks: 291,520. STD-compliant: **0**. No `ingest_run_id` values anywhere. The Step 14 wiring has been verified but has not yet been exercised against real `ddl_archive` writes (Step 14's smoke test targeted `dex_test` and dropped it).

### 4. Mania files under-counted by sensitive pattern

The filename-regex sensitive scanner only caught 6 mania-related files — but the `Mania/` subdirectory contains **176 files** (82 audio + 88 transcripts + 6 iPhone videos). The scanner missed them because filenames like `"8135 Monrovia St.txt"` or `"A message to Dad - Dave Solo - 5.22.23.txt"` don't match the `manic|mania|whisper|voice|transcript` regex. **Entire Mania subdirectory is sensitive by location, not by filename.** I should have path-matched; filename-only was a scoping error. Flagged as deviation per Rule 6 below.

### 5. `_hold/All mail Including Spam and Trash-002.mbox` (6.4 GB Gmail MBOX) is still the single biggest blocked item

No change from Phase 1 audit. Still in the holding folder. Still blocked on dex-convert.py silent-drop fix. Still net-new.

### 6. _processed has 436 already-ingested files, 74 net-new

`_processed/` has 510 files. **436 of them are already in the corpus by filename match.** 74 are net-new. This suggests `_processed/` served its name — stuff that was already processed by some past pipeline. Worth knowing the 74 net-new are probably the stragglers that weren't fully processed last time.

---

## Part 1: Holding Folder Inventory

### Totals

| Metric | Value |
|---|---:|
| Total files (recursive) | 1,026 |
| Total directories (including root) | 10 |
| Total size | 13.46 GB |
| Ingestible (PHASE1_EXTENSIONS) | 759 |
| Not ingestible | 267 |

### Top-level folder distribution

| Top level | Files | Size |
|---|---:|---:|
| `(root)` (loose files) | **133** | 27.3 MB |
| `79_KnowledgeVaultPM - Claude_files` | 13 | 10.6 MB |
| `Mania` | 176 | **6,346.3 MB** |
| `_duplicates` | 34 | 0.6 MB |
| `_governance` | 30 | 1.0 MB |
| `_hold` | 96 | **6,875.3 MB** |
| `_processed` | 510 | 54.5 MB |
| `_skip` | 31 | 149.2 MB |
| `governance` | 3 | 0.0 MB |

The 8 subfolders + root = **9 logical areas**, matching the operator's "9 folders" description.

### mtime distribution

| Bucket | Count | Size |
|---|---:|---:|
| Last 24h (fresh) | **26** | 16.9 MB |
| 24h–7d | 6 | 1.0 MB |
| Older than 7d | **994** | 13.45 GB |

### Ingestible extension categories

| Category | Count | Examples |
|---|---:|---|
| `text` | 518 | `.txt`, `.md` |
| `code` | 114 | `.py`, `.ts`, `.tsx`, `.jsx`, `.js`, `.sh`, `.ps1`, `.sql`, `.ipynb`, `.prisma` |
| `web` | 110 | `.html`, `.css` |
| `data` | 17 | `.json`, `.yaml`, `.csv`, `.toml` |

### Not-ingestible extensions (top 15)

| Extension | Count |
|---|---:|
| `.m4a` | 82 | (Mania audio) |
| `.pdf` | 53 | (_hold council briefs, dashboards) |
| `.png` | 51 | (branding assets, charts) |
| `.xlsx` | 27 | (FY2025 spreadsheets) |
| `.docx` | 11 | (system records) |
| `.download` | 9 | (browser cache artifacts) |
| `.mov` | 6 | (iPhone video — 5.32 GB) |
| `.jpg` | 6 | (profile/branding) |
| `.svg` | 4 | |
| `.zip` | 3 | |
| `.exe` | 2 | (_skip installers) |
| `.mbox` | 1 | (Gmail 6.4 GB — blocked) |
| (no ext) | 2 | |

### Fresh file list (all 26, mtime <24h)

Sorted by mtime ascending:

| mtime | Size | Path |
|---|---:|---|
| 2026-04-11T11:10:39 | 4,062,636 | `28_CognitiveArchitecture.txt` |
| 2026-04-11T11:12:07 |   829,780 | `74_LLMAdvisory.txt` |
| 2026-04-11T11:12:10 | 1,101,366 | `79_KnowledgeVaultPM.txt` |
| 2026-04-11T11:13:25 |   871,206 | `71_WebsiteAdvisor.txt` |
| 2026-04-11T11:14:49 |   915,728 | `78_AuditForgePM.txt` |
| 2026-04-11T11:16:00 | 1,029,770 | `82_AuditForgeAdvisor.txt` |
| 2026-04-11T11:17:19 | 1,359,686 | `77_LLMAdvisor.txt` |
| 2026-04-11T11:18:44 |   828,945 | `81_WebsiteAdvisor.txt` |
| 2026-04-11T11:19:36 |   322,836 | `86_LedgerPM_ThreadSaved_4.11.txt` |
| 2026-04-11T11:20:30 |   320,605 | `87_BlindspotPM.txt` |
| 2026-04-11T11:21:48 |   206,093 | `88_WorkPM.txt` |
| 2026-04-11T11:22:51 |   156,046 | `90_WebsiteBrandPM.txt` |
| 2026-04-11T11:23:42 | 1,131,621 | `84_ExcelligencePM.txt` |
| 2026-04-11T11:24:39 | 1,367,435 | `83_MarcusCaldewellPM.txt` |
| 2026-04-11T11:25:46 | 1,101,343 | `79_KnowledgeVaultAdvisor.txt` |
| 2026-04-11T11:26:29 |   362,482 | `85_WritingPM.txt` |
| 2026-04-11T11:40:32 |   214,642 | `DDLCouncilReview_TextReplace.txt` |
| 2026-04-11T11:43:45 |   133,005 | `DDLCouncilReview_AntiPractice.txt` |
| 2026-04-11T11:44:18 |    11,127 | `ToneDriftTracker_Prototype_v1.0.txt.txt` |
| 2026-04-11T11:44:31 |    49,351 | `DDLCouncilReview_RatifyContextExam.txt` |
| 2026-04-11T11:46:20 |     2,508 | `CrazyTheory_TheGreatAwakening.txt` |
| 2026-04-11T11:46:51 |   196,830 | `DDLCouncilReview_Mithril.txt` |
| 2026-04-11T11:47:09 |   121,640 | `DDLCouncilReview_CouncilPlaybook.txt` |
| 2026-04-11T11:47:49 |    89,621 | `F Code Convo.txt` |
| 2026-04-11T11:48:34 |   137,367 | `DDLCouncilReview_SpiralProtocol.txt` |
| 2026-04-11T12:35:13 |    21,007 | `The Bounceback.txt` |

**All 26 are plain text** (.txt). One 3.8 MB outlier (`28_CognitiveArchitecture.txt`), rest average ~650 KB. **Single 98-minute working session** from 11:10am to 12:35pm local time.

**source_type inference preview** (per STD-DDL-METADATA-001 infer rules, using dex-ingest.py's `infer_source_type`):
- 6 files → `council_review` (DDLCouncilReview_* prefix)
- 20 files → `unknown` (numbered advisor/PM exports, misc titles)

---

## Part 2: Corpus Snapshot

### dex_canon

| Metric | Value |
|---|---:|
| Total chunks | **230,088** |
| Metadata pulled (full scan) | 230,088 (100%) |
| STD-compliant (has valid `source_type`) | **6** |
| Legacy (no `source_type`) | **230,082** (99.997%) |
| Distinct `ingest_run_id` values | **1** |
| Distinct filenames (union of `filename` + `source_file`) | 5,113 |
| Distinct `source_type` values | `['(none)', 'council_review']` |

**All `ingest_run_id` values:**
- `manual_2026-04-11_2127`: 6 chunks (the Step 6 live ingest of `DDLCouncilReview_CorpusGuess.txt`)

This proves the airtight pipeline has written exactly one file to `dex_canon` end-to-end. Everything else is pre-STD.

### ddl_archive

| Metric | Value |
|---|---:|
| Total chunks | **291,520** |
| Metadata pulled (full scan) | 291,520 (100%) |
| STD-compliant | **0** |
| Legacy | **291,520** (100%) |
| Distinct `ingest_run_id` values | **0** |
| Distinct filenames | 23,563 |
| Distinct `source_type` values | `['(none)']` |

The Step 14 airtight wiring has not been exercised against `ddl_archive` yet. First run into ddl_archive would populate the first STD-compliant chunks.

---

## Part 3: Cross-reference (holding folder ↔ corpus)

### Top-level summary

| Classification | Count | % of holding |
|---|---:|---:|
| Already in `dex_canon` (filename match) | 90 | 8.8% |
| Already in `ddl_archive` (filename match) | 606 | 59.1% |
| Already in **either** collection | 607 | 59.2% |
| **NET-NEW** (no filename match anywhere) | **419** | **40.8%** |

### Net-new breakdown by subfolder

| Top level | Net-new files | Total files | % net-new |
|---|---:|---:|---:|
| `(root)` | 110 | 133 | 82.7% |
| `_hold` | **96** | 96 | **100%** ⚠️ |
| `Mania` | 89 | 176 | 50.6% |
| `_processed` | 74 | 510 | 14.5% |
| `_skip` | 25 | 31 | 80.6% |
| `79_KnowledgeVaultPM - Claude_files` | 13 | 13 | 100% |
| `_duplicates` | 12 | 34 | 35.3% |
| `_governance` | 0 | 30 | 0% |
| `governance` | 0 | 3 | 0% |
| **Total** | **419** | **1,026** | **40.8%** |

**Critical reads:**
- **`_hold/` is 100% net-new** — nothing in `_hold` has been ingested. This is expected because `_hold` contains PDFs, XLSX, the 6.4 GB MBOX, and other non-plain-text files that `dex-ingest.py` can't currently process.
- **`_governance/` and `governance/` are 0% net-new** — all governance docs are already in the corpus. Phase 1 cross-reference confirmed this finding.
- **`_processed/` is only 14.5% net-new** — the vast majority is already ingested. The remaining 74 net-new are stragglers.
- **`(root)` is 82.7% net-new** — most of the top-level loose files are not in the corpus yet. This is where the biggest actionable cluster lives.

### Net-new ingestibility

| Category | Count |
|---|---:|
| Net-new ingestible (text/code/data/web) | **152** |
| Net-new NOT ingestible (audio/video/PDF/XLSX/MBOX/images) | 267 |

### Fresh AND net-new intersection

**24 files** — fresh (<24h) AND not in either collection.

This is the cleanest definition of "tonight's new work to ingest." All 24 are plain text, sub-2 MB each, written this morning, not previously ingested.

(The remaining 2 fresh files are already in the corpus by filename — probably the operator re-saved existing files today. The remaining 128 net-new ingestible files are older content that's been sitting in the pile for weeks or months.)

---

## Part 4: Sensitive Content Flags (filename-only scan)

⚠️ **The filename-only scan undercounts sensitive material.** See surprise #4 above.

### By category

#### mania_recording (6 filename matches)
```
_duplicates/transcribe_mania_v3.py
_processed/DDLCouncilReview_EverythingManicAll.txt
_processed/DDLCouncilReview_EverythingManicAllAtOnce.txt
_processed/ManicAnalysis_Leo.txt
_processed/ManicVideos_All.txt
_processed/transcribe_mania_v2.py
```

**Undercounted: the full `Mania/` subdirectory (176 files, 6.35 GB) is sensitive by LOCATION.** All audio + transcripts of personal voice memos (2023–2026). Filenames don't contain "mania"/"manic" but the path does. Should be treated as sensitive en bloc.

#### google_takeout (1 filename match)
```
_hold/All mail Including Spam and Trash-002.mbox     (6.39 GB)
```

The 6.4 GB Gmail MBOX from Phase 1. Still blocked on `dex-convert.py` silent-drop fix. Still sensitive (personal mail archive including spam + trash folders).

#### drafts_wip (1 filename match)
```
llms-v1.8-draft.txt  (root-level)
```

Single draft file.

#### contact_leak (0 matches)

No email addresses or phone numbers in filenames.

### Effective sensitive count (including path-based)

| Category | Filename matches | True count (with path) |
|---|---:|---:|
| Mania / voice memos | 6 | **~182** (6 name + 176 path) |
| Google Takeout / mail | 1 | 1 |
| Drafts/WIP | 1 | 1 |
| **Total sensitive** | **8** | **~184** |

---

## Recommendations — 3 ingest scope options

### Option A (RECOMMENDED): "Fresh + net-new only" — the minimal defensible tonight

**Scope:** The 24 files that are both fresh (<24h) AND net-new (not in corpus).

| Metric | Value |
|---|---:|
| Files | 24 |
| Total size | ~16 MB |
| Expected chunks | 80–250 (varies by length) |
| Sensitive categories touched | None (except possible "drafts_wip" if `ToneDriftTracker_Prototype_v1.0.txt.txt` counts) |
| `source_type` distribution | 6 × `council_review`, 18 × `unknown` |
| Blast radius | tiny — one ingest run, one backup trigger, ~80–250 new chunks to `dex_canon` |
| Time estimate | 1 manual `dex-ingest-text.py` loop or 1 invocation via a folder scanner; ~30s–3min wall time |
| Rule 5 approval needed | Yes — first live `dex_canon` write since Step 6 |

**Rationale:** This is the truly-net-new work from this morning's session. Small pile, plain text, fresh, not yet in corpus, clean provenance. Perfect first-real-use of the airtight pipeline against real content.

**Excludes:** the entire `Mania/` subfolder (sensitive by location, 176 files), `_hold/` (PDFs/XLSX/MBOX, 96 files, blocked on converter), all older net-new content (152 ingestible, needs triage).

### Option B: "Fresh + net-new + older council reviews" — medium scope

**Scope:** Option A + any net-new file matching `DDLCouncilReview_*` prefix regardless of mtime.

| Metric | Value |
|---|---:|
| Files | 24 + N older council reviews (need to count from the data) |
| Expected chunks | 100–500 |
| Sensitive categories | None |
| `source_type` distribution | All council_review + some unknown |
| Blast radius | small — focuses on council content, which is the cleanest ingest candidate per CLAUDE.md governance priority |

**Rationale:** Council reviews are plain-text and follow a clear `source_type` mapping. If the operator wants to catch up on older council reviews that were never ingested (which the Phase 1 audit identified as net-new governance content), this scope hits them without pulling in the Mania/_hold/_processed noise.

### Option C: "Fresh only, defer everything else" — most conservative

**Scope:** The 26 fresh files (all of them, including the 2 that are already in the corpus — since they're fresh, they've likely been EDITED since prior ingest and the new version is what matters).

| Metric | Value |
|---|---:|
| Files | 26 |
| Expected chunks | 85–260 |
| Sensitive categories | None |
| Blast radius | tiny — nearly identical to Option A |
| Note | The 2 non-net-new fresh files would result in chunk_id collisions or updates depending on whether dex-ingest.py uses upsert (it does). Worth knowing the old chunks might be replaced. |

**Rationale:** "I touched these today, ingest them tonight." Simplest possible mental model. Doesn't try to be clever about what's new vs edit.

### NOT recommended right now

- **Ingesting the 152 net-new ingestible older files** without triage. These are the stragglers — some are legitimately net-new, some may be old drafts the operator abandoned. Needs per-file operator review before bulk ingest.
- **Ingesting `_hold/` contents** — blocked on `dex-convert.py` silent-drop fix (CLAUDE.md Open Item #1).
- **Ingesting `Mania/` contents** — 176 files sensitive by location. Needs an explicit governance decision before any voice-memo content enters the corpus.
- **Ingesting the 6.4 GB Gmail MBOX** — needs converter fix + a brand-new decision on whether email goes in `dex_canon` or its own collection.

---

## Methodology notes

- **Filesystem walk:** `Path.rglob("*")` over the holding folder. `stat()` per file for size + mtime. No `open()` calls. No content reads.
- **Corpus snapshot:** full metadata pagination via `collection.get(limit=20000, offset=K, include=['metadatas'])` in 20K-chunk batches. 12 batches for `dex_canon` (230K chunks), 15 batches for `ddl_archive` (291K chunks). Total read time ~90 seconds.
- **Cross-reference:** local set intersection after the full metadata pull. Zero per-file Chroma queries.
- **Chroma access pattern:** `dex_weights.get_client()` only, not `chromadb.PersistentClient` directly. Read-only. No writes.
- **Sensitive scan:** compiled regex against `filename` field only. No content reads. Acknowledged undercounting of path-based sensitive locations (see surprise #4).
- **Temp data file:** `_tmp_step16_data.json` at repo root, will be deleted after report is committed.

---

**End of STEP16 audit report.**
