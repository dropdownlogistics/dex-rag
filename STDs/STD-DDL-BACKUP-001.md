```markdown
# STD-DDL-BACKUP-001 — ChromaDB Backup Standard

**Status:** Active
**Date:** 2026-04-11
**Author:** Marcus Caldwell (Seat 1002, Claude in app) on behalf of operator
**Authority:** ADR-INGEST-PIPELINE-001, CLAUDE.md Rule 8
**Applies to:** Every backup of the live dex-rag ChromaDB

---

## Purpose

The ChromaDB corpus is the asset. Code is rebuildable, prompts are rewritable, governance docs are versionable — the corpus is the only thing that took months of cumulative work to produce and cannot be reconstructed from anything else. This standard defines how the corpus gets backed up so that "what if dex_canon got nuked" stops being a fear and becomes a 30-second restore.

This standard is the contract every backup operation obeys. It is enforceable in code via `dex-backup.py` and via the `ensure_backup_current()` helper that gates ingest writes.

---

## What gets backed up

The entire live ChromaDB directory at `C:\Users\dkitc\.dex-jr\chromadb\`, including:

- `chroma.sqlite3` (master metadata DB)
- All UUID-named segment subdirectories (HNSW vector indexes per collection segment)
- Any other files at the same level (writeable lock files, journal files, etc.)

The backup is a **byte-for-byte structural copy**, not a logical export. Restoring is "stop ChromaDB, replace the directory, restart" — no schema migration, no re-import, no re-embedding. This is the fastest possible restore path and the most resilient to ChromaDB version drift.

---

## Where backups live

Backups live under `D:\DDL_Backup\chromadb_backups\` (note the new path — separate from the existing untouched `D:\DDL_Backup\chromadb\` so we don't disturb the existing 19-day-old artifact while we transition).

Each backup is a **dated subdirectory**:

```
D:\DDL_Backup\chromadb_backups\
├── chromadb_2026-04-11_2150\
│   ├── chroma.sqlite3
│   ├── <uuid-1>\
│   ├── <uuid-2>\
│   └── _manifest.json
├── chromadb_2026-04-08_0300\
├── chromadb_2026-04-01_0300\
├── ...
└── _backup_log.jsonl
```

The `_manifest.json` inside each backup directory contains:
- Backup creation timestamp (ISO 8601 UTC)
- Source path (the live `chromadb/` location at time of backup)
- Total size in bytes
- File count
- Collection list with chunk counts (queried from the just-backed-up `chroma.sqlite3`)
- Backup tool version
- Backup duration in seconds
- SHA256 of `chroma.sqlite3` (integrity check anchor)

The `_backup_log.jsonl` at the root is an append-only log of every backup run (success or failure), one JSON line per run, for audit purposes. This file is itself eligible for ingest into the corpus as `source_type: system_telemetry` once the sweep is wired up.

---

## When backups run (trigger policy)

A backup runs when ANY of the following triggers fires:

### Trigger 1 — Time-based (default cadence)

Last successful backup is older than **3 days**.

This is the floor. Even if nothing else triggers, the corpus gets backed up at least every 3 days.

### Trigger 2 — Volume-based (growth gate)

Live total chunk count has grown by more than **1,000 chunks** since the last successful backup.

Calculated as: `sum(collection.count() for collection in live_collections) - last_backup_total_count > 1000`.

### Trigger 3 — Pre-write gate (ingest-aware)

Any ingest path can call `ensure_backup_current()` before a write. The function checks Triggers 1 and 2 and runs a backup if either fires. If the backup fails, the ingest is aborted and the failure is reported. This is how Rule 8 becomes self-enforcing.

### Trigger 4 — Manual override

Operator runs `python dex-backup.py --force` or any helper that explicitly requests a backup regardless of the other triggers. Useful before risky operations or when the operator just wants the comfort of "I just backed up."

### Trigger 5 — Pre-batch (large operation gate)

Any operation that intends to write more than **100 chunks in a single run** must call `ensure_backup_current()` before starting, regardless of when the last backup ran. This is the per-milestone rule from CLAUDE.md Rule 8 made concrete.

---

## Retention policy (rotation)

Backups are kept on a tiered rotation schedule:

- **Last 7 daily backups** — keep all
- **Last 4 weekly backups** — keep one per week (the Sunday backup, or the latest if no Sunday)
- **Last 3 monthly backups** — keep one per month (the first-of-month backup, or the latest if no first)
- **Anything older** — automatically pruned

Maximum estimated storage at full rotation: **~14 backups × ~12 GB each ≈ 168 GB**. This fits comfortably on `D:\` (the operator confirms D: is the corpus backup drive and has space).

Rotation runs at the end of every backup operation, after the new backup is verified. If rotation fails, the new backup is still kept and the failure is logged — better to have one too many backups than one too few.

---

## How backups happen (the copy mechanism)

Backups use a **hot copy** strategy — ChromaDB does NOT need to be stopped. The mechanism:

1. **For `chroma.sqlite3`:** Use SQLite's built-in backup API via the Python `sqlite3` module. This produces a consistent snapshot even if writes are happening concurrently. The SQLite backup API copies pages while holding appropriate locks; concurrent readers and writers continue uninterrupted.

   ```python
   src = sqlite3.connect(live_sqlite_path)
   dst = sqlite3.connect(backup_sqlite_path)
   src.backup(dst)
   src.close()
   dst.close()
   ```

2. **For UUID segment directories:** ChromaDB's HNSW segment files are append-only on disk. File-level copy (`shutil.copytree`) is safe — even if a write happens mid-copy, the worst case is a slightly older view of one segment, which is consistent with the backup's point-in-time snapshot semantics.

3. **For lock files / journal files:** Skip them. They're transient and unnecessary for restore.

The backup captures the corpus as it exists at the moment the SQLite backup completes. Any writes that happen after that moment are not in this backup — they'll be in the next one.

**Restore procedure** (documented for completeness, not automated):

1. Stop any process using ChromaDB (Ollama, dex-rag scripts)
2. Move the current `C:\Users\dkitc\.dex-jr\chromadb\` to a safe holding location
3. `Copy-Item -Recurse <backup-path> C:\Users\dkitc\.dex-jr\chromadb`
4. Restart processes
5. Verify collection counts match the backup's `_manifest.json`

---

## Validation rules

After every backup, the following checks run. If ANY fails, the backup is marked **failed**, the corrupted backup directory is renamed with a `_FAILED` suffix, and the next backup attempt starts fresh.

1. `chroma.sqlite3` exists at the backup destination
2. Backup `chroma.sqlite3` size is within ±5% of source size (sanity check, not exact because SQLite may compact)
3. Backup `chroma.sqlite3` opens cleanly with `sqlite3.connect(uri='file:...?mode=ro')`
4. Backup contains the same collection names as the source (queried from `collections` table)
5. Backup chunk counts per collection are equal to source chunk counts (the most important check — if they don't match, the snapshot is incomplete)
6. All UUID subdirectories from source are present in backup
7. `_manifest.json` is valid JSON and contains all required fields
8. SHA256 of backup `chroma.sqlite3` matches the value written into `_manifest.json`

---

## The `dex-backup.py` script contract

The executable that implements this standard. CLI shape:

```
python dex-backup.py [--force] [--dry-run] [--rotate-only] [--check-only]
```

- `--force` — Run a backup regardless of triggers
- `--dry-run` — Check triggers, report what would happen, exit without copying
- `--rotate-only` — Skip the backup, just run the retention rotation
- `--check-only` — Validate the most recent existing backup against this standard, exit. Useful for the `ensure_backup_current()` path.

Default behavior (no flags): check triggers, run backup if any trigger fires, run rotation, exit.

Exit codes:
- `0` — Success (backup completed and validated, OR no backup needed)
- `1` — Backup attempted and failed validation
- `2` — Pre-flight failure (source not accessible, destination not writable, etc.)
- `3` — Rotation failure (backup succeeded but rotation didn't)

---

## The `ensure_backup_current()` helper contract

Lives in `dex_pipeline.py` alongside the other helpers. Called by ingest paths before writes.

```python
def ensure_backup_current(
    expected_write_chunks: int = 0,
    force_check: bool = False,
) -> dict:
    """
    Ensure the corpus backup is current per STD-DDL-BACKUP-001.
    
    Checks the backup triggers. If a backup is needed, runs dex-backup.py.
    If the backup runs and fails, raises BackupFailedError so the caller
    can abort the write.
    
    Args:
        expected_write_chunks: How many chunks the caller intends to write.
            If > 100, Trigger 5 (pre-batch gate) fires regardless of other triggers.
        force_check: Force a fresh backup status check even if one was just done.
    
    Returns:
        dict with keys: backup_ran (bool), backup_path (str or None),
        triggers_fired (list of str), backup_age_hours (float), status (str).
    
    Raises:
        BackupFailedError: if a needed backup ran and failed validation.
        BackupNotFoundError: if no backup exists at all and one couldn't be created.
    """
