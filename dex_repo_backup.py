"""
dex_repo_backup.py — Back up all DDL repos to local storage.

Weekly mirror of all 11 repos to D:\DDL_Backup\repos\

Usage:
  python dex_repo_backup.py              # full backup
  python dex_repo_backup.py --dry-run    # show what would happen
  dex repo-backup                        # via CLI

For each repo in GIT_REPOS (dex_core.py):
  - If backup doesn't exist: git clone --mirror <origin> <backup_path>
  - If backup exists: cd <backup_path> && git remote update

Mirror clones include all branches, tags, and refs. git remote update
fetches new commits without needing a working tree.

Step 63.1 | Authority: CLAUDE.md Rule 8 (corpus integrity)
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from dex_core import GIT_REPOS, SCRIPT_DIR

REPO_BACKUP_DIR = r"D:\DDL_Backup\repos"
BACKUP_LOG = os.path.join(SCRIPT_DIR, "dex-repo-backup-log.jsonl")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_origin_url(repo_path: str) -> str | None:
    """Get the origin remote URL for a repo."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def backup_repo(name: str, source_path: str, dry_run: bool = False) -> dict:
    """
    Mirror-backup a single repo.

    Returns a result dict with status, detail, and timing.
    """
    backup_path = os.path.join(REPO_BACKUP_DIR, f"{name}.git")
    result = {
        "repo": name,
        "source": source_path,
        "backup_path": backup_path,
        "status": "unknown",
        "detail": "",
    }

    # Check source exists
    if not os.path.isdir(source_path):
        result["status"] = "SKIP"
        result["detail"] = f"source not found: {source_path}"
        return result

    # Get origin URL
    origin_url = get_origin_url(source_path)
    if not origin_url:
        result["status"] = "SKIP"
        result["detail"] = "no origin remote configured"
        return result

    result["origin"] = origin_url

    if os.path.isdir(backup_path):
        # Existing mirror — fetch updates
        action = "update"
        if dry_run:
            result["status"] = "DRY_RUN"
            result["detail"] = f"would run: git -C {backup_path} remote update"
            return result

        try:
            proc = subprocess.run(
                ["git", "-C", backup_path, "remote", "update"],
                capture_output=True, text=True, timeout=120,
            )
            if proc.returncode == 0:
                result["status"] = "OK"
                result["detail"] = "remote update complete"
            else:
                result["status"] = "FAIL"
                result["detail"] = f"remote update failed: {proc.stderr.strip()[:200]}"
        except subprocess.TimeoutExpired:
            result["status"] = "FAIL"
            result["detail"] = "remote update timed out (120s)"
        except Exception as e:
            result["status"] = "FAIL"
            result["detail"] = f"remote update error: {e}"
    else:
        # New mirror — clone
        action = "clone"
        if dry_run:
            result["status"] = "DRY_RUN"
            result["detail"] = f"would run: git clone --mirror {origin_url} {backup_path}"
            return result

        try:
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            proc = subprocess.run(
                ["git", "clone", "--mirror", origin_url, backup_path],
                capture_output=True, text=True, timeout=300,
            )
            if proc.returncode == 0:
                result["status"] = "OK"
                result["detail"] = "mirror clone complete"
            else:
                result["status"] = "FAIL"
                result["detail"] = f"clone failed: {proc.stderr.strip()[:200]}"
        except subprocess.TimeoutExpired:
            result["status"] = "FAIL"
            result["detail"] = "clone timed out (300s)"
        except Exception as e:
            result["status"] = "FAIL"
            result["detail"] = f"clone error: {e}"

    result["action"] = action
    return result


def append_log(entry: dict) -> None:
    with open(BACKUP_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Mirror backup of all DDL repos to D:\\DDL_Backup\\repos"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without doing it")
    args = parser.parse_args()

    print(f"dex-repo-backup")
    print(f"  Source: {len(GIT_REPOS)} repos from dex_core.GIT_REPOS")
    print(f"  Target: {REPO_BACKUP_DIR}")
    if args.dry_run:
        print(f"  Mode: DRY RUN")
    print()

    if not args.dry_run:
        os.makedirs(REPO_BACKUP_DIR, exist_ok=True)

    results = []
    ok_count = 0
    fail_count = 0
    skip_count = 0

    for name, source_path in sorted(GIT_REPOS.items()):
        r = backup_repo(name, source_path, dry_run=args.dry_run)
        results.append(r)

        tag = r["status"]
        print(f"  [{tag:<8}] {name:<20} {r['detail']}")

        if tag == "OK":
            ok_count += 1
        elif tag == "FAIL":
            fail_count += 1
        else:
            skip_count += 1

    print()
    print(f"  Done: {ok_count} OK, {fail_count} FAIL, {skip_count} SKIP/DRY_RUN")

    # Log the run
    log_entry = {
        "timestamp": utc_now_iso(),
        "dry_run": args.dry_run,
        "repos_total": len(GIT_REPOS),
        "ok": ok_count,
        "fail": fail_count,
        "skip": skip_count,
        "results": results,
    }
    if not args.dry_run:
        append_log(log_entry)

    sys.exit(1 if fail_count > 0 else 0)


if __name__ == "__main__":
    main()
