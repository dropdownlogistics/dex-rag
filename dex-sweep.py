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

# -----------------------------
# SWEEP
# -----------------------------
def scan_drop_folders():
    """Find all ingestible files across all drop folders."""
    found = []
    for folder in DROP_FOLDERS:
        if not os.path.exists(folder):
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
    """Trigger canon ingestion."""
    if dry_run:
        print(f"  [DRY RUN] Would run: python {INGEST_SCRIPT} --path {CANON_DIR} --build-canon")
        return True

    if not os.path.exists(INGEST_SCRIPT):
        print(f"  ERROR: Ingest script not found: {INGEST_SCRIPT}")
        return False

    try:
        print(f"  Running ingestion...")
        result = subprocess.run(
            ["python", INGEST_SCRIPT, "--path", CANON_DIR, "--build-canon", "--fast"],
            capture_output=True, text=True, timeout=600
        )

        # Show key stats
        for line in result.stdout.split("\n"):
            if any(k in line for k in ["Found:", "New chunks", "INGESTION COMPLETE", "Errors:", "Time:"]):
                print(f"    {line.strip()}")

        return "INGESTION COMPLETE" in result.stdout
    except subprocess.TimeoutExpired:
        print("  ERROR: Ingestion timed out (5 min limit)")
        return False
    except Exception as e:
        print(f"  ERROR running ingestion: {e}")
        return False

def log_sweep(files_found, files_copied, ingestion_ok):
    """Log the sweep results."""
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "files_found": len(files_found),
        "files_copied": len(files_copied),
        "filenames": [f["filename"] for f in files_copied],
        "ingestion_triggered": len(files_copied) > 0,
        "ingestion_success": ingestion_ok,
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except:
        pass

# -----------------------------
# SINGLE SWEEP
# -----------------------------
def sweep(dry_run=False):
    """Run one sweep cycle."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n  {'='*50}")
    print(f"  DEX JR AUTO-SWEEP — {ts}")
    print(f"  {'='*50}")
    print(f"  Scanning {len(DROP_FOLDERS)} drop folder(s)...")

    # Scan
    files = scan_drop_folders()
    if not files:
        print(f"  No new files found.")
        log_sweep([], [], False)
        return False

    print(f"  Found {len(files)} file(s):")
    for f in files:
        print(f"    - {f['filename']} ({f['size']:,} bytes) from {f['folder']}")

    # Copy
    print()
    copied = copy_to_corpus(files, dry_run=dry_run)

    # Ingest
    ingestion_ok = False
    if copied and not dry_run:
        print()
        ingestion_ok = run_ingestion(dry_run=dry_run)
    elif copied and dry_run:
        print(f"\n  [DRY RUN] Would trigger ingestion for {len(copied)} file(s)")
        ingestion_ok = True

    # Log
    log_sweep(files, copied, ingestion_ok)

    # Summary
    print(f"\n  {'─'*50}")
    print(f"  Sweep complete: {len(copied)} file(s) ingested")
    if ingestion_ok:
        print(f"  Corpus updated successfully")
    print(f"  {'─'*50}\n")

    return len(copied) > 0

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
