"""
DEX JR AUTO-SWEEP — v1.0
Watches a drop folder for new files, copies to corpus, triggers ingestion.

Usage:
  python dex-sweep.py                    # Run once (check and ingest)
  python dex-sweep.py --watch            # Watch continuously (check every N minutes)
  python dex-sweep.py --interval 30      # Check every 30 minutes
  python dex-sweep.py --dry-run          # Show what would happen without doing it

Drop folder: Where you save files for ingestion (OneDrive, Downloads, etc.)
Canon folder: Where ingested files live in the corpus
Archive folder: Where processed files are moved after ingestion

The script:
  1. Scans the drop folder for new .txt files
  2. Copies them to the canon corpus folder
  3. Moves originals to a "processed" subfolder (not deleted)
  4. Triggers canon ingestion
  5. Logs everything

Dropdown Logistics — Chaos -> Structured -> Automated
Auto-Sweep v1.0 | 2026-03-06
"""

import os
import sys
import json
import time
import shutil
import datetime
import subprocess
import argparse

# Make dex_pipeline importable regardless of cwd (sweep is often run unattended)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dex_pipeline import (
    ensure_backup_current,
    BackupNotFoundError,
    BackupFailedError,
)

# -----------------------------
# CONFIG — EDIT THESE PATHS
# -----------------------------

# Where you drop files for ingestion (OneDrive, Downloads, etc.)
# Add multiple folders if you want to watch several locations
DROP_FOLDERS = [
    r"C:\Users\dkitc\OneDrive\DexJr",                    # OneDrive drop folder
    r"C:\Users\dkitc\OneDrive\DDL_Ingest",                # Alternative drop folder
    r"C:\Users\dkitc\Downloads\DDL_Ingest",               # Local downloads drop
r"C:\Users\dkitc\iCloudDrive\Documents\04_DDL_Ingest",                   # iOS drop folder

]

# Where files go in the corpus
CANON_DIR = r"C:\Users\dexjr\99_DexUniverseArchive\00_Archive\DDL-Standards-Canon"

# Where processed files are moved (so you know what's been ingested)
PROCESSED_DIR = None  # Each drop folder gets its own _processed subfolder

# Ingest script location
INGEST_SCRIPT = r"C:\Users\dexjr\dex-rag\dex-ingest.py"

# File types to ingest
INGEST_EXTENSIONS = {
    ".txt", ".md", ".html", ".jsx", ".json",
    ".py", ".cs", ".js", ".mjs", ".ts", ".tsx",
    ".css", ".sql", ".sh", ".bat", ".ps1", ".bas",
    ".csv", ".yml", ".yaml", ".toml",
    ".ipynb", ".prisma",
}

# Log file
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "dex-sweep-log.jsonl")

# Default watch interval (minutes)
DEFAULT_INTERVAL = 60

# Any value >100 fires Trigger 5 in ensure_backup_current per STD-DDL-BACKUP-001.
# Sweep is a bulk operation — one backup per sweep run, not N per dex-ingest call.
# Matches dex-ingest.py BULK_CHUNK_ESTIMATE.
SWEEP_CHUNK_ESTIMATE = 10_000

# -----------------------------
# SWEEP
# -----------------------------
def scan_drop_folders():
    """Find all ingestible files across all drop folders."""
    found = []
    for folder in DROP_FOLDERS:
        if not os.path.exists(folder):
            # Rule 15 fix: surface missing drop folders instead of silent skip.
            print(f"  WARN: drop folder not found (skipping): {folder}")
            continue
        for filename in os.listdir(folder):
            filepath = os.path.join(folder, filename)
            if os.path.isfile(filepath):
                ext = os.path.splitext(filename)[1].lower()
                if ext in INGEST_EXTENSIONS:
                    found.append({
                        "source": filepath,
                        "filename": filename,
                        "folder": folder,
                        "size": os.path.getsize(filepath),
                    })
    return found

