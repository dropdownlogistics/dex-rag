"""
dex_weights.py v1.3
Source weighting and ranked retrieval for Dex Jr.'s multi-collection corpus.
v1.1: Uses requests instead of ollama library for embeddings
v1.2: Fixed score_result formula for L2 distance scale
v1.3: Step 49 — env-gated mxbai + _v2 suffix, remove phantom collections

WEIGHT TIERS:
  Tier 1 (0.99) — dex_canon council_review
  Tier 2 (0.90) — dex_canon all other file types
  Tier 3 (0.85) — dex_code, ext_creator
  Tier 4 (0.75) — ext_reference
  Tier 5 (0.65) — ddl_archive (raw historical)
"""

import os
import chromadb
import requests
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────

CHROMA_PATH      = r"C:\Users\dkitc\.dex-jr\chromadb"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"

# Step 49: env-gated, matching dex_jr_query.py pattern
EMBED_MODEL = os.environ.get("DEXJR_EMBED_MODEL", "mxbai-embed-large")
COLLECTION_SUFFIX = os.environ.get("DEXJR_COLLECTION_SUFFIX", "_v2")

# Adaptive truncation levels for mxbai-embed-large (512-token context)
EMBED_TRUNC_LEVELS = (1200, 900, 600, 300)

# Base collection names (logical identifiers). Suffix applied at query time.
# Step 49: ext_canon and ext_archive removed — never existed in live DB.
COLLECTIONS = {
    "dex_canon":     {"base_weight": 0.90, "label": "Canon"},
    "ddl_archive":   {"base_weight": 0.65, "label": "Archive"},
    "dex_code":      {"base_weight": 0.85, "label": "Code"},
    "ext_creator":   {"base_weight": 0.85, "label": "ExtCreator"},
    "ext_reference": {"base_weight": 0.75, "label": "ExtReference"},
}

def _suffixed(name: str) -> str:
    """Apply collection suffix to a base name."""
    return name + COLLECTION_SUFFIX

FILE_TYPE_WEIGHTS = {
    "council_review": 1.10,
    "standard":       1.08,
    "protocol":       1.08,
    "deliberation":   1.06,
    "calibration":    1.05,
    "canon_doc":      1.03,
    "external_web":   1.00,
    "text_message":   0.90,
    "ios_note":       0.92,
    "thread_export":  0.88,
}

# ── ChromaDB ──────────────────────────────────────────────────────────────────

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
    """Embed text with adaptive truncation for mxbai-embed-large."""
    last_err: Exception | None = None
    for lim in EMBED_TRUNC_LEVELS:
        prompt = (text or "")[:lim]
        try:
            r = requests.post(
                OLLAMA_EMBED_URL,
                json={"model": EMBED_MODEL, "prompt": prompt},
                timeout=60,
            )
            if r.status_code == 200:
                return r.json()["embedding"]
            last_err = requests.HTTPError(
                f"{r.status_code} at trunc={lim}: {r.text[:200]}"
            )
        except requests.RequestException as e:
            last_err = e
    if last_err:
        raise last_err
    raise RuntimeError("embed: unreachable")

# ── Weight calculation ────────────────────────────────────────────────────────

def calculate_weight(collection_name: str, metadata: dict) -> float:
    # Strip suffix for COLLECTIONS lookup (caller may pass suffixed name)
    base_name = collection_name
    if COLLECTION_SUFFIX and base_name.endswith(COLLECTION_SUFFIX):
        base_name = base_name[:-len(COLLECTION_SUFFIX)]
    base      = COLLECTIONS.get(base_name, {}).get("base_weight", 0.65)
    file_type = metadata.get("file_type", "").lower()
    type_mult = FILE_TYPE_WEIGHTS.get(file_type, 1.00)

    filename = metadata.get("filename", "").lower()
    source   = metadata.get("source_file", "").lower()

    # Pattern-based type detection if file_type not set cleanly
    if file_type == "" or file_type not in FILE_TYPE_WEIGHTS:
        if any(x in filename for x in ["cr-llms", "cr-site", "cr-ops", "cr-infra", "cr-nuet"]):
            type_mult = FILE_TYPE_WEIGHTS["council_review"]
        elif any(x in filename for x in ["std-", "pro-c2d", "pro-"]):
            type_mult = FILE_TYPE_WEIGHTS["protocol"]
        elif any(x in source for x in ["98_threads", "thread"]):
            type_mult = FILE_TYPE_WEIGHTS["thread_export"]
        elif any(x in source for x in ["note", "ios_note"]):
            type_mult = FILE_TYPE_WEIGHTS["ios_note"]

    status       = metadata.get("status", "").lower()
    status_bonus = 1.02 if status in ("governed", "ratified", "canon") else 1.00

    return base * type_mult * status_bonus


