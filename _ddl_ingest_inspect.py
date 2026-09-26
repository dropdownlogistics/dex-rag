"""Read-only inspection of DDL_Ingest folder vs dex_canon_v2 / ddl_archive_v2."""
import os, hashlib, json
from collections import defaultdict
import chromadb

INGEST_DIR = r"C:\Users\dkitc\OneDrive\DDL_Ingest"
CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"
SUPPORTED = {".txt", ".md", ".html", ".jsx", ".json", ".py", ".cs", ".js", ".mjs",
             ".ts", ".tsx", ".css", ".sql", ".sh", ".bat", ".ps1", ".bas",
             ".csv", ".yml", ".yaml", ".toml", ".ipynb", ".prisma"}
SKIP_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
SKIP_PREFIXES = ("ingest_report_",)

def sha256_file(p):
    try:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(8192), b""): h.update(b)
        return h.hexdigest()
    except Exception as e:
        return f"ERR:{e}"

# Top-level files only (sweep uses os.listdir, no recursion)
files = []
unsupported = []
skipped = []
hash_err = []
for name in sorted(os.listdir(INGEST_DIR)):
    full = os.path.join(INGEST_DIR, name)
    if not os.path.isfile(full): continue
    ext = os.path.splitext(name)[1].lower()
    if name in SKIP_NAMES or any(name.startswith(p) for p in SKIP_PREFIXES):
        skipped.append({"name": name, "reason": "SKIP_NAMES/prefix"})
        continue
    size = os.path.getsize(full)
    h = sha256_file(full)
    if h.startswith("ERR:"):
        hash_err.append({"name": name, "error": h})
        continue
    rec = {"name": name, "path": full, "ext": ext, "size": size,
           "sha256": h, "file_hash": h[:16], "supported": ext in SUPPORTED}
    files.append(rec)
    if ext not in SUPPORTED:
        unsupported.append(rec)

# Internal duplicates (same sha256 in multiple files)
by_hash = defaultdict(list)
for f in files:
    by_hash[f["sha256"]].append(f["name"])
internal_dupes = {h: names for h, names in by_hash.items() if len(names) > 1}

# Check against corpus using file_hash (first 16 chars of sha256)
client = chromadb.PersistentClient(path=CHROMA_DIR)
canon_hashes = set()
archive_hashes = set()
for coll_name, dest in [("dex_canon_v2", canon_hashes), ("ddl_archive_v2", archive_hashes)]:
    col = client.get_collection(coll_name)
    total = col.count()
    offset = 0
    batch = 20000
    while offset < total:
        r = col.get(include=["metadatas"], limit=batch, offset=offset)
        for md in r["metadatas"]:
            if md and md.get("file_hash"):
                dest.add(md["file_hash"])
        offset += batch
    print(f"  {coll_name}: {len(dest):,} unique file_hashes")

# Classify each supported file
in_canon = []
in_archive = []
in_both = []
novel = []
supported_files = [f for f in files if f["supported"]]
for f in supported_files:
    fh = f["file_hash"]
    c = fh in canon_hashes
    a = fh in archive_hashes
    if c and a: in_both.append(f)
    elif c: in_canon.append(f)
    elif a: in_archive.append(f)
    else: novel.append(f)

out = {
    "total_files_top_level": len(files) + len(skipped) + len(hash_err),
    "files_inspected": len(files),
    "skipped_by_name_rule": skipped,
    "hash_errors": hash_err,
    "supported_count": len(supported_files),
    "unsupported_count": len(unsupported),
    "unsupported_files": [{"name":f["name"],"ext":f["ext"],"size":f["size"]} for f in unsupported],
    "internal_duplicates": [{"sha256":h, "names":names} for h,names in internal_dupes.items()],
    "already_in_canon": [{"name":f["name"],"size":f["size"],"file_hash":f["file_hash"]} for f in in_canon],
    "already_in_archive": [{"name":f["name"],"size":f["size"],"file_hash":f["file_hash"]} for f in in_archive],
    "already_in_both": [{"name":f["name"],"size":f["size"],"file_hash":f["file_hash"]} for f in in_both],
    "novel": [{"name":f["name"],"ext":f["ext"],"size":f["size"]} for f in novel],
    "total_size_bytes": sum(f["size"] for f in files),
}
with open(r"C:\Users\dexjr\dex-rag\_ddl_ingest_inspect.json", "w") as f:
    json.dump(out, f, indent=2)
print(json.dumps(out, indent=2))