def copy_to_corpus(files, dry_run=False):
    """Copy files to canon folder, move originals to processed."""
    os.makedirs(CANON_DIR, exist_ok=True)

    copied = []
    for f in files:
        dest = os.path.join(CANON_DIR, f["filename"])
        processed_dir = os.path.join(f["folder"], "_processed")
        os.makedirs(processed_dir, exist_ok=True)
        processed = os.path.join(processed_dir, f["filename"])

        # Handle filename conflicts
        if os.path.exists(dest):
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            name, ext = os.path.splitext(f["filename"])
            f["filename"] = f"{name}_{ts}{ext}"
            dest = os.path.join(CANON_DIR, f["filename"])

        if dry_run:
            print(f"  [DRY RUN] Would copy: {f['source']}")
            print(f"            -> {dest}")
            copied.append(f)
        else:
            try:
                shutil.copy2(f["source"], dest)
                shutil.move(f["source"], processed)
                copied.append(f)
                print(f"  Copied: {f['filename']} ({f['size']:,} bytes)")
            except Exception as e:
                print(f"  ERROR copying {f['filename']}: {e}")

    return copied

def run_ingestion(dry_run=False):
    """
    Trigger canon ingestion via subprocess to dex-ingest.py.

    Passes --skip-backup-check so dex-ingest.py does not redundantly
    fire Trigger 5; sweep() has already gated upstream via
    ensure_backup_current() earlier in the sweep cycle.

    Returns: (ok: bool, stderr_on_failure: str | None)
    """
    cmd_args = ["python", INGEST_SCRIPT, "--path", CANON_DIR,
                "--build-canon", "--fast", "--skip-backup-check"]

    if dry_run:
        print(f"  [DRY RUN] Would run: {' '.join(cmd_args)}")
        return (True, None)

    if not os.path.exists(INGEST_SCRIPT):
        msg = f"Ingest script not found: {INGEST_SCRIPT}"
        print(f"  ERROR: {msg}")
        return (False, msg)

    try:
        print(f"  Running ingestion...")
        result = subprocess.run(
            cmd_args,
            capture_output=True, text=True, timeout=600
        )

        # Show key stats
        for line in result.stdout.split("\n"):
            if any(k in line for k in ["Found:", "New chunks", "INGESTION COMPLETE", "Errors:", "Time:"]):
                print(f"    {line.strip()}")

        ok = "INGESTION COMPLETE" in result.stdout
        # Capture stderr only on failure (keeps logs small on success)
        stderr_on_failure = result.stderr.strip() if not ok else None
        return (ok, stderr_on_failure)
    except subprocess.TimeoutExpired as e:
        msg = f"TimeoutExpired after {e.timeout}s"
        print(f"  ERROR: Ingestion timed out ({e.timeout}s)")
        return (False, msg)
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        print(f"  ERROR running ingestion: {msg}")
        return (False, msg)

def log_sweep(files_found, files_copied, ingestion_ok,
              start_ts=None, end_ts=None,
              backup_ran=None, backup_path=None,
              error=None, recovery_hint=None,
              subprocess_stderr=None, dry_run=False):
    """
    Append a JSON line to dex-sweep-log.jsonl.

    All new fields default to None so old readers tolerate the schema
    evolution. Log write failures are non-blocking (Rule 15 compliance:
    non-silent WARN, but must not prevent sweep completion).
    """
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "start_ts": start_ts,
        "end_ts": end_ts,
        "files_found": len(files_found),
        "files_copied": len(files_copied),
        "filenames": [f["filename"] for f in files_copied],
        "ingestion_triggered": len(files_copied) > 0,
        "ingestion_success": ingestion_ok,
        "backup_ran": backup_ran,
        "backup_path": backup_path,
        "error": error,
        "recovery_hint": recovery_hint,
        "subprocess_stderr": subprocess_stderr,
        "dry_run": dry_run,
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        # Rule 15: non-blocking, but not silent.
        print(f"  WARN: sweep log write failed (non-blocking): {e}", file=sys.stderr)

