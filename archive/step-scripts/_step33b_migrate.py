"""Step 33b — full mxbai-embed-large migration of all 4 live collections
into _v2 twins. Resumable via _step33b_checkpoint.json.

NEVER modifies original collections. Upserts into _v2 only.
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import chromadb
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"
OLLAMA = "http://localhost:11434"
MODEL = "mxbai-embed-large"
BATCH = 8
PAGE = 2000  # paged read (avoids SQLite 32K variable limit)
TRUNC_LEVELS = (1200, 900, 600, 300)
MAX_RETRY = 3
CHECKPOINT = "_step33b_checkpoint.json"

COLLECTIONS = [
    ("ext_creator",  "ext_creator_v2"),
    ("dex_code",     "dex_code_v2"),
    ("dex_canon",    "dex_canon_v2"),
    ("ddl_archive",  "ddl_archive_v2"),
]


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_checkpoint() -> dict:
    if os.path.exists(CHECKPOINT):
        with open(CHECKPOINT, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"collections": {}, "start": iso_now()}


def save_checkpoint(cp: dict):
    tmp = CHECKPOINT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cp, f, indent=2)
    os.replace(tmp, CHECKPOINT)


def embed_batch(texts: list[str]) -> list[list[float]] | None:
    for lim in TRUNC_LEVELS:
        trimmed = [(t or "")[:lim] for t in texts]
        for attempt in range(MAX_RETRY):
            try:
                r = requests.post(f"{OLLAMA}/api/embed",
                                  json={"model": MODEL, "input": trimmed},
                                  timeout=300)
                if r.status_code == 200:
                    return r.json()["embeddings"]
                break  # non-200 -> try smaller truncation
            except requests.exceptions.RequestException:
                if attempt == MAX_RETRY - 1:
                    break
                time.sleep(1)
    return None


def migrate_collection(client, src_name: str, dst_name: str, cp: dict):
    src = client.get_collection(src_name)
    total = src.count()
    print(f"\n{'=' * 60}")
    print(f"{src_name} -> {dst_name}  total={total:,}")
    print(f"{'=' * 60}")

    # Create dst if missing; preserve/add metadata
    try:
        dst = client.get_collection(dst_name)
        print(f"  [resume] {dst_name} exists with {dst.count():,} chunks")
    except Exception:
        src_meta = src.metadata or {}
        desc = src_meta.get("description", src_name)
        dst = client.create_collection(
            dst_name,
            metadata={
                "description": f"{desc} (mxbai v2)",
                "embedding_model": MODEL,
                "chunker_version": "dex-ingest_500tok_v1",
                "parent_collection": src_name,
                "migration_step": "33b",
                "migration_start": iso_now(),
            },
        )
        print(f"  [fresh] created {dst_name}")

    col_cp = cp["collections"].setdefault(src_name, {
        "dst": dst_name,
        "offset": 0,
        "migrated": 0,
        "skipped": 0,
        "started": iso_now(),
        "completed": None,
    })
    offset = col_cp["offset"]
    migrated_start = col_cp["migrated"]
    skipped = col_cp["skipped"]

    # If already complete, skip
    if col_cp.get("completed"):
        print(f"  [done] already completed at {col_cp['completed']}")
        return

    t0 = time.time()
    while True:
        # Page the source
        try:
            page = src.get(limit=PAGE, offset=offset,
                           include=["documents", "metadatas"])
        except Exception as e:
            print(f"  ERROR reading page at offset={offset}: {e}")
            save_checkpoint(cp)
            raise
        ids = page.get("ids", []) or []
        if not ids:
            break

        docs = page.get("documents", []) or []
        metas = page.get("metadatas", []) or []

        # Batch-embed + upsert
        for i in range(0, len(ids), BATCH):
            bids = ids[i:i + BATCH]
            bdocs = docs[i:i + BATCH]
            bmetas = metas[i:i + BATCH]
            # Skip null doc rows (shouldn't happen, but defensive)
            clean_pairs = [(cid, d, m) for cid, d, m in zip(bids, bdocs, bmetas)
                           if d is not None]
            if not clean_pairs:
                continue
            b_ids_c = [p[0] for p in clean_pairs]
            b_docs_c = [p[1] for p in clean_pairs]
            b_metas_c = [(p[2] or {}) for p in clean_pairs]
            embs = embed_batch(b_docs_c)
            if embs is None:
                skipped += len(b_ids_c)
                col_cp["skipped"] = skipped
                continue
            try:
                dst.upsert(ids=b_ids_c, embeddings=embs,
                           documents=b_docs_c, metadatas=b_metas_c)
            except Exception as e:
                print(f"  upsert failed ({len(b_ids_c)} items): {e}")
                save_checkpoint(cp)
                raise
            col_cp["migrated"] += len(b_ids_c)

            # Checkpoint every batch
            if col_cp["migrated"] % (BATCH * 10) == 0:
                save_checkpoint(cp)

        offset += len(ids)
        col_cp["offset"] = offset
        col_cp["skipped"] = skipped
        save_checkpoint(cp)

        elapsed = time.time() - t0
        done_in_run = col_cp["migrated"] - migrated_start
        rate = done_in_run / elapsed if elapsed > 0 else 0
        remaining = total - col_cp["migrated"]
        eta = remaining / rate if rate > 0 else 0
        print(f"  {col_cp['migrated']:>8,}/{total:,}  "
              f"rate={rate:.1f} c/s  eta={eta/60:.1f}m  skipped={skipped}")

        if len(ids) < PAGE:
            break

    col_cp["completed"] = iso_now()
    col_cp["elapsed_sec"] = round(time.time() - t0, 1)
    save_checkpoint(cp)
    elapsed = time.time() - t0
    rate = (col_cp["migrated"] - migrated_start) / elapsed if elapsed > 0 else 0
    print(f"  DONE  {col_cp['migrated']:,} migrated  "
          f"{skipped} skipped  elapsed={elapsed/60:.1f}m  rate={rate:.1f} c/s")


def main():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    cp = load_checkpoint()
    cp.setdefault("start", iso_now())
    save_checkpoint(cp)

    t0 = time.time()
    print(f"Migration start: {iso_now()}")
    print(f"Checkpoint: {CHECKPOINT}")

    for src_name, dst_name in COLLECTIONS:
        migrate_collection(client, src_name, dst_name, cp)

    cp["completed"] = iso_now()
    cp["total_elapsed_sec"] = round(time.time() - t0, 1)
    save_checkpoint(cp)
    print(f"\n{'=' * 60}")
    print(f"ALL COLLECTIONS MIGRATED  total elapsed={cp['total_elapsed_sec']/60:.1f}m")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
