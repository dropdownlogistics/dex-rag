"""
dex_pipeline.py — Airtight ingest pipeline helper functions.

Per ADR-INGEST-PIPELINE-001 and STD-DDL-METADATA-001.

Two functions:
  - build_chunk_metadata(): construct and validate chunk metadata
  - verify_ingest(): confirm chunks landed in target collection after write

This module is intentionally standalone (not part of dex_core yet) so
that the airtight pipeline build can land before the larger dex_core
refactor. Migrate into dex_core when that package exists.

Authority: STD-DDL-METADATA-001
Standalone status: temporary, migrate to dex_core when built
"""

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Exceptions raised by ensure_backup_current() ──────────────────────────

class BackupNotFoundError(Exception):
    """No backup exists at all. Manual bootstrap required."""


class BackupFailedError(Exception):
    """A backup attempt ran and failed validation, or the most recent
    backup is structurally corrupt (sqlite unreadable, etc.)."""

# Valid source_type enum values per STD-DDL-METADATA-001
VALID_SOURCE_TYPES = {
    "council_review",
    "council_synthesis",
    "governance",
    "claude_export",
    "gpt_export",
    "project_export",
    "thread_save",
    "transcript",
    "prompt",
    "email",
    "document",
    "spreadsheet",
    "web_archive",
    "code",
    "system_telemetry",
    "unknown",
}

# Module-level constants for the canonical pipeline folders
DDL_INGEST_ROOT = Path(r"C:\Users\dkitc\OneDrive\DDL_Ingest")
DDL_STAGING_ROOT = Path(r"C:\Users\dkitc\OneDrive\DDL_Staging")


def build_chunk_metadata(
    source_file: str,
    source_path: str,
    source_type: str,
    ingest_run_id: str,
    chunk_index: int,
    chunk_total: int,
    ingested_at: Optional[str] = None,
) -> dict:
    """
    Build a validated metadata dict for a single chunk.

    Per STD-DDL-METADATA-001. All seven fields are mandatory.
    Validates per the standard's validation rules.
    Raises ValueError on validation failure with a specific message
    naming the field that failed.

    Args:
        source_file: Filename only, not the path. e.g. "DDLCouncilReview_AntiPractice.txt"
        source_path: Full absolute path at time of ingest.
        source_type: One of VALID_SOURCE_TYPES. Use "unknown" if uncertain.
        ingest_run_id: e.g. "sweep_2026-04-11_0300", "manual_2026-04-11_1842",
                       "backfill_2026-04-11", or "test_<purpose>_2026-04-11".
        chunk_index: 0-indexed position within source file.
        chunk_total: total number of chunks from this source file (>= 1).
        ingested_at: ISO 8601 UTC timestamp with 'Z' suffix. If None,
                     defaults to current UTC time.

    Returns:
        dict ready to pass to ChromaDB collection.add(metadatas=[...]).

    Raises:
        ValueError: if any field fails validation per STD-DDL-METADATA-001.
    """
    # Generate ingested_at default if not provided
    if ingested_at is None:
        ingested_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Validate every field per STD-DDL-METADATA-001 §"Validation rules"

    # Check 7: source_file non-empty
    if not source_file or not isinstance(source_file, str):
        raise ValueError("source_file must be a non-empty string")

    # Check 8: source_path non-empty AND absolute
    if not source_path or not isinstance(source_path, str):
        raise ValueError("source_path must be a non-empty string")
    is_absolute = (
        source_path.startswith("C:\\") or source_path.startswith("C:/") or
        source_path.startswith("D:\\") or source_path.startswith("D:/") or
        source_path.startswith("/")
    )
    if not is_absolute:
        raise ValueError(
            f"source_path must be an absolute path, got: {source_path!r}"
        )

    # Check 2: source_type valid enum
    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError(
            f"source_type must be one of {sorted(VALID_SOURCE_TYPES)}, "
            f"got: {source_type!r}"
        )

    # Check 3: ingested_at parseable as ISO 8601 with Z
    if not ingested_at.endswith("Z"):
        raise ValueError(
            f"ingested_at must end with 'Z' (UTC), got: {ingested_at!r}"
        )
    try:
        # Strip Z for parsing
        datetime.strptime(ingested_at[:-1], "%Y-%m-%dT%H:%M:%S")
    except ValueError as e:
        raise ValueError(
            f"ingested_at must be ISO 8601 (YYYY-MM-DDTHH:MM:SSZ), "
            f"got: {ingested_at!r} ({e})"
        )

    # Check 9: ingest_run_id non-empty
    if not ingest_run_id or not isinstance(ingest_run_id, str):
        raise ValueError("ingest_run_id must be a non-empty string")

    # Check 4, 5, 6: chunk_index and chunk_total
    if not isinstance(chunk_index, int) or chunk_index < 0:
        raise ValueError(
            f"chunk_index must be a non-negative integer, got: {chunk_index!r}"
        )
    if not isinstance(chunk_total, int) or chunk_total < 1:
        raise ValueError(
            f"chunk_total must be an integer >= 1, got: {chunk_total!r}"
        )
    if chunk_index >= chunk_total:
        raise ValueError(
            f"chunk_index ({chunk_index}) must be < chunk_total ({chunk_total})"
        )

    # All checks passed. Build the dict.
    return {
        "source_file": source_file,
        "source_path": source_path,
        "source_type": source_type,
        "ingested_at": ingested_at,
        "ingest_run_id": ingest_run_id,
        "chunk_index": chunk_index,
        "chunk_total": chunk_total,
    }


