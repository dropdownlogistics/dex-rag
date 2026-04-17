"""Step 33c Part B pre-flight — list the 44 drift source_files. Read-only."""
import os, json
import chromadb

CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"
client = chromadb.PersistentClient(path=CHROMA_DIR)

def distinct_source_files(name):
    col = client.get_collection(name)
    total = col.count()
    sf_counts = {}
    sf_runs = {}  # source_file -> min ingest_run_id
    sf_ext = {}
    batch = 10000
    offset = 0
    while offset < total:
        r = col.get(include=["metadatas"], limit=batch, offset=offset)
        for md in r["metadatas"]:
            if not md: continue
            sf = md.get("source_file") or md.get("filename") or "(unknown)"
            sf_counts[sf] = sf_counts.get(sf, 0) + 1
            run = md.get("ingest_run_id")
            if run:
                cur = sf_runs.get(sf)
                if cur is None or run < cur:
                    sf_runs[sf] = run
            ext = os.path.splitext(sf)[1].lower()
            sf_ext[sf] = ext
        offset += batch
    return sf_counts, sf_runs, sf_ext

nomic_sf, nomic_runs, nomic_ext = distinct_source_files("dex_canon")
v2_sf, _, _ = distinct_source_files("dex_canon_v2")

v2_set = set(v2_sf.keys())
drift = [(sf, cnt, nomic_runs.get(sf, ""), nomic_ext.get(sf, ""))
         for sf, cnt in nomic_sf.items() if sf not in v2_set]
drift.sort(key=lambda x: -x[1])

out = {"total_source_files": len(drift),
       "total_chunks": sum(x[1] for x in drift),
       "rows": drift}
with open(r"C:\Users\dexjr\dex-rag\_step33c_partb_drift.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)
print(json.dumps(out, indent=2, ensure_ascii=False))
