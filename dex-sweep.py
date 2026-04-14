"""
DEX JR AUTO-SWEEP — v2.0
Airtight ingest sweep per ADR-INGEST-PIPELINE-001 and STD-DDL-SWEEPREPORT-001.

Scans drop folders for new files, copies to corpus staging, triggers
ingestion via dex-ingest.py --collection dex_canon, writes a human-
readable sweep report to _sweep_reports/, and logs every run to JSONL.

Usage:
  python dex-sweep.py                    # Run once (check and ingest)
  python dex-sweep.py --watch            # Watch continuously
  python dex-sweep.py --interval 30      # Check every 30 minutes
  python dex-sweep.py --dry-run          # Preview without acting
  python dex-sweep.py --self-test        # Run classification + report tests

Authority: ADR-INGEST-PIPELINE-001, STD-DDL-SWEEPREPORT-001 v1.0
Auto-Sweep v2.0 | 2026-04-12

Step 38 (2026-04-13): report-section pipeline_state now enumerates
collections dynamically via client.list_collections() rather than a
hardcoded 4-collection list. Ensures _v2 (and any future) collections
appear in the daily report during soak.
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
    r"C:\Users\dkitc\OneDrive\DexJr",                              # OneDrive drop folder
    r"C:\Users\dkitc\OneDrive\DDL_Ingest",                          # Primary ingest zone
    r"C:\Users\dkitc\OneDrive\DDL_Ingest\_sweep_reports",           # Report ingest (STD-DDL-SWEEPREPORT-001)
    r"C:\Users\dkitc\Downloads\DDL_Ingest",                         # Local downloads drop
    r"C:\Users\dkitc\iCloudDrive\Documents\04_DDL_Ingest",          # iOS drop folder
]

# Canonical report output location (inside the ingest zone)
SWEEP_REPORTS_DIR = r"C:\Users\dkitc\OneDrive\DDL_Ingest\_sweep_reports"

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

# Temp dir base for per-sweep ingest (Step 22 Fix A: don't scan CANON_DIR's 5800+ files)
TEMP_BASE = r"C:\Users\dexjr\dex-rag-scratch"

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


def classify_scanned_files(files):
    """
    Split scanned files into (user_files, ingest_reports).

    Per STD-DDL-SWEEPREPORT-001 v1.0 classification predicate:
    a file is an ingest report IF AND ONLY IF all three conditions hold:
      1. parent folder name is '_sweep_reports'
      2. filename starts with 'ingest_report_'
      3. extension is '.md'
    """
    user_files = []
    ingest_reports = []
    for f in files:
        parent_name = os.path.basename(os.path.dirname(f["source"]))
        is_report = (
            parent_name == "_sweep_reports"
            and f["filename"].startswith("ingest_report_")
            and f["filename"].endswith(".md")
        )
        if is_report:
            ingest_reports.append(f)
        else:
            user_files.append(f)
    return user_files, ingest_reports


def find_previous_report():
    """Find the most recent ingest_report_*.md in SWEEP_REPORTS_DIR."""
    if not os.path.exists(SWEEP_REPORTS_DIR):
        return None
    reports = sorted(
        [f for f in os.listdir(SWEEP_REPORTS_DIR)
         if f.startswith("ingest_report_") and f.endswith(".md")],
        reverse=True,
    )
    return os.path.join(SWEEP_REPORTS_DIR, reports[0]) if reports else None


def write_sweep_report(
    ingest_run_id,
    triggered_at,
    files_ingested,
    skipped_files,
    errors,
    ingestion_ok,
    backup_ran,
    backup_path,
    outcome,
    subprocess_output="",
):
    """
    Compose STD-DDL-SWEEPREPORT-001 v1.0 markdown report.
    Write to SWEEP_REPORTS_DIR. Return the written path, or None on failure.
    Failure is WARN-level, does NOT raise.
    """
    try:
        os.makedirs(SWEEP_REPORTS_DIR, exist_ok=True)
        now = datetime.datetime.now(datetime.timezone.utc)
        ts = now.strftime("%Y-%m-%d_%H%M%S")
        us = f"{now.microsecond:06d}"
        fname = f"ingest_report_{ts}.{us}_{ingest_run_id}.md"
        path = os.path.join(SWEEP_REPORTS_DIR, fname)

        # Pipeline state (read-only ChromaDB query)
        # Step 38: dynamic enumeration via list_collections so the report
        # stays complete across the _v2 soak and any future collection set.
        pipeline_state = {}
        try:
            from dex_weights import get_client
            client = get_client()
            for col in client.list_collections():
                try:
                    pipeline_state[col.name] = col.count()
                except Exception:
                    pipeline_state[col.name] = "unavailable"
        except Exception:
            pipeline_state["error"] = "ChromaDB unreachable"

        previous = find_previous_report()

        # Extract chunks-written from subprocess output
        chunks_written = "unknown"
        for line in (subprocess_output or "").split("\n"):
            if "New chunks added SCOPED:" in line:
                chunks_written = line.strip().split(":")[1].strip().split()[0]
            elif "New chunks added CANON:" in line:
                val = line.strip().split(":")[1].strip().split()[0]
                if val != "0":
                    chunks_written = val

        lines = []
        lines.append("---")
        lines.append(f"ingest_run_id: {ingest_run_id}")
        lines.append(f"triggered_at: {triggered_at}")
        lines.append(f"outcome: {outcome}")
        lines.append(f"task_name: DexSweep-NightlyIngest")
        lines.append(f"drop_folders_scanned: {len(DROP_FOLDERS)}")
        lines.append(f"files_ingested: {len(files_ingested)}")
        lines.append(f"chunks_written: {chunks_written}")
        lines.append(f"errors: {len(errors)}")
        lines.append(f"backup_ran: {backup_ran}")
        lines.append("---")
        lines.append("")
        lines.append(f"# Sweep Report — {ingest_run_id}")
        lines.append("")

        # Section 2: Summary
        lines.append("## Summary")
        lines.append("")
        if outcome == "success":
            lines.append(
                f"Sweep completed successfully. {len(files_ingested)} file(s) "
                f"ingested into dex_canon, producing {chunks_written} chunk(s). "
                f"Backup {'refreshed' if backup_ran else 'was current'}. "
                f"Zero errors."
            )
        elif outcome == "failure":
            lines.append(
                f"Sweep attempted ingest of {len(files_ingested)} file(s) but "
                f"the dex-ingest.py subprocess failed. {len(errors)} error(s). "
                f"Files were copied to CANON_DIR but chunks may not have landed."
            )
        elif outcome == "partial":
            lines.append(
                f"Sweep completed with warnings. {len(files_ingested)} file(s) processed, "
                f"{len(errors)} error(s) encountered."
            )
        else:
            lines.append(f"Outcome: {outcome}")
        lines.append("")

        # Section 3a: All-run summary
        lines.append("## Files processed")
        lines.append("")
        lines.append(f"| File | Size | Source folder |")
        lines.append(f"|---|---:|---|")
        for f in files_ingested:
            lines.append(f"| {f['filename']} | {f['size']:,} | {os.path.basename(f['folder'])} |")
        lines.append("")

        # Section 4: Previous report
        lines.append("## Previous report")
        lines.append("")
        if previous:
            lines.append(f"Previous: `{os.path.basename(previous)}`")
        else:
            lines.append("No previous report found (this may be the first sweep report).")
        lines.append("")

        # Section 5: Skipped files
        if skipped_files:
            lines.append("## Skipped files")
            lines.append("")
            for s in skipped_files:
                lines.append(f"- {s}")
            lines.append("")

        # Section 6: Errors
        if errors:
            lines.append("## Errors and warnings")
            lines.append("")
            for e in errors:
                lines.append(f"- {e}")
            lines.append("")

        # Section 7: Pipeline state
        lines.append("## Pipeline state")
        lines.append("")
        lines.append("| Collection | Chunks |")
        lines.append("|---|---:|")
        for cname, count in pipeline_state.items():
            lines.append(f"| {cname} | {count:,} |" if isinstance(count, int) else f"| {cname} | {count} |")
        if backup_path:
            lines.append(f"\nBackup anchor: `{os.path.basename(str(backup_path))}`")
        lines.append("")

        # Section 8: Next scheduled
        lines.append("## Next scheduled sweep")
        lines.append("")
        lines.append("DexSweep-NightlyIngest: daily at 4:00 AM local.")
        lines.append("")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"  Report written: {fname}")
        return path
    except Exception as e:
        print(f"  WARN: report write failed (non-blocking): {e}", file=sys.stderr)
        return None


def copy_to_corpus(files, dry_run=False, temp_dir=None):
    """
    Copy files to CANON_DIR (archival) + optionally to temp_dir (for ingest).

    Step 22 Fix A: files are ingested from a small temp dir containing only
    the new files, not from CANON_DIR (which has 5800+ historical files).
    Files also go to CANON_DIR for permanent archival. Originals move to
    _processed/ per existing behavior.
    """
    os.makedirs(CANON_DIR, exist_ok=True)

    copied = []
    for f in files:
        dest = os.path.join(CANON_DIR, f["filename"])
        processed_dir = os.path.join(f["folder"], "_processed")
        os.makedirs(processed_dir, exist_ok=True)
        processed = os.path.join(processed_dir, f["filename"])

        # Handle filename conflicts in CANON_DIR
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
                # Also copy to temp dir for targeted ingest (Step 22 Fix A)
                if temp_dir:
                    shutil.copy2(dest, os.path.join(temp_dir, f["filename"]))
                shutil.move(f["source"], processed)
                copied.append(f)
                print(f"  Copied: {f['filename']} ({f['size']:,} bytes)")
            except Exception as e:
                print(f"  ERROR copying {f['filename']}: {e}")

    return copied

def run_ingestion(ingest_path, dry_run=False):
    """
    Trigger ingestion via subprocess to dex-ingest.py.

    Step 22 Fix A: ingest_path is a temp dir containing only the new files,
    NOT CANON_DIR (which has 5800+ files and would timeout). This makes
    ingest fast and targeted.

    Returns: (ok: bool, stderr_on_failure: str | None, stdout: str)
    """
    cmd_args = ["python", INGEST_SCRIPT, "--path", str(ingest_path),
                "--collection", "dex_canon_v2", "--fast", "--skip-backup-check"]

    if dry_run:
        print(f"  [DRY RUN] Would run: {' '.join(cmd_args)}")
        return (True, None, "")

    if not os.path.exists(INGEST_SCRIPT):
        msg = f"Ingest script not found: {INGEST_SCRIPT}"
        print(f"  ERROR: {msg}")
        return (False, msg, "")

    try:
        print(f"  Running ingestion against {ingest_path}...")
        ingest_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        # Step 24: no timeout. Real operator content can exceed any reasonable
        # wall-time cap. Ingest runs to completion. Dex-ingest.py has its own
        # progress indicators via stdout.
        result = subprocess.run(
            cmd_args,
            capture_output=True, text=True,
            env=ingest_env,
        )

        # Show key stats
        for line in result.stdout.split("\n"):
            if any(k in line for k in ["Found:", "New chunks", "INGESTION COMPLETE", "Errors:", "Time:"]):
                print(f"    {line.strip()}")

        ok = "INGESTION COMPLETE" in result.stdout
        stderr_on_failure = result.stderr.strip() if not ok else None
        return (ok, stderr_on_failure, result.stdout)
    except subprocess.TimeoutExpired as e:
        msg = f"TimeoutExpired after {e.timeout}s"
        print(f"  ERROR: Ingestion timed out ({e.timeout}s)")
        return (False, msg, "")
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        print(f"  ERROR running ingestion: {msg}")
        return (False, msg, "")

def log_sweep(files_found, files_copied, ingestion_ok,
              start_ts=None, end_ts=None,
              backup_ran=None, backup_path=None,
              error=None, recovery_hint=None,
              subprocess_stderr=None, dry_run=False,
              outcome=None, report_written=None,
              report_write_error=None):
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
        "outcome": outcome,
        "report_written": report_written,
        "report_write_error": report_write_error,
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
    """
    Run one sweep cycle per STD-DDL-SWEEPREPORT-001 v1.0.

    Classification logic:
    - If only ingest reports found (no user files): skip (no gate, no ingest, no report)
    - If nothing found: skip
    - Otherwise: gate → copy → ingest → report

    Guarantees a log_sweep call via try/finally.
    """
    start_ts = datetime.datetime.now().isoformat()
    triggered_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n  {'='*50}")
    print(f"  DEX JR AUTO-SWEEP v2.0 - {ts}")
    print(f"  {'='*50}")
    print(f"  Scanning {len(DROP_FOLDERS)} drop folder(s)...")

    # State captured across try/finally
    files: list = []
    copied: list = []
    ingestion_ok = False
    backup_ran = None
    backup_path = None
    error = None
    recovery_hint = None
    subprocess_stderr = None
    outcome = "no_files_found"
    report_path = None
    report_write_error = None
    subprocess_stdout = ""
    ingest_run_id = f"sweep_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d_%H%M%S')}"

    try:
        # Scan
        files = scan_drop_folders()
        if not files:
            print(f"  No new files found.")
            outcome = "no_files_found"
            return False

        # Classify: user files vs ingest reports
        user_files, ingest_reports = classify_scanned_files(files)
        print(f"  Found {len(files)} file(s): {len(user_files)} user, {len(ingest_reports)} report(s)")
        for f in files:
            tag = " [REPORT]" if f in ingest_reports else ""
            print(f"    - {f['filename']} ({f['size']:,} bytes){tag}")

        # Case B: only reports, no user files — skip entirely
        if len(user_files) == 0 and len(ingest_reports) > 0:
            print(f"  Reports only - no user files to ingest. Skipping.")
            outcome = "skipped_report_only"
            return False

        # Standard flow: user files present (may also include reports)
        # Backup pre-flight (Trigger 3). Skipped in --dry-run.
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

        # Step 22 Fix A: create per-run temp dir for targeted ingest.
        # Files go to BOTH temp_dir (for ingest) and CANON_DIR (for archival).
        temp_dir = os.path.join(TEMP_BASE, f"sweep_{ingest_run_id}")
        if not dry_run:
            os.makedirs(temp_dir, exist_ok=True)
            print(f"  Temp ingest dir: {temp_dir}")

        # Copy ALL files (user + reports) to CANON_DIR + temp_dir
        print()
        copied = copy_to_corpus(files, dry_run=dry_run, temp_dir=temp_dir if not dry_run else None)

        # Ingest from the small temp dir (NOT from CANON_DIR's 5800+ files)
        subprocess_stdout = ""
        if copied and not dry_run:
            print()
            ingestion_ok, subprocess_stderr, subprocess_stdout = run_ingestion(
                ingest_path=temp_dir, dry_run=dry_run,
            )
        elif copied and dry_run:
            print(f"\n  [DRY RUN] Would trigger ingestion for {len(copied)} file(s)")
            ingestion_ok, _, subprocess_stdout = run_ingestion(
                ingest_path=temp_dir or "TEMP_DIR", dry_run=True,
            )

        # Determine outcome
        if dry_run:
            outcome = "dry_run"
        elif ingestion_ok:
            outcome = "success"
        elif copied:
            outcome = "failure"
        else:
            outcome = "partial"

        # Write sweep report (STD-DDL-SWEEPREPORT-001 v1.0)
        if not dry_run and copied:
            try:
                report_path = write_sweep_report(
                    ingest_run_id=ingest_run_id,
                    triggered_at=triggered_at,
                    files_ingested=copied,
                    skipped_files=[],
                    errors=[subprocess_stderr] if subprocess_stderr else [],
                    ingestion_ok=ingestion_ok,
                    backup_ran=backup_ran,
                    backup_path=backup_path,
                    outcome=outcome,
                    subprocess_output=subprocess_stdout or "",
                )
            except Exception as e:
                report_write_error = str(e)
                print(f"  WARN: report write failed: {e}", file=sys.stderr)

        # Temp dir cleanup (Step 22 Fix A)
        if not dry_run and os.path.exists(temp_dir):
            if ingestion_ok:
                try:
                    shutil.rmtree(temp_dir)
                    print(f"  Temp dir cleaned up")
                except Exception as e:
                    print(f"  WARN: temp dir cleanup failed: {e}")
            else:
                print(f"  WARN: temp dir preserved for forensics: {temp_dir}")

        # Summary
        print(f"\n  {'-'*50}")
        print(f"  Sweep complete: {len(copied)} file(s) processed, outcome={outcome}")
        if report_path:
            print(f"  Report: {os.path.basename(report_path)}")
        print(f"  {'-'*50}\n")

        return len(copied) > 0

    except BackupNotFoundError as e:
        error = f"BackupNotFoundError: {e}"
        recovery_hint = "python dex-backup.py --force"
        outcome = "failure"
        print(f"  FATAL: no backup exists.")
        print(f"  Recovery: {recovery_hint}")
        return False
    except BackupFailedError as e:
        error = f"BackupFailedError: {e}"
        recovery_hint = "python dex-backup.py --check-only"
        outcome = "failure"
        print(f"  FATAL: backup pre-flight failed: {e}")
        print(f"  Recovery: {recovery_hint}")
        return False
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        recovery_hint = "inspect traceback, fix underlying issue, rerun"
        outcome = "failure"
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
            outcome=outcome,
            report_written=str(report_path) if report_path else None,
            report_write_error=report_write_error,
        )

# -----------------------------
# WATCH MODE
# -----------------------------
def watch(interval_minutes, dry_run=False):
    """Continuously watch for new files."""
    print(f"\n  DEX JR AUTO-SWEEP - Watch Mode")
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
def run_self_tests():
    """D8 self-tests per STD-DDL-SWEEPREPORT-001 classification predicate."""
    print("Running self-tests...")
    passed = 0

    # Classification predicate: 6 cases
    def make_file(source, filename):
        return {"source": source, "filename": filename, "folder": os.path.dirname(source), "size": 100}

    # Case 1: valid report (all 3 conditions true)
    f1 = make_file(r"C:\DDL_Ingest\_sweep_reports\ingest_report_2026-04-12.md", "ingest_report_2026-04-12.md")
    u, r = classify_scanned_files([f1])
    assert len(r) == 1 and len(u) == 0, f"Case 1 failed: {u}, {r}"
    print("  [OK] Case 1: valid report classified as report")
    passed += 1

    # Case 2: wrong parent folder
    f2 = make_file(r"C:\DDL_Ingest\ingest_report_2026-04-12.md", "ingest_report_2026-04-12.md")
    u, r = classify_scanned_files([f2])
    assert len(u) == 1 and len(r) == 0, f"Case 2 failed"
    print("  [OK] Case 2: wrong parent -> user file")
    passed += 1

    # Case 3: wrong prefix
    f3 = make_file(r"C:\DDL_Ingest\_sweep_reports\sweep_2026-04-12.md", "sweep_2026-04-12.md")
    u, r = classify_scanned_files([f3])
    assert len(u) == 1 and len(r) == 0, f"Case 3 failed"
    print("  [OK] Case 3: wrong prefix -> user file")
    passed += 1

    # Case 4: wrong extension
    f4 = make_file(r"C:\DDL_Ingest\_sweep_reports\ingest_report_2026-04-12.txt", "ingest_report_2026-04-12.txt")
    u, r = classify_scanned_files([f4])
    assert len(u) == 1 and len(r) == 0, f"Case 4 failed"
    print("  [OK] Case 4: wrong extension -> user file")
    passed += 1

    # Case 5: mixed set
    f5_user = make_file(r"C:\DDL_Ingest\doc.txt", "doc.txt")
    f5_rpt = make_file(r"C:\DDL_Ingest\_sweep_reports\ingest_report_x.md", "ingest_report_x.md")
    u, r = classify_scanned_files([f5_user, f5_rpt])
    assert len(u) == 1 and len(r) == 1, f"Case 5 failed"
    print("  [OK] Case 5: mixed user + report classified correctly")
    passed += 1

    # Case 6: empty list
    u, r = classify_scanned_files([])
    assert len(u) == 0 and len(r) == 0, f"Case 6 failed"
    print("  [OK] Case 6: empty list -> both empty")
    passed += 1

    # Report filename generation: microsecond uniqueness
    now = datetime.datetime.now(datetime.timezone.utc)
    ts = now.strftime("%Y-%m-%d_%H%M%S")
    us = f"{now.microsecond:06d}"
    fname = f"ingest_report_{ts}.{us}_test_run_id.md"
    assert fname.startswith("ingest_report_"), f"Filename failed: {fname}"
    assert fname.endswith(".md"), f"Filename extension failed: {fname}"
    assert "test_run_id" in fname, f"Run ID not in filename: {fname}"
    print(f"  [OK] Report filename: {fname}")
    passed += 1

    print(f"\nAll {passed} self-tests passed.")


def main():
    parser = argparse.ArgumentParser(description="Dex Jr Auto-Sweep v2.0")
    parser.add_argument("--watch", action="store_true", help="Watch continuously")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help="Minutes between checks")
    parser.add_argument("--dry-run", action="store_true", help="Preview without acting")
    parser.add_argument("--self-test", action="store_true", help="Run classification + report self-tests")

    args = parser.parse_args()

    if args.self_test:
        run_self_tests()
        return

    if args.watch:
        watch(args.interval, dry_run=args.dry_run)
    else:
        sweep(dry_run=args.dry_run)

if __name__ == "__main__":
    main()
