#!/usr/bin/env python3
"""
DEX JR. RAG PIPELINE - Phase 1 Ingestion (Dual Collections)

Collections:
  - ddl_archive : RAW (everything)   [NORMAL mode]
  - dex_canon   : CANON (canon+foundation)

Modes:
  - NORMAL: writes RAW + CANON (conditional)
  - BUILD CANON: writes CANON only (does NOT expand RAW)

Notes:
  - Per-user Chroma DB location: ~\\.dex-jr\\chromadb
  - Guardrail: skip extremely large files in NORMAL mode to avoid chunking stalls

Changes from v4.1:
  - PHASE1_EXTENSIONS expanded: .txt .md .html .jsx .json .py .cs .js .mjs .ts .tsx .css .sql .sh .bat .ps1 .bas .csv .yml .yaml .toml .ipynb .prisma
  - Fixed phantom chunk count: switched add() to upsert() with pre-check
  - Fixed SyntaxWarning on escape sequence in docstring
  - scan_archive print updated to reflect all supported extensions
  - Added --collection flag: route ingest to any named ChromaDB collection
  - Added --ext-filter flag: limit ingest to specific file extensions
  - Added --nominated-by flag: tag chunks with nominating seat(s) for ext_ collections
"""

import os
import sys
import time
import json
import argparse
import hashlib
from datetime import datetime, timezone
from typing import Optional, List, Tuple

import requests

from dex_pipeline import (
    build_chunk_metadata,
    ensure_backup_current,
    BackupNotFoundError,
    BackupFailedError,
)
from ingest_cache import IngestCache, hash_file


# -----------------------------
# CONFIG
# -----------------------------
CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"

# Step 33c Part B: flipped to _v2 (mxbai-embed-large) collections.
# Readers (dex_jr_query.py, dex-search-api.py) also target _v2.
RAW_COLLECTION = "ddl_archive_v2"
CANON_COLLECTION = "dex_canon_v2"

OLLAMA_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "mxbai-embed-large"

# Chunking heuristic
CHUNK_SIZE_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 50
CHARS_PER_TOKEN = 4

# Any value >100 fires Trigger 5 (pre-batch) per STD-DDL-BACKUP-001.
# Bulk runs almost always exceed 100 chunks; we use a large estimate
# to guarantee the trigger regardless of actual file count.
BULK_CHUNK_ESTIMATE = 10_000

# Forensic audit log for --reset operations. Append-only JSONL.
RESET_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".reset_log")

# Extension-based source_type inference subset (STD-DDL-METADATA-001 enum: "code")
CODE_EXTENSIONS = {
    ".py", ".cs", ".js", ".mjs", ".ts", ".tsx", ".jsx",
    ".css", ".sql", ".sh", ".bat", ".ps1", ".bas",
    ".prisma", ".ipynb",
    ".yml", ".yaml", ".toml", ".json",
}

# File scan
PHASE1_EXTENSIONS = {
    # Original
    ".txt", ".md", ".html", ".jsx", ".json",
    # Code
    ".py", ".cs", ".js", ".mjs", ".ts", ".tsx",
    ".css", ".sql", ".sh", ".bat", ".ps1", ".bas",
    # Config / data
    ".csv", ".yml", ".yaml", ".toml",
    # Notebooks
    ".ipynb",
    # Prisma schema
    ".prisma",
}
SKIP_FILENAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}

# Step 33c Part B: exclude files whose names match these prefixes regardless
# of extension. Prevents the sweep's own ingest_report_*.md artifacts from
# being ingested into the corpus (feedback loop observed 2026-04-14).
SKIP_FILENAME_PREFIXES = ("ingest_report_",)

# Guardrail: skip huge files in NORMAL mode (10MB of text)
# Step 38: bumped 5MB -> 10MB after Mon sweep ingested 2.5-2.7MB files;
# 6MB+ operator threads would silently drop at the old ceiling.
MAX_TEXT_CHARS_NORMAL = 10_000_000  # ~10MB (roughly)

