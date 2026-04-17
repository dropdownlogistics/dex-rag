"""Step 33c Part B drift migration.

Re-embeds the 42 drift source_files (44 minus 2 ingest_report) from
nomic dex_canon into mxbai dex_canon_v2. Idempotent and resumable.

Default mode is --dry-run TRUE (no writes). Operator must pass --execute.
"""
import os, sys, json, time, argparse
import requests
import chromadb

CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"
SRC = "dex_canon"
DST = "dex_canon_v2"
OLLAMA_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "mxbai-embed-large"
PROGRESS_FILE = r"C:\Users\dexjr\dex-rag\_step33c_migrate_progress.json"
DRIFT_INPUT = r"C:\Users\dexjr\dex-rag\_step33c_partb_drift.json"

EXCLUDE_SOURCE_FILES = {
    "ingest_report_2026-04-12_091252.904104_sweep_2026-04-12_090000.md",
    "ingest_report_2026-04-13_223640.834186_sweep_2026-04-13_221606.md",
}

# mxbai-embed-large context = 512 tokens. Chunks were sized at 500 tokens
# assuming 4 chars/token, but actual tokenization pushes some over. Fall
# back to progressive truncation on context-length errors. Returns
# (embedding, truncated_chars) so the caller can log truncation rate.
def get_embedding(text, retries=3):
    attempts = [text, text[:1500], text[:1000], text[:600]]
    last_err = None
    for att_idx, t in enumerate(attempts):
        for i in range(retries):
            try:
                r = requests.post(OLLAMA_URL, json={"model": EMBED_MODEL, "prompt": t}, timeout=120)
                if r.status_code == 500 and "context length" in r.text.lower():
                    break  # jump to next truncation level
                r.raise_for_status()
                emb = r.json().get("embedding")
                return emb, (len(text) - len(t))
            except requests.exceptions.HTTPError as e:
                if r.status_code == 500 and "context length" in r.text.lower():
                    last_err = e
                    break
                last_err = e
                if i == retries - 1:
                    raise
                time.sleep(2 ** i)
            except Exception as e:
                last_err = e
                if i == retries - 1:
                    raise
                time.sleep(2 ** i)
    raise RuntimeError(f"all truncation levels rejected (last: {last_err})")

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        return json.load(open(PROGRESS_FILE))
    return {"completed_source_files": [], "chunks_written": 0, "chunks_skipped_idempotent": 0}

def save_progress(p):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(p, f, indent=2)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true",
                    help="Actually write. Default is dry-run (no writes).")
    args = ap.parse_args()
    dry_run = not args.execute

    drift = json.load(open(DRIFT_INPUT))
    rows = drift["rows"]
    targets = [r for r in rows if r[0] not in EXCLUDE_SOURCE_FILES]
    excluded = [r for r in rows if r[0] in EXCLUDE_SOURCE_FILES]

    expected_chunks = sum(r[1] for r in targets)
    print(f"Mode:                 {'DRY-RUN' if dry_run else 'EXECUTE'}")
    print(f"Drift source_files:   {len(rows)}")
    print(f"Excluded (reports):   {len(excluded)} -> {[r[0] for r in excluded]}")
    print(f"Migration targets:    {len(targets)}")
    print(f"Expected chunks:      {expected_chunks}")
    print()

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    src_col = client.get_collection(SRC)
    dst_col = client.get_collection(DST)
    print(f"Pre-migration {DST} count: {dst_col.count()}")
    print()

    # Resume state
    progress = load_progress() if not dry_run else {"completed_source_files": [], "chunks_written": 0, "chunks_skipped_idempotent": 0}
    completed = set(progress["completed_source_files"])

    # Preload destination ids for idempotency
    dst_ids = set()
    if not dry_run:
        print(f"Loading {DST} ids for idempotency check...")
        total = dst_col.count()
        offset = 0
        batch = 20000
        while offset < total:
            r = dst_col.get(include=[], limit=batch, offset=offset)
            dst_ids.update(r["ids"])
            offset += batch
        print(f"  loaded {len(dst_ids):,} dst ids")
        print()

    t0 = time.time()
    for idx, (sf, expected_cnt, _run, _ext) in enumerate(targets, 1):
        if sf in completed:
            print(f"[{idx}/{len(targets)}] SKIP already-migrated: {sf}")
            continue
        print(f"[{idx}/{len(targets)}] {sf}  (expected {expected_cnt} chunks)")
        if dry_run:
            continue

        # Pull all chunks from source for this source_file
        r = src_col.get(where={"source_file": sf},
                        include=["documents", "metadatas"])
        ids = r["ids"]
        docs = r["documents"]
        metas = r["metadatas"]
        if len(ids) != expected_cnt:
            print(f"   WARN: actual chunk count {len(ids)} != expected {expected_cnt}")

        t_file = time.time()
        wrote = 0
        skipped = 0
        truncated_chunks = 0
        for i, cid in enumerate(ids):
            if cid in dst_ids:
                skipped += 1
                continue
            doc = docs[i]
            md = metas[i]
            try:
                emb, trunc = get_embedding(doc)
            except Exception as e:
                print(f"   ERR embed failed id={cid}: {e}")
                raise
            if emb is None:
                print(f"   ERR null embedding id={cid}")
                raise RuntimeError("null embedding")
            if trunc > 0:
                truncated_chunks += 1
            try:
                dst_col.upsert(ids=[cid], embeddings=[emb], documents=[doc], metadatas=[md])
                dst_ids.add(cid)
                wrote += 1
            except Exception as e:
                print(f"   ERR upsert failed id={cid}: {e}")
                raise
        elapsed = time.time() - t_file
        rate = wrote / elapsed if elapsed > 0 else 0
        print(f"   wrote {wrote}  skipped(idem) {skipped}  truncated {truncated_chunks}  in {elapsed:.1f}s ({rate:.1f}/s)")
        progress["completed_source_files"].append(sf)
        progress["chunks_written"] += wrote
        progress["chunks_skipped_idempotent"] += skipped
        save_progress(progress)

    total_elapsed = time.time() - t0
    print()
    print(f"Done in {total_elapsed:.1f}s ({total_elapsed/60:.1f} min)")
    print(f"Chunks written:               {progress['chunks_written']}")
    print(f"Chunks skipped (idempotent):  {progress['chunks_skipped_idempotent']}")
    print(f"Post-migration {DST} count:   {dst_col.count()}")

if __name__ == "__main__":
    main()