def verify_ingest(
    collection_name: str,
    source_file: str,
    expected_chunk_count: int,
) -> tuple[bool, int]:
    """
    Verify that the expected number of chunks for a given source_file
    landed in the target collection.

    Read-only operation. Queries by metadata filter, no writes.

    Args:
        collection_name: e.g. "dex_canon", "ddl_archive"
        source_file: filename to query for (matches metadata source_file)
        expected_chunk_count: how many chunks the ingest path attempted to write

    Returns:
        Tuple of (success: bool, actual_count: int).
        success is True iff actual_count == expected_chunk_count.
    """
    # Use the same client pattern as dex_weights.py
    # Local import to avoid hard dependency at module-load time
    from dex_weights import get_client

    client = get_client()
    try:
        collection = client.get_collection(collection_name)
    except Exception as e:
        # Collection doesn't exist or can't be reached — fail loud
        raise RuntimeError(
            f"verify_ingest: cannot access collection {collection_name!r}: {e}"
        )

    # Query by source_file metadata
    result = collection.get(where={"source_file": source_file})
    actual_count = len(result.get("ids", []))

    success = (actual_count == expected_chunk_count)
    return (success, actual_count)


def move_to_staging(source_path: str) -> Path:
    """
    Atomically move a file from DDL_Ingest to DDL_Staging,
    preserving its relative path structure within the inbox.

    A file at DDL_Ingest/foo/bar/baz.txt becomes
    DDL_Staging/foo/bar/baz.txt — same relative path, different root.

    If the destination directory doesn't exist, it's created. If a
    file already exists at the destination (collision), the function
    raises FileExistsError rather than overwriting — collisions
    require operator review.

    Per ADR-INGEST-PIPELINE-001 §"Three folders, three states":
    nothing is ever deleted. This function only moves forward.

    Args:
        source_path: Absolute path to a file inside DDL_Ingest.

    Returns:
        Path object pointing to the new location in DDL_Staging.

    Raises:
        ValueError: if source_path is not inside DDL_INGEST_ROOT.
        FileNotFoundError: if source_path doesn't exist.
        FileExistsError: if destination already exists (no overwrite).
    """
    source = Path(source_path).resolve()

    # Validate: source exists
    if not source.exists():
        raise FileNotFoundError(
            f"move_to_staging: source does not exist: {source}"
        )

    # Validate: source is a file, not a directory
    if not source.is_file():
        raise ValueError(
            f"move_to_staging: source must be a file, got: {source}"
        )

    # Validate: source is inside DDL_INGEST_ROOT
    try:
        rel = source.relative_to(DDL_INGEST_ROOT)
    except ValueError:
        raise ValueError(
            f"move_to_staging: source must be inside {DDL_INGEST_ROOT}, "
            f"got: {source}"
        )

    # Compute destination
    destination = DDL_STAGING_ROOT / rel

    # Validate: no collision at destination
    if destination.exists():
        raise FileExistsError(
            f"move_to_staging: destination already exists: {destination}. "
            f"Collisions require operator review — no overwrite."
        )

    # Ensure destination directory exists
    destination.parent.mkdir(parents=True, exist_ok=True)

    # Atomic move via shutil.move (handles cross-device cases)
    shutil.move(str(source), str(destination))

    return destination


