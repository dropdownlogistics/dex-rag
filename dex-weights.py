"""
dex-weights.py v1.0
Source weighting and ranked retrieval for Dex Jr.'s multi-collection corpus.

PROBLEM SOLVED:
  Without weighting, a casual text message outranks a council review
  on the same topic because keyword density wins. This module applies
  tier-based weights so governed documents outrank raw archive material.

WEIGHT TIERS:
  Tier 1 (1.00) — dex_canon, file_type=council_review or standard or protocol
  Tier 2 (0.90) — dex_canon, all other file types
  Tier 3 (0.80) — ext_canon (vetted external reference)
  Tier 4 (0.65) — ddl_archive (raw historical, unreviewed)
  Tier 5 (0.50) — ext_archive (unvetted external)

HOW IT WORKS:
  ChromaDB returns distance scores (lower = more similar).
  We convert distance to similarity (1 - distance), apply
  the tier weight, and re-rank. Result: governed documents
  beat raw noise on equal semantic ground.

USAGE IN dex-query.py and dex-bridge.py:
  from dex_weights import weighted_query

  results = weighted_query(
      query_text="Munger cognitive biases",
      n_results=5,
      include_external=False
  )

  for r in results:
      print(r['document'])
      print(r['source'], r['tier'], r['weighted_score'])
"""

import chromadb
import ollama
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────

CHROMA_PATH  = r"C:\Users\dkitc.dex-jr\chromadb"
EMBED_MODEL  = "nomic-embed-text"

# Collection names
COLLECTIONS = {
    "dex_canon":   {"base_weight": 0.90, "label": "Canon"},
    "ddl_archive": {"base_weight": 0.65, "label": "Archive"},
    "ext_canon":   {"base_weight": 0.80, "label": "ExtCanon"},
    "ext_archive": {"base_weight": 0.50, "label": "ExtArchive"},
}

# File type boosts applied on top of base collection weight
FILE_TYPE_WEIGHTS = {
    "council_review": 1.10,
    "standard":       1.08,
    "protocol":       1.08,
    "deliberation":   1.06,
    "calibration":    1.05,
    "canon_doc":      1.03,
    "external_web":   1.00,  # neutral
    "text_message":   0.90,  # demote casual texts
    "ios_note":       0.92,
    "thread_export":  0.88,
}

# ── ChromaDB setup ────────────────────────────────────────────────────────────

def get_client():
    return chromadb.PersistentClient(path=CHROMA_PATH)

def collection_exists(client, name: str) -> bool:
    try:
        client.get_collection(name)
        return True
    except Exception:
        return False

# ── Embedding ─────────────────────────────────────────────────────────────────

def embed(text: str) -> list[float]:
    response = ollama.embeddings(model=EMBED_MODEL, prompt=text)
    return response["embedding"]

# ── Weight calculation ────────────────────────────────────────────────────────

def calculate_weight(collection_name: str, metadata: dict) -> float:
    """
    Returns final weight for a chunk based on:
    1. Collection base weight
    2. File type multiplier
    3. Status bonus (governed/ratified docs get small boost)
    """
    base = COLLECTIONS.get(collection_name, {}).get("base_weight", 0.65)

    file_type = metadata.get("file_type", "").lower()
    type_mult = FILE_TYPE_WEIGHTS.get(file_type, 1.00)

    # Detect council reviews and governance docs from filename patterns
    filename = metadata.get("filename", "").lower()
    source   = metadata.get("source_file", "").lower()

    # Pattern-based type detection (if file_type not set cleanly)
    if file_type == "" or file_type not in FILE_TYPE_WEIGHTS:
        if any(x in filename for x in ["cr-llms", "cr-site", "cr-ops", "cr-infra", "cr-nuet"]):
            type_mult = FILE_TYPE_WEIGHTS["council_review"]
        elif any(x in filename for x in ["std-", "pro-c2d", "pro-"]):
            type_mult = FILE_TYPE_WEIGHTS["protocol"]
        elif any(x in source for x in ["98_threads", "thread"]):
            type_mult = FILE_TYPE_WEIGHTS["thread_export"]
        elif any(x in source for x in ["note", "ios_note"]):
            type_mult = FILE_TYPE_WEIGHTS["ios_note"]

    # Status bonus: ratified/governed docs
    status = metadata.get("status", "").lower()
    status_bonus = 1.02 if status in ("governed", "ratified", "canon") else 1.00

    return base * type_mult * status_bonus


def score_result(distance: float, weight: float) -> float:
    """
    Convert ChromaDB distance to weighted similarity score.
    ChromaDB cosine distance: 0 = identical, 2 = opposite.
    Similarity = 1 - (distance / 2), then apply weight.
    """
    similarity = max(0.0, 1.0 - (distance / 2.0))
    return round(similarity * weight, 6)

# ── Core weighted query ───────────────────────────────────────────────────────

