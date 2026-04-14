"""
dex-backup.py — ChromaDB backup executable per STD-DDL-BACKUP-001.

Hot-copy backup of the live ChromaDB to D:\\DDL_Backup\\chromadb_backups\\
with validation, manifest generation, and rolling rotation.

Usage:
    python dex-backup.py                # check triggers, backup if needed
    python dex-backup.py --force        # backup regardless of triggers
    python dex-backup.py --dry-run      # check triggers, report, no copy
    python dex-backup.py --rotate-only  # skip backup, run rotation only
    python dex-backup.py --check-only   # validate most recent backup, exit

Exit codes:
    0 — success (backup completed and validated, or no backup needed)
    1 — backup attempted and failed validation
    2 — pre-flight failure
    3 — rotation failure (backup succeeded but rotation didn't)

Authority: STD-DDL-BACKUP-001
"""

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Canonical paths
LIVE_CHROMADB = Path(r"C:\Users\dkitc\.dex-jr\chromadb")
BACKUP_ROOT = Path(r"D:\DDL_Backup\chromadb_backups")
BACKUP_LOG = BACKUP_ROOT / "_backup_log.jsonl"

# Trigger thresholds per STD-DDL-BACKUP-001
TRIGGER_DAYS = 3
TRIGGER_CHUNK_DELTA = 1000
TRIGGER_BATCH_THRESHOLD = 100

# Rotation policy
RETAIN_DAILY = 7
RETAIN_WEEKLY = 4
RETAIN_MONTHLY = 3

BACKUP_TOOL_VERSION = "dex-backup-001"


class RestoreTestFailedError(Exception):
    """
    Raised by restore_test() when a backup fails post-creation verification.

    Trigger 6 of STD-DDL-BACKUP-001 (pending formalization). The backup
    directory that failed the restore test is NOT automatically renamed
    or deleted — the operator inspects it manually. The exception message
    contains the full diff (collection counts, missing collections, etc.).
    """
    def __init__(self, message: str, result: dict | None = None):
        super().__init__(message)
        self.result = result


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now_compact() -> str:
    # Step 47: seconds added. Combined with the PID suffix appended at
    # the call site, this gives collision-resistant backup directory
    # names even when Windows Task Scheduler double-fires (the 4 AM
    # race diagnosed in Step 46, fires observed 44-54 ms apart).
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")


def cleanup_stale_scratch(max_age_hours: float = 1.0) -> int:
    """
    Reclaim orphan restore_test_* directories in dex-rag-scratch/ that
    are older than max_age_hours.

    Exists because restore_test()'s in-process cleanup can fail on
    Windows when ChromaDB's HNSW data_level0.bin is still memory-mapped
    after `del client` + `gc.collect()`. The mmap is released when the
    Python process exits, so the *next* dex-backup.py run can safely
    remove what the previous run left behind.

    Tolerates file-lock errors by logging a WARN and continuing.
    Returns the count of directories actually removed.
    """
    scratch_root = Path(__file__).parent.parent / "dex-rag-scratch"
    if not scratch_root.exists():
        return 0

    removed = 0
    cutoff = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
    for child in scratch_root.iterdir():
        if not child.is_dir():
            continue
        if not child.name.startswith("restore_test_"):
            continue
        try:
            mtime = child.stat().st_mtime
            if mtime < cutoff:
                shutil.rmtree(child)
                removed += 1
                print(f"  Reclaimed stale scratch: {child.name}")
        except Exception as e:
            print(f"  WARN: could not reclaim {child.name}: {e}")
    return removed


def find_existing_backups() -> list[Path]:
    """Return sorted list of existing backup directories (newest first)."""
    if not BACKUP_ROOT.exists():
        return []
    backups = [
        p for p in BACKUP_ROOT.iterdir()
        if p.is_dir()
        and p.name.startswith("chromadb_")
        and not p.name.endswith("_FAILED")
        and not p.name.endswith("_INCOMPLETE")
    ]
    backups.sort(key=lambda p: p.name, reverse=True)
    return backups


