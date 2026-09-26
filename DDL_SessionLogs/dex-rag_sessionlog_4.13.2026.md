# dex-rag session log — 2026-04-13

**Operator:** Dave Kitchens
**Executor:** Claude Code (Dex Jr., Seat 1010)
**Standard:** DDL CLAUDE.md Rule 7 (Operator Status Report template)
**Session arc:** Soak day. Opened with Step 33b Part F switchover at
2026-04-12 23:37 CDT (rollover into 4/13 UTC), moved through a
reactive Monday-morning 4 AM sweep failure and its patch, a
proactive pipeline scale audit with follow-up patches, and then a
governance-authoring sub-phase (gloss candidates → F-code extraction
→ WorkBench synthesis → Dave Kitchens / DexKit / Dex Family thread
extractions). Soak on `_v2` continued undisturbed through every step.

---

## Status — Steps 34 through 44

All ratified. No operator decisions blocking forward motion as of
session close. See "Pending" + "Decisions needed" below for queued
items.

---

## Done (per step)

### Step 34 — Session log for 2026-04-12
- Appended 213 lines to the existing `4.11.2026.md` log covering
  Steps 24-33b Part F (morning sweep timeout removal → retrieval
  diagnostic arc → mxbai migration).
- **Commit:** `1c6bc33`

