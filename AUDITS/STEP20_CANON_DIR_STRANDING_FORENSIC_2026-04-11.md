# Step 20: CANON_DIR Stranding Forensic

**Date:** 2026-04-11
**Auditor:** CC (executor) on behalf of Marcus Caldwell 1002 (advisor)
**Scope:** CANON_DIR inventory, sweep-log cross-reference, dex_canon cross-reference, March 16 stranding event forensic, `_processed/` folder inspection
**Method:** Read-only filesystem walk, full dex_canon metadata pull (batched 20K), local set intersection. No file moves. No ChromaDB writes. No modifications.

---

## Headline

| Metric | Value |
|---|---:|
| **CANON_DIR total files** | **5,803** |
| With rename-suffix (collision evidence) | 233 (4.0%) |
| **STRANDED** (in CANON_DIR, NOT in dex_canon) | **1,869** (32.2%) |
| INGESTED (in dex_canon by filename match) | 3,934 (67.8%) |
| Zero-byte stranded (empty files) | 80 |
| Stranded <50 bytes | 11 |
| Stranded non-ingestible extension | 11 |
| **Recovery pool (ingestible + ≥50 bytes)** | **1,767** |
| March 16 event: stranded of 169 | **143** |
| March 16 event: already ingested | 26 |
| March 16 event: missing from disk | 0 |
| Stranding events in log (failed-ingest batches) | 8 |
| Total filenames from log stranding events | 292 |
| Total filenames from log successful events | 5 |
| **Every automated sweep ingest FAILED** | 10 of 10 |
| **Largest stranding by mtime date** | 2026-03-23: **1,438 files** |

**Verdict:** CANON_DIR contains nearly 6,000 files spanning 11 months (May 2025 – April 2026). One-third are stranded — present on disk but never made it into the ChromaDB corpus. The largest single stranding event (1,438 files, mtime 2026-03-23) appears to be from a bulk archive scan or manual `dex-run-canon.ps1` run where `--build-canon`'s tier filter silently skipped most files. **1,767 files are fully recoverable** via the airtight pipeline's `--collection dex_canon` path.

---

## Part 1: CANON_DIR Inventory

**Path:** `C:\Users\dexjr\99_DexUniverseArchive\00_Archive\DDL-Standards-Canon`
**Total:** 5,803 files

### Structure

Mostly flat root (5,643 files) with 3 subfolders:

| Location | Files |
|---|---:|
| `(root)` | 5,643 |
| `video_transcripts/` | 156 |
| `councilnom/` | 1 |
| `_processed/` | 3 |

### mtime distribution (files by creation/modification date)

| Date | Files | Notes |
|---|---:|---|
| 2025-05-26 | 53 | Original MindFrame corpus |
| 2025-11-15 – 11-17 | 127 | MindFrame v4 templates (many 0-byte) |
| 2026-01-31 | 49 | Pre-DDL content |
| 2026-03-01 – 03-05 | 153 | Early DDL content builds |
| **2026-03-06** | **1,902** | **Initial bulk load** |
| 2026-03-07 | 241 | Follow-up ingests |
| **2026-03-08** | **1,356** | **Second bulk load** |
| 2026-03-13 – 03-21 | 225 | Ongoing sweep additions |
| **2026-03-23** | **1,438** | **Massive single-day event (see Part 4)** |
| 2026-04-05 – 04-06 | 2 | Last pre-Step-17 additions |

The March 6, 8, and 23 spikes account for 4,696 files (81% of CANON_DIR).

### Extension breakdown

| Extension | Count |
|---|---:|
| `.txt` | 5,626 (97%) |
| `.html` | 84 |
| `.jsx` | 37 |
| `.py` | 16 |
| `.js` | 13 |
| `.tsx` | 7 |
| `.pdf` | 6 |
| `.css` | 3 |
| `.md` | 2 |
| `.docx` | 2 |
| other | 7 |

### Collision-renamed files

233 files (4%) have `_YYYYMMDD_HHMMSS` suffixes from `copy_to_corpus()`'s collision handler. These are files that were swept into CANON_DIR when a file with the same name already existed — the sweep renamed the incoming copy. The rename timestamps correlate with sweep dates (March 15, 16, 22, April 6).

---

## Part 2: Log Cross-Reference

Parsed all 48 `dex-sweep-log.jsonl` entries (47 non-dry-run).

### Stranded batches (copied + ingest FAILED)

| Date | Files copied | Ingestion | Sample filenames |
|---|---:|---|---|
| 2026-03-07 07:10 | 3 | ❌ | DDLCouncilReview_GradeTheQuery, LocalAI, WebsiteDeployment |
| 2026-03-07 07:18 | 19 | ❌ | Profile docs (01_Keith_O_Profile_v2.0 etc.), conversation exports |
| 2026-03-14 11:23 | 2 | ❌ | CR-CORPUS-NOMINATIONS-001, STD-VAULT-002 |
| 2026-03-15 04:10 | 3 | ❌ | DDL-KnowledgeVault HTML, EugeneWei_StaaS_clean |
| **2026-03-16 04:10** | **169** | **❌** | **78_AuditForgePM, ADR-CORPUS-001, AuditForge pitchflyers, canonpress JSX, council reviews, DDL landing pages, etc.** |
| 2026-03-19 04:10 | 2 | ❌ | 0012_CanonPressConclusion, 0016_WorkMgmt |
| 2026-03-22 04:10 | 93 | ❌ | 72_BlindspotPM, ledger HTML, GroundTune texts, DDL council reviews, Python fixers, etc. |
| 2026-04-06 04:10 | 1 | ❌ | audit.txt |