```

This function is the single point of enforcement for Rule 8. Every ingest path calls it. No ingest path is allowed to write to a live collection without calling it first.

---

## Backwards compatibility

The existing 19-day-old backup at `D:\DDL_Backup\chromadb\` is **preserved as-is**. We do not delete it, modify it, or rotate it. It's the historical snapshot from 2026-03-23 and may be useful as a deep-history rollback point. The new backup system writes to a different path (`D:\DDL_Backup\chromadb_backups\`) so the existing artifact stays untouched.

If we ever decide to formally retire the old backup, that's its own ADR. Default is keep.

---

## Versioning

Same convention as STD-DDL-METADATA-001: `STD-DDL-BACKUP-001`, `-002`, etc. Amendments to a major version are tracked in a changelog at the end. New trigger types or new validation rules are minor amendments. Changing the backup mechanism (e.g., switching from SQLite backup API to a different snapshot tool) is a major amendment.

---

## Related

- **CLAUDE.md Rule 8** — Corpus Integrity Is Sacred (this standard is how we honor it)
- **ADR-INGEST-PIPELINE-001** — defines the pipeline this standard protects
- **STD-DDL-METADATA-001** — the metadata schema; backup manifests follow similar provenance principles
- **CR-DEXJR-DDLING-001** — surfaced the 19-day-stale backup that motivated this standard

---

## Changelog

- **2026-04-11** — v001 created. 5 trigger types, hot-copy via SQLite backup API, rolling rotation (7 daily / 4 weekly / 3 monthly), `_manifest.json` schema, `ensure_backup_current()` helper contract.

---

**End of STD-DDL-BACKUP-001**
```

