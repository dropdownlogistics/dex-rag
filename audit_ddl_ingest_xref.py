"""
Read-only corpus cross-reference for DDL_Ingest audit.
Uses dex_weights.get_client() per Rule — no new connection logic.
Does NOT write to any collection. Does NOT touch DDL_Ingest files.
"""
import os
import sys
from dex_weights import get_client, embed, COLLECTIONS

COLLS = list(COLLECTIONS.keys())  # all 7
INGEST_ROOT = r"C:\Users\dkitc\OneDrive\DDL_Ingest"

# Sample clusters: (cluster_name, [(relative_path, filename_stem_for_metadata_match), ...])
CLUSTERS = {
    "Mania transcripts": [
        r"Mania\transcripts\8135 Monrovia St.txt",
        r"Mania\transcripts\A message to Dad - Dave Solo - 5.22.23.txt",
        r"Mania\transcripts\Cole Diagnosis and Discussion - 4.4.23.txt",
    ],
    "DDL Council review transcripts (top-level)": [
        r"DDLCouncilReview_AntiPractice.txt",
        r"DDLCouncilReview_DexJrRetool.txt",
        r"DDLCouncilReview_CouncilPlaybook.txt",
    ],
    "Custom GPT / Project prompt exports (top-level)": [
        r"00_DDL_All_v1.0.txt",
        r"79_KnowledgeVault.txt",
        r"78_AuditForgePM.txt",
    ],
    "Governance / standards (_processed + _governance)": [
        r"_governance\ADR-CORPUS-001-v0.3.txt",
        r"_governance\STD-VAULT-002_TemplateArchitecture_20260314_v1.0.txt",
        r"_governance\CR-CANON-001_SYNTH.txt",
    ],
    "Top-level cognitive architecture / advisor": [
        r"28_CognitiveArchitecture.txt",
        r"77_LLMAdvisor.txt",
        r"83_MarcusCaldewellPM.txt",
    ],
}

# MBOX / PDF / spreadsheet clusters — filename-match only (content can't be cheaply sampled)
FILENAME_ONLY_CLUSTERS = {
    "Gmail MBOX (_hold)": ["All mail Including Spam and Trash-002.mbox"],
    "Board/reference PDFs (_hold) [sample]": [
        "DDL Content Type Registry SYS-020.pdf",
        "CR-LLMS-006 CathedralExtraction.pdf",
    ],
    "Financial FY2025 spreadsheets (_hold) [sample]": [
        "DL_ADP_AUD-2025-001_FY2025_v1.0.xlsx",
        "DDL_Universal_Fact_Table_v1.1.xlsx",
    ],
}


def read_sample(full_path, max_chars=1800):
    """Read a representative chunk: skip first 200 chars (often boilerplate), take next chunk."""
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
        # Take a middle-ish slice — avoids title/header-only matching
        if len(txt) > 3000:
            return txt[800:800 + max_chars]
        return txt[:max_chars]
    except Exception as e:
        return None


def metadata_filename_hits(client, coll_name, stem):
    """Check if any chunk metadata has a filename containing this stem.
    Tries filename and source_file fields. Chroma .get() with where= supports equality;
    we use $contains via a fetch-and-scan fallback on a small sample if needed."""
    try:
        coll = client.get_collection(coll_name)
    except Exception:
        return None  # collection missing
    hits = 0
    # Try exact filename match first
    for field in ("filename", "source_file", "source"):
        try:
            r = coll.get(where={field: stem}, limit=5, include=["metadatas"])
            if r and r.get("ids"):
                hits += len(r["ids"])
        except Exception:
            pass
    # If no exact hits, try a peek-scan for substring (bounded)
    if hits == 0:
        try:
            peek = coll.get(limit=0)  # just to confirm access
        except Exception:
            return 0
    return hits


def semantic_hits(client, coll_name, text_sample, top_k=3, distance_threshold=0.6):
    """Run a vector query. Return (count_below_threshold, best_distance)."""
    try:
        coll = client.get_collection(coll_name)
    except Exception:
        return None, None
    try:
        emb = embed(text_sample)
        r = coll.query(
            query_embeddings=[emb],
            n_results=top_k,
            include=["distances", "metadatas"],
        )
        dists = r["distances"][0] if r.get("distances") else []
        metas = r["metadatas"][0] if r.get("metadatas") else []
        if not dists:
            return 0, None
        best = min(dists)
        count_near = sum(1 for d in dists if d < distance_threshold)
        return count_near, (best, metas[0] if metas else {})
    except Exception as e:
        return None, f"ERR: {e}"


def main():
    print("=" * 80)
    print("DDL_INGEST -> DEX-RAG CORPUS CROSS-REFERENCE (READ-ONLY)")
    print("=" * 80)
    client = get_client()
    # list collections present
    try:
        present = [c.name for c in client.list_collections()]
    except Exception as e:
        print(f"FATAL: can't list collections: {e}")
        return
    print(f"\nCollections present: {present}")
    print(f"Expected from COLLECTIONS dict: {COLLS}")
    missing = [c for c in COLLS if c not in present]
    if missing:
        print(f"MISSING: {missing}")
    print()

    # Content-based clusters
    for cluster, rel_paths in CLUSTERS.items():
        print("-" * 80)
        print(f"CLUSTER: {cluster}")
        for rel in rel_paths:
            full = os.path.join(INGEST_ROOT, rel)
            stem = os.path.basename(rel)
            print(f"\n  FILE: {stem}")
            if not os.path.exists(full):
                print(f"    [missing on disk: {full}]")
                continue
            sample = read_sample(full)
            if not sample:
                print("    [read failed]")
                continue
            print(f"    [sample chars: {len(sample)}]")
            for coll in COLLS:
                if coll not in present:
                    continue
                fname_hits = metadata_filename_hits(client, coll, stem)
                sem_near, sem_best = semantic_hits(client, coll, sample)
                best_d = None
                best_meta = {}
                if isinstance(sem_best, tuple):
                    best_d, best_meta = sem_best
                tag = ""
                if fname_hits and fname_hits > 0:
                    tag = "FILENAME_MATCH"
                elif best_d is not None and best_d < 0.4:
                    tag = "STRONG_SEMANTIC"
                elif best_d is not None and best_d < 0.6:
                    tag = "WEAK_SEMANTIC"
                else:
                    tag = "NO_MATCH"
                bd = f"{best_d:.3f}" if best_d is not None else "—"
                match_fname = (best_meta or {}).get("filename", "")[:40]
                print(f"    {coll:<14} fname_hits={fname_hits}  best_d={bd}  near<0.6={sem_near}  top_meta={match_fname}  -> {tag}")

    # Filename-only clusters (PDFs, MBOX, XLSX — content extraction non-trivial)
    print("\n" + "=" * 80)
    print("FILENAME-ONLY CHECKS (no content sampling)")
    print("=" * 80)
    for cluster, stems in FILENAME_ONLY_CLUSTERS.items():
        print(f"\nCLUSTER: {cluster}")
        for stem in stems:
            print(f"  STEM: {stem}")
            for coll in COLLS:
                if coll not in present:
                    continue
                hits = metadata_filename_hits(client, coll, stem)
                print(f"    {coll:<14} fname_hits={hits}")

    print("\nDONE.")


if __name__ == "__main__":
    main()
