```markdown
# ADR-INGEST-PIPELINE-001 — DDL Content Pipeline & Self-Documenting Ingest Loop

**Status:** Proposed — awaiting operator ratification
**Date:** 2026-04-11
**Author:** Marcus Caldwell (Seat 1002, Claude in app) on behalf of operator
**Supersedes:** N/A (first ADR for content pipeline architecture)
**Related:** ADR-CORPUS-001 (collections), CR-DEXJR-AUDIT-001, CR-DEXJR-DDLING-001

---

## Context

DDL has a corpus (~542K chunks across 4 live ChromaDB collections) and an ad-hoc folder system (`DDL_Ingest`, ~12.5 GB across 8 subfolders) that has accumulated content over six months. The 2026-04-11 audit (CR-DEXJR-DDLING-001) revealed:

1. The folder is an active staging area, not a static archive — files land daily from Claude exports, custom GPT exports, council reviews, voice memos, and ad-hoc downloads.
2. There is no formal pipeline between the staging folder and the corpus. Ingest happens manually, occasionally, and without provenance tracking.
3. A significant fraction of valuable text (council reviews, today's GPT exports, Mania transcripts) is **outside** the corpus and Dex Jr. cannot retrieve it.
4. Existing chunks in the corpus lack `source_type` and `ingested_at` metadata, so the system cannot answer "what came from where" or "what got added when."
5. The operator wants nothing deleted, ever — but does want the staging folder kept clean enough to function as an active inbox.
6. The nightly 3am sweep exists (`dex-sweep.py`) but currently runs in `--fast` mode against the broken scoped+fast file-skip path, and produces no auditable record of what it did.

These conditions create three structural problems:

- **No clear destination for files after they're ingested.** They sit in DDL_Ingest forever, mixed with un-ingested files, with no way to know which is which.
- **No memory of system activity.** The ingest layer is invisible to itself. Dex Jr. cannot answer "what got ingested last week" because no record of the answer exists.
- **No source of truth for ingest state.** The audit had to query ChromaDB live to figure out what's in there. There's no canonical history.

This ADR defines the pipeline that resolves all three.

---

## Decision

Adopt a three-stage content pipeline (`DDL_Ingest` → `DDL_Staging` → `DDL_Archive`) with mandatory provenance metadata on every ingested chunk and a self-documenting nightly sweep that emits a structured ingest report after every non-empty run. The reports themselves become first-class corpus content, ingested on the following sweep.

---

## The pipeline

### Three folders, three states

```
DDL_Ingest    (the inbox)        — hot folder, files arrive here from any source
    ↓
DDL_Staging   (the waiting room) — files known to be ingested, not yet organized
    ↓
