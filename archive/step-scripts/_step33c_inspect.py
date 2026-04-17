"""Step 33c Part A — read-only drift inspection. No writes."""
import os, json, sys
import chromadb

CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"

PAIRS = [
    ("dex_canon", "dex_canon_v2"),
    ("ddl_archive", "ddl_archive_v2"),
    ("dex_code", "dex_code_v2"),
    ("ext_creator", "ext_creator_v2"),
]
TEST_COLS = ["dex_canon_mxbai_test", "dex_canon_mxbai_rechunk_test"]

client = chromadb.PersistentClient(path=CHROMA_DIR)

def safe_count(name):
    try:
        return client.get_collection(name).count()
    except Exception as e:
        return f"ERR:{type(e).__name__}"

def distinct_source_files(name):
    try:
        col = client.get_collection(name)
    except Exception as e:
        return None, f"ERR:{e}"
    sf_counts = {}
    # Paginate over metadata only
    batch = 10000
    offset = 0
    total = col.count()
    while offset < total:
        r = col.get(include=["metadatas"], limit=batch, offset=offset)
        for md in r["metadatas"]:
            if not md: continue
            sf = md.get("source_file") or md.get("filename") or "(unknown)"
            sf_counts[sf] = sf_counts.get(sf, 0) + 1
        offset += batch
    return sf_counts, None

def sample_timestamps(name, source_files, limit=500):
    try:
        col = client.get_collection(name)
    except Exception:
        return None, None
    # Try to read ingest_run_id from metadata of drift source_files
    if not source_files:
        return None, None
    min_ts, max_ts = None, None
    # Sample: use $in on source_file for a subset
    sf_list = list(source_files)[:100]
    try:
        r = col.get(where={"source_file": {"$in": sf_list}}, include=["metadatas"], limit=limit)
        for md in r["metadatas"]:
            if not md: continue
            ts = md.get("ingest_run_id") or md.get("ingested_at")
            if ts:
                if min_ts is None or ts < min_ts: min_ts = ts
                if max_ts is None or ts > max_ts: max_ts = ts
    except Exception as e:
        return None, str(e)
    return min_ts, max_ts

report = {"pairs": [], "tests": {}, "drift_details": {}}

for nomic, v2 in PAIRS:
    n_count = safe_count(nomic)
    v2_count = safe_count(v2)
    drift = None
    pct = None
    if isinstance(n_count, int) and isinstance(v2_count, int):
        drift = n_count - v2_count
        pct = (drift / v2_count * 100) if v2_count else None
    report["pairs"].append({
        "nomic": nomic, "nomic_count": n_count,
        "v2": v2, "v2_count": v2_count,
        "drift": drift, "drift_pct": pct
    })

for tc in TEST_COLS:
    report["tests"][tc] = safe_count(tc)

# Drift fingerprint per pair
for nomic, v2 in PAIRS:
    print(f"[fingerprint] {nomic} vs {v2}", file=sys.stderr)
    n_sf, err1 = distinct_source_files(nomic)
    v2_sf, err2 = distinct_source_files(v2)
    if n_sf is None or v2_sf is None:
        report["drift_details"][nomic] = {"error": f"nomic:{err1} v2:{err2}"}
        continue
    v2_set = set(v2_sf.keys())
    drift_sf = {sf: cnt for sf, cnt in n_sf.items() if sf not in v2_set}
    sorted_drift = sorted(drift_sf.items(), key=lambda x: -x[1])
    min_ts, max_ts = sample_timestamps(nomic, list(drift_sf.keys()))
    report["drift_details"][nomic] = {
        "unique_source_files_in_drift": len(drift_sf),
        "total_drift_chunks": sum(drift_sf.values()),
        "nomic_unique_files": len(n_sf),
        "v2_unique_files": len(v2_sf),
        "top30": sorted_drift[:30],
        "ts_min": min_ts, "ts_max": max_ts,
    }

with open(r"C:\Users\dexjr\dex-rag\_step33c_inspection.json", "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
print(json.dumps(report, indent=2))