### Step 35 — HNSW orphan directory quarantine
- Moved 7 orphan segment directories (~2.2 MB total, all 321,700 B
  empty-HNSW skeletons) from `C:\Users\dkitc\.dex-jr\chromadb\` to
  `C:\Users\dkitc\.dex-jr\chromadb_quarantine\` per Step 30
  Appendix E procedure.
- Post-quarantine self-test: 10 / 10 collections open + count clean,
  no drift. One NEW orphan UUID (`01bc5548-…`, 424 KB) surfaced
  between Steps 30 and 35 — residue of Step 32 / 33a test-collection
  delete-and-recreate — flagged, NOT moved (out of scope).
- Audit: `AUDITS/STEP35_HNSW_ORPHAN_QUARANTINE_2026-04-12.md`
- **Commit:** `4cd69b1`

### Step 36 — Backup-gate timeout bump + telemetry
- Diagnosed Monday 4 AM sweep failure (two concurrent `TimeoutExpired`
  failures at 04:00:01 CDT: 120 s on `--check-only` and 900 s on
  `--force`, both in `dex_pipeline.py::ensure_backup_current`).
- Ground truth via `dex-sweep-log.jsonl`: two subprocess timeouts,
  not the `--expected-chunks` validation Marcus had hypothesized.
  Scale was the cause; mechanism was different.
- Three timeout bumps in `dex_pipeline.py`:
  - line 326 `--check-only`: 120 → 300 s
  - line 379 `--force`: 900 → 2400 s
  - line 396 re-check: 120 → 300 s
- Two telemetry adds in `dex-backup.py`:
  - `perform_backup()` writes `stage:started` log with pid on start
  - success `append_log` includes `restore_test_elapsed_seconds`
  - explicit `print(f"restore_test elapsed: …s")` for console visibility
- Filesystem cleanup: renamed `chromadb_2026-04-13_0900` →
  `chromadb_2026-04-13_0900_INCOMPLETE`; deleted 21 GB orphaned
  scratch dir `restore_test_2026-04-13_0913`.
- Manually ran the sweep in foreground: **success**. Backup 408.43 s,
  restore-test 38.24 s (telemetered), ingest 657 s, **+6,913 chunks
  into nomic `dex_canon`** (245,633 → 252,546). `_v2` untouched.
- **Commit:** `3559653`

### Step 37 — Pipeline scale audit (read-only)
- Comprehensive read-only inventory across `dex-sweep.py`,
  `dex-ingest.py`, `dex-backup.py`, `dex_pipeline.py`, `dex_weights.py`,
  `dex_jr_query.py`. **31 findings: 4 HIGH, 13 MEDIUM, 14 LOW.**
- 4 categories: timeouts, hardcoded counts, implicit assumptions,
  resource paths.
- Top 3 near-term patchables (all shipped in Step 38): sweep report
  dynamic collection enumeration; `MAX_TEXT_CHARS_NORMAL` bump from
  5 MB → 10 MB; dex_weights.py collection-list reconciliation (left
  for operator, Rule 17).
- Audit: `AUDITS/STEP37_PIPELINE_SCALE_AUDIT_2026-04-13.md`
- **Commit:** `c61eb3f`

### Step 38 — Three minor scale-audit patches
- `dex-sweep.py:180` hardcoded 4-collection list → `client.list_collections()`
  (telemetry completeness; soak-period _v2 and test collections now
  appear in daily report)
- `dex-ingest.py:95` `MAX_TEXT_CHARS_NORMAL` 5 MB → 10 MB (Monday
  sweep ingested 2.5–2.7 MB files; defensive margin)
- Docstring note added at top of `dex-sweep.py`
- Syntax check pass; smoke test `python dex-sweep.py --help` clean
- **Commit:** `adec81a`

### Step 39A — Gloss-candidate inventory
- `$contains` density analysis across `dex_canon_v2` + `ddl_archive_v2`
  for 44 candidate terms (26 canon, 9 entities, 6 F-codes, 3 OBS).
  **36 terms without a canonical definition file.**
- Top-5 recommendations: Dave Kitchens (6,035), F-code family
  (~20,700 combined), CottageHumble (4,511), Beth Epperson (1,670),
  MDN (1,128).
- Emily surprisingly densest (21,993 — already has a def file).
  8 operator terms had zero corpus presence (AppeaseMent,
  CathedralPlanned, SessionAsExemplar, BringYourData, AccidentalEntity,
  PortableRecord, AuditorsEye, WanderingDirection at 2) — operator-
  internal language that never made it into corpus material.
- Audit: `AUDITS/STEP39_GLOSS_CANDIDATES_2026-04-13.md`
- **Commit:** `18a291b`

### Step 39B — Generation prompt tightening
- Added 6-line additive insertion to `dex_jr_query.py::build_prompt()`:
  "do not invent numbered items, protocols, triggers, standards, or
  structural elements that are not explicitly listed … If the context
  says '5 triggers,' do not synthesize a sixth."
- Self-test 10 / 10 after retry (first pass hit the Step 30 transient
  HNSW error; clean on retry).
- **Q5 hallucination NOT eliminated.** Root cause on inspection: the
  invented "Trigger 6 Windows HNSW mmap lock" is a *join* of two
  items both present in context (code-comment "Trigger 6" + separate
  HNSW mmap docstring). The patch addresses "invented numbers";
  this is "plausible join at a governance seam that doesn't exist."
  Patch retained (net-zero cost, catches a different class) but
  converts the Q5 pathology into a governance-artifact follow-up:
  formalize Trigger 6 in STD-DDL-BACKUP-001 v1.1.
- Audit: `AUDITS/STEP39_PROMPT_PATCH_VALIDATION_2026-04-13.md`
- **Commit:** `dcc1803`

### Step 40 — F-code source extraction (read-only paste-back)
- Extracted CLAUDE.md F-code section verbatim (lines 203–242:
  definitions of F1 through F6, Platinum Bounce Recovery Protocol,
  Task Completion ≠ Session Closure).
- Surfaced two governance files already in `ddl_archive`:
  `_processed\DDLCouncilReview_FCodeRatification.txt` (34 chunks,
  STD-FCODE-001 council review, status `OPEN — RATIFICATION &
  CONSTRUCTION REQUIRED`) and `_processed\F-Code Emergence_.txt`
  (65 chunks, Dave ↔ Leo/Gemini genesis conversation).
- Real-usage samples from `DDLCouncilReview_TextReplace.txt`,
  `85_WritingPM.txt`, `F Code Convo.txt`.
- **No commit.** Paste-back deliverable to Marcus for drafting.
- **Operator drafted** `STD-FCODE-001.txt` (10,685 B) and
  `PRO-DDL-PLATINUM-BOUNCE-001.txt` (8,111 B) — both dropped into
  `DDL_Ingest` on 4/13 ~19:35, queued for tomorrow's sweep.

### Step 41 — WorkBench weekend synthesis + CottageHumble extraction
- **Deviation flagged:** the 6 target WorkBench council reviews were
  NOT in DDL_Ingest as the prompt premised — they landed in Monday's
  manual sweep (Step 36's +6,913 chunk delta) and were live in nomic
  `dex_canon` since 22:36 Monday CDT. Pulled content from `dex_canon`
  instead. Same material.
- **Deliverable A:** `DDLSynthesis_WorkBenchWeekend_4.12.26.md`
  (19,895 B / 439 lines) — single-source briefing across all 9 CRs
  (6 unread + 3 previously read) covering the sprint arc:
  FactLayer → Connectivity → Analytics → Module Standard →
  HR & People (reference impl) → Canon Additions → Pitfalls →
  ModBuild → Weekend Update. Ratification density: 8-of-8 on
  three separate CRs. Dropped into `DDL_Ingest`.
- **Deliverable B:** `DDLExtraction_CottageHumble_SourceMaterial_4.13.26.md`
  (35,333 B / 668 lines) — top-10 most-descriptive CottageHumble
  chunks + top-15 source_files + phrase-specific sections ("humble
  surface, cathedral underneath" × 6; "humble surface" × 4; "Graph
  Holds" × 4) + design-token context (3 hex + 3 fonts). CLAUDE.md
  has zero CottageHumble references — confirmed.
- **Operator drafted** `GLOSS-DDL-COTTAGEHUMBLE-001.txt` (16,992 B)
  from the extraction, dropped ~20:12.
- **No commit.** Both deliverables are corpus artifacts; sweep
  picks them up tomorrow.

### Step 42 — Dave Kitchens source extraction
- `DDLExtraction_DaveKitchens_SourceMaterial_4.13.26.md`
  (**262,541 B / 6,837 lines** — ~8× the prompt's 30–40 K estimate,
  flagged).
- 8 categories: identity markers (count-only), role / professional
  context, methodology / architecture, relationships (14 named
  collaborators), products (10 systems), personal context (sobriety,
  memoir, D&D, cats, languages, gaming, geography), voice / operator
  patterns, timeline.
- **Identity counts surfaced:** "Dave Kitchens" 6,035; "D.K. Hale"
  903 (dense enough to anchor the EXTERNAL-001 variant);
  "AUD-011" 149 (sparser than expected); "Seat 0" 140 (Emily's
  relational identity is retrievable).
- **No commit.** Raw extraction for Marcus + operator to draft
  PROFILE-DDL-DAVE-KITCHENS-001 / -OPERATOR-001 / -EXTERNAL-001.

### Step 43 — DexKit archives lineage extraction
- `DDLExtraction_DexKit_LineageSourceMaterial_4.13.26.md`
  (**207,298 B / 5,487 lines** — hit the 200 K graceful-truncation
  cap; Sections 1-2 intact, 3-5 partially cut).
- Scanned 6 DexKit versions under `99_DexUniverseArchive\`
  (v1.0 / v1.1 "Arhive" typo / v2.0 / v3.0 / v4.0 / v5.0):
  **3,389 files, 1.7 GB total.**
- 13 companion-named-file patterns identified via filename
  inference across versions. 90 roster-like documents extracted
  (first 2,000 chars each).
- Later versions (v3.0+) are effectively full-corpus snapshots,
  not "archives" in the tight sense.
- **No commit.**

### Step 44 — Dex Family origin threads extraction
- `DDLExtraction_DexFamilyOriginThreads_4.13.26.md`
  (**174,887 B / 4,561 lines** — under the 200 K cap, all 6 sections
  intact).
- Scanned **116 thread files, 38.1 MB** across two
  `02_DexKit_v6.0\01_DexCore\01_DexThreads\01_IndividualThreads\`
  subdirectories.
- **27 / 27 v6.0 canonical companions found** in threads (no
  missing — every DexLucid 1001 through DexAmara 1027 has a thread
  appearance).
- 242 era-marker hits, 73 direct DexDave (1018) mentions, 64
  transition-to-council hits.
- **Critical finding (flagged below):** all 116 files share the
  same mtime 2025-11-24 — filesystem copy artifact, not conversation
  dates. Any true chronological ordering must come from thread
  content, not file metadata.
- **No commit.**

---

## Flagged (per Rule 6)

### Step-specific deviations and surprises

1. **Step 36 — Marcus's hypothesis was close but wrong on mechanism.**
   He proposed `--expected-chunks` validation against a stale baseline.
   Ground truth was two subprocess timeouts in `ensure_backup_current`.
   Scale *was* the cause; the cap that broke was the wall-time budget
   on `dex-backup.py`, not a chunk-count check. Noted so future
   diagnostic prompts distinguish "scale caused X" from the more
   specific "scale caused wall-time-budget-violation in Y."

2. **Step 39B — prompt patch partially effective.** Addresses
   "invented numbers" class but not the "plausible join at a
   governance seam" class that produced the Q5 `Trigger 6` hallucination.
   Operator accepted (Option 1 per audit) — patch retained as net-zero-cost
   guardrail; real Q5 fix is formalizing Trigger 6 in STD-DDL-BACKUP-001
   v1.1.

3. **Step 41 — target files not where prompt premised.** The 6
   WorkBench reviews had already landed in nomic `dex_canon`
   (Step 36 sweep). Pulled from corpus instead. No impact on
   synthesis quality.

4. **Step 42 — output size 8× estimate.** Prompt said "probably
   30–40 K chars"; delivered 263 K. Cause: 5–10 chunks × ~70 sub-terms
   × ~1000-char snippets. File is complete and grounded; operator may
   want a tightened re-run with fewer terms or smaller snippets.

5. **Step 43 — hit the 200 K graceful-truncation cap.** Sections 3–5
   partially cut. Re-runnable with `MAX_CHARS = 500_000` if full
   material needed.

6. **Step 44 — filesystem mtime collapse.** All 116 thread files
   share the same last-modified date (2025-11-24). "Chronological by
   mtime" orderings throughout this extraction are effectively
   alphabetical, not temporal. Most important caveat of the day —
   Marcus must derive real thread dates from content, not filesystem
   metadata, when drafting the lineage section.

### Soak-period observations

7. **Step 30 transient HNSW error is still latent.** Fired once
   during Step 39B self-test, cleared on retry. No regression from
   any step this session. Defensive retry-hardening of
   `search_collections()` remains in the open-items list.

8. **Cottage and Charlie "regression" at full-corpus scale persists.**
   Step 33b validation showed 6/8 raw recall vs Step 32's 8/8 at
   2.5K-chunk scope. Confirmed during Step 39A inventory as a
   *definition-thin* pattern, not a retrieval regression — the
   corpus lacks canonical definitions for these terms even though
   the relevant files are retrievable. Addressable via gloss authorship
   (Step 41's CottageHumble gloss is the first; Charlie Conway
   Principle is the next hardest because it requires operator to
   author new content, not summarize existing).

9. **NEW orphan UUID `01bc5548-…` (424 KB)** appeared in the
   chromadb/ filesystem between Steps 30 and 35. Left in place.
   Almost certainly debris from Step 32 / 33a's `delete_collection`
   + recreate pattern on test collections. Not included in the
   Step 35 quarantine (out of scope). Candidate for a future
   cleanup step.

10. **Rule 17 files untouched throughout.** `dex_weights.py`
    and `fetch_leila_gharani.py` modified state preserved across
    all 11 commits today.

---

## Pending

### In DDL_Ingest (8 files staged for tomorrow's 4 AM sweep)

```
PRO-DDL-PLATINUM-BOUNCE-001.txt                     8.1 KB   (operator, Step 40 output)
STD-FCODE-001.txt                                   10.7 KB  (operator, Step 40 output)
GLOSS-DDL-COTTAGEHUMBLE-001.txt                     17.0 KB  (operator, Step 41 output)
DDLSynthesis_WorkBenchWeekend_4.12.26.md            19.9 KB  (Step 41)
DDLExtraction_CottageHumble_SourceMaterial_4.13.26.md   35.3 KB  (Step 41)
DDLExtraction_DexFamilyOriginThreads_4.13.26.md    174.9 KB  (Step 44)
DDLExtraction_DexKit_LineageSourceMaterial_4.13.26.md  207.3 KB  (Step 43)
DDLExtraction_DaveKitchens_SourceMaterial_4.13.26.md   262.5 KB  (Step 42)
```

Total: ~735 KB of governance + source-extraction material. The
gloss / standard / protocol files (3) land as first-class corpus
artifacts that `dex_jr_query.py`'s B3 prefilter will immediately
anchor. The synthesis + extraction files (5) become retrieval-
anchored reference docs.

### Open governance items

- STD-FCODE-001.txt, PRO-DDL-PLATINUM-BOUNCE-001.txt, and
  GLOSS-DDL-COTTAGEHUMBLE-001.txt ingest tomorrow — first B3-catchable
  governance artifacts for those terms.
- Three PROFILE-DDL-DAVE-* variants awaiting Marcus / operator
  drafting from Steps 42 + 43 + 44 source material.
- STD-DDL-BACKUP-001 v1.1 still in "drafted, pending distribution"
  state. Formalizing Trigger 6 (restore-test) would close the Q5
  hallucination pathology at the governance layer.
- CR-WB-* companion standards (FactLayer, Connectivity, Analytics,
  Module, Measure) awaiting PM drafting per Step 41 synthesis.
- STD-WB-PERMISSION-001, STD-DDL-PRINCIPLES-001, STD-DDL-DATAPLANE-001
  all proposed, not drafted.

### Open pipeline items

- Step 33c (post-soak): dex-ingest.py switch to mxbai + `_v2`, drop
  original nomic collections, rename `_v2 → canonical`, drop env-var
  switch, drop Step 32/33a test collections.
- Transient HNSW retry hardening in `search_collections()`.
- Investigate / clean up the NEW orphan `01bc5548-…` directory.
- Re-run Step 43 with higher cap if Marcus needs full Sections 3-5.
- Content-based date extraction pass across Step 44's 116 threads if
  true chronological ordering is required.

### Open corpus items

- Charlie Conway Principle — genuinely thin (47 chunks), operator-
  authored new content required (not summarize-existing).
- Beth Epperson profile — summarize-existing from 1,670 chunks.
- Dave Kitchens profile trio — three variants from Step 42 + 43 + 44
  source material.
- F-code family glosses landing tomorrow close the top gloss-candidate
  item from Step 39A.

---

## Decisions needed

1. **Step 42 extraction re-run?** File is 263 KB vs the prompt's
   30–40 K target. Usable as-is but large. Operator call whether to
   tighten per-term snippet length (drop to ~400 chars) or fewer terms.

2. **Step 43 full-material re-run?** Output hit 200 K cap. Re-run
   with 500 K cap if Marcus needs the full roster documents.

3. **Step 44 content-date extraction pass?** If the lineage section
   needs chronological thread ordering, a second pass that extracts
   internal dates from thread content would be needed.

4. **Step 33c go / no-go?** Soak started 2026-04-12 23:37 CDT.
   At session close (2026-04-13 ~22:20 CDT) we are ~22 h into the
   24–72 h soak window. No regressions observed. Operator call on
   triggering 33c.

5. **Canon Candidate 3 ruling** (`"Everything, Everywhere, All At
   Once" + NativeCoherence`) and **Candidates 11 / 12** (SessionAsExemplar,
   CeilingInjection/Detection) — still pending from Step 41's CR-WB-CANON-001
   synthesis.