DDL_Archive   (the permanent home) — organized by category, never deleted
```

**DDL_Ingest** is the operator's working folder. It does not get cleaned automatically. The operator drops files here freely. The sweep reads from here.

**DDL_Staging** is the post-ingest waiting room. After a file is verified ingested (chunks present in target collection with matching `source_type` and `source_file` metadata), the sweep moves it from `DDL_Ingest` to `DDL_Staging`. This is the "I know it's safe in the corpus, but I haven't decided where it lives forever" zone. Files can sit here indefinitely.

**DDL_Archive** is the permanent organized destination. CC sweeps Staging on demand or on a separate schedule and routes each file into the correct bucket based on `source_type`, file extension, and content classification.

### Archive bucket structure (initial)

```
DDL_Archive/
├── code/
│   ├── installers/
│   ├── scripts/
│   └── components/
├── corpus/
│   ├── council_reviews/
│   ├── governance/
│   ├── prompts/
│   ├── threads/
│   ├── transcripts/
│   └── synthesis/
├── financial/
│   ├── audits/
│   └── budgets/
├── google_takeout/
│   ├── mail/
│   ├── drive/
│   └── [other services]/
├── media/
│   ├── audio/
│   ├── video/
│   └── images/
├── reference/
│   ├── articles/
│   ├── books/
│   └── docs/
├── social/
├── system/
│   ├── sweep_reports/
│   │   └── YYYY/MM/
│   └── audit_reports/
└── unsorted/
```

The `unsorted/` bucket exists as the safety net. If CC cannot confidently classify a file, it goes to `unsorted/` rather than guessing. Operator reviews `unsorted/` periodically.

Buckets can be added but not removed. Reorganizations require their own ADR.

### Nothing is ever deleted

This is the load-bearing principle. Files move between folders. They never leave. Even installers, browser cache, and accidental empty files (`F`, `The` from the audit) get archived to `unsorted/` rather than deleted. Storage is cheap. Regret is expensive. The operator has watched the system catch enough surprises today to know that "I'll just delete it" is exactly when you lose the thing you needed.

If the operator explicitly approves a deletion in a specific case, that's a separate operation governed by CLAUDE.md Rule 5 (sensitive operations). The default is move, not delete.

---

## Provenance metadata (mandatory)

Every chunk written to any collection MUST carry the following metadata fields:

| Field | Type | Example | Purpose |
|---|---|---|---|
| `source_file` | string | `DDLCouncilReview_AntiPractice.txt` | filename for retrieval and dedup |
| `source_path` | string | `DDL_Ingest/DDLCouncilReview_AntiPractice.txt` | full path at time of ingest |
| `source_type` | enum | `council_review` | what kind of content this is |
| `ingested_at` | ISO timestamp | `2026-04-11T15:42:18Z` | when this chunk entered the corpus |
| `ingest_run_id` | string | `sweep_2026-04-11_0300` | which sweep run created this chunk |
| `chunk_index` | int | `12` | position within source file |
| `chunk_total` | int | `47` | total chunks from this source file |

`source_type` initial enum values:

- `council_review`
- `council_synthesis`
- `governance` (ADRs, standards, protocols)
- `gpt_export` / `claude_export` / `project_export`
- `thread_save`
- `transcript` (audio-derived text)
- `prompt` (saved prompts)
- `email` (MBOX-derived)
- `document` (PDF-derived)
- `spreadsheet` (XLSX-derived)
- `web_archive` (HTML/MHTML)
- `code` (source files)
- `system_telemetry` (sweep reports, audit reports)
- `unknown` (catch-all for unclassified)

New `source_type` values can be added but not removed. Adding a value requires updating this ADR.

### Backfill requirement

Existing chunks in the corpus lack these fields. They must be backfilled. The backfill operation is its own scoped task:

1. For each existing chunk, infer `source_file` from existing metadata (if present) or from a best-effort match against `DDL_Archive` filenames.
2. Set `source_type` to best-guess based on content patterns (council reviews, governance docs, transcripts, etc.) with `unknown` as the fallback.
3. Set `ingested_at` to the file's last modified timestamp where available, otherwise to `2026-04-11T00:00:00Z` (the date this ADR was ratified) as a "before this point" marker.
4. `ingest_run_id` for backfilled chunks gets the value `backfill_2026-XX-XX`.

Backfill is read-once, write-once. Future audits use these fields as truth.

---

## The self-documenting ingest loop

### The nightly sweep

The 3am sweep (`dex-sweep.py`, post-retool) runs the following sequence:

1. **Scan** `DDL_Ingest` recursively for files matching ingestible types.
2. **For each file:** check if already ingested (by `source_path` + content hash). Skip if ingested.
3. **Convert** as needed (PDF → text, MBOX → messages, HTML → text, etc.) — using the post-fix `dex-convert.py` with silent-drop counters.
4. **Chunk** with current chunking strategy.
5. **Embed** via Ollama.
6. **Write** to the appropriate collection with full provenance metadata.
7. **Verify** the chunks landed (count check).
8. **Move** the source file from `DDL_Ingest` to `DDL_Staging`. Preserve original filename. Add `.ingested-YYYY-MM-DD` suffix only if a name collision exists.
9. **Emit** a sweep report (see below) IFF any file was processed.
10. **Save** the report to `DDL_Ingest/_reports/sweep_YYYY-MM-DD_HHMM.md`.

### Sweep report format

The report is a Markdown file with the following structure:

```markdown
# Sweep Report — [run_id]