**Total distinct filenames from stranded batches: 292**

### Successful batches (copied + ingest OK)

| Date | Files copied | Ingestion | Filenames |
|---|---:|---|---|
| 2026-03-07 07:03 | 3 | ✅ | DDLCouncilReview_GradeTheQuery, LocalAI, WebsiteDeployment |
| 2026-03-14 11:12 | 2 | ✅ | CR-CORPUS-NOMINATIONS-001, STD-VAULT-002 |

**Total distinct filenames from successful batches: 5**

**All 5 successful filenames also appeared in stranded batches** — meaning they were copied twice: once via a failed run, once via a successful manual retry. The log-documented stranding accounts for only 292 of the 1,869 total stranded files. The remaining ~1,577 were stranded by non-sweep mechanisms (manual copies, `dex-run-canon.ps1`, direct archive scans).

---

## Part 3: CANON_DIR vs dex_canon Cross-Reference

Full dex_canon metadata pulled in 13 batches of 20,000 (242,009 chunks). 5,147 distinct filenames in dex_canon metadata.

| Classification | Files | % of CANON_DIR |
|---|---:|---:|
| **INGESTED** (filename match in dex_canon) | **3,934** | **67.8%** |
| **STRANDED** (not in dex_canon) | **1,869** | **32.2%** |

### Stranded file recovery assessment

| Subset | Count | Recoverable? |
|---|---:|---|
| Zero-byte (empty files) | 80 | ❌ No content to ingest |
| <50 bytes (stubs) | 11 | ❌ Below `dex-ingest.py` minimum threshold |
| Non-ingestible extension (PDF, DOCX, XLSX, etc.) | 11 | ⏳ Blocked on `dex-convert.py` fix |
| **Fully recoverable** (ingestible ext + ≥50 bytes) | **1,767** | **✅ Ready for `--collection dex_canon`** |

### Stranded files by mtime date (concentration analysis)

| Date | Stranded | Interpretation |
|---|---:|---|
| **2026-03-23** | **1,438** (77%) | Bulk event — `dex-run-canon.ps1` or manual ingest with `--build-canon` tier filter. Tier skipped most files. |
| 2025-11-15 – 11-17 | 102 (5%) | MindFrame v4 templates, many 0-byte. Not worth recovering. |
| 2026-03-06 – 03-21 | 230 (12%) | Mixed sweep-stranding + tier-filter residue from early March bulk loads. |
| All other dates | 99 (5%) | Various historical files that were never ingested. |

---

## Part 4: March 16 Forensic

The March 16 sweep found 169 files, copied all 169 to CANON_DIR, then ran `dex-ingest.py --build-canon --fast`. Ingestion reported FAILED.

| Fate | Count | % |
|---|---:|---:|
| Currently in CANON_DIR (file present on disk) | **169** | 100% |
| Chunks exist in dex_canon (by filename match) | **26** | 15.4% |
| **STRANDED** (in CANON_DIR but NOT in dex_canon) | **143** | **84.6%** |
| Missing from CANON_DIR (file lost) | 0 | 0% |

**Zero data loss from disk.** All 169 files are physically present in CANON_DIR. The "stranding" means they're in the source directory but were never chunked, embedded, and written to ChromaDB.

The 26 files that ARE in dex_canon likely got there via the earlier ingest pipeline (the March 5-8 bulk load), not from the March 16 sweep's failed ingestion. They have `DDLCouncilReview_` prefixes and `.html` pages that match CANON_PATH_MARKERS — exactly the subset that `--build-canon`'s tier filter would pass.

The 143 stranded files include:
- Custom GPT/PM exports (`62_WebsiteSME.txt`, `70_WebsiteAdvisor.txt`, `75_AuditForge.txt`, `76_WebsitePM.txt`)
- Session recaps (`AUDITFORGE — SESSION RECAP.txt`)
- Governance docs that DON'T match the tier markers (`CR-AUDITFORGE-004_Decision.txt` — "CR-" matches, but this file also appeared in the log as having been copied before; likely the copy was successful but the INGEST failed)
- Web components (JSX, HTML landing pages, branding pages)
- Python fix scripts, config files

These are all DDL-authored content that SHOULD be in dex_canon per the operator's governance intent, but were silently excluded by the `--build-canon` tier filter.

---

## Part 5: `_processed/` Folder Inspection