# Canon classification markers (path-based)
CANON_PATH_MARKERS = [
    "councilreview", "council reviews", "council_reviews",
    "governance", "standards", "protocol", "charter",
    "dexos",
    "video_transcripts",
    "tiktok",
    "councilnom",
]
FOUNDATION_PATH_MARKERS = [
    "mindframe", "dexcontinuum", "missionstatement",
    "visionstatement", "participationprinciples"
]
ARCHIVE_PATH_MARKERS = [
    "threads", "chatgpt", "exports", "transcripts",
    "logs", "conversations"
]


def classify_tier(rel_path: str, filename: str, folder: str) -> Tuple[str, str]:
    s = f"{rel_path} {filename} {folder}".lower()
    if any(m in s for m in CANON_PATH_MARKERS):
        return ("canon", "ratified")
    if any(m in s for m in FOUNDATION_PATH_MARKERS):
        return ("foundation", "conceptual")
    if any(m in s for m in ARCHIVE_PATH_MARKERS):
        return ("archive", "historical")
    return ("unknown", "unknown")


def infer_source_type(filename: str, extension: str) -> str:
    """
    Infer STD-DDL-METADATA-001 source_type enum value from filename + extension.

    Extension-first for code/data/web. Filename-prefix override for text
    files that are classifiable by naming convention (council reviews,
    governance docs, synthesis, system telemetry). Fallback: "unknown".
    """
    ext = (extension or "").lower()
    if ext in CODE_EXTENSIONS:
        return "code"
    if ext == ".csv":
        return "spreadsheet"
    if ext in (".html", ".mhtml"):
        return "web_archive"
    # Text-file filename-prefix rules (.md / .txt)
    name = filename or ""
    if name.startswith("DDLCouncilReview_"):
        return "council_review"
    if name.startswith("SYNTH-") or "_SYNTH." in name:
        return "council_synthesis"
    if any(name.startswith(p) for p in ("ADR-", "STD-", "PRO-", "CR-")):
        return "governance"
    if name.startswith("sweep_") and name.endswith(".md"):
        return "system_telemetry"
    if name.startswith("audit_") and name.endswith(".md"):
        return "system_telemetry"
    return "unknown"


def append_reset_log(entry: dict) -> None:
    """
    Append one JSON line to .reset_log at the repo root. Forensic-only;
    failures log to stderr but do NOT block the reset (the backup is
    the real recovery path, the log is a paper trail).
    """
    try:
        with open(RESET_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"    WARN: reset log write failed (non-blocking): {e}", file=sys.stderr)


# -----------------------------
# EMBEDDING
# -----------------------------
def get_embedding(text: str) -> Optional[List[float]]:
    try:
        r = requests.post(
            OLLAMA_URL,
            json={"model": EMBED_MODEL, "prompt": text},
            timeout=60,
        )
        r.raise_for_status()
        return r.json().get("embedding")
    except Exception as e:
        print(f"    ? Embedding failed: {e}")
        return None


