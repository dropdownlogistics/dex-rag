import argparse
import requests
import chromadb
from dex_weights import weighted_query, print_weight_stats

# Force the DB path to the real database we already built
CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"

# Ollama embeddings endpoint (must match ingest)
OLLAMA_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"
DEFAULT_TOP_N = 5

def get_embedding(text: str):
    r = requests.post(
        OLLAMA_URL,
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=60
    )
    r.raise_for_status()
    return r.json()["embedding"]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N)
    parser.add_argument("--raw", action="store_true", help="Search RAW archive instead of canon (unweighted)")
    parser.add_argument("--external", action="store_true", help="Include ext_canon and ext_archive in search")
    parser.add_argument("--stats", action="store_true", help="Show DB stats")
    parser.add_argument("--weight-stats", action="store_true", help="Show source weight table and exit")
    args = parser.parse_args()

    # Weight table — no DB needed
    if args.weight_stats:
        print_weight_stats()
        return

    # DB stats — open client here only
    if args.stats:
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        canon   = client.get_collection("dex_canon").count()
        archive = client.get_collection("ddl_archive").count()
        print("\n================ DATABASE STATS ================")
        print("Canon chunks:   ", canon)
        print("Archive chunks: ", archive)
        try:
            ext_canon   = client.get_collection("ext_canon").count()
            ext_archive = client.get_collection("ext_archive").count()
            print("ExtCanon chunks:  ", ext_canon)
            print("ExtArchive chunks:", ext_archive)
        except Exception:
            print("ExtCanon / ExtArchive: not yet created")
        print("DB path:", CHROMA_DIR)
        print("================================================\n")
        return

    if not args.query:
        print("Please provide a query.")
        return

    # --raw: legacy unweighted single-collection path
    if args.raw:
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        collection = client.get_collection("ddl_archive")
        embedding = get_embedding(args.query)
        results = collection.query(
            query_embeddings=[embedding],
            n_results=args.top,
            include=["documents", "metadatas", "distances"]
        )
        hits = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        ):
            hits.append({"text": doc, "metadata": meta, "distance": dist})

        print(f"\n{'='*60}")
        print(f" QUERY: {args.query}  [RAW ARCHIVE — unweighted]")
        print(f" Results: {len(hits)}")
        print(f"{'='*60}\n")
        for i, h in enumerate(hits, 1):
            meta = h["metadata"] or {}
            print(f"[{i}] distance={h['distance']:.4f}")
            if "source_file" in meta:
                print("file:", meta["source_file"])
            print(h["text"][:400])
            print("\n" + "-"*60 + "\n")
        return

    # Weighted query (default)
    results = weighted_query(
        query_text=args.query,
        n_results=args.top,
        include_external=args.external
    )

    # Provenance summary
    label_counts: dict[str, int] = {}
    for r in results:
        label = r["label"]
        label_counts[label] = label_counts.get(label, 0) + 1
    provenance_parts = [f"{count}×{label}" for label, count in sorted(label_counts.items())]
    provenance = " | ".join(provenance_parts)

    print(f"\n{'='*60}")
    print(f" QUERY: {args.query}")
    print(f" Results: {len(results)}  [{provenance}]")
    print(f"{'='*60}\n")

    for i, r in enumerate(results, 1):
        print(f"[{i}] score={r['weighted_score']:.4f}  weight={r['weight']:.3f}  [{r['label']}]")
        meta = r["metadata"] or {}
        if "source_file" in meta:
            print("file:", meta["source_file"])
        if r.get("file_type"):
            print("type:", r["file_type"])
        print(r["document"][:400])
        print("\n" + "-"*60 + "\n")

    print("DB location:", CHROMA_DIR)

if __name__ == "__main__":
    main()