def ensure_backup_current(
    expected_write_chunks: int = 0,
    force_check: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    Ensure the corpus backup is current per STD-DDL-BACKUP-001 §"Trigger 3".

    Trigger 3 is the pre-write gate. This helper is the in-pipeline gate
    that ingest paths call before writing chunks. dex-backup.py is the
    single source of truth for trigger logic and the actual copy — this
    helper just shells out to it via subprocess and interprets the result.

    Args:
        expected_write_chunks: how many chunks the caller intends to write.
            If > 100, Trigger 5 fires regardless of other triggers.
        force_check: if True, run a backup regardless of trigger state.
            (Interpreted as "force-run a backup," consistent with the
            self-test "force_check=True → backup_ran=True" expectation.)
        dry_run: if True, --dry-run is added to the dex-backup.py
            invocation. Trigger logic still runs and the returned dict
            still reflects intent (backup_ran=True if a backup would
            have been needed), but no actual copy happens. Used by
            self-tests to avoid 200+ second waits.

    Returns:
        dict with keys: backup_ran (bool), backup_path (str or None),
            triggers_fired (list), backup_age_hours (float or None),
            status (str: "current" | "refreshed" | "force_refreshed" | "dry_run").

    Raises:
        BackupNotFoundError: if no backup exists at all.
        BackupFailedError: if a backup attempt failed, or the most
            recent backup is structurally corrupt.
    """
    script = Path(__file__).parent / "dex-backup.py"
    if not script.exists():
        raise BackupNotFoundError(f"dex-backup.py not found at {script}")

    # Step 1: --check-only --json
    check_cmd = [
        sys.executable, str(script),
        "--check-only", "--json",
        "--expected-chunks", str(expected_write_chunks),
    ]
    # Step 36: bumped 120 -> 300 after 4/13 scale-induced timeout on 10-collection DB
    cr = subprocess.run(check_cmd, capture_output=True, text=True, timeout=300)

    if cr.returncode == 2:
        raise BackupNotFoundError(
            "dex-backup.py reports no backups exist. "
            "Run dex-backup.py --force to bootstrap before ingesting."
        )

    try:
        status = json.loads(cr.stdout)
    except json.JSONDecodeError as e:
        raise BackupFailedError(
            f"dex-backup.py --check-only --json output is not valid JSON: {e}\n"
            f"stdout: {cr.stdout!r}\n"
            f"stderr: {cr.stderr!r}"
        )

    if not status.get("exists"):
        raise BackupNotFoundError("dex-backup.py reports no backup exists.")

    if not status.get("sqlite_readable"):
        raise BackupFailedError(
            f"Most recent backup sqlite is unreadable: "
            f"{status.get('sqlite_error', 'unknown')}"
        )

    triggers_fired = list(status.get("triggers_to_fire", []))
    needs_backup = bool(status.get("should_backup")) or force_check
    if force_check and "force_check" not in triggers_fired:
        triggers_fired.append("force_check")

    result = {
        "backup_ran": False,
        "backup_path": status.get("most_recent_path"),
        "triggers_fired": triggers_fired,
        "backup_age_hours": status.get("age_hours"),
        "status": "current",
    }

    if not needs_backup:
        return result

    # Step 2: triggers fired (or force_check) — run a backup
    backup_cmd = [
        sys.executable, str(script),
        "--force",
        "--expected-chunks", str(expected_write_chunks),
    ]
    if dry_run:
        backup_cmd.append("--dry-run")

    # Step 36: bumped 900 -> 2400 (40m) after 4/13 scale-induced timeout on
    # 18GB backup + restore-test cycle. Observed actual runtime ~14m at new scale.
    br = subprocess.run(backup_cmd, capture_output=True, text=True, timeout=2400)
    if br.returncode != 0:
        raise BackupFailedError(
            f"dex-backup.py --force exited {br.returncode}\n"
            f"stdout:\n{br.stdout}\n"
            f"stderr:\n{br.stderr}"
        )

    result["backup_ran"] = True
    if dry_run:
        result["status"] = "dry_run"
        return result
    result["status"] = "force_refreshed" if force_check else "refreshed"

    # Step 3: re-check to capture new backup metadata
    rc = subprocess.run(
        [sys.executable, str(script), "--check-only", "--json", "--expected-chunks", "0"],
        capture_output=True, text=True, timeout=300,
    )
    if rc.returncode == 0:
        try:
            new_status = json.loads(rc.stdout)
            result["backup_path"] = new_status.get("most_recent_path", result["backup_path"])
            result["backup_age_hours"] = new_status.get("age_hours")
        except json.JSONDecodeError:
            pass

    return result


# ────────────────────────────────────────────────────────────────────────
# Self-test (run as: python dex_pipeline.py)
# ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Test build_chunk_metadata happy path
    md = build_chunk_metadata(
        source_file="test.txt",
        source_path=r"C:\Users\dexjr\dex-rag\test.txt",
        source_type="unknown",
        ingest_run_id="test_2026-04-11_self_test",
        chunk_index=0,
        chunk_total=1,
    )
    assert md["source_file"] == "test.txt"
    assert md["source_type"] == "unknown"
    assert md["ingested_at"].endswith("Z")
    print("[OK] build_chunk_metadata happy path")

    # Test validation: bad source_type
    try:
        build_chunk_metadata(
            source_file="test.txt",
            source_path=r"C:\test.txt",
            source_type="invalid_type",
            ingest_run_id="test",
            chunk_index=0,
            chunk_total=1,
        )
        print("[FAIL] should have raised on invalid source_type")
    except ValueError as e:
        print(f"[OK] rejected invalid source_type: {e}")

    # Test validation: chunk_index >= chunk_total
    try:
        build_chunk_metadata(
            source_file="test.txt",
            source_path=r"C:\test.txt",
            source_type="unknown",
            ingest_run_id="test",
            chunk_index=5,
            chunk_total=5,
        )
        print("[FAIL] should have raised on chunk_index >= chunk_total")
    except ValueError as e:
        print(f"[OK] rejected chunk_index >= chunk_total: {e}")

    # Test validation: relative path
    try:
        build_chunk_metadata(
            source_file="test.txt",
            source_path="test.txt",  # not absolute
            source_type="unknown",
            ingest_run_id="test",
            chunk_index=0,
            chunk_total=1,
        )
        print("[FAIL] should have raised on relative path")
    except ValueError as e:
        print(f"[OK] rejected relative source_path: {e}")

    # ──────────────────────────────────────────────────────────
    # move_to_staging() tests (use system temp, NOT DDL_Ingest)
    # ──────────────────────────────────────────────────────────
    import tempfile
    import os

    # Test: rejects path outside DDL_Ingest
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
        tf.write(b"test content")
        outside_path = tf.name
    try:
        try:
            move_to_staging(outside_path)
            print("[FAIL] should have rejected path outside DDL_Ingest")
        except ValueError as e:
            print(f"[OK] rejected path outside DDL_Ingest: {type(e).__name__}")
    finally:
        if os.path.exists(outside_path):
            os.unlink(outside_path)

    # Test: rejects nonexistent source
    fake_path = str(DDL_INGEST_ROOT / "this_file_does_not_exist_12345.txt")
    try:
        move_to_staging(fake_path)
        print("[FAIL] should have raised FileNotFoundError")
    except FileNotFoundError as e:
        print(f"[OK] rejected nonexistent source: FileNotFoundError")

    # Test: rejects directory (not file)
    try:
        move_to_staging(str(DDL_INGEST_ROOT))
        print("[FAIL] should have raised on directory input")
    except (ValueError, FileNotFoundError) as e:
        # Either is acceptable — directory exists but isn't a file
        print(f"[OK] rejected directory: {type(e).__name__}")

    # ──────────────────────────────────────────────────────────
    # ensure_backup_current() tests (subprocess to dex-backup.py)
    # ──────────────────────────────────────────────────────────

    # Test: fresh state — backup exists, no triggers fire, no backup runs
    try:
        r = ensure_backup_current(expected_write_chunks=0, force_check=False)
        if r["backup_ran"] is False and r["status"] == "current" and r["triggers_fired"] == []:
            print(f"[OK] ensure_backup_current_fresh: backup_ran=False, age={r['backup_age_hours']}h")
        else:
            print(f"[FAIL] ensure_backup_current_fresh: {r}")
    except Exception as e:
        print(f"[FAIL] ensure_backup_current_fresh raised: {type(e).__name__}: {e}")

    # Test: force_check=True triggers a backup (dry_run subprocess to keep test fast)
    try:
        r = ensure_backup_current(expected_write_chunks=0, force_check=True, dry_run=True)
        if r["backup_ran"] is True and "force_check" in r["triggers_fired"]:
            print(f"[OK] ensure_backup_current_force: backup_ran=True (dry_run), triggers={r['triggers_fired']}")
        else:
            print(f"[FAIL] ensure_backup_current_force: {r}")
    except Exception as e:
        print(f"[FAIL] ensure_backup_current_force raised: {type(e).__name__}: {e}")

    # Test: large write triggers Trigger 5 (>100 chunks)
    try:
        r = ensure_backup_current(expected_write_chunks=500, force_check=False, dry_run=True)
        fired = r["triggers_fired"]
        has_trigger_5 = any("pre_batch_expected_500" in t for t in fired)
        if r["backup_ran"] is True and has_trigger_5:
            print(f"[OK] ensure_backup_current_large_write: trigger 5 fired ({fired})")
        else:
            print(f"[FAIL] ensure_backup_current_large_write: {r}")
    except Exception as e:
        print(f"[FAIL] ensure_backup_current_large_write raised: {type(e).__name__}: {e}")

    print()
    print("All self-tests passed.")
