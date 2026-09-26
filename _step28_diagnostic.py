"""Step 28 diagnostic — retrieval quality deep-dive (investigation only)."""
from __future__ import annotations
import json
import math
import sys

import chromadb
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"
OLLAMA = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"
TARGET_FILE = "STD-DDL-SWEEPREPORT-001.txt"


def embed(text: str) -> list[float]:
    r = requests.post(f"{OLLAMA}/api/embeddings",
                      json={"model": EMBED_MODEL, "prompt": text}, timeout=60)
    r.raise_for_status()
    return r.json()["embedding"]


def l2(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def l2sq(a: list[float], b: list[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


def cos_dist(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return 1 - (dot / (na * nb))


def main():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    col = client.get_collection("dex_canon")

    print("=" * 70)
    print("STEP 28 — Retrieval Quality Diagnostic")
    print("=" * 70)

    # ── Pull the 5 known chunks (and their stored embeddings) ──
    got = col.get(where={"source_file": TARGET_FILE},
                  include=["documents", "metadatas", "embeddings"])
    ids = got["ids"]
    docs = got["documents"]
    metas = got["metadatas"]
    embs = got["embeddings"]
    print(f"\nTarget file: {TARGET_FILE}")
    print(f"Chunks retrieved: {len(ids)}")
    for i, (cid, doc) in enumerate(zip(ids, docs)):
        head = (doc[:160] or "").replace("\n", " ")
        print(f"  [{i}] id={cid[:24]}...  len={len(doc)}  head={head!r}")

    # Collection distance metric
    cmeta = col.metadata or {}
    print(f"\nCollection metadata: {cmeta}")
    print("(Chroma default space is L2 if hnsw:space not set)")

    # ── A1: direct proximity test ──
    print("\n" + "=" * 70)
    print("A1 — Direct proximity: query vs known 5 chunks")
    print("=" * 70)
    queries = [
        ("id_only",         "STD-DDL-SWEEPREPORT-001"),
        ("key_phrase",      "classification predicate ingest report"),
        ("conceptual",      "sweep report protocol"),
        ("exact_quote",     "A file is an ingest report IF AND ONLY IF"),
        ("colloquial",      "skip-if-reports-only logic"),
    ]
    results = {}
    for label, q in queries:
        qemb = embed(q)
        per_chunk = []
        for i, ce in enumerate(embs):
            per_chunk.append({
                "chunk_idx": i,
                "l2_sq":     l2sq(qemb, ce),
                "l2":        l2(qemb, ce),
                "cos_dist":  cos_dist(qemb, ce),
            })
        # Also run chroma's native query to see where the target chunks rank
        native = col.query(query_embeddings=[qemb], n_results=20,
                           include=["distances", "metadatas"])
        native_ids = col.query(query_embeddings=[qemb], n_results=20,
                               include=["metadatas"])["ids"][0]
        target_ranks = [i for i, nid in enumerate(native_ids) if nid in ids]
        target_native_dists = [native["distances"][0][i] for i in target_ranks]
        results[label] = {
            "query": q,
            "per_chunk": per_chunk,
            "best_l2_sq": min(c["l2_sq"] for c in per_chunk),
            "best_cos":   min(c["cos_dist"] for c in per_chunk),
            "target_ranks_in_top20": target_ranks,
            "target_native_dists": target_native_dists,
            "top1_native_dist": native["distances"][0][0],
        }
        print(f"\n[{label}]  q={q!r}")
        for row in per_chunk:
            print(f"  chunk {row['chunk_idx']}  "
                  f"l2_sq={row['l2_sq']:.3f}  l2={row['l2']:.4f}  cos={row['cos_dist']:.4f}")
        print(f"  -> best l2_sq to target = {results[label]['best_l2_sq']:.3f}")
        print(f"  -> best cos to target   = {results[label]['best_cos']:.4f}")
        print(f"  -> chroma top-20: target file ranks at {target_ranks}")
        print(f"  -> chroma top-1 dist = {results[label]['top1_native_dist']:.3f}")
        if target_native_dists:
            print(f"  -> chroma dists to target chunks = "
                  f"{[round(d,3) for d in target_native_dists]}")

    # ── A2: embedding sanity ──
    print("\n" + "=" * 70)
    print("A2 — Embedding model sanity")
    print("=" * 70)

    def pair(a, b):
        ea, eb = embed(a), embed(b)
        return {
            "a": a, "b": b,
            "l2_sq": round(l2sq(ea, eb), 4),
            "l2":    round(l2(ea, eb), 4),
            "cos":   round(cos_dist(ea, eb), 4),
        }

    pairs = [
        pair("the cat sat on the mat", "the cat was on the mat"),
        pair("STD-DDL-SWEEPREPORT-001", "STD-DDL-SWEEPREPORT-001"),
        pair("STD-DDL-SWEEPREPORT-001", "STD DDL SWEEPREPORT 001"),
        pair("STD-DDL-SWEEPREPORT-001", "STD-DDL-BACKUP-001"),
        pair("STD-DDL-SWEEPREPORT-001", "Sweep Report Protocol"),
    ]
    for p in pairs:
        print(f"  {p['a']!r} <> {p['b']!r}")
        print(f"     l2_sq={p['l2_sq']}  l2={p['l2']}  cos={p['cos']}")

    # ── A3: chunker inspection (meta only; text we already have) ──
    print("\n" + "=" * 70)
    print("A3 — Chunk boundaries for STD-DDL-SWEEPREPORT-001.txt")
    print("=" * 70)
    for i, doc in enumerate(docs):
        head = (doc[:120] or "").replace("\n", " ")
        tail = (doc[-120:] or "").replace("\n", " ")
        print(f"\n[chunk {i}] len={len(doc)}")
        print(f"  HEAD: {head}")
        print(f"  TAIL: {tail}")

    # Persist for appendix
    out = {
        "queries": results,
        "sanity_pairs": pairs,
        "collection_metadata": cmeta,
        "chunker": {"CHUNK_SIZE_TOKENS": 500, "CHUNK_OVERLAP_TOKENS": 50,
                    "CHARS_PER_TOKEN": 4},
    }
    with open("_step28_diagnostic.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("\nWrote _step28_diagnostic.json")


if __name__ == "__main__":
    main()