# -----------------------------
# CHUNKING
# -----------------------------
def chunk_text(text: str) -> List[str]:
    """
    Chunk a text string into overlapping segments.

    This is intentionally simple and safe for most files.
    Guardrail for extremely large files is handled before calling this.
    """
    char_size = CHUNK_SIZE_TOKENS * CHARS_PER_TOKEN
    char_overlap = CHUNK_OVERLAP_TOKENS * CHARS_PER_TOKEN

    t = (text or "").strip()
    if not t:
        return []
    if len(t) <= char_size:
        return [t]

    out: List[str] = []
    start = 0
    n = len(t)

    while start < n:
        end = min(n, start + char_size)

        # Prefer breaking on paragraph/sentence boundary (best-effort)
        if end < n:
            para = t.rfind("\n\n", start + char_size // 2, end)
            if para > start:
                end = para + 2
            else:
                for sep in [". ", ".\n", "!\n", "?\n", "! ", "? "]:
                    brk = t.rfind(sep, start + char_size // 2, end)
                    if brk > start:
                        end = brk + len(sep)
                        break

        chunk = t[start:end].strip()
        if chunk:
            out.append(chunk)

        # Move window forward with overlap
        start = end - char_overlap
        if start < 0:
            start = 0
        if end == n:
            break

    return out


# -----------------------------
# FILE HELPERS
# -----------------------------
def sha256_file(path: str) -> Optional[str]:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for b in iter(lambda: f.read(8192), b""):
                h.update(b)
        return h.hexdigest()
    except Exception:
        return None


def read_text_file(path: str) -> Optional[str]:
    # Try a few encodings; keep it simple
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except Exception:
            continue
    return None


def scan_archive(root: str, extensions: Optional[set] = None) -> List[dict]:
    if extensions is None:
        extensions = PHASE1_EXTENSIONS
    files = []
    for r, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for n in names:
            if n in SKIP_FILENAMES:
                continue
            if any(n.startswith(p) for p in SKIP_FILENAME_PREFIXES):
                continue
            ext = os.path.splitext(n)[1].lower()
            if ext not in extensions:
                continue
            full = os.path.join(r, n)
            rel = os.path.relpath(full, root)
            files.append(
                {
                    "path": full,
                    "rel_path": rel,
                    "filename": n,
                    "extension": ext,
                    "folder": os.path.basename(r),
                }
            )
    return files


# -----------------------------
# INGEST
# -----------------------------
def ingest(archive_path: str, reset: bool = False, build_canon: bool = False, fast: bool = False,
           collection: Optional[str] = None, ext_filter: Optional[set] = None,
           nominated_by: Optional[str] = None, skip_backup_check: bool = False,
           force_rechunk: bool = False, no_ingest_cache: bool = False) -> None:
    import chromadb

    ext_list = ", ".join(sorted(ext_filter if ext_filter else PHASE1_EXTENSIONS))

    print("\n" + "=" * 60)
    print("  DEX JR. RAG PIPELINE - PHASE 1 INGESTION")
    print(f"  Archive: {archive_path}")
    if collection:
        print(f"  Mode: SCOPED COLLECTION -> {collection}")
    else:
        print(f"  Mode: {'BUILD CANON' if build_canon else 'NORMAL'}")
    print(f"  Extensions: {ext_list}")
    if nominated_by:
        print(f"  Nominated by: {nominated_by}")
    if force_rechunk:
        print(f"  ** --force-rechunk: cache bypassed, all files will be re-chunked **")
    if no_ingest_cache:
        print(f"  ** --no-ingest-cache: pre-Step-48 behavior (no cache reads/writes) **")
    print("=" * 60)

    # Generate ingest run id (HHMMSS precision to avoid same-minute collisions)
    ingest_run_id = f"manual_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M%S')}"
    print(f"  Ingest run id: {ingest_run_id}")

    # Backup pre-flight (Trigger 3 of STD-DDL-BACKUP-001)
    if not skip_backup_check:
        try:
            backup_status = ensure_backup_current(expected_write_chunks=BULK_CHUNK_ESTIMATE)
            if backup_status["backup_ran"]:
                print(f"  Backup refreshed: {backup_status['backup_path']}")
            else:
                print(f"  Backup current: age={backup_status['backup_age_hours']}h")
        except BackupNotFoundError as e:
            print(f"FATAL: no backup exists. Run 'python dex-backup.py --force' first.")
            print(f"  ({e})")
            sys.exit(1)
        except BackupFailedError as e:
            print(f"FATAL: backup pre-flight failed: {e}")
            sys.exit(1)
    else:
        print(f"  Backup pre-flight SKIPPED (--skip-backup-check)")

    os.makedirs(CHROMA_DIR, exist_ok=True)
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    if reset:
        # NOTE: On Windows this can occasionally hang if the DB is locked.
        # If that happens, delete the folder manually:
        #   C:\\Users\\dexjr\\.dex-jr\\chromadb
        # Rule 15 fix: explicit per-collection logging + forensic audit log.
        # Gated upstream by ensure_backup_current() — backup must exist first.
        pre_drop_counts: dict = {}
        dropped: List[str] = []
        drop_failures: List[dict] = []
        for cname in (RAW_COLLECTION, CANON_COLLECTION):
            try:
                pre_drop_counts[cname] = client.get_collection(cname).count()
            except Exception:
                pre_drop_counts[cname] = 0  # didn't exist pre-reset
        for cname in (RAW_COLLECTION, CANON_COLLECTION):
            try:
                client.delete_collection(cname)
                dropped.append(cname)
                print(f"  Reset: dropped {cname} (had {pre_drop_counts[cname]:,} chunks)")
            except Exception as e:
                drop_failures.append({"collection": cname, "error": str(e)})
                print(f"  Reset: WARN - {cname} drop failed: {e}")
        append_reset_log({
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "dex-ingest.py",
            "dropped": dropped,
            "drop_failures": drop_failures,
            "pre_drop_counts": pre_drop_counts,
            "ingest_run_id": ingest_run_id,
        })

    raw_col = client.get_or_create_collection(
        RAW_COLLECTION, metadata={"description": "DDL Archive RAW"}
    )
    canon_col = client.get_or_create_collection(
        CANON_COLLECTION, metadata={"description": "Dex Canon"}
    )

    # Scoped collection — created on demand when --collection is specified
    scoped_col = None
    scoped_existing_ids: set = set()
    if collection:
        scoped_col = client.get_or_create_collection(
            collection, metadata={"description": f"DDL Scoped Collection: {collection}"}
        )
        print(f"\n  Scoped collection '{collection}': {scoped_col.count()} existing chunks")

    raw_count_start = raw_col.count()
    canon_count_start = canon_col.count()

    print(f"\n  Existing chunks in RAW:   {raw_count_start}")
    print(f"  Existing chunks in CANON: {canon_count_start}")

    active_extensions = ext_filter if ext_filter else PHASE1_EXTENSIONS
    print(f"\n  Scanning archive for {', '.join(sorted(active_extensions))} files...")
    files = scan_archive(archive_path, active_extensions)
    print(f"  Found: {len(files)} files")
    if not files:
        return

    print("\n  Running dedup pass (SHA-256)...")
    seen_hashes = set()
    unique_files = []
    dupes = 0

    for f in files:
        h = sha256_file(f["path"])
        if not h:
            continue
        if h in seen_hashes:
            dupes += 1
            continue
        seen_hashes.add(h)
        f["hash"] = h
        unique_files.append(f)

    print(f"  Unique files: {len(unique_files)}")
    print(f"  Duplicates skipped: {dupes}")

    # Load existing IDs from DB to accurately detect new vs existing chunks
    # Skipped in --fast mode (auto-ingest path) — upsert handles dedup, delta reporting approximate
    if fast:
        print("\n  Fast mode: skipping ID load, using upsert directly.")
    else:
        print("\n  Loading existing chunk IDs...")

    raw_existing_ids: set = set()
    canon_existing_ids: set = set()

    if not fast:
        if not build_canon and raw_count_start > 0:
            try:
                result = raw_col.get(include=[])
                raw_existing_ids = set(result["ids"])
                print(f"  RAW IDs loaded:   {len(raw_existing_ids)}")
            except Exception as e:
                print(f"  Warning: could not load RAW IDs: {e}")

        if canon_count_start > 0:
            try:
                result = canon_col.get(include=[])
                canon_existing_ids = set(result["ids"])
                print(f"  CANON IDs loaded: {len(canon_existing_ids)}")
            except Exception as e:
                print(f"  Warning: could not load CANON IDs: {e}")

    if not fast and scoped_col and scoped_col.count() > 0:
        try:
            result = scoped_col.get(include=[])
            scoped_existing_ids = set(result["ids"])
            print(f"  SCOPED IDs loaded: {len(scoped_existing_ids)}")
        except Exception as e:
            print(f"  Warning: could not load SCOPED IDs: {e}")

    seen_chunk_ids: set = set()  # run-scoped de-dupe

    # Step 48: initialize ingest cache for file-level dedup
    cache = None
    use_cache = not no_ingest_cache
    if use_cache:
        cache = IngestCache()
        # Determine which collection to cache against
        cache_collection_name = collection if collection else CANON_COLLECTION
        cache_target_col = scoped_col if scoped_col else canon_col
        # Lazy-build: on first run with no cache file, build from collection metadata
        cache_data = cache.load(cache_collection_name)
        if not cache_data and cache_target_col and cache_target_col.count() > 0:
            cache.build_from_collection(cache_target_col, cache_collection_name)
        print(f"\n  Ingest cache: {len(cache.load(cache_collection_name))} entries for {cache_collection_name}")
    else:
        print("\n  Ingest cache: disabled (--no-ingest-cache)")

    print("\n  Ingesting...")
    start_time = time.time()

    files_skipped = 0
    files_skipped_unchanged = 0
    files_skipped_no_cache = 0
    files_rechunked = 0
    files_new = 0
    errors = 0
    add_raw = 0
    add_canon = 0
    add_scoped = 0
    skip_raw_existing = 0
    skip_canon_existing = 0
    skip_scoped_existing = 0

    # Per-file status tracking (for sweep report consumption)
    file_statuses: List[dict] = []

    total_files = len(unique_files)

    for i, f in enumerate(unique_files):
        if (i + 1) % 100 == 0 or i == 0:
            elapsed = time.time() - start_time
            rate = ((i + 1) / elapsed) * 60 if elapsed > 0 else 0
            print(
                f"    [{i+1}/{total_files}] {rate:.0f} files/min"
                f" | RAW+{add_raw} CANON+{add_canon}"
                + (f" SCOPED+{add_scoped}" if scoped_col else "")
            )

        tier, status = classify_tier(f["rel_path"], f["filename"], f["folder"])
        file_id_prefix = f"f_{f['hash'][:16]}"

        # Step 48: cache-aware file-level skip decision
        cache_collection_name = collection if collection else CANON_COLLECTION
        file_content_hash = f["hash"]  # full SHA-256 from dedup pass

        if use_cache and not force_rechunk:
            decision = cache.decide(f["path"], file_content_hash, cache_collection_name)

            if decision == "SKIPPED (unchanged)":
                files_skipped += 1
                files_skipped_unchanged += 1
                file_statuses.append({"filename": f["filename"], "status": decision})
                continue
            elif decision == "RE-CHUNKED (modified)":
                files_rechunked += 1
                file_statuses.append({"filename": f["filename"], "status": decision})
                # Fall through to re-chunk and ingest
            elif decision == "SKIPPED (no cache, upsert expected)":
                files_skipped_no_cache += 1
                file_statuses.append({"filename": f["filename"], "status": decision})
                # Fall through — ingest via upsert, then update cache
            else:
                # "NEW"
                files_new += 1
                file_statuses.append({"filename": f["filename"], "status": "NEW"})
                # Fall through to chunk and ingest
        elif force_rechunk:
            file_statuses.append({"filename": f["filename"], "status": "FORCE-RECHUNK"})
            files_new += 1
        else:
            # Pre-Step-48 behavior: NORMAL mode skip by RAW ID prefix
            if (not build_canon) and any(
                eid.startswith(file_id_prefix) for eid in raw_existing_ids
            ):
                files_skipped += 1
                file_statuses.append({"filename": f["filename"], "status": "SKIPPED (legacy)"})
                continue
            file_statuses.append({"filename": f["filename"], "status": "NEW (no cache)"})

        text = read_text_file(f["path"])
        if not text or len(text.strip()) < 50:
            continue

        # Guardrail: skip huge files in NORMAL mode (prevents chunk_text stalls)
        if (not build_canon) and len(text) > MAX_TEXT_CHARS_NORMAL:
            continue

        chunks = chunk_text(text)
        if not chunks:
            continue

        # Determine where to store
        if scoped_col:
            # SCOPED mode: write ONLY to the named collection, skip RAW/CANON
            store_to_raw = False
            store_to_canon = False
            store_to_scoped = True
        else:
            store_to_raw = (not build_canon)
            store_to_canon = tier in ("canon", "foundation")
            store_to_scoped = False

        # If nowhere to store, skip
        if not store_to_raw and not store_to_canon and not store_to_scoped:
            continue

        for ci, chunk in enumerate(chunks):
            chunk_id = f"{file_id_prefix}_c{ci}"

            if chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk_id)

            emb = get_embedding(chunk)
            if emb is None:
                errors += 1
                continue

            # Legacy metadata (preserved for read-side back-compat with dex_weights.py)
            md = {
                "filename": f["filename"],
                "folder": f["folder"],
                "file_type": f["extension"],   # extension string, legacy — dex_weights reads this
                "file_hash": f["hash"][:16],
                "char_count": len(chunk),
                "tier": tier,
                "status": status,
                "rel_path": f["rel_path"],     # was legacy "source_file"; renamed for STD slot
            }
            if nominated_by:
                md["nominated_by"] = nominated_by
            if collection:
                md["collection_tag"] = collection

            # STD-DDL-METADATA-001 mandatory fields — validates on construction
            std_md = build_chunk_metadata(
                source_file=f["filename"],
                source_path=os.path.abspath(f["path"]),
                source_type=infer_source_type(f["filename"], f["extension"]),
                ingest_run_id=ingest_run_id,
                chunk_index=ci,
                chunk_total=len(chunks),
            )
            md.update(std_md)

            if store_to_raw:
                if chunk_id not in raw_existing_ids:
                    try:
                        raw_col.upsert(
                            ids=[chunk_id],
                            embeddings=[emb],
                            documents=[chunk],
                            metadatas=[md],
                        )
                        raw_existing_ids.add(chunk_id)
                        add_raw += 1
                    except Exception as e:
                        print(f"    ? RAW upsert failed ({chunk_id}): {e}")
                        errors += 1
                else:
                    skip_raw_existing += 1

            if store_to_canon:
                if chunk_id not in canon_existing_ids:
                    try:
                        canon_col.upsert(
                            ids=[chunk_id],
                            embeddings=[emb],
                            documents=[chunk],
                            metadatas=[md],
                        )
                        canon_existing_ids.add(chunk_id)
                        add_canon += 1
                    except Exception as e:
                        print(f"    ? CANON upsert failed ({chunk_id}): {e}")
                        errors += 1
                else:
                    skip_canon_existing += 1

            if store_to_scoped:
                if chunk_id not in scoped_existing_ids:
                    try:
                        scoped_col.upsert(
                            ids=[chunk_id],
                            embeddings=[emb],
                            documents=[chunk],
                            metadatas=[md],
                        )
                        scoped_existing_ids.add(chunk_id)
                        add_scoped += 1
                    except Exception as e:
                        print(f"    ? SCOPED upsert failed ({chunk_id}): {e}")
                        errors += 1
                else:
                    skip_scoped_existing += 1

        # Step 48: update cache after successful file ingest
        if use_cache and len(chunks) > 0:
            source_type = infer_source_type(f["filename"], f["extension"])
            cache.update(f["path"], cache_collection_name, file_content_hash, len(chunks), source_type)

    elapsed = time.time() - start_time

    raw_count_end = raw_col.count()
    canon_count_end = canon_col.count()

    print("\n" + "=" * 60)
    print("  INGESTION COMPLETE")
    print("=" * 60)
    if use_cache:
        print(f"  Files NEW:                      {files_new}")
        print(f"  Files RE-CHUNKED (modified):    {files_rechunked}")
        print(f"  Files SKIPPED (unchanged):      {files_skipped_unchanged}")
        print(f"  Files SKIPPED (no cache/upsert):{files_skipped_no_cache}")
    else:
        print(f"  Files skipped (already in RAW): {files_skipped}")
    print(f"  New chunks added RAW:           {add_raw}")
    print(f"  New chunks added CANON:         {add_canon}")
    if scoped_col:
        print(f"  New chunks added SCOPED:        {add_scoped}  -> {collection}")
        print(f"  Chunks skipped (SCOPED exist):  {skip_scoped_existing}")
    print(f"  Chunks skipped (RAW existing):  {skip_raw_existing}")
    print(f"  Chunks skipped (CANON existing):{skip_canon_existing}")
    print(f"  Errors:                         {errors}")
    print(f"  Time: {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  DB total chunks RAW:   {raw_count_end}  (was {raw_count_start}, delta +{raw_count_end - raw_count_start})")
    print(f"  DB total chunks CANON: {canon_count_end}  (was {canon_count_start}, delta +{canon_count_end - canon_count_start}){' [approx - fast mode]' if fast else ''}")
    if scoped_col:
        scoped_end = scoped_col.count()
        print(f"  DB total chunks {collection}: {scoped_end}")
    print(f"  DB location: {CHROMA_DIR}")

    # Step 48: per-file status summary for sweep report
    if file_statuses:
        print(f"\n  Per-file status:")
        for fs in file_statuses:
            print(f"    {fs['status']:40s} {fs['filename']}")


def main() -> None:
    p = argparse.ArgumentParser(description="DEX JR RAG - Ingest")
    p.add_argument("--path", type=str, required=True, help="Archive path")
    p.add_argument("--reset", action="store_true", help="Reset collections")
    p.add_argument(
        "--build-canon",
        action="store_true",
        help="Backfill CANON only; do not expand RAW",
    )
    p.add_argument(
        "--collection",
        type=str,
        default=None,
        help="Route ingest to a named scoped collection (e.g. dex_code, ext_reference). Bypasses RAW/CANON routing.",
    )
    p.add_argument(
        "--ext-filter",
        nargs="+",
        default=None,
        help="Limit ingest to specific extensions (e.g. --ext-filter .py .cs .ts). Dot prefix required.",
    )
    p.add_argument(
        "--nominated-by",
        type=str,
        default=None,
        help="Tag chunks with nominating seat(s) for ext_ collections (e.g. '1002,1004').",
    )
    p.add_argument(
        "--fast",
        action="store_true",
        help="Skip existing ID load - use upsert directly. Faster for auto-ingest. Delta reporting approximate.",
    )
    p.add_argument(
        "--skip-backup-check",
        action="store_true",
        help="Skip Trigger 3 backup pre-flight. Use only when caller (e.g. dex-sweep.py) has already gated upstream.",
    )
    p.add_argument(
        "--force-rechunk",
        action="store_true",
        help="Bypass ingest cache. Re-chunk and upsert all files regardless of cache state.",
    )
    p.add_argument(
        "--no-ingest-cache",
        action="store_true",
        help="Disable ingest cache reads AND writes. Behaves like pre-Step-48 code.",
    )
    args = p.parse_args()

    archive = args.path
    if not os.path.isdir(archive):
        print(f"? Not a directory: {archive}")
        sys.exit(1)

    ext_filter = set(args.ext_filter) if args.ext_filter else None

    ingest(
        archive,
        reset=args.reset,
        build_canon=args.build_canon,
        fast=args.fast,
        collection=args.collection,
        ext_filter=ext_filter,
        nominated_by=args.nominated_by,
        skip_backup_check=args.skip_backup_check,
        force_rechunk=args.force_rechunk,
        no_ingest_cache=args.no_ingest_cache,
    )


if __name__ == "__main__":
    main()