def cleanup_dead_letter_backups(min_age_hours: float = 24.0) -> list[dict]:
    """
    Remove dead-letter backup directories older than min_age_hours.

    Targets (per Step 47):
      - *_INCOMPLETE  — crash residue from prior sweep failures
      - *_FAILED      — validation-failure residue

    Safety: anything newer than min_age_hours is left alone (could be
    an in-flight sibling-PID run during the Step 46 concurrency race).
    Returns a list of action records, which the caller logs.
    """
    actions: list[dict] = []
    if not BACKUP_ROOT.exists():
        return actions
    cutoff = datetime.now(timezone.utc).timestamp() - (min_age_hours * 3600)
    for child in BACKUP_ROOT.iterdir():
        if not child.is_dir():
            continue
        if not (child.name.endswith("_INCOMPLETE") or child.name.endswith("_FAILED")):
            continue
        try:
            mtime = child.stat().st_mtime
            age_hours = round((datetime.now(timezone.utc).timestamp() - mtime) / 3600, 2)
            if mtime >= cutoff:
                print(f"  Dead-letter kept (too fresh): {child.name} age={age_hours}h")
                continue
            reason = "_INCOMPLETE" if child.name.endswith("_INCOMPLETE") else "_FAILED"
            shutil.rmtree(child)
            actions.append({
                "action": "cleanup",
                "path": str(child),
                "reason": reason,
                "age_hours": age_hours,
            })
            print(f"  Dead-letter removed: {child.name} ({reason}, age={age_hours}h)")
        except Exception as e:
            print(f"  WARN: could not clean {child.name}: {e}")
    return actions


def get_live_chunk_count() -> int:
    """Get total chunk count across all live collections."""
    sys.path.insert(0, str(Path(__file__).parent))
    from dex_weights import get_client
    client = get_client()
    total = 0
    for col in client.list_collections():
        total += client.get_collection(col.name).count()
    return total


def read_manifest(backup_dir: Path) -> dict | None:
    """Read a backup's _manifest.json. Returns None if missing or invalid."""
    manifest_path = backup_dir / "_manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def check_triggers(expected_write_chunks: int = 0) -> tuple[bool, list[str]]:
    """
    Check all backup triggers per STD-DDL-BACKUP-001.
    Returns (should_backup, list_of_triggers_that_fired).
    """
    fired = []
    backups = find_existing_backups()

    if not backups:
        # No backups exist at all — Trigger 1 effectively fires
        fired.append("no_existing_backups")
        return (True, fired)

    most_recent = backups[0]
    manifest = read_manifest(most_recent)

    if manifest is None:
        fired.append("most_recent_manifest_invalid")
        return (True, fired)

    # Trigger 1: time-based
    last_backup_at = datetime.fromisoformat(manifest["created_at"].replace("Z", "+00:00"))
    age = datetime.now(timezone.utc) - last_backup_at
    if age > timedelta(days=TRIGGER_DAYS):
        fired.append(f"time_based_age_{age.days}d")

    # Trigger 2: volume-based
    try:
        live_count = get_live_chunk_count()
        backup_count = manifest.get("total_chunk_count", 0)
        delta = live_count - backup_count
        if delta > TRIGGER_CHUNK_DELTA:
            fired.append(f"volume_based_delta_{delta}_chunks")
    except Exception as e:
        fired.append(f"live_count_unreachable_{type(e).__name__}")

    # Trigger 5: pre-batch
    if expected_write_chunks > TRIGGER_BATCH_THRESHOLD:
        fired.append(f"pre_batch_expected_{expected_write_chunks}_chunks")

    return (len(fired) > 0, fired)