**Run:** sweep_2026-04-11_0300
**Started:** 2026-04-11T03:00:00Z
**Completed:** 2026-04-11T03:14:32Z
**Duration:** 14m 32s
**Sweep version:** dex-sweep v[X.Y]
**Operator:** Dave Kitchens

## Summary

- Files scanned: N
- Files ingested: N
- Files skipped (already ingested): N
- Files dropped (errors): N
- Total chunks added: N
- Collections touched: [list]

## Collections

| Collection | Chunks before | Chunks after | Delta |
|---|---|---|---|
| dex_canon | 230,082 | 230,154 | +72 |
| ddl_archive | 291,520 | 291,520 | 0 |
| ...

## Files ingested

| File | Source type | Chunks | Collection | Notes |
|---|---|---|---|---|
| DDLCouncilReview_AntiPractice.txt | council_review | 47 | dex_canon | clean |
| ...

## Files skipped

| File | Reason |
|---|---|
| 00_DDL_All_v1.0.txt | already_ingested (matched on source_path + hash) |
| ...

## Errors / Drops

| File | Error | Action |
|---|---|---|
| (none) | | |

## Anomalies flagged

- File X exceeded size threshold (>50 MB)
- File Y had unrecognized extension `.maff`, ingested as text fallback
- ...

## Next-day projection

- Files queued for tomorrow: [count]
- Blocked by known issues: [list]

## Sweep version notes