def weighted_query(
    query_text: str,
    n_results: int = 5,
    include_external: bool = False,
    collections: Optional[list[str]] = None,
    where_filter: Optional[dict] = None
) -> list[dict]:
    """
    Query multiple collections, apply tier-based weights, re-rank, return top N.

    Args:
        query_text:       The search query
        n_results:        How many results to return (after re-ranking)
        include_external: Include ext_canon and ext_archive in search
        collections:      Override which collections to query
        where_filter:     ChromaDB metadata filter (optional)

    Returns:
        List of result dicts, sorted by weighted_score descending.
        Each dict: document, metadata, collection, distance,
                   weighted_score, weight, label
    """
    client = get_client()
    query_embedding = embed(query_text)

    # Determine which collections to query
    if collections:
        target_collections = collections
    else:
        target_collections = ["dex_canon", "ddl_archive"]
        if include_external:
            target_collections += ["ext_canon", "ext_archive"]

    # Fetch more than n_results per collection so re-ranking has material to work with
    fetch_per_collection = max(n_results * 3, 15)

    all_results = []

    for coll_name in target_collections:
        if not collection_exists(client, coll_name):
            continue
        try:
            collection = client.get_collection(coll_name)
            query_kwargs = {
                "query_embeddings": [query_embedding],
                "n_results": fetch_per_collection,
                "include": ["documents", "metadatas", "distances"]
            }
            if where_filter:
                query_kwargs["where"] = where_filter

            raw = collection.query(**query_kwargs)

            docs      = raw["documents"][0]
            metas     = raw["metadatas"][0]
            distances = raw["distances"][0]

            for doc, meta, dist in zip(docs, metas, distances):
                weight   = calculate_weight(coll_name, meta)
                w_score  = score_result(dist, weight)
                label    = COLLECTIONS.get(coll_name, {}).get("label", coll_name)
                all_results.append({
                    "document":       doc,
                    "metadata":       meta,
                    "collection":     coll_name,
                    "label":          label,
                    "distance":       round(dist, 6),
                    "weight":         round(weight, 4),
                    "weighted_score": w_score,
                    "source":         meta.get("source_file", ""),
                    "filename":       meta.get("filename", ""),
                    "file_type":      meta.get("file_type", ""),
                })
        except Exception as e:
            print(f"  [WARN] Collection '{coll_name}' query failed: {e}")
            continue

    # Re-rank by weighted score, return top N
    all_results.sort(key=lambda x: x["weighted_score"], reverse=True)
    return all_results[:n_results]


def weighted_query_with_provenance(
    query_text: str,
    n_results: int = 5,
    include_external: bool = False
) -> tuple[list[dict], str]:
    """
    Same as weighted_query, plus a provenance summary string
    for injection into AutoCouncil/bridge responses.

    Returns: (results, provenance_string)

    Provenance string example:
      [Sources: 3×Canon | 1×Archive | 1×ExtCanon]
    """
    results = weighted_query(query_text, n_results, include_external)

    # Count by label
    label_counts: dict[str, int] = {}
    for r in results:
        label = r["label"]
        label_counts[label] = label_counts.get(label, 0) + 1

    parts = [f"{count}×{label}" for label, count in sorted(label_counts.items())]
    provenance = f"[Sources: {' | '.join(parts)}]"

    return results, provenance

# ── Stats ─────────────────────────────────────────────────────────────────────

def print_weight_stats():
    """Show effective weight ranges for each collection/type combination."""
    print("\n  DEX JR. SOURCE WEIGHT TABLE")
    print("  " + "="*55)
    print(f"  {'Collection':<15} {'File Type':<20} {'Weight':>8}")
    print("  " + "-"*55)

    for coll, cconf in COLLECTIONS.items():
        base = cconf["base_weight"]
        for ftype, mult in sorted(FILE_TYPE_WEIGHTS.items(), key=lambda x: -x[1]):
            effective = round(base * mult, 4)
            print(f"  {coll:<15} {ftype:<20} {effective:>8.4f}")
        print()

# ── CLI (optional standalone use) ─────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys

    parser = argparse.ArgumentParser(description="Weighted query against Dex Jr. corpus")
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--n", type=int, default=5, help="Number of results")
    parser.add_argument("--external", action="store_true", help="Include external collections")
    parser.add_argument("--stats", action="store_true", help="Show weight table")
    args = parser.parse_args()

    if args.stats:
        print_weight_stats()
        sys.exit(0)

    if not args.query:
        print("Usage: python dex-weights.py \"your query\" [--n 5] [--external]")
        sys.exit(1)

    results, provenance = weighted_query_with_provenance(
        args.query, n_results=args.n, include_external=args.external
    )

    print(f"\n  Query: {args.query}")
    print(f"  {provenance}\n")

    for i, r in enumerate(results, 1):
        print(f"  [{i}] Score: {r['weighted_score']:.4f} | "
              f"Weight: {r['weight']:.3f} | "
              f"Collection: {r['label']}")
        print(f"      File: {r['filename']}")
        print(f"      Type: {r['file_type']}")
        print(f"      {r['document'][:200].strip()}")
        print()