def build_check_status(expected_write_chunks: int = 0) -> dict:
    """
    Lightweight status of the most recent backup, suitable for the
    --check-only --json path consumed by ensure_backup_current().

    Does NOT call validate_backup() — that function compares the backup
    against current live state and would fail on any drift since the
    backup was taken. This function checks existence + manifest + sqlite
    readability only, plus runs check_triggers() to report what would
    fire if a write happened now.
    """
    result = {
        "exists": False,
        "most_recent": None,
        "most_recent_path": None,
        "manifest_valid": False,
        "sqlite_present": False,
        "sqlite_readable": False,
        "age_hours": None,
        "created_at": None,
        "total_chunk_count": None,
        "triggers_to_fire": [],
        "should_backup": False,
        "live_chunk_count": None,
        "expected_write_chunks": expected_write_chunks,
    }

    backups = find_existing_backups()
    if not backups:
        result["should_backup"] = True
        result["triggers_to_fire"] = ["no_existing_backups"]
        return result

    most_recent = backups[0]
    result["exists"] = True
    result["most_recent"] = most_recent.name
    result["most_recent_path"] = str(most_recent)

    manifest = read_manifest(most_recent)
    if manifest is None:
        result["should_backup"] = True
        result["triggers_to_fire"] = ["most_recent_manifest_invalid"]
        return result

    result["manifest_valid"] = True
    result["created_at"] = manifest.get("created_at")
    result["total_chunk_count"] = manifest.get("total_chunk_count")

    if result["created_at"]:
        try:
            last = datetime.fromisoformat(result["created_at"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - last).total_seconds()
            result["age_hours"] = round(age / 3600, 2)
        except (ValueError, TypeError):
            pass

    sqlite_path = most_recent / "chroma.sqlite3"
    result["sqlite_present"] = sqlite_path.exists()
    if sqlite_path.exists():
        try:
            db_uri = f"file:/{str(sqlite_path).replace(chr(92), '/')}?mode=ro"
            con = sqlite3.connect(db_uri, uri=True)
            con.close()
            result["sqlite_readable"] = True
        except Exception as e:
            result["sqlite_error"] = str(e)

    # Trigger check (uses check_triggers — same logic as the main backup path)
    try:
        should, fired = check_triggers(expected_write_chunks)
        result["should_backup"] = should
        result["triggers_to_fire"] = fired
    except Exception as e:
        result["trigger_check_error"] = type(e).__name__

    # Live count for context
    try:
        result["live_chunk_count"] = get_live_chunk_count()
    except Exception as e:
        result["live_count_error"] = type(e).__name__

    return result


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def query_collection_state(sqlite_path: Path) -> dict[str, int]:
    """
    Query a ChromaDB SQLite file for collection names and chunk counts.
    Read-only. Returns dict of {collection_name: chunk_count}.
    """
    db_uri = f"file:/{str(sqlite_path).replace(chr(92), '/')}?mode=ro"
    con = sqlite3.connect(db_uri, uri=True)
    cur = con.cursor()
    cur.execute("SELECT id, name FROM collections")
    collections = cur.fetchall()
    result = {}
    for col_id, col_name in collections:
        # Count via embeddings table joined through segments
        # Fall back to a simpler count if join is unreliable
        try:
            cur.execute("""
                SELECT COUNT(*) FROM embeddings e
                JOIN segments s ON e.segment_id = s.id
                WHERE s.collection = ?
            """, (col_id,))
            result[col_name] = cur.fetchone()[0]
        except sqlite3.OperationalError:
            # Schema variant — just total embeddings, not per collection
            result[col_name] = -1
    con.close()
    return result


def perform_backup(dry_run: bool = False, skip_cleanup: bool = False) -> tuple[bool, Path | None, dict]:
    """
    Run the actual backup. Returns (success, backup_path, manifest).
    """
    started_at = datetime.now(timezone.utc)
    timestamp = utc_now_compact()
    pid = os.getpid()
    # Step 47: seconds + PID suffix. See utc_now_compact() note and the
    # Step 46 audit on the 4 AM Task Scheduler double-fire race.
    backup_dir = BACKUP_ROOT / f"chromadb_{timestamp}_{pid}"

    if dry_run:
        print(f"[DRY RUN] Would create backup at: {backup_dir}")
        return (True, None, {})

    # Step 47: sweep dead-letter siblings before creating today's backup.
    # Gated behind --skip-cleanup for manual debugging runs that want the
    # filesystem left as-is.
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    if not skip_cleanup:
        for entry in cleanup_dead_letter_backups():
            append_log({"timestamp": utc_now_iso(), **entry})

    # Step 36: footprint at start so killed processes are visible in the log.
    append_log({
        "timestamp": utc_now_iso(),
        "stage": "started",
        "pid": pid,
        "backup_path": str(backup_dir),
    })

    print(f"Creating backup at: {backup_dir}")
    backup_dir.mkdir(parents=True, exist_ok=False)

    # Step 1: SQLite backup API for chroma.sqlite3
    src_sqlite = LIVE_CHROMADB / "chroma.sqlite3"
    dst_sqlite = backup_dir / "chroma.sqlite3"
    print(f"  SQLite backup: {src_sqlite.name}")
    src_con = sqlite3.connect(str(src_sqlite))
    dst_con = sqlite3.connect(str(dst_sqlite))
    src_con.backup(dst_con)
    src_con.close()
    dst_con.close()

    # Step 2: shutil.copytree for each UUID segment directory
    for item in LIVE_CHROMADB.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            print(f"  Copying segment: {item.name}")
            shutil.copytree(item, backup_dir / item.name)

    # Step 3: Build manifest
    completed_at = datetime.now(timezone.utc)
    duration = (completed_at - started_at).total_seconds()

    total_size = sum(f.stat().st_size for f in backup_dir.rglob("*") if f.is_file())
    file_count = sum(1 for f in backup_dir.rglob("*") if f.is_file())
    sqlite_sha = sha256_file(dst_sqlite)
    collection_state = query_collection_state(dst_sqlite)
    total_chunks = sum(c for c in collection_state.values() if c >= 0)

    manifest = {
        "created_at": started_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "completed_at": completed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "duration_seconds": round(duration, 2),
        "source_path": str(LIVE_CHROMADB),
        "backup_path": str(backup_dir),
        "total_size_bytes": total_size,
        "file_count": file_count,
        "sqlite_sha256": sqlite_sha,
        "collections": collection_state,
        "total_chunk_count": total_chunks,
        "backup_tool_version": BACKUP_TOOL_VERSION,
    }

    (backup_dir / "_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"  Manifest written. Total chunks: {total_chunks:,}")

    return (True, backup_dir, manifest)


def validate_backup(backup_dir: Path, manifest: dict) -> tuple[bool, list[str]]:
    """Validate a backup against STD-DDL-BACKUP-001 §"Validation rules"."""
    failures = []

    sqlite_path = backup_dir / "chroma.sqlite3"
    if not sqlite_path.exists():
        failures.append("chroma.sqlite3 missing in backup")
        return (False, failures)

    src_size = (LIVE_CHROMADB / "chroma.sqlite3").stat().st_size
    dst_size = sqlite_path.stat().st_size
    if abs(dst_size - src_size) / src_size > 0.05:
        failures.append(f"size delta >5%: src={src_size}, dst={dst_size}")

    try:
        db_uri = f"file:/{str(sqlite_path).replace(chr(92), '/')}?mode=ro"
        con = sqlite3.connect(db_uri, uri=True)
        con.close()
    except Exception as e:
        failures.append(f"backup sqlite won't open read-only: {e}")

    src_state = query_collection_state(LIVE_CHROMADB / "chroma.sqlite3")
    dst_state = manifest["collections"]
    if set(src_state.keys()) != set(dst_state.keys()):
        failures.append(f"collection name mismatch: src={set(src_state.keys())}, dst={set(dst_state.keys())}")

    for name, src_count in src_state.items():
        if name not in dst_state:
            failures.append(f"collection {name} missing in backup")
            continue
        if src_count != dst_state[name] and src_count >= 0 and dst_state[name] >= 0:
            failures.append(f"chunk count mismatch for {name}: src={src_count}, dst={dst_state[name]}")

    src_uuids = {p.name for p in LIVE_CHROMADB.iterdir() if p.is_dir() and not p.name.startswith(".")}
    dst_uuids = {p.name for p in backup_dir.iterdir() if p.is_dir()}

    # Backup contains UUIDs that live no longer has = live-side deletion
    # or segment loss. This is a corruption/loss signal — FATAL.
    missing_in_live = dst_uuids - src_uuids
    if missing_in_live:
        failures.append(
            f"UUIDs in backup but missing from live (possible data loss): "
            f"{sorted(missing_in_live)}"
        )

    # Live has UUIDs the backup doesn't = orphan segments from dropped
    # collections (Chroma doesn't GC segment dirs on collection drop).
    # Informational only — does NOT make the backup invalid.
    extra_in_live = src_uuids - dst_uuids
    if extra_in_live:
        sample = sorted(extra_in_live)[:3]
        print(
            f"  WARN: {len(extra_in_live)} orphan segment(s) in live not in backup "
            f"(likely dropped-collection residue): {sample}"
        )

    actual_sha = sha256_file(sqlite_path)
    if actual_sha != manifest["sqlite_sha256"]:
        failures.append(f"sha256 mismatch")

    return (len(failures) == 0, failures)


def restore_test(backup_path: "Path | None" = None) -> dict:
    """
    Trigger 6 — post-backup restore verification.

    Copies a backup to a scratch location outside the repo and outside
    OneDrive, opens it as a fresh ChromaDB PersistentClient, enumerates
    all collections, counts each one, and compares the result to the
    manifest's recorded counts. Any mismatch raises
    RestoreTestFailedError with full diff detail.

    The original backup directory is never opened or modified — only
    the scratch copy is touched. Scratch is always cleaned up via a
    try/finally, even on failure. On Windows, a GC hint + one retry
    with a small delay handles the SQLite file-lock case.

    Args:
        backup_path: path to a backup directory. If None, uses the
            most recent backup from find_existing_backups().

    Returns:
        dict with test result:
            backup_tested: backup dir name
            scratch_path: scratch location (deleted by the time this returns)
            collections_verified: {name: count} from the restored DB
            manifest_counts: {name: count} from the manifest
            match: bool — True if all counts match
            duration_seconds: float
            status: "PASS" or "FAIL"

    Raises:
        RestoreTestFailedError: on missing backup, invalid manifest,
            open failure, or any count mismatch. The exception carries
            the partial result dict on `.result` for the caller to log.
    """
    started_at = datetime.now(timezone.utc)

    # Resolve backup path
    if backup_path is None:
        backups = find_existing_backups()
        if not backups:
            raise RestoreTestFailedError("restore_test: no backups found")
        backup_path = backups[0]

    backup_path = Path(backup_path)
    if not backup_path.exists():
        raise RestoreTestFailedError(
            f"restore_test: backup path does not exist: {backup_path}"
        )

    manifest = read_manifest(backup_path)
    if manifest is None:
        raise RestoreTestFailedError(
            f"restore_test: manifest missing or invalid at {backup_path}"
        )

    raw_counts = dict(manifest.get("collections", {}))
    # Filter out -1 fallback values from schema-mismatch cases
    manifest_counts = {k: v for k, v in raw_counts.items() if v >= 0}
    if not manifest_counts:
        raise RestoreTestFailedError(
            f"restore_test: manifest has no valid collection counts "
            f"(all -1 or empty): {raw_counts}"
        )

    # Scratch path: outside repo, outside OneDrive, outside live .dex-jr
    scratch_root = Path(__file__).parent.parent / "dex-rag-scratch"
    scratch_root.mkdir(parents=True, exist_ok=True)
    scratch_dir = scratch_root / f"restore_test_{utc_now_compact()}"

    print(f"Restore test: {backup_path.name}")
    print(f"  Scratch: {scratch_dir}")
    total_size_gb = manifest.get("total_size_bytes", 0) / 1e9
    print(f"  Copying backup (~{total_size_gb:.1f} GB) to scratch...")

    result = {
        "backup_tested": backup_path.name,
        "scratch_path": str(scratch_dir),
        "collections_verified": {},
        "manifest_counts": manifest_counts,
        "match": False,
        "duration_seconds": None,
        "status": "FAIL",
    }

    failures: list[str] = []
    client = None
    try:
        copy_start = datetime.now(timezone.utc)
        shutil.copytree(backup_path, scratch_dir)
        copy_duration = (datetime.now(timezone.utc) - copy_start).total_seconds()
        print(f"  Copy complete ({copy_duration:.1f}s)")

        # Local import to keep chromadb out of the module-load path
        import chromadb
        try:
            from chromadb.config import Settings
            client = chromadb.PersistentClient(
                path=str(scratch_dir),
                settings=Settings(anonymized_telemetry=False),
            )
        except Exception:
            # Fallback if chromadb version differs on the Settings API
            client = chromadb.PersistentClient(path=str(scratch_dir))

        verified: dict[str, int] = {}
        for col in client.list_collections():
            name = col.name
            collection = client.get_collection(name)
            count = collection.count()
            verified[name] = count
            expected = manifest_counts.get(name)
            if expected is None:
                tag = "EXTRA"
                exp_str = "-"
            elif expected == count:
                tag = "OK"
                exp_str = f"{expected:,}"
            else:
                tag = "MISMATCH"
                exp_str = f"{expected:,}"
            print(f"  {name:<15} restored={count:>10,}  manifest={exp_str:>11}  [{tag}]")

        result["collections_verified"] = verified

        # Compare: every manifest collection must appear with matching count
        for name, manifest_count in manifest_counts.items():
            if name not in verified:
                failures.append(f"missing collection in restore: {name}")
                continue
            if verified[name] != manifest_count:
                failures.append(
                    f"count mismatch for {name}: "
                    f"restored={verified[name]} manifest={manifest_count}"
                )
        extra_cols = set(verified.keys()) - set(manifest_counts.keys())
        if extra_cols:
            failures.append(
                f"extra collections in restore not in manifest: {sorted(extra_cols)}"
            )

        if not failures:
            result["match"] = True
            result["status"] = "PASS"
        else:
            result["status"] = "FAIL"
    finally:
        # Release client before tearing down scratch (Windows file locks)
        if client is not None:
            try:
                del client
            except Exception:
                pass
        import gc
        gc.collect()

        completed_at = datetime.now(timezone.utc)
        result["duration_seconds"] = round(
            (completed_at - started_at).total_seconds(), 2
        )

        # Clean up scratch (retry once on Windows SQLite lock edge case)
        if scratch_dir.exists():
            for attempt in range(2):
                try:
                    shutil.rmtree(scratch_dir)
                    print(f"  Scratch cleaned up")
                    break
                except Exception as e:
                    if attempt == 0:
                        import time as _time
                        _time.sleep(1)
                        gc.collect()
                        continue
                    print(f"  WARNING: scratch cleanup failed: {e}")

    if failures:
        raise RestoreTestFailedError(
            f"restore_test FAILED for {backup_path.name}:\n  " +
            "\n  ".join(failures),
            result=result,
        )

    return result


def rotate_backups() -> tuple[bool, list[str]]:
    """Apply retention policy. Returns (success, list_of_pruned_paths)."""
    backups = find_existing_backups()
    if len(backups) <= RETAIN_DAILY:
        return (True, [])

    keep = set()

    # Keep last 7 daily
    for b in backups[:RETAIN_DAILY]:
        keep.add(b.name)

    # Keep last 4 weekly (one per week from older backups)
    weeks_kept = set()
    for b in backups[RETAIN_DAILY:]:
        manifest = read_manifest(b)
        if not manifest:
            continue
        created = datetime.fromisoformat(manifest["created_at"].replace("Z", "+00:00"))
        week_key = created.strftime("%Y-W%U")
        if week_key not in weeks_kept and len(weeks_kept) < RETAIN_WEEKLY:
            weeks_kept.add(week_key)
            keep.add(b.name)

    # Keep last 3 monthly
    months_kept = set()
    for b in backups[RETAIN_DAILY:]:
        manifest = read_manifest(b)
        if not manifest:
            continue
        created = datetime.fromisoformat(manifest["created_at"].replace("Z", "+00:00"))
        month_key = created.strftime("%Y-%m")
        if month_key not in months_kept and len(months_kept) < RETAIN_MONTHLY:
            months_kept.add(month_key)
            keep.add(b.name)

    pruned = []
    for b in backups:
        if b.name not in keep:
            shutil.rmtree(b)
            pruned.append(str(b))

    return (True, pruned)


def append_log(entry: dict) -> None:
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    with open(BACKUP_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    parser = argparse.ArgumentParser(description="ChromaDB backup per STD-DDL-BACKUP-001")
    parser.add_argument("--force", action="store_true", help="Backup regardless of triggers")
    parser.add_argument("--dry-run", action="store_true", help="Check triggers, report, no copy")
    parser.add_argument("--rotate-only", action="store_true", help="Skip backup, just rotate")
    parser.add_argument("--check-only", action="store_true", help="Validate most recent backup")
    parser.add_argument("--json", action="store_true", help="Output structured JSON (only with --check-only)")
    parser.add_argument("--restore-test", action="store_true", help="Run Trigger 6 restore test on most recent backup")
    parser.add_argument("--skip-restore-test", action="store_true", help="Skip Trigger 6 restore test after backup creation")
    parser.add_argument("--skip-cleanup", action="store_true", help="Skip Step 47 dead-letter cleanup (manual debug runs)")
    parser.add_argument("--expected-chunks", type=int, default=0, help="For pre-batch trigger")
    args = parser.parse_args()

    # Suppress banner in --check-only --json mode so stdout is clean JSON
    json_mode = args.check_only and args.json
    if not json_mode:
        print(f"dex-backup {BACKUP_TOOL_VERSION}")
        print(f"Live: {LIVE_CHROMADB}")
        print(f"Backup root: {BACKUP_ROOT}")
        print()

        # Reclaim any orphan restore_test_* scratch dirs left by a prior
        # run that hit the Windows HNSW mmap lock on in-process cleanup.
        # Skipped in JSON mode to keep stdout a single clean JSON line.
        cleanup_stale_scratch()

    # Pre-flight
    if not LIVE_CHROMADB.exists():
        print(f"FATAL: live ChromaDB not found at {LIVE_CHROMADB}")
        sys.exit(2)
    if not (LIVE_CHROMADB / "chroma.sqlite3").exists():
        print(f"FATAL: chroma.sqlite3 not found at {LIVE_CHROMADB}")
        sys.exit(2)

    if args.check_only:
        if args.json:
            # Lightweight JSON status for ensure_backup_current() callers.
            # Does NOT call validate_backup() — see build_check_status() docstring.
            status = build_check_status(args.expected_chunks)
            print(json.dumps(status))
            if not status["exists"]:
                sys.exit(2)
            if not status["manifest_valid"] or not status.get("sqlite_readable", False):
                sys.exit(1)
            sys.exit(0)
        backups = find_existing_backups()
        if not backups:
            print("No backups found.")
            sys.exit(2)
        manifest = read_manifest(backups[0])
        if not manifest:
            print("Most recent backup has invalid manifest.")
            sys.exit(1)
        ok, failures = validate_backup(backups[0], manifest)
        if ok:
            print(f"Most recent backup VALID: {backups[0].name}")
            sys.exit(0)
        else:
            print(f"Most recent backup FAILED validation:")
            for f in failures:
                print(f"  - {f}")
            sys.exit(1)

    if args.rotate_only:
        ok, pruned = rotate_backups()
        print(f"Rotation: {'OK' if ok else 'FAILED'}, pruned {len(pruned)} backups")
        sys.exit(0 if ok else 3)

    if args.restore_test:
        try:
            rt = restore_test()
            print()
            print(f"Restore test: {rt['status']}")
            print(f"  Backup: {rt['backup_tested']}")
            print(f"  Duration: {rt['duration_seconds']:.1f}s")
            print(f"  Collections:")
            for name in sorted(rt['collections_verified'].keys()):
                restored = rt['collections_verified'][name]
                manifest_count = rt['manifest_counts'].get(name, None)
                tag = "OK" if restored == manifest_count else "MISMATCH"
                exp = f"{manifest_count:,}" if manifest_count is not None else "-"
                print(f"    {name:<15} restored={restored:>10,}  manifest={exp:>11}  [{tag}]")
            append_log({
                "timestamp": utc_now_iso(),
                "result": "success",
                "stage": "restore_test_standalone",
                "backup_path": rt.get("scratch_path"),
                "backup_tested": rt.get("backup_tested"),
                "duration_seconds": rt.get("duration_seconds"),
                "collections_verified": rt.get("collections_verified"),
            })
            sys.exit(0)
        except RestoreTestFailedError as e:
            print()
            print(f"RESTORE TEST FAILED:")
            print(str(e))
            append_log({
                "timestamp": utc_now_iso(),
                "result": "failed",
                "stage": "restore_test_standalone",
                "error": str(e),
            })
            sys.exit(1)

    # Trigger check
    if args.force:
        should_backup = True
        triggers = ["force"]
    else:
        should_backup, triggers = check_triggers(args.expected_chunks)

    print(f"Triggers fired: {triggers}")
    if not should_backup:
        print("No backup needed.")
        sys.exit(0)

    if args.dry_run:
        print("[DRY RUN] Would run backup now. Exiting.")
        sys.exit(0)

    # Run backup
    success, backup_dir, manifest = perform_backup(dry_run=False, skip_cleanup=args.skip_cleanup)
    if not success:
        append_log({"timestamp": utc_now_iso(), "result": "failed", "stage": "perform_backup"})
        sys.exit(1)

    # Validate
    ok, failures = validate_backup(backup_dir, manifest)
    if not ok:
        failed_dir = backup_dir.with_name(backup_dir.name + "_FAILED")
        backup_dir.rename(failed_dir)
        print(f"VALIDATION FAILED. Renamed to {failed_dir.name}")
        for f in failures:
            print(f"  - {f}")
        append_log({
            "timestamp": utc_now_iso(),
            "result": "failed",
            "stage": "validate",
            "failures": failures,
            "backup_path": str(failed_dir),
        })
        sys.exit(1)

    print("Validation: OK")

    # Trigger 6 — restore test (post-creation verification)
    rt = None
    if not args.skip_restore_test:
        try:
            rt = restore_test(backup_dir)
            print(f"Restore test: PASS ({rt['duration_seconds']:.1f}s)")
            print(f"restore_test elapsed: {rt['duration_seconds']:.1f}s")
        except RestoreTestFailedError as e:
            print()
            print(f"TRIGGER 6 RESTORE TEST FAILED for {backup_dir.name}:")
            print(str(e))
            print(f"Backup directory NOT renamed or rotated. Inspect manually:")
            print(f"  {backup_dir}")
            append_log({
                "timestamp": utc_now_iso(),
                "result": "failed",
                "stage": "restore_test",
                "backup_path": str(backup_dir),
                "error": str(e),
            })
            sys.exit(1)
    else:
        print("Restore test: SKIPPED (--skip-restore-test)")

    # Rotate
    rot_ok, pruned = rotate_backups()
    if pruned:
        print(f"Rotation: pruned {len(pruned)} old backups")

    append_log({
        "timestamp": utc_now_iso(),
        "result": "success",
        "backup_path": str(backup_dir),
        "duration_seconds": manifest["duration_seconds"],
        "total_size_bytes": manifest["total_size_bytes"],
        "total_chunk_count": manifest["total_chunk_count"],
        "triggers": triggers,
        "rotation_pruned": len(pruned),
        "restore_test_elapsed_seconds": (rt or {}).get("duration_seconds"),
    })

    print()
    print(f"Backup complete: {backup_dir.name}")
    print(f"Total chunks: {manifest['total_chunk_count']:,}")
    print(f"Duration: {manifest['duration_seconds']:.1f}s")
    sys.exit(0)


if __name__ == "__main__":
    main()