def score_result(distance: float, weight: float) -> float:
    """
    Convert L2 distance to weighted similarity score.
    Uses 1/(1+distance) — works at any distance scale.
    Higher score = better match.
    """
    similarity = 1.0 / (1.0 + distance)
    return round(similarity * weight, 6)

# ── Core weighted query ───────────────────────────────────────────────────────

def weighted_query(
    query_text: str,
    n_results: int = 5,
    include_external: bool = False,
    collections: Optional[list] = None,
    where_filter: Optional[dict] = None
) -> list[dict]:
    client          = get_client()
    query_embedding = embed(query_text)

    if collections:
        target_collections = collections
    else:
        # 4 live collections by default; ext_reference added with --external
        target_collections = [_suffixed(c) for c in ["dex_canon", "ddl_archive", "dex_code", "ext_creator"]]
        if include_external:
            target_collections.append(_suffixed("ext_reference"))

    fetch_per_collection = max(n_results * 3, 15)
    all_results = []

    for coll_name in target_collections:
        if not collection_exists(client, coll_name):
            continue
        try:
            collection   = client.get_collection(coll_name)
            query_kwargs = {
                "query_embeddings": [query_embedding],
                "n_results":        fetch_per_collection,
                "include":          ["documents", "metadatas", "distances"]
            }
            if where_filter:
                query_kwargs["where"] = where_filter

            raw       = collection.query(**query_kwargs)
            docs      = raw["documents"][0]
            metas     = raw["metadatas"][0]
            distances = raw["distances"][0]

            for doc, meta, dist in zip(docs, metas, distances):
                weight  = calculate_weight(coll_name, meta)
                w_score = score_result(dist, weight)
                # Strip suffix for label lookup
                base_n = coll_name[:-len(COLLECTION_SUFFIX)] if COLLECTION_SUFFIX and coll_name.endswith(COLLECTION_SUFFIX) else coll_name
                label   = COLLECTIONS.get(base_n, {}).get("label", coll_name)
                all_results.append({
                    "document":       doc,
                    "metadata":       meta,
                    "collection":     coll_name,
                    "label":          label,
                    "distance":       round(dist, 4),
                    "weight":         round(weight, 4),
                    "weighted_score": w_score,
                    "source":         meta.get("source_file", ""),
                    "filename":       meta.get("filename", ""),
                    "file_type":      meta.get("file_type", ""),
                })
        except Exception as e:
            print(f"  [WARN] Collection '{coll_name}' query failed: {e}")
            continue

    all_results.sort(key=lambda x: x["weighted_score"], reverse=True)
    return all_results[:n_results]


def weighted_query_with_provenance(
    query_text: str,
    n_results: int = 5,
    include_external: bool = False
) -> tuple[list[dict], str]:
    results = weighted_query(query_text, n_results, include_external)

    label_counts: dict[str, int] = {}
    for r in results:
        label_counts[r["label"]] = label_counts.get(r["label"], 0) + 1

    parts      = [f"{count}×{label}" for label, count in sorted(label_counts.items())]
    provenance = f"[Sources: {' | '.join(parts)}]"

    return results, provenance

# ── Stats ─────────────────────────────────────────────────────────────────────

def print_weight_stats():
    print(f"\n  DEX JR. SOURCE WEIGHT TABLE  (model={EMBED_MODEL}, suffix={COLLECTION_SUFFIX})")
    print("  " + "="*65)
    print(f"  {'Collection':<20} {'File Type':<20} {'Weight':>8}")
    print("  " + "-"*65)

    for coll, cconf in COLLECTIONS.items():
        base = cconf["base_weight"]
        display = _suffixed(coll)
        for ftype, mult in sorted(FILE_TYPE_WEIGHTS.items(), key=lambda x: -x[1]):
            effective = round(base * mult, 4)
            print(f"  {display:<20} {ftype:<20} {effective:>8.4f}")
        print()

# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Weighted query against Dex Jr. corpus")
    parser.add_argument("query",      nargs="?", help="Search query")
    parser.add_argument("--n",        type=int, default=5, help="Number of results")
    parser.add_argument("--external", action="store_true", help="Include external collections")
    parser.add_argument("--stats",    action="store_true", help="Show weight table")
    args = parser.parse_args()

    if args.stats:
        print_weight_stats()
        sys.exit(0)

    if not args.query:
        print("Usage: python dex_weights.py \"your query\" [--n 5] [--external]")
        sys.exit(1)

    results, provenance = weighted_query_with_provenance(
        args.query, n_results=args.n, include_external=args.external
    )

    print(f"\n  Query: {args.query}")
    print(f"  {provenance}\n")

    for i, r in enumerate(results, 1):
        print(f"  [{i}] Score: {r['weighted_score']:.4f} | "
              f"Weight: {r['weight']:.3f} | "
              f"Dist: {r['distance']:.2f} | "
              f"Collection: {r['label']}")
        print(f"      File: {r['filename']}")
        print(f"      {r['document'][:200].strip()}")
        print()



