"""Step 32 — comparative retrieval test: nomic vs mxbai on 8 queries.

Read-only. Queries live `dex_canon` (nomic) and `dex_canon_mxbai_test` (mxbai)
side-by-side, reports top-5 source_files + key-term recall per query."""
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
NOMIC = "nomic-embed-text"
MXBAI = "mxbai-embed-large"
TOP_K = 5
MAX_CHARS_MXBAI = 1200


def embed(model: str, text: str) -> list[float]:
    if model == MXBAI:
        text = text[:MAX_CHARS_MXBAI]
    r = requests.post(f"{OLLAMA}/api/embeddings",
                      json={"model": model, "prompt": text}, timeout=60)
    r.raise_for_status()
    return r.json()["embedding"]


def cos_dist(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return 1 - (dot / (na * nb))


QUERIES = [
    # (label, query, key_term_for_recall_check)
    ("id_sweep", "STD-DDL-SWEEPREPORT-001 protocol classification predicate", "STD-DDL-SWEEPREPORT-001"),
    ("id_cap",   "CR-OPERATOR-CAPACITY-001",                                 "CR-OPERATOR-CAPACITY-001"),
    ("accidental","What is AccidentalIntelligence?",                          "AccidentalIntelligence"),
    ("emergence", "Explain the GuidedEmergence pattern",                      "GuidedEmergence"),
    ("cottage",   "What does CottageHumble mean?",                            "CottageHumble"),
    ("charlie",   "What is the Charlie Conway Principle?",                    "Charlie Conway"),
    ("beth",      "Who is Beth Epperson?",                                    "Beth Epperson"),
    ("mithril",   "What is the Mithril Standard about?",                      "Mithril"),
]


def main():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    nomic_col = client.get_collection("dex_canon")
    mxbai_col = client.get_collection("dex_canon_mxbai_test")
    print(f"nomic col (dex_canon): {nomic_col.count():,} chunks")
    print(f"mxbai col (dex_canon_mxbai_test): {mxbai_col.count():,} chunks")

    # A2 sanity pairs under mxbai
    print("\n" + "=" * 70)
    print("A2 sanity — mxbai-embed-large")
    print("=" * 70)
    pairs = [
        ("the cat sat on the mat", "the cat was on the mat"),
        ("STD-DDL-SWEEPREPORT-001", "STD-DDL-BACKUP-001"),
        ("STD-DDL-SWEEPREPORT-001", "STD-DDL-SWEEPREPORT-001"),
        ("STD-DDL-SWEEPREPORT-001", "STD DDL SWEEPREPORT 001"),
        ("CottageHumble", "humble surface cathedral underneath"),
    ]
    a2 = []
    for a, b in pairs:
        ea = embed(MXBAI, a)
        eb = embed(MXBAI, b)
        d = cos_dist(ea, eb)
        a2.append({"a": a, "b": b, "cos_dist": round(d, 4)})
        print(f"  {a!r:40} <> {b!r:40}  cos={d:.4f}")

    # Per-query comparison
    print("\n" + "=" * 70)
    print("Comparative retrieval")
    print("=" * 70)
    results = []
    for label, q, key_term in QUERIES:
        row = {"label": label, "query": q, "key_term": key_term}
        # nomic side
        en = embed(NOMIC, q)
        r_n = nomic_col.query(query_embeddings=[en], n_results=TOP_K,
                              include=["documents", "metadatas", "distances"])
        n_docs = r_n["documents"][0]
        n_metas = r_n["metadatas"][0]
        n_dists = r_n["distances"][0]
        n_srcs = [(m or {}).get("source_file", "<?>") for m in n_metas]
        n_recall = any(key_term in (d or "") for d in n_docs)
        row["nomic_top5"] = n_srcs
        row["nomic_best_dist"] = round(float(n_dists[0]), 3)
        row["nomic_key_term_in_top5"] = n_recall

        # mxbai side
        em = embed(MXBAI, q)
        r_m = mxbai_col.query(query_embeddings=[em], n_results=TOP_K,
                              include=["documents", "metadatas", "distances"])
        m_docs = r_m["documents"][0]
        m_metas = r_m["metadatas"][0]
        m_dists = r_m["distances"][0]
        m_srcs = [(m or {}).get("source_file", "<?>") for m in m_metas]
        m_recall = any(key_term in (d or "") for d in m_docs)
        row["mxbai_top5"] = m_srcs
        row["mxbai_best_dist"] = round(float(m_dists[0]), 3)
        row["mxbai_key_term_in_top5"] = m_recall

        print(f"\n[{label}]  q={q!r}  key_term={key_term!r}")
        print(f"  nomic top-1 dist={row['nomic_best_dist']}  key_term_in_top5={n_recall}")
        for s in n_srcs:
            print(f"    nomic: {s}")
        print(f"  mxbai top-1 dist={row['mxbai_best_dist']}  key_term_in_top5={m_recall}")
        for s in m_srcs:
            print(f"    mxbai: {s}")

        results.append(row)

    # Summary
    wins_m = sum(1 for r in results if r["mxbai_key_term_in_top5"] and not r["nomic_key_term_in_top5"])
    wins_n = sum(1 for r in results if r["nomic_key_term_in_top5"] and not r["mxbai_key_term_in_top5"])
    both = sum(1 for r in results if r["nomic_key_term_in_top5"] and r["mxbai_key_term_in_top5"])
    neither = sum(1 for r in results if not r["nomic_key_term_in_top5"] and not r["mxbai_key_term_in_top5"])
    print("\n" + "=" * 70)
    print(f"SUMMARY  n_queries={len(results)}")
    print(f"  both retrieved key term: {both}")
    print(f"  only mxbai retrieved:    {wins_m}")
    print(f"  only nomic retrieved:    {wins_n}")
    print(f"  neither retrieved:       {neither}")
    print("=" * 70)

    with open("_step32_comparative_test.json", "w", encoding="utf-8") as f:
        json.dump({
            "sanity_pairs": a2,
            "queries": results,
            "summary": {"both": both, "only_mxbai": wins_m,
                        "only_nomic": wins_n, "neither": neither},
        }, f, indent=2)


if __name__ == "__main__":
    main()
