"""
dex-ingest-text.py — Plain-text ingest path for the airtight pipeline.

First caller of dex_pipeline.py helpers. Handles .txt and .md files only.
Bypasses dex-convert.py entirely (no conversion needed for plain text).

Per ADR-INGEST-PIPELINE-001 and STD-DDL-METADATA-001.

Usage:
    python dex-ingest-text.py <source_file> [--collection NAME] [--dry-run]

Defaults to --collection dex_test for safety. Real collection writes
require explicit --collection name.

Authority: ADR-INGEST-PIPELINE-001, STD-DDL-METADATA-001
"""

import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

from dex_pipeline import (
    build_chunk_metadata,
    verify_ingest,
    move_to_staging,
    DDL_INGEST_ROOT,
    VALID_SOURCE_TYPES,
)

# Chunking config — start simple, refine later
CHUNK_SIZE_CHARS = 2000  # ~500 tokens at 4 chars/token average
CHUNK_OVERLAP_CHARS = 200

# Embedding model — match the existing dex-rag setup
EMBEDDING_MODEL = "nomic-embed-text"


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_CHARS,
               overlap: int = CHUNK_OVERLAP_CHARS) -> list[str]:
    """Simple character-based chunker with overlap. Returns list of strings."""
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def get_embedding(text: str) -> list[float]:
    """Generate an embedding via Ollama. Single source of truth for embedding calls."""
    # Matches dex-ingest.py:45-46,105-113 and dex_weights.py:23,62-69
    import requests
    response = requests.post(
        "http://localhost:11434/api/embeddings",
        json={"model": EMBEDDING_MODEL, "prompt": text},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["embedding"]


def infer_source_type(filename: str) -> str:
    """Infer source_type from filename per STD-DDL-METADATA-001 §"Inference rules"."""
    name = filename
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


def ingest_text_file(
    source_path: Path,
    collection_name: str,
    dry_run: bool = False,
) -> dict:
    """
    Ingest a single plain-text file end-to-end through the pipeline.

    Returns a summary dict with keys: file, chunks_written, source_type,
    collection, verified, moved_to, dry_run.
    """
    # Step 1: Validate input
    if not source_path.exists():
        raise FileNotFoundError(f"source file does not exist: {source_path}")
    if source_path.suffix.lower() not in (".txt", ".md"):
        raise ValueError(
            f"dex-ingest-text only handles .txt and .md, got: {source_path.suffix}"
        )

    # Step 2: Read file
    text = source_path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise ValueError(f"source file is empty: {source_path}")

    # Step 3: Chunk
    chunks = chunk_text(text)
    chunk_total = len(chunks)
    print(f"  Chunked into {chunk_total} chunks")

    # Step 4: Build metadata for each chunk
    source_type = infer_source_type(source_path.name)
    ingest_run_id = f"manual_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}"
    metadatas = []
    for i in range(chunk_total):
        md = build_chunk_metadata(
            source_file=source_path.name,
            source_path=str(source_path.absolute()),
            source_type=source_type,
            ingest_run_id=ingest_run_id,
            chunk_index=i,
            chunk_total=chunk_total,
        )
        metadatas.append(md)
    print(f"  Built {len(metadatas)} metadata records (source_type={source_type})")

    # Step 5: Generate embeddings
    if dry_run:
        print(f"  [DRY RUN] would generate {chunk_total} embeddings via {EMBEDDING_MODEL}")
        embeddings = None
    else:
        print(f"  Generating {chunk_total} embeddings via {EMBEDDING_MODEL}...")
        embeddings = [get_embedding(c) for c in chunks]
        print(f"  Generated {len(embeddings)} embeddings")

    # Step 6: Write to collection
    if dry_run:
        print(f"  [DRY RUN] would write {chunk_total} chunks to {collection_name}")
        verified = None
        moved_to = None
    else:
        from dex_weights import get_client
        client = get_client()
        collection = client.get_or_create_collection(collection_name)

        ids = [f"{source_path.stem}__chunk_{i:04d}__{ingest_run_id}" for i in range(chunk_total)]

        collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        print(f"  Wrote {chunk_total} chunks to collection {collection_name}")

        # Step 7: Verify
        success, actual = verify_ingest(collection_name, source_path.name, chunk_total)
        verified = success
        if not success:
            raise RuntimeError(
                f"Verification failed: expected {chunk_total} chunks, "
                f"found {actual} for {source_path.name}"
            )
        print(f"  Verified: {actual}/{chunk_total} chunks present")

        # Step 8: Move to staging (only if source is inside DDL_Ingest)
        try:
            new_path = move_to_staging(str(source_path))
            moved_to = str(new_path)
            print(f"  Moved to: {new_path}")
        except ValueError as e:
            # File wasn't inside DDL_Ingest — ok for some test scenarios
            moved_to = None
            print(f"  Skipped move (not inside DDL_Ingest): {e}")

    return {
        "file": str(source_path),
        "chunks_written": chunk_total,
        "source_type": source_type,
        "collection": collection_name,
        "verified": verified,
        "moved_to": moved_to,
        "dry_run": dry_run,
        "ingest_run_id": ingest_run_id,
    }


def main():
    parser = argparse.ArgumentParser(description="Plain-text ingest for dex-rag pipeline")
    parser.add_argument("source", help="Path to .txt or .md file to ingest")
    parser.add_argument("--collection", default="dex_test",
                        help="Target ChromaDB collection (default: dex_test)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate and chunk only — no embeddings, no writes, no move")
    args = parser.parse_args()

    source = Path(args.source).resolve()
    print(f"Ingesting: {source}")
    print(f"Target collection: {args.collection}")
    print(f"Dry run: {args.dry_run}")
    print()

    summary = ingest_text_file(source, args.collection, dry_run=args.dry_run)

    print()
    print("─" * 60)
    print("SUMMARY")
    print("─" * 60)
    for k, v in summary.items():
        print(f"  {k:20} {v}")
    print()


if __name__ == "__main__":
    main()
