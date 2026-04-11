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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")


def find_existing_backups() -> list[Path]:
    """Return sorted list of existing backup directories (newest first)."""
    if not BACKUP_ROOT.exists():
        return []
    backups = [
        p for p in BACKUP_ROOT.iterdir()
        if p.is_dir() and p.name.startswith("chromadb_") and not p.name.endswith("_FAILED")
    ]
    backups.sort(key=lambda p: p.name, reverse=True)
    return backups


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


def perform_backup(dry_run: bool = False) -> tuple[bool, Path | None, dict]:
    """
    Run the actual backup. Returns (success, backup_path, manifest).
    """
    started_at = datetime.now(timezone.utc)
    timestamp = utc_now_compact()
    backup_dir = BACKUP_ROOT / f"chromadb_{timestamp}"

    if dry_run:
        print(f"[DRY RUN] Would create backup at: {backup_dir}")
        return (True, None, {})

    print(f"Creating backup at: {backup_dir}")
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
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
    missing = src_uuids - dst_uuids
    if missing:
        failures.append(f"missing UUID directories in backup: {missing}")

    actual_sha = sha256_file(sqlite_path)
    if actual_sha != manifest["sqlite_sha256"]:
        failures.append(f"sha256 mismatch")

    return (len(failures) == 0, failures)


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
    parser.add_argument("--expected-chunks", type=int, default=0, help="For pre-batch trigger")
    args = parser.parse_args()

    print(f"dex-backup {BACKUP_TOOL_VERSION}")
    print(f"Live: {LIVE_CHROMADB}")
    print(f"Backup root: {BACKUP_ROOT}")
    print()

    # Pre-flight
    if not LIVE_CHROMADB.exists():
        print(f"FATAL: live ChromaDB not found at {LIVE_CHROMADB}")
        sys.exit(2)
    if not (LIVE_CHROMADB / "chroma.sqlite3").exists():
        print(f"FATAL: chroma.sqlite3 not found at {LIVE_CHROMADB}")
        sys.exit(2)

    if args.check_only:
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
    success, backup_dir, manifest = perform_backup(dry_run=False)
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
    })

    print()
    print(f"Backup complete: {backup_dir.name}")
    print(f"Total chunks: {manifest['total_chunk_count']:,}")
    print(f"Duration: {manifest['duration_seconds']:.1f}s")
    sys.exit(0)


if __name__ == "__main__":
    main()