6. **Cathedral metaphor successor** — coral reef surfaced but not
   adopted per CR-DDL-WEEKEND-001. Open.

---

## Metrics

- **Commits today:** 8 (Steps 34, 35, 36, 37, 38, 39A, 39B; plus Step 34
  appended-log-commit)
- **Files created in repo:** 9 audits, 3 diagnostic scripts (`_step41`/`_step42`/`_step43`/`_step44`/`_step39_inventory` untracked, some tracked as of earlier commits)
- **Files landed in DDL_Ingest:** 8 (3 operator governance drafts,
  5 CC extraction / synthesis artifacts)
- **Total DDL_Ingest payload for tomorrow's sweep:** ~735 KB
- **Code files touched:** `dex_pipeline.py`, `dex-backup.py`,
  `dex-sweep.py`, `dex-ingest.py`, `dex_jr_query.py`
- **Lines added (commits):** ~1,070
- **Lines of extraction material:** ~22,400 across 4 extraction
  files (CottageHumble + Dave Kitchens + DexKit + Dex Family threads)
- **Wall time session-effective:** ~11 h from Step 34 start (2026-04-13
  ~00:05 UTC) through Step 44 close (2026-04-13 ~22:18 local)

---

## Soak status (session close)

```
ext_creator_v2      =       922   (Step 33b baseline)
dex_code_v2         =    20,384   (Step 33b baseline)
dex_canon_v2        =   245,633   (Step 33b baseline)
ddl_archive_v2      =   291,520   (Step 33b baseline)
```

