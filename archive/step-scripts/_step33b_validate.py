"""Step 33b — post-migration validation of _v2 collections."""
from __future__ import annotations
import json
import sys

import chromadb
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"
OLLAMA = "http://localhost:11434"
MODEL = "mxbai-embed-large"
TRUNC = 1200

COLLECTIONS = [
    ("ext_creator",  "ext_creator_v2"),
    ("dex_code",     "dex_code_v2"),
    ("dex_canon",    "dex_canon_v2"),
    ("ddl_archive",  "ddl_archive_v2"),
]

# Step 32 queries with key-term recall check
QUERIES_STEP32 = [
    ("id_sweep",   "STD-DDL-SWEEPREPORT-001 protocol classification predicate", "STD-DDL-SWEEPREPORT-001"),
    ("id_cap",     "CR-OPERATOR-CAPACITY-001",                                  "CR-OPERATOR-CAPACITY-001"),
    ("accidental", "What is AccidentalIntelligence?",                           "AccidentalIntelligence"),
    ("emergence",  "Explain the GuidedEmergence pattern",                       "GuidedEmergence"),
    ("cottage",    "What does CottageHumble mean?",                             "CottageHumble"),
    ("charlie",    "What is the Charlie Conway Principle?",                     "Charlie Conway"),
    ("beth",       "Who is Beth Epperson?",                                     "Beth Epperson"),
    ("mithril",    "What is the Mithril Standard about?",                       "Mithril"),
]

# Real-workflow identifier queries (Step 29/30 cases)
QUERIES_IDENT = [
    ("sweep_repo", "What is STD-DDL-SWEEPREPORT-001?",         "STD-DDL-SWEEPREPORT-001"),
    ("cap",        "What does CR-OPERATOR-CAPACITY-001 say?",  "CR-OPERATOR-CAPACITY-001"),
    ("adr",        "Describe ADR-INGEST-PIPELINE-001",         "ADR-INGEST-PIPELINE-001"),
    ("spiral",     "What is PRO-DDL-SPIRAL-001 about?",        "PRO-DDL-SPIRAL-001"),
    ("backup",     "Summarize STD-DDL-BACKUP-001",             "STD-DDL-BACKUP-001"),
]


def embed(text: str) -> list[float]:
    r = requests.post(f"{OLLAMA}/api/embeddings",
                      json={"model": MODEL, "prompt": (text or "")[:TRUNC]},
                      timeout=60)
    r.raise_for_status()
    return r.json()["embedding"]


def main():
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    print("=" * 70)
    print("STEP 33B VALIDATION")
    print("=" * 70)

    # 1. Count parity
    print("\n1. COUNT PARITY")
    parity = []
    all_counts_ok = True
    for src_name, dst_name in COLLECTIONS:
        src = client.get_collection(src_name)
        dst = client.get_collection(dst_name)
        sc, dc = src.count(), dst.count()
        ok = (dc == sc)  # strict initial parity — live-writes during migration may add to src
        parity.append({"src": src_name, "src_count": sc, "dst": dst_name,
                       "dst_count": dc, "delta": sc - dc, "ok": ok})
        mark = "OK" if ok else f"DELTA={sc-dc}"
        print(f"  {src_name:15}={sc:>8,}   {dst_name:20}={dc:>8,}   {mark}")
        if not ok and abs(sc - dc) > 100:
            all_counts_ok = False  # allow small drift but flag big ones

    # 2. Metadata preservation — sample 100 per collection
    print("\n2. METADATA PRESERVATION (sample 100/col)")
    meta_ok = True
    meta_report = []
    for src_name, dst_name in COLLECTIONS:
        src = client.get_collection(src_name)
        dst = client.get_collection(dst_name)
        sample = src.get(limit=100, include=["metadatas"])
        sids = sample["ids"]
        smetas = sample["metadatas"]
        if not sids:
            meta_report.append({"col": src_name, "ok": True, "note": "empty"})
            continue
        got = dst.get(ids=sids, include=["metadatas"])
        got_map = dict(zip(got["ids"], got["metadatas"]))
        mismatches = 0
        missing = 0
        for sid, smd in zip(sids, smetas):
            dmd = got_map.get(sid)
            if dmd is None:
                missing += 1
                continue
            smd = smd or {}
            dmd = dmd or {}
            for k in ("source_file", "ingest_run_id", "source_type"):
                if k in smd and smd.get(k) != dmd.get(k):
                    mismatches += 1
                    break
        row = {"col": src_name, "sampled": len(sids),
               "missing_in_dst": missing, "meta_mismatches": mismatches,
               "ok": missing == 0 and mismatches == 0}
        if not row["ok"]:
            meta_ok = False
        meta_report.append(row)
        print(f"  {src_name:15}  sampled={len(sids)}  missing={missing}  mismatch={mismatches}  "
              f"{'OK' if row['ok'] else 'FAIL'}")

    # 3. Retrieval: 8 Step 32 queries against dex_canon_v2
    print("\n3. RETRIEVAL — 8 Step 32 queries on dex_canon_v2")
    canon_v2 = client.get_collection("dex_canon_v2")
    q32_results = []
    for qlabel, q, key in QUERIES_STEP32:
        e = embed(q)
        r = canon_v2.query(query_embeddings=[e], n_results=5,
                           include=["documents", "metadatas", "distances"])
        docs = r["documents"][0]
        recall = any(key in (d or "") for d in docs)
        dist = round(float(r["distances"][0][0]), 4)
        q32_results.append({"label": qlabel, "recall": recall, "top1_dist": dist})
        print(f"  [{qlabel:12}]  dist={dist:>8}  recall={'OK' if recall else '--'}")
    q32_ok = sum(r["recall"] for r in q32_results)
    print(f"  -> {q32_ok}/{len(q32_results)} recall")

    # 4. Identifier queries raw (no B3/B2)
    print("\n4. RETRIEVAL — 5 real-workflow identifier queries on dex_canon_v2 (raw)")
    qid_results = []
    for qlabel, q, key in QUERIES_IDENT:
        e = embed(q)
        r = canon_v2.query(query_embeddings=[e], n_results=5,
                           include=["documents", "metadatas", "distances"])
        docs = r["documents"][0]
        recall = any(key in (d or "") for d in docs)
        dist = round(float(r["distances"][0][0]), 4)
        qid_results.append({"label": qlabel, "recall": recall, "top1_dist": dist})
        print(f"  [{qlabel:12}]  dist={dist:>8}  recall={'OK' if recall else '--'}")
    qid_ok = sum(r["recall"] for r in qid_results)
    print(f"  -> {qid_ok}/{len(qid_results)} recall")

    # Summary
    print("\n" + "=" * 70)
    overall = all_counts_ok and meta_ok and q32_ok >= 7 and qid_ok >= 4
    print(f"OVERALL: {'PASS' if overall else 'REVIEW'}")
    print(f"  count parity: {'ok' if all_counts_ok else 'DRIFT'}")
    print(f"  metadata:     {'ok' if meta_ok else 'FAIL'}")
    print(f"  step32 recall: {q32_ok}/{len(q32_results)} (target ≥7)")
    print(f"  ident recall:  {qid_ok}/{len(qid_results)} (target ≥4)")
    print("=" * 70)

    out = {
        "parity": parity,
        "metadata": meta_report,
        "step32_queries": q32_results,
        "ident_queries": qid_results,
        "overall_pass": overall,
    }
    with open("_step33b_validate.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
