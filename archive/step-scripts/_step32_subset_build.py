"""Step 32 — build subset test collection with mxbai-embed-large.

Read-only against live collections. Creates a NEW collection
`dex_canon_mxbai_test` with re-embedded chunks. No live-collection
modification.
"""
from __future__ import annotations
import json
import sys
import time

import chromadb
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"
OLLAMA = "http://localhost:11434"
MXBAI = "mxbai-embed-large"
SOURCE_COL = "dex_canon"
TEST_COL = "dex_canon_mxbai_test"

SEED_TERMS = [
    "CottageHumble",
    "AccidentalIntelligence",
    "GuidedEmergence",
    "Charlie Conway",
    "Beth Epperson",
    "Mithril",
    "STD-DDL-PRIVACY-001",
    "STD-DDL-SWEEPREPORT-001",  # positive control
    "STD-DDL-BACKUP-001",        # positive control
]
PER_TERM_LIMIT = 200
TARGET_MIN = 1500
TARGET_MAX = 2500


# mxbai-embed-large has a 512-token context limit. Real tokens/char varies
# by content (code, punctuation-heavy = more tokens per char), so start
# aggressive and back off on failure.
MXBAI_MAX_CHARS = 1200


def mxbai_embed(text: str) -> list[float] | None:
    t = (text or "")[:MXBAI_MAX_CHARS]
    for trunc in (MXBAI_MAX_CHARS, 900, 600, 300):
        t2 = (text or "")[:trunc]
        try:
            r = requests.post(f"{OLLAMA}/api/embeddings",
                              json={"model": MXBAI, "prompt": t2}, timeout=60)
            if r.status_code == 200:
                return r.json()["embedding"]
        except Exception:
            continue
    return None  # skip this chunk


def main():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    src = client.get_collection(SOURCE_COL)

    print("=" * 60)
    print("Step 32 — subset build")
    print("=" * 60)

    # 1. Collect candidate chunk ids per seed term.
    selected_ids: list[str] = []
    seen: set[str] = set()
    term_counts: dict[str, int] = {}
    for term in SEED_TERMS:
        try:
            got = src.get(where_document={"$contains": term},
                          limit=PER_TERM_LIMIT, include=[])
        except Exception as e:
            print(f"  [warn] $contains failed for {term!r}: {e}")
            term_counts[term] = 0
            continue
        ids = got.get("ids", []) or []
        new = [i for i in ids if i not in seen]
        for i in new:
            seen.add(i)
            selected_ids.append(i)
        term_counts[term] = len(new)
        print(f"  term={term!r:40}  new_chunks={len(new):>5}  total={len(selected_ids)}")

    print(f"\nAfter seed-term pass: {len(selected_ids)} unique chunks")

    # 2. If under target, expand by source_file (pull all chunks from the
    #    same source_files as already-selected chunks) until we reach TARGET_MIN
    if len(selected_ids) < TARGET_MIN:
        print("  Expanding by source_file...")
        got = src.get(ids=selected_ids, include=["metadatas"])
        src_files = {
            (m or {}).get("source_file") for m in got.get("metadatas", [])
            if (m or {}).get("source_file")
        }
        src_files = [s for s in src_files if s]
        print(f"    {len(src_files)} unique source_files to expand")
        for sf in src_files:
            if len(selected_ids) >= TARGET_MAX:
                break
            try:
                expand = src.get(where={"source_file": sf},
                                 limit=100, include=[])
            except Exception:
                continue
            for i in expand.get("ids", []) or []:
                if i not in seen:
                    seen.add(i)
                    selected_ids.append(i)
                    if len(selected_ids) >= TARGET_MAX:
                        break
        print(f"    after expansion: {len(selected_ids)} chunks")

    # Cap
    if len(selected_ids) > TARGET_MAX:
        selected_ids = selected_ids[:TARGET_MAX]
        print(f"  capped to {TARGET_MAX}")

    # 3. Fetch full data for selected ids (docs + metas)
    print(f"\nFetching full data for {len(selected_ids)} chunks...")
    # batched fetch (chroma .get() can handle many at once; safer in batches of 500)
    docs: list[str] = []
    metas: list[dict] = []
    ids_fetched: list[str] = []
    for i in range(0, len(selected_ids), 500):
        chunk_ids = selected_ids[i:i + 500]
        got = src.get(ids=chunk_ids, include=["documents", "metadatas"])
        got_ids = got.get("ids", []) or []
        got_docs = got.get("documents", []) or []
        got_metas = got.get("metadatas", []) or []
        for cid, d, m in zip(got_ids, got_docs, got_metas):
            if d is None:
                continue
            ids_fetched.append(cid)
            docs.append(d)
            metas.append(m or {})

    print(f"  fetched {len(docs)} docs")

    # 4. Create test collection (drop if exists, for idempotent reruns).
    try:
        client.delete_collection(TEST_COL)
        print(f"  dropped existing {TEST_COL}")
    except Exception:
        pass
    test_col = client.create_collection(
        TEST_COL,
        metadata={"description": "B1 subset test with mxbai-embed-large",
                  "test_only": "true"},
    )
    print(f"  created {TEST_COL}")

    # 5. Re-embed with mxbai + upsert in batches.
    print(f"\nRe-embedding with {MXBAI}...")
    t0 = time.time()
    batch = 32
    total = len(docs)
    done = 0
    skipped = 0
    for i in range(0, total, batch):
        bdocs = docs[i:i + batch]
        bids = ids_fetched[i:i + batch]
        bmetas = metas[i:i + batch]
        ok_ids, ok_docs, ok_metas, ok_embs = [], [], [], []
        for cid, d, m in zip(bids, bdocs, bmetas):
            e = mxbai_embed(d)
            if e is None:
                skipped += 1
                continue
            ok_ids.append(cid); ok_docs.append(d); ok_metas.append(m); ok_embs.append(e)
        if ok_ids:
            test_col.upsert(
                ids=ok_ids, embeddings=ok_embs, documents=ok_docs, metadatas=ok_metas,
            )
        done += len(bdocs)
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0
        print(f"  {done}/{total}  rate={rate:.1f} c/s  eta={eta:.0f}s  skipped={skipped}")

    elapsed = time.time() - t0
    rate = total / elapsed if elapsed > 0 else 0
    print("\n" + "=" * 60)
    print(f"DONE  {total} chunks  elapsed={elapsed:.0f}s  rate={rate:.2f} chunks/sec")
    print(f"Extrapolated full re-embed of 554K chunks: "
          f"{554_000 / rate / 3600:.2f} hours @ this rate")
    print("=" * 60)

    # Persist meta for audit
    out = {
        "test_collection": TEST_COL,
        "chunks": total,
        "seed_term_counts": term_counts,
        "elapsed_sec": round(elapsed, 1),
        "chunks_per_sec": round(rate, 2),
        "extrap_full_reembed_hours": round(554_000 / rate / 3600, 2) if rate > 0 else None,
        "model": MXBAI,
    }
    with open("_step32_subset_build.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
