#!/usr/bin/env python
"""
ingest_mindframe_v4.py — Batch ingest MindFrame v4.0 spec files from archive.

Reads all *mindframe*v4* .txt/.md files from 99_DexUniverseArchive,
chunks them, embeds with mxbai-embed-large via the ddl-intel core,
and upserts into the ddl_intel collection.

Tier: 1 (canonical spec documents)
Status: active

Usage:
    python ingest_mindframe_v4.py --dry-run   # show what would be ingested
    python ingest_mindframe_v4.py             # actually ingest
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure chromadb path is set before importing core
os.environ.setdefault("DDLINTEL_CHROMA_DIR", r"C:\Users\dexjr\.ddl-intel\chromadb")

# Add ddl-intel to path for core imports
DDL_INTEL_ROOT = r"C:\Users\dkitc\ddl-intel"
sys.path.insert(0, DDL_INTEL_ROOT)

from core.intel_core import (
    CHUNK_OVERLAP_TOKENS,
    CHUNK_SIZE_TOKENS,
    chunk_text,
    check_ollama,
    embed_batch,
    get_chroma_client,
    get_collection,
    get_logger,
)

log = get_logger("ingest_mindframe_v4")

ARCHIVE_ROOT = Path(r"C:\Users\dexjr\99_DexUniverseArchive")
TIER = "1"
STATUS = "active"
BATCH_ID = "mindframe_v4_ingest_20260718"


def find_mindframe_v4_files() -> list[Path]:
    """Find all MindFrame v4.0 text files in the archive."""
    files = []
    for p in ARCHIVE_ROOT.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".txt", ".md"):
            continue
        name_lower = p.name.lower()
        if "mindframe" in name_lower and "v4" in name_lower:
            files.append(p)
    return sorted(files)


def read_file(path: Path) -> str | None:
    """Read a text file, trying multiple encodings."""
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=enc, errors="replace")
        except Exception:
            continue
    return None


def normalize_text(text: str) -> str:
    """Light normalization before chunking (matches ddl-intel pipeline)."""
    # Decorative separator lines
    text = re.sub(r"[-=*#~]{5,}", lambda m: m.group(0)[0] * 3, text)
    # Hex strings >= 20 chars
    text = re.sub(r"\b[0-9A-Fa-f]{20,}\b", "[hash]", text)
    return text


def make_chunk_id(file_path: Path, chunk_index: int) -> str:
    """Stable chunk ID: file hash prefix + chunk index."""
    file_hash = hashlib.md5(str(file_path).encode()).hexdigest()[:8]
    return f"mf4__{file_hash}__chunk_{chunk_index:04d}"


def ingest(dry_run: bool = False) -> None:
    """Main ingest routine."""
    files = find_mindframe_v4_files()
    print(f"Found {len(files)} MindFrame v4.0 files in archive.")

    if not files:
        print("No files found. Exiting.")
        return

    if not dry_run:
        if not check_ollama(log):
            print("ERROR: Ollama not reachable. Cannot embed.", file=sys.stderr)
            sys.exit(1)

        client = get_chroma_client()
        collection = get_collection(client)
        print(f"Collection: {collection.name}, current count: {collection.count()}")

    now = datetime.now(timezone.utc).isoformat()
    total_chunks = 0
    total_files_ingested = 0
    skipped = []
    errors = []

    for i, fpath in enumerate(files, 1):
        text = read_file(fpath)
        if not text or not text.strip():
            skipped.append((fpath, "empty"))
            continue

        text = normalize_text(text)
        chunks = chunk_text(text, CHUNK_SIZE_TOKENS, CHUNK_OVERLAP_TOKENS)

        if not chunks:
            skipped.append((fpath, "no chunks after split"))
            continue

        if dry_run:
            print(f"  [{i:3d}/{len(files)}] {fpath.name} -> {len(chunks)} chunks")
            total_chunks += len(chunks)
            total_files_ingested += 1
            continue

        # Generate IDs and metadata
        ids = [make_chunk_id(fpath, ci) for ci in range(len(chunks))]
        metadatas = [
            {
                "artifact_id": "",
                "artifact_type": "mindframe_spec",
                "file_path": str(fpath),
                "tier": TIER,
                "status": STATUS,
                "ingested_at": now,
                "chunk_index": ci,
                "chunk_total": len(chunks),
                "batch_id": BATCH_ID,
            }
            for ci in range(len(chunks))
        ]

        # Embed (batch — one vector per chunk)
        try:
            embeddings = embed_batch(chunks)
        except Exception as exc:
            errors.append((fpath, str(exc)))
            print(f"  [{i:3d}/{len(files)}] ERROR embedding {fpath.name}: {exc}")
            continue

        # Upsert
        try:
            collection.upsert(
                ids=ids,
                documents=chunks,
                embeddings=embeddings,
                metadatas=metadatas,
            )
        except Exception as exc:
            errors.append((fpath, str(exc)))
            print(f"  [{i:3d}/{len(files)}] ERROR upserting {fpath.name}: {exc}")
            continue

        total_chunks += len(chunks)
        total_files_ingested += 1
        print(f"  [{i:3d}/{len(files)}] {fpath.name} -> {len(chunks)} chunks [OK]")

    print(f"\n{'DRY RUN ' if dry_run else ''}COMPLETE:")
    print(f"  Files ingested: {total_files_ingested}/{len(files)}")
    print(f"  Total chunks: {total_chunks}")
    print(f"  Skipped: {len(skipped)}")
    print(f"  Errors: {len(errors)}")

    if skipped:
        print("\n  Skipped files:")
        for fp, reason in skipped:
            print(f"    {fp.name}: {reason}")

    if errors:
        print("\n  Errors:")
        for fp, err in errors:
            print(f"    {fp.name}: {err}")

    if not dry_run and total_chunks > 0:
        final_count = collection.count()
        print(f"\n  Collection count after ingest: {final_count}")
        print(f"  Batch ID for rollback: {BATCH_ID}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ingest MindFrame v4.0 archive into ddl_intel")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be ingested")
    args = parser.parse_args()
    ingest(dry_run=args.dry_run)
