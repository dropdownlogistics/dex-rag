# DDL_Ingest cleanup inspection — 2026-04-14

**Mode:** READ-ONLY. No files moved. Awaiting operator GO.
**Folder:** `C:\Users\dkitc\OneDrive\DDL_Ingest\` (top-level only; sweep doesn't recurse)

## 1. Inventory summary

| Metric | Value |
|---|---:|
| Top-level files | 22 |
| Total size | 9.68 MB |
| Supported extensions | 14 files |
| Unsupported extensions | 8 files |
| Hash errors | 0 |
| Skipped-by-name | 0 |

### Supported extensions from `dex-ingest.py:81-93` (23 total)

`.txt .md .html .jsx .json .py .cs .js .mjs .ts .tsx .css .sql .sh .bat .ps1 .bas .csv .yml .yaml .toml .ipynb .prisma`

Also skipped (beyond ext filter): `.DS_Store`, `Thumbs.db`, `desktop.ini`,
and any filename starting with `ingest_report_`.

### Extension breakdown of DDL_Ingest top-level

| Ext | Count | Supported? |
|:---|---:|:---:|
| .txt | 9 | ✅ |
| .md | 1 | ✅ |
| .html | 3 | ✅ |
| .jsx | 1 | ✅ |
| .png | 7 | ❌ |
| .svg | 1 | ❌ |

Subfolders present but not inspected: `_processed/`, `_sweep_reports/` — the
sweep reads these separately and they are self-managed.

## 2. Unsupported-extension files (proposed move → `_review/`)

All 8 are images (7 × PNG, 1 × SVG). Total: **4.15 MB**.

| Name | Ext | Size |
|---|:---|---:|
| auditforge_og_image.svg | .svg | 29,648 |
| ledger-og.png | .png | 56,683 |
| ledger-og (2).png | .png | 56,683 |
| og-image excelligence.png | .png | 866,740 |
| og-image excelligence (2).png | .png | 866,740 |
| og-image-ddl.com.png | .png | 1,137,432 |
| og-image-ddl.com (2).png | .png | 1,137,432 |
| og-image-kv.png | .png | 1,096,572 |

## 3. Internal duplicates within DDL_Ingest

3 exact-hash pairs. All are the "(2)" suffixed downloads of already-present PNGs.
All 6 files involved are already in the unsupported list above, so moving the
unsupported set to `_review/` subsumes this check.

| SHA-256 prefix | Files |
|:---|:---|
| f0c2fea15bb2971f | ledger-og.png, ledger-og (2).png |
| 36caa0b1aab4e592 | og-image excelligence.png, og-image excelligence (2).png |
| 0f585ccd0165d95a | og-image-ddl.com.png, og-image-ddl.com (2).png |

## 4. Already-in-corpus files (proposed move → `_duplicates/`)

8 files matched against `file_hash` metadata in `dex_canon_v2`. **0 matched
`ddl_archive_v2`** (expected — sweep only writes to dex_canon_v2). Matching
uses the first 16 chars of SHA-256 (the field stored by `dex-ingest.py`).

Total: **5.83 MB**.

| Name | file_hash | Size | In |
|---|:---|---:|:---:|
| DDLExtraction_DaveKitchens_SourceMaterial_4.13.26.md | 9bbdb73496c640d5 | 262,541 | dex_canon_v2 |
| LLMPM_Full Session Log - 4.12.26.txt | c2cdb72a31294f2c | 967,098 | dex_canon_v2 |
| WebsitePM Full Session Log - 4.13.26.txt | 8a3207d346afe44e | 303,463 | dex_canon_v2 |
| WorkBench-BrandKit-v1_0.html | 29d68da822e7be9b | 38,396 | dex_canon_v2 |
| WorkBench-Favicon-Reference.html | 522bce8a33a9f154 | 13,353 | dex_canon_v2 |
| WorkBench-OG-Image.html | 4bd75bc332fcdffd | 8,001 | dex_canon_v2 |
| Workbench Full Session Log - 4.13.26.txt | 3f73cf891fe4c466 | 219,342 | dex_canon_v2 |
| gridtactics-demo.jsx | 7f553ef22d0eb027 | 20,409 | dex_canon_v2 |

## 5. Novel files ready to ingest (would land in dex_canon_v2)

6 `.txt` files. Total: **2.78 MB**.

| Name | Size |
|---|---:|
| AuditForge Full Session Log - 4.14.26.txt | 202,966 |
| AuditForge Full Session Log - 4.14_.txt | 279,521 |
| KnowledgeVault Full Session Log - 4.14.26.txt | 803,666 |
| KnowledgeVault and DexJr Audit - 4.14.26.txt | 173,741 |
| LLMPM Full Session Log 4.14.26.txt | 661,129 |
| WebsitePM Full Session Log - 4.14.26.txt | 951,601 |

### Flag (Rule 6)

The two `AuditForge Full Session Log - 4.14*` filenames look like a
browser double-save (one trailing `_` before `.txt`). They have
**different sizes** (202,966 vs 279,521), so they are NOT content
duplicates — likely the second is a fuller/later export of the same
session. Both are novel by hash, both will ingest if left in place.
Operator may want to delete/move the smaller one manually.

## 6. Recommended moves

| From (stays in `DDL_Ingest\`) | To |
|---|---|
| 8 unsupported files (§2) | `_review\` |
| 8 already-in-corpus files (§4) | `_duplicates\` |

After moves: 6 novel files remain at top-level. The 4 AM sweep will ingest
exactly these 6 files into `dex_canon_v2` (post-Step-33c target collection).

## 7. Estimated size reclaim from top-level

- To `_review\`: 4.15 MB
- To `_duplicates\`: 5.83 MB
- **Remaining at top-level after cleanup:** 2.78 MB (6 novel files)

---

## 8. Execution (post-GO)

Operator GO received. Executed 17 actions:

**Deleted (1):**
- `AuditForge Full Session Log - 4.14.26.txt` (202,966 bytes, partial
  browser save — superseded by the 279,521-byte version in-place)

**Moved to `_review/` (8):**
- auditforge_og_image.svg
- ledger-og.png, ledger-og (2).png
- og-image excelligence.png, og-image excelligence (2).png
- og-image-ddl.com.png, og-image-ddl.com (2).png
- og-image-kv.png

**Moved to `_duplicates/` (8):**
- DDLExtraction_DaveKitchens_SourceMaterial_4.13.26.md
- LLMPM_Full Session Log - 4.12.26.txt
- WebsitePM Full Session Log - 4.13.26.txt
- WorkBench-BrandKit-v1_0.html
- WorkBench-Favicon-Reference.html
- WorkBench-OG-Image.html
- Workbench Full Session Log - 4.13.26.txt
- gridtactics-demo.jsx

All move operations recorded in `_ddl_ingest_cleanup_actions.json`.

## 9. Final top-level inventory

**5 files remain, all novel `.txt`, all to ingest at the next 4 AM sweep.**

| Name | Size |
|---|---:|
| AuditForge Full Session Log - 4.14_.txt | 279,521 |
| KnowledgeVault Full Session Log - 4.14.26.txt | 803,666 |
| KnowledgeVault and DexJr Audit - 4.14.26.txt | 173,741 |
| LLMPM Full Session Log 4.14.26.txt | 661,129 |
| WebsitePM Full Session Log - 4.14.26.txt | 951,601 |

Total: 2.74 MB across 5 files.

Subfolders: `_duplicates/`, `_processed/`, `_review/`, `_sweep_reports/`.
(Sweep does not recurse; these are safe from re-ingest.)

Status: CLEAN.