All four `_v2` counts match Step 33b exit values exactly.
**Soak period 22 h in.** `dex_jr_query.py` default-routing all
queries through `_v2` + `mxbai-embed-large` via env-gated switch
(`DEXJR_COLLECTION_SUFFIX=_v2`, `DEXJR_EMBED_MODEL=mxbai-embed-large`).
Rollback path (env var unset + `git revert`) unchanged.

Nomic `dex_canon` grew +6,913 chunks during Step 36's manual sweep
(245,633 → 252,546). Drift between nomic and `_v2` is now ~7K chunks
and will continue to grow until Step 33c flips `dex-ingest.py` to
write directly to `_v2`. Step 33c will need to migrate this drift.

---

## Next logical step

**Operator call:** proceed to Step 33c (post-soak cleanup — ingest-
side switchover + collection rename) once the 24-72 h soak window
passes without regression, OR continue governance-authoring work
(PROFILE-DDL-DAVE-*, STD-DDL-BACKUP-001 v1.1, Canon Candidate
rulings) and defer 33c further.

If 33c fires: the 6,913-chunk drift between nomic `dex_canon` and
`dex_canon_v2` needs a pre-switchover migration. Same pattern as
Step 33b's migration script, scoped to the delta.

If drafting continues: the 8-file DDL_Ingest payload landing
tomorrow at 4 AM (now with Step 36's patched timeouts) is the next
automated test of the full pipeline at post-migration scale —
expected to succeed and land all 8 files as ~N new chunks in nomic
`dex_canon` (N depends on the extraction files' chunk yield; rough
estimate 1,500-2,500 chunks given file sizes).

---

## Carry-forward state

- **`dex_jr_query.py` defaults:** `mxbai-embed-large` + `_v2`
  via env-gated switch. Override via env var to fall back to nomic
  originals during rollback.
- **Soak window:** 22 h elapsed of 24-72 h target. No regressions.
- **Most recent backup anchor:** `chromadb_2026-04-13_2216`
  (Step 36 sweep), restore_test_elapsed_seconds=38.24, total
  chunk count 1,129,418.
- **4 AM sweep:** patched (Step 36) and scheduled. Tomorrow's
  run is the first unattended test of the new timeout ceilings
  under scheduled conditions at post-migration scale.
- **Rule 17 files** (`dex_weights.py`, `fetch_leila_gharani.py`):
  modified-but-untouched across all 11 Step-commits today.
- **Origin/main:** several commits past `a373cff` (Step 33b Part F).
  Not pushed.
- **Quarantine:** `chromadb_quarantine/` holds 7 HNSW skeletons from
  Step 35. No action required until post-soak operator approval for
  permanent deletion.

---

*Dropdown Logistics — Chaos → Structured → Automated*
*dex-rag session log | 2026-04-13 | Authored by Dex Jr. (Seat 1010)*