| Drop folder `_processed/` path | Exists | Files | mtime range | Overlap with CANON_DIR stranded |
|---|:---:|---:|---|---:|
| `C:\Users\dkitc\OneDrive\DexJr\_processed` | ❌ | — | — | — |
| `C:\Users\dkitc\OneDrive\DDL_Ingest\_processed` | ❌ | — | — | — |
| Holding folder `..._step16_batch...\_processed` | ✅ | 510 | 2023-12-05 → 2026-04-05 | **235** |
| `C:\Users\dkitc\Downloads\DDL_Ingest\_processed` | ❌ | — | — | — |
| `C:\Users\dkitc\iCloudDrive\...\04_DDL_Ingest\_processed` | ✅ | 1 | 2026-03-07 | 0 |

The holding folder's `_processed/` (which IS the Phase 1 DDL_Ingest `_processed/` relocated) has **235 files that overlap with CANON_DIR stranded files by filename**. This is the full stranding loop at work:
1. File originally in a drop folder (DDL_Ingest, iCloud, etc.)
2. Sweep ran, `copy_to_corpus()` copied the file to CANON_DIR
3. Sweep moved original to `_processed/` (so it wouldn't be re-discovered)
4. `dex-ingest.py --build-canon --fast` FAILED (tier filter or Ollama issue)
5. File now stranded in BOTH locations: a copy in CANON_DIR (never ingested) and the original in `_processed/` (hidden from re-discovery)

**235 files are confirmed to have this dual-stranding pattern.** The remaining ~1,634 stranded files in CANON_DIR were placed there by non-sweep mechanisms (manual copies, archive scans) and may not have a `_processed/` counterpart.

---

## Findings

1. **CANON_DIR is a 5,803-file corpus staging area** spanning 11 months (May 2025 – April 2026). 97% are `.txt` files. The directory is mostly flat with a `video_transcripts/` subfolder.

2. **1,869 files (32.2%) are stranded** — present in CANON_DIR but never made it into dex_canon. The recovery pool is **1,767 files** after excluding 80 zero-byte, 11 too-small, and 11 non-ingestible-extension files.

3. **The `--build-canon` tier filter is the primary stranding cause.** The March 23 event (1,438 files) and the March 16 sweep (143 of 169 stranded) both show the same pattern: files copied to CANON_DIR, `--build-canon` tier filter excluded most of them silently, ingestion "failed" (or appeared to fail because zero chunks were written for non-tier files).

4. **Every automated sweep ingest failed** (10 of 10 file-finding runs in the log). Only 2 manual daytime runs succeeded. The sweep's `--build-canon --fast` subprocess has a 0% automated success rate.

5. **235 files are confirmed dual-stranded** — copy in CANON_DIR (never ingested) + original in `_processed/` (hidden from sweep re-discovery). These are the forensically confirmed victims of the copy-before-ingest-success bug.

6. **No files are lost.** Every file from every sweep run is still on disk — either in CANON_DIR, in `_processed/`, or both. Zero data loss. The problem is un-ingested content, not missing content.

7. **The 233 collision-renamed files** (`_YYYYMMDD_HHMMSS` suffixes) are from sweep runs that copied files already present in CANON_DIR. These duplicates may cause double-ingestion if recovered naively — each version would produce separate chunks with slightly different filenames.

---

## Recommendations for Step 21+ (do NOT execute — proposal only)

### Option A: Bulk recovery of the 1,767-file pool (RECOMMENDED)

Run `dex-ingest.py --path CANON_DIR --collection dex_canon` (Option C pattern from Step 17) against the full CANON_DIR. The scoped `--collection dex_canon` path bypasses the tier filter. Files already in dex_canon would be deduplicated by the existing chunk-ID logic (hash-based IDs match on identical content). New-to-corpus files would be ingested with full STD metadata.

**Considerations:**
- ~1,767 files × ~10-50 chunks each = **~18,000-90,000 new chunks**
- Trigger 5 would fire (BULK_CHUNK_ESTIMATE=10000 > 100) → backup before write
- Wall time: ~30-120 minutes depending on Ollama embedding throughput
- The 80 zero-byte and 11 too-small files would be skipped by dex-ingest.py's `len(text.strip()) < 50` check (line 377) — not silently, but via the normal skip path
- The 233 collision-renamed files would be ingested as distinct files (different filenames → different chunk IDs). This creates content duplication in dex_canon. A post-ingest dedup pass could clean these up later.

### Option B: Selective recovery (only sweep-stranded files)

Only re-ingest the 292 filenames identified in the log's stranded batches. Creates a temp dir with those 292 files, runs the airtight pipeline. Smaller scope, cleaner provenance.

**Consideration:** misses the 1,475+ files stranded by non-sweep mechanisms (the March 23 bulk event, the November 2025 MindFrame content, etc.).

### Option C: Triage pass before recovery

Walk the 1,767-file recovery pool, classify each by content type (council review, governance, prompt, web page, code, etc.), and present a tier-by-tier recovery plan. More work upfront but produces a cleaner corpus with better `source_type` classification.

---

**End of STEP20 forensic report.**
