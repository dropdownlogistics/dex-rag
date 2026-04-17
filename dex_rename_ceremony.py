"""
dex_rename_ceremony.py — _v2 suffix retirement ceremony.

Removes the _v2 suffix from all collection names.
Pre-ceremony: validates, backs up, presents dry-run.
Ceremony: renames collections, updates dex_core.py, clears caches.

Usage:
  python dex_rename_ceremony.py --dry-run     # preview
  python dex_rename_ceremony.py --execute     # do it (requires --execute flag)

Safety:
  - REQUIRES --execute flag — no accidental runs
  - Full backup must exist within 24 hours
  - Health check must pass before starting
  - Each collection rename is atomic (copy -> verify -> delete)
  - If any step fails, stops and reports what completed

Step 63.3 | Authority: CR-DDL-SOAK-RENAME-001
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

from dex_core import (
    CHROMA_DIR, COLLECTIONS, COLLECTION_SUFFIX, CHUNK_FLOORS,
    INGEST_CACHE_DIR, SCRIPT_DIR, suffixed,
)

LOG_PATH = os.path.join(SCRIPT_DIR, "dex-rename-ceremony-log.jsonl")
BATCH_SIZE = 5000


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_log(entry: dict) -> None:
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_health_check() -> bool:
    """Run dex health --json and check for failures."""
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, "dex_health.py"), "--json"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            print(f"  FAIL: health check returned exit code {result.returncode}")
            return False

        data = json.loads(result.stdout)
        fail_count = data.get("fail_count", 0)
        if fail_count > 0:
            print(f"  FAIL: health check has {fail_count} failure(s)")
            for check in data.get("checks", []):
                if check.get("status") == "FAIL":
                    print(f"    - {check['name']}: {check.get('detail', '')}")
            return False

        print(f"  PASS: health check ({data.get('pass_count', 0)}/{data.get('total', 0)})")
        return True
    except Exception as e:
        print(f"  FAIL: could not run health check: {e}")
        return False


def check_backup_currency() -> bool:
    """Check that a backup exists and is less than 24 hours old."""
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, "dex-backup.py"),
             "--check-only", "--json"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            print(f"  FAIL: backup check returned exit code {result.returncode}")
            return False

        data = json.loads(result.stdout)
        if not data.get("exists"):
            print("  FAIL: no backup exists")
            return False

        age_hours = data.get("age_hours")
        if age_hours is None or age_hours > 24:
            print(f"  FAIL: most recent backup is {age_hours:.1f} hours old (max 24)")
            return False

        print(f"  PASS: backup is {age_hours:.1f} hours old ({data.get('most_recent', '')})")
        return True
    except Exception as e:
        print(f"  FAIL: could not check backup: {e}")
        return False


def check_collection_floors() -> bool:
    """Verify all live collections are above their chunk floors."""
    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    all_ok = True

    for base_name, floor in CHUNK_FLOORS.items():
        coll_name = suffixed(base_name)
        try:
            col = client.get_collection(coll_name)
            count = col.count()
            if count < floor:
                print(f"  FAIL: {coll_name} has {count:,} chunks (floor: {floor:,})")
                all_ok = False
            else:
                print(f"  PASS: {coll_name} = {count:,} chunks (floor: {floor:,})")
        except Exception as e:
            print(f"  FAIL: {coll_name} not found: {e}")
            all_ok = False

    return all_ok


def rename_collection(client, old_name: str, new_name: str) -> dict:
    """
    Rename a collection by copying all data to a new name, then deleting the old.

    Returns a result dict with status and details.
    """
    result = {
        "old_name": old_name,
        "new_name": new_name,
        "status": "unknown",
        "chunks_copied": 0,
    }

    try:
        old_col = client.get_collection(old_name)
    except Exception as e:
        result["status"] = "FAIL"
        result["detail"] = f"source collection not found: {e}"
        return result

    old_count = old_col.count()
    result["source_count"] = old_count

    # Check if target already exists
    try:
        client.get_collection(new_name)
        result["status"] = "FAIL"
        result["detail"] = f"target collection '{new_name}' already exists"
        return result
    except Exception:
        pass  # Expected — target should not exist yet

    # Create new collection (inherit metadata from old)
    try:
        new_col = client.create_collection(
            name=new_name,
            metadata=old_col.metadata,
        )
    except Exception as e:
        result["status"] = "FAIL"
        result["detail"] = f"could not create target collection: {e}"
        return result

    # Copy data in batches
    offset = 0
    total_copied = 0

    while offset < old_count:
        try:
            batch = old_col.get(
                include=["documents", "metadatas", "embeddings"],
                limit=BATCH_SIZE,
                offset=offset,
            )
        except Exception as e:
            result["status"] = "FAIL"
            result["detail"] = f"read failed at offset {offset}: {e}"
            result["chunks_copied"] = total_copied
            # Clean up partial target
            try:
                client.delete_collection(new_name)
            except Exception:
                pass
            return result

        ids = batch.get("ids", [])
        if not ids:
            break

        docs = batch.get("documents", [])
        metas = batch.get("metadatas", [])
        embeds = batch.get("embeddings", [])

        try:
            new_col.add(
                ids=ids,
                documents=docs,
                metadatas=metas,
                embeddings=embeds,
            )
            total_copied += len(ids)
        except Exception as e:
            result["status"] = "FAIL"
            result["detail"] = f"write failed at offset {offset}: {e}"
            result["chunks_copied"] = total_copied
            try:
                client.delete_collection(new_name)
            except Exception:
                pass
            return result

        offset += len(ids)
        print(f"    copied {total_copied:,} / {old_count:,} chunks", end="\r")

    print()  # newline after progress

    # Verify counts match
    new_count = new_col.count()
    if new_count != old_count:
        result["status"] = "FAIL"
        result["detail"] = (
            f"count mismatch after copy: source={old_count:,}, "
            f"target={new_count:,}"
        )
        result["chunks_copied"] = total_copied
        # Do NOT delete the new collection — operator should inspect
        return result

    # Delete old collection
    try:
        client.delete_collection(old_name)
    except Exception as e:
        result["status"] = "PARTIAL"
        result["detail"] = f"copy OK but could not delete source: {e}"
        result["chunks_copied"] = total_copied
        result["target_count"] = new_count
        return result

    result["status"] = "OK"
    result["detail"] = f"{new_count:,} chunks migrated"
    result["chunks_copied"] = total_copied
    result["target_count"] = new_count
    return result


def clear_ingest_cache() -> int:
    """
    Clear ingest cache files (they reference _v2 collection names).
    Returns number of files removed.
    """
    if not os.path.isdir(INGEST_CACHE_DIR):
        return 0

    removed = 0
    for f in os.listdir(INGEST_CACHE_DIR):
        if f.endswith(".json"):
            try:
                os.remove(os.path.join(INGEST_CACHE_DIR, f))
                removed += 1
            except Exception:
                pass
    return removed


def update_dex_core_suffix() -> bool:
    """
    Update COLLECTION_SUFFIX default in dex_core.py from '_v2' to ''.
    """
    core_path = os.path.join(SCRIPT_DIR, "dex_core.py")
    try:
        with open(core_path, "r", encoding="utf-8") as f:
            content = f.read()

        old = 'COLLECTION_SUFFIX = os.environ.get("DEXJR_COLLECTION_SUFFIX", "_v2")'
        new = 'COLLECTION_SUFFIX = os.environ.get("DEXJR_COLLECTION_SUFFIX", "")'

        if old not in content:
            print("  WARN: expected COLLECTION_SUFFIX line not found in dex_core.py")
            return False

        content = content.replace(old, new)

        with open(core_path, "w", encoding="utf-8") as f:
            f.write(content)

        print("  Updated COLLECTION_SUFFIX in dex_core.py: '_v2' -> ''")
        return True
    except Exception as e:
        print(f"  FAIL: could not update dex_core.py: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="_v2 suffix retirement ceremony (CR-DDL-SOAK-RENAME-001)"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what will change without doing it")
    parser.add_argument("--execute", action="store_true",
                        help="Actually perform the rename (required for execution)")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("Usage:")
        print("  python dex_rename_ceremony.py --dry-run     # preview")
        print("  python dex_rename_ceremony.py --execute     # do it")
        print()
        print("The --execute flag is required to prevent accidental runs.")
        sys.exit(0)

    print()
    print("=" * 60)
    print("  _v2 SUFFIX RETIREMENT CEREMONY")
    print(f"  CR-DDL-SOAK-RENAME-001")
    print(f"  {utc_now_iso()}")
    if args.dry_run:
        print("  MODE: DRY RUN")
    else:
        print("  MODE: EXECUTE")
    print("=" * 60)
    print()

    # ── Pre-ceremony checks ─────────────────────────────────────────
    print("PRE-CEREMONY CHECKS")
    print("-" * 40)

    # 1. Health check
    print("[1/3] Health check...")
    health_ok = run_health_check()

    # 2. Backup currency
    print("[2/3] Backup currency...")
    backup_ok = check_backup_currency()

    # 3. Collection floors
    print("[3/3] Collection floors...")
    floors_ok = check_collection_floors()

    print()
    if not (health_ok and backup_ok and floors_ok):
        print("PRE-CEREMONY CHECKS FAILED. Cannot proceed.")
        failures = []
        if not health_ok:
            failures.append("health check")
        if not backup_ok:
            failures.append("backup currency")
        if not floors_ok:
            failures.append("collection floors")
        print(f"  Failed: {', '.join(failures)}")
        append_log({
            "timestamp": utc_now_iso(),
            "stage": "pre_ceremony",
            "status": "BLOCKED",
            "failures": failures,
        })
        sys.exit(1)

    print("PRE-CEREMONY CHECKS PASSED")
    print()

    # ── Build rename plan ────────────────────────────────────────────
    live_collections = {
        k: v for k, v in COLLECTIONS.items()
        if v["status"] == "LIVE"
    }

    print("RENAME PLAN")
    print("-" * 40)
    for base_name in sorted(live_collections.keys()):
        old_name = suffixed(base_name)
        new_name = base_name
        print(f"  {old_name:<25} -> {new_name}")
    print()

    if args.dry_run:
        print("DRY RUN — no changes made.")
        print("Run with --execute to perform the ceremony.")
        sys.exit(0)

    # ── Ceremony execution ───────────────────────────────────────────
    print("CEREMONY EXECUTION")
    print("-" * 40)

    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    completed = []
    failed = []

    for base_name in sorted(live_collections.keys()):
        old_name = suffixed(base_name)
        new_name = base_name

        print(f"\n  Renaming: {old_name} -> {new_name}")
        result = rename_collection(client, old_name, new_name)

        append_log({
            "timestamp": utc_now_iso(),
            "stage": "rename",
            **result,
        })

        if result["status"] == "OK":
            print(f"  [{result['status']}] {result['detail']}")
            completed.append(result)
        else:
            print(f"  [{result['status']}] {result.get('detail', 'unknown error')}")
            failed.append(result)
            print()
            print("  CEREMONY HALTED — failure during rename.")
            print(f"  Completed: {[r['old_name'] for r in completed]}")
            print(f"  Failed at: {old_name}")
            print("  Remaining collections are UNCHANGED.")
            print("  Operator review required before retry.")
            sys.exit(1)

    print()

    # ── Post-ceremony ────────────────────────────────────────────────
    print("POST-CEREMONY")
    print("-" * 40)

    # Update dex_core.py suffix
    print("[1/3] Updating COLLECTION_SUFFIX in dex_core.py...")
    suffix_ok = update_dex_core_suffix()

    # Clear ingest cache
    print("[2/3] Clearing ingest cache (stale _v2 references)...")
    cache_cleared = clear_ingest_cache()
    print(f"  Removed {cache_cleared} cache file(s)")

    # Run health check again
    print("[3/3] Post-ceremony health check...")
    # Need to reload after suffix change — run as subprocess
    post_health = run_health_check()

    print()
    print("=" * 60)
    print("  CEREMONY COMPLETE")
    print(f"  Collections renamed: {len(completed)}")
    print(f"  Suffix updated: {'YES' if suffix_ok else 'NO'}")
    print(f"  Cache cleared: {cache_cleared} files")
    print(f"  Post-health: {'PASS' if post_health else 'FAIL'}")
    print("=" * 60)

    append_log({
        "timestamp": utc_now_iso(),
        "stage": "complete",
        "collections_renamed": len(completed),
        "suffix_updated": suffix_ok,
        "cache_cleared": cache_cleared,
        "post_health_pass": post_health,
    })

    if not post_health:
        print()
        print("  WARNING: Post-ceremony health check did not pass.")
        print("  Collections were renamed successfully but downstream")
        print("  tools may need attention. Run `dex health --verbose`")
        print("  for details.")

    sys.exit(0)


if __name__ == "__main__":
    main()
