"""Step 33a — 3-way comparative retrieval: nomic vs mxbai vs mxbai+rechunk."""
from __future__ import annotations
import json
import sys

import chromadb
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"
OLLAMA = "http://localhost:11434"
NOMIC = "nomic-embed-text"
MXBAI = "mxbai-embed-large"
TOP_K = 5
MAX_CHARS_MXBAI = 1200

COLLECTIONS = [
    ("nomic_original", "dex_canon", NOMIC),
    ("mxbai_original", "dex_canon_mxbai_test", MXBAI),
    ("mxbai_rechunk",  "dex_canon_mxbai_rechunk_test", MXBAI),
]

QUERIES = [
    ("id_sweep",    "STD-DDL-SWEEPREPORT-001 protocol classification predicate", "STD-DDL-SWEEPREPORT-001"),
    ("id_cap",      "CR-OPERATOR-CAPACITY-001",                                  "CR-OPERATOR-CAPACITY-001"),
    ("accidental",  "What is AccidentalIntelligence?",                           "AccidentalIntelligence"),
    ("emergence",   "Explain the GuidedEmergence pattern",                       "GuidedEmergence"),
    ("cottage",     "What does CottageHumble mean?",                             "CottageHumble"),
    ("charlie",     "What is the Charlie Conway Principle?",                     "Charlie Conway"),
    ("beth",        "Who is Beth Epperson?",                                     "Beth Epperson"),
    ("mithril",     "What is the Mithril Standard about?",                       "Mithril"),
    ("struct",      "What are the three conditions in STD-DDL-SWEEPREPORT-001's classification predicate?",
                    "CLASSIFICATION PREDICATE"),
]


def embed(model: str, text: str) -> list[float]:
    if model == MXBAI:
        text = text[:MAX_CHARS_MXBAI]
    r = requests.post(f"{OLLAMA}/api/embeddings",
                      json={"model": model, "prompt": text}, timeout=60)
    r.raise_for_status()
    return r.json()["embedding"]


def main():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    results: list[dict] = []

    cols = {}
    for label, cname, model in COLLECTIONS:
        c = client.get_collection(cname)
        cols[label] = c
        print(f"{label:20} col={cname:35} chunks={c.count():>8,}  model={model}")

    for qlabel, q, key in QUERIES:
        row = {"label": qlabel, "query": q, "key": key, "per_col": {}}
        print(f"\n[{qlabel}]  q={q!r}")
        for clabel, cname, model in COLLECTIONS:
            e = embed(model, q)
            r = cols[clabel].query(query_embeddings=[e], n_results=TOP_K,
                                   include=["documents", "metadatas", "distances"])
            docs = r["documents"][0]
            metas = r["metadatas"][0]
            dists = r["distances"][0]
            srcs = [(m or {}).get("source_file", "<?>") for m in metas]
            recall = any(key in (d or "") for d in docs)
            row["per_col"][clabel] = {
                "top_1_dist": round(float(dists[0]), 4),
                "top_srcs": srcs,
                "key_in_top5": recall,
            }
            flag = "OK" if recall else "--"
            print(f"  {clabel:20} dist={dists[0]:>9.4f}  recall={flag}")
            for s in srcs:
                print(f"     - {s}")
        results.append(row)

    # Summary — compare mxbai_rechunk vs mxbai_original
    same = lt = better = 0
    for r in results:
        a = r["per_col"]["mxbai_original"]["key_in_top5"]
        b = r["per_col"]["mxbai_rechunk"]["key_in_top5"]
        if a == b:
            same += 1
        elif b and not a:
            better += 1
        else:
            lt += 1
    nomic_ok = sum(r["per_col"]["nomic_original"]["key_in_top5"] for r in results)
    mxbai_ok = sum(r["per_col"]["mxbai_original"]["key_in_top5"] for r in results)
    rechunk_ok = sum(r["per_col"]["mxbai_rechunk"]["key_in_top5"] for r in results)

    print("\n" + "=" * 70)
    print(f"SUMMARY  n_queries={len(results)}")
    print(f"  nomic_original   recall: {nomic_ok}/{len(results)}")
    print(f"  mxbai_original   recall: {mxbai_ok}/{len(results)}")
    print(f"  mxbai_rechunk    recall: {rechunk_ok}/{len(results)}")
    print(f"  rechunk vs mxbai_original: same={same} better={better} worse={lt}")
    print("=" * 70)

    with open("_step33a_comparative_test.json", "w", encoding="utf-8") as f:
        json.dump({
            "queries": results,
            "summary": {
                "nomic_ok": nomic_ok, "mxbai_ok": mxbai_ok, "rechunk_ok": rechunk_ok,
                "rechunk_vs_mxbai_same": same, "better": better, "worse": lt,
            }
        }, f, indent=2)


if __name__ == "__main__":
    main()