# -----------------------------
# SINGLE SWEEP
# -----------------------------
def sweep(dry_run=False):
    """Run one sweep cycle. Guarantees a log_sweep call via try/finally."""
    start_ts = datetime.datetime.now().isoformat()
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n  {'='*50}")
    print(f"  DEX JR AUTO-SWEEP — {ts}")
    print(f"  {'='*50}")
    print(f"  Scanning {len(DROP_FOLDERS)} drop folder(s)...")

    # State captured across try/finally so the log entry always has
    # whatever the sweep managed to accomplish before it exited.
    files: list = []
    copied: list = []
    ingestion_ok = False
    backup_ran = None
    backup_path = None
    error = None
    recovery_hint = None
    subprocess_stderr = None

    try:
        # Scan
        files = scan_drop_folders()
        if not files:
            print(f"  No new files found.")
            return False

        print(f"  Found {len(files)} file(s):")
        for f in files:
            print(f"    - {f['filename']} ({f['size']:,} bytes) from {f['folder']}")

        # Backup pre-flight (Trigger 3 of STD-DDL-BACKUP-001)
        # Skipped in --dry-run (dry-run is read-only — no gate needed).
        if not dry_run:
            print()
            print(f"  Backup pre-flight (Trigger 3)...")
            backup_status = ensure_backup_current(expected_write_chunks=SWEEP_CHUNK_ESTIMATE)
            backup_ran = bool(backup_status.get("backup_ran"))
            backup_path = backup_status.get("backup_path")
            if backup_ran:
                print(f"  Backup refreshed: {backup_path}")
            else:
                age = backup_status.get("backup_age_hours")
                print(f"  Backup current: age={age}h")

        # Copy
        print()
        copied = copy_to_corpus(files, dry_run=dry_run)

        # Ingest
        if copied and not dry_run:
            print()
            ingestion_ok, subprocess_stderr = run_ingestion(dry_run=dry_run)
        elif copied and dry_run:
            print(f"\n  [DRY RUN] Would trigger ingestion for {len(copied)} file(s)")
            ingestion_ok, _ = run_ingestion(dry_run=True)

        # Summary
        print(f"\n  {'─'*50}")
        print(f"  Sweep complete: {len(copied)} file(s) ingested")
        if ingestion_ok:
            print(f"  Corpus updated successfully")
        print(f"  {'─'*50}\n")

        return len(copied) > 0

    except BackupNotFoundError as e:
        error = f"BackupNotFoundError: {e}"
        recovery_hint = "python dex-backup.py --force"
        print(f"  FATAL: no backup exists.")
        print(f"  Recovery: {recovery_hint}")
        return False
    except BackupFailedError as e:
        error = f"BackupFailedError: {e}"
        recovery_hint = "python dex-backup.py --check-only"
        print(f"  FATAL: backup pre-flight failed: {e}")
        print(f"  Recovery: {recovery_hint}")
        return False
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        recovery_hint = "inspect traceback, fix underlying issue, rerun"
        print(f"  CRASH: {error}", file=sys.stderr)
        raise
    finally:
        end_ts = datetime.datetime.now().isoformat()
        log_sweep(
            files, copied, ingestion_ok,
            start_ts=start_ts,
            end_ts=end_ts,
            backup_ran=backup_ran,
            backup_path=backup_path,
            error=error,
            recovery_hint=recovery_hint,
            subprocess_stderr=subprocess_stderr,
            dry_run=dry_run,
        )

# -----------------------------
# WATCH MODE
# -----------------------------
def watch(interval_minutes, dry_run=False):
    """Continuously watch for new files."""
    print(f"\n  DEX JR AUTO-SWEEP — Watch Mode")
    print(f"  Checking every {interval_minutes} minute(s)")
    print(f"  Drop folders: {len(DROP_FOLDERS)}")
    for f in DROP_FOLDERS:
        exists = "OK" if os.path.exists(f) else "NOT FOUND"
        print(f"    [{exists}] {f}")
    print(f"  Press Ctrl+C to stop\n")

    while True:
        try:
            sweep(dry_run=dry_run)
            time.sleep(interval_minutes * 60)
        except KeyboardInterrupt:
            print("\n  Watch stopped.")
            break

# -----------------------------
# MAIN
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Dex Jr Auto-Sweep v1.0")
    parser.add_argument("--watch", action="store_true", help="Watch continuously")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help="Minutes between checks")
    parser.add_argument("--dry-run", action="store_true", help="Preview without acting")

    args = parser.parse_args()

    if args.watch:
        watch(args.interval, dry_run=args.dry_run)
    else:
        sweep(dry_run=args.dry_run)

if __name__ == "__main__":
    main()