- Running dex-sweep v[X.Y]
- Known limitations active: [list]
```

### Skip-if-no-ingest rule

If the sweep scans `DDL_Ingest` and finds zero new files to process, it does NOT emit a report. Empty days produce no noise. The presence of a report is itself a signal that activity happened.

### The loop closes

The next sweep run picks up the previous night's report from `DDL_Ingest/_reports/` and ingests it as `source_type: system_telemetry` into the appropriate collection (likely `dex_canon`). Then it moves the report from `DDL_Ingest/_reports/` to `DDL_Staging/_reports/` like any other ingested file.

This means: **Dex Jr. acquires persistent memory of its own ingest activity.** Queries like "what got added to the corpus last week?" or "did the council review on anti-patterns ever get ingested?" can be answered by retrieving sweep reports rather than by querying the live database.

A report cannot ingest itself in the same run that created it (infinite loop). Reports are always ingested by the *next* sweep, never the current one.

### Audit reports follow the same pattern

Audit reports (like CR-DEXJR-DDLING-001 itself) follow the same lifecycle:
1. Generated by a CC session
2. Saved to `DDL_Ingest/_reports/audit_YYYY-MM-DD_<topic>.md`
3. Picked up by the next sweep and ingested with `source_type: system_telemetry`
4. Moved to `DDL_Staging/_reports/`
5. Eventually archived to `DDL_Archive/system/audit_reports/YYYY/`

This means the corpus eventually contains its own audit history. Future questions like "what bandaids were in dex-rag in April?" can be answered by retrieving the dex-rag audit report from the corpus directly.

---

## Rationale

### Why three folders instead of two

A two-stage pipeline (Ingest → Archive) forces the organization decision at ingest time. That's the wrong moment — it requires knowing where every file belongs the instant it lands, which is exactly when you don't have time to think about it.

A three-stage pipeline (Ingest → Staging → Archive) separates the *correctness* question (is this in the corpus?) from the *organization* question (where does this live forever?). The correctness question is binary and can be automated. The organization question is fuzzy and benefits from batched human or CC review of the Staging contents.

### Why the metadata is mandatory, not optional

Without provenance metadata, the corpus is a soup. You can retrieve chunks but you can't answer questions about the chunks. With provenance metadata, the corpus becomes a queryable database where "show me everything ingested in the last 30 days" or "show me all council reviews from March" become trivial queries.

The metadata is also the *only* mechanism by which the pipeline can verify that a file has been ingested. Without it, the move from Ingest → Staging is guesswork.

### Why sweep reports are first-class corpus content

The reports are valuable for two reasons:

1. **System self-knowledge.** Dex Jr. can answer questions about its own activity, which is otherwise opaque.
2. **Drift detection.** If a sweep ever silently drops records (post-fix), the report's discrepancy between "files scanned" and "files ingested" will surface it the next morning instead of in a six-month-later audit.

Treating reports as content rather than logs means they're searchable, retrievable, and durable. JSONL logs in a sidecar file are write-only — nobody reads them. Markdown reports in the corpus get retrieved when relevant.

### Why nothing is ever deleted

This is operator policy, not technical preference. The operator has spent the day watching the system catch surprises that would have been disasters under a delete-by-default model. The cost of storage is trivial; the cost of losing a file you needed is high. Move-not-delete is also reversible by definition — you can always un-move. You cannot un-delete.

The `unsorted/` bucket is the relief valve. It absorbs ambiguity without forcing a decision.

---

## Alternatives considered

### Alternative 1: Two-stage pipeline (Ingest → Archive)

Force organization at ingest time. **Rejected** because it puts the slowest decision (where does this live forever) in the hot path of the fastest action (just dropped a file in Ingest, get it into the corpus). Three stages is slower in design but faster in operation.

### Alternative 2: Single mega-folder with metadata-only organization

Don't move files at all — just tag them with metadata and let queries handle organization. **Rejected** because filesystem-level organization is the operator's primary mental model. The operator wants to be able to navigate `DDL_Archive/corpus/council_reviews/` in a file explorer and find things. Pure metadata organization is invisible until you query for it.

### Alternative 3: Auto-classify on ingest with no Staging step

Skip Staging, classify into Archive immediately. **Rejected** because auto-classification will be wrong sometimes, and "wrong" without a Staging review step means files end up in the wrong bucket and the operator never knows. Staging is the human-or-CC-eyeballs review point.

### Alternative 4: Logs instead of reports

Use JSONL logs for sweep telemetry instead of Markdown reports. **Rejected** because logs are write-only by convention — nobody reads them. Markdown reports in the corpus get retrieved organically during normal Dex Jr. queries. Same data, different durability.

### Alternative 5: Delete after ingest

Default to delete files from `DDL_Ingest` once ingested. **Rejected per operator policy.** Files are evidence, not just data. The operator may want to re-process, re-export, or investigate the original later. Delete-by-default is irreversible and loses options for no real benefit.

---

## Consequences

### What becomes easier

- The operator can drop files in `DDL_Ingest` freely without having to think about where they live forever.
- Dex Jr. acquires persistent memory of its own ingest activity, enabling retrospective queries.
- The corpus becomes queryable by provenance — "show me everything from the council reviews bucket" becomes a real query.
- Drift detection is automatic — sweep reports surface anomalies the next morning.
- Audits become incremental — future audits read sweep reports instead of re-querying the live DB.
- The "what's been ingested?" question has a single source of truth (the metadata), not the operator's memory.

### What becomes harder

- The retool now has to land `source_type` and `ingested_at` metadata as a load-bearing requirement, not a nice-to-have. The dex-rag refactor target list moves these to priority 1.
- The backfill operation is real work — touching 542K existing chunks to add metadata is non-trivial and needs its own pre-flight plan.
- The sweep needs to be smarter than the current `--fast` shortcut. It needs to verify ingestion, move files, write reports, and handle the loop-back gracefully. This is a real chunk of post-retool work.
- The Archive bucket structure needs to be created and maintained. CC needs classification logic. The first version will be wrong in some places and need iteration.

### What this enables that wasn't possible before

- **Self-documenting infrastructure.** Dex Jr. knows what it knows.
- **Provenance-based retrieval.** Queries can filter by source_type, date range, or ingest run.
- **Incremental audits.** Every sweep is its own audit; the audit history is queryable.
- **Safe automation.** The operator can trust the sweep because the report tells him what it did.
- **Reversibility.** Every move is reversible because the source is preserved.
- **Cross-machine clarity.** When the operator switches from Reborn to the iMac to the Surface, the file pipeline is the same in all three places.

### What this imposes

- New CLAUDE.md rule (or amendment) requiring all ingest operations to write provenance metadata.
- New ADR (this one) referenced from CLAUDE.md as the canonical authority on the pipeline.
- Discipline around the `unsorted/` bucket — it must be reviewed periodically or it grows without bound.
- A one-time backfill operation that touches every chunk in the corpus.

---

## Validation

How we'll know this decision was right:

- **Within 30 days of implementation:** the operator can ask Dex Jr. "what got ingested last week?" and get a real answer.
- **Within 60 days:** at least one drift incident is caught by a sweep report's anomaly section that would otherwise have been invisible.
- **Within 90 days:** the operator stops mentally tracking what's in `DDL_Ingest` because the pipeline handles it.
- **At the next major audit:** the audit reads sweep reports instead of querying ChromaDB live.

How we'll know it's wrong (and should be superseded):

- The operator finds himself manually moving files between Ingest, Staging, and Archive because the sweep can't decide. (Means classification logic is too weak.)
- Sweep reports are not retrieved by Dex Jr. in normal operation because they're noise rather than signal. (Means the report format is wrong.)
- The `unsorted/` bucket grows to hundreds of files without operator review. (Means the operator's review cadence isn't sustainable, and we need a different relief valve.)
- Backfill produces too many `unknown` source_types to be useful. (Means the inference rules are too weak and we need a smarter classifier.)

---

## Pending decisions (do not block ratification)

These are open questions that don't need to be resolved for the ADR to be ratified, but should be tracked:

1. **Missing collections.** ADR-CORPUS-001 names seven collections; only four exist (`dex_canon`, `ddl_archive`, `dex_code`, `ext_creator`). Decision: create the three missing (`ext_canon`, `ext_archive`, `ext_reference`), or revise ADR-CORPUS-001 to reflect the four-collection reality? **Recommended:** revise the ADR. Reality is the source of truth.

2. **Google Takeout.** Partial Takeout content may be in the corpus already without provenance tags. Decision: re-request a full Takeout from Google and use this pipeline to ingest it cleanly, accepting some duplicate ingestion of already-present chunks; or attempt to identify what's already in via backfill and only ingest the gaps. **Recommended:** re-request and let dedup handle overlap. The duplicate-detection logic in the sweep handles this naturally.

3. **Sweep schedule.** Currently 3am. Should it stay 3am, move to a different time, or run multiple times per day? **Default:** keep 3am until there's a reason to change.

4. **Archive sweep cadence.** How often does CC sweep `DDL_Staging` → `DDL_Archive`? On-demand only? Weekly? **Recommended:** on-demand initially. Add a schedule once we see how full Staging gets in practice.

5. **Sensitive content handling.** The Gmail MBOX (and any future mail ingest) contains personal/sensitive content. Does it go in `dex_canon` like everything else, or does it get its own collection (`dex_mail` or similar) with restricted access? Does it have retention policy? **Deferred** until the Gmail ingest is actually planned.

---

## Authority

This ADR is authored by Marcus Caldwell (Seat 1002) on behalf of the operator. It is **proposed** as of 2026-04-11. It becomes **accepted** when the operator says so explicitly. Once accepted, it is canon and supersedes any conflicting language in CLAUDE.md (which will be updated to reference this ADR).

Future amendments require their own ADR (`ADR-INGEST-PIPELINE-002`, etc.) referencing and superseding the relevant sections.

The operator decides. The architecture does not change. The data does.

---

**End of ADR-INGEST-PIPELINE-001**
``