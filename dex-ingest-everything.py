#!/usr/bin/env python3
"""
DEX BRAIN - consolidated "everything" ingest.

Operator directive 2026-08-14: get everything into the brain first, curate
after. We cannot organize what we cannot see, and today the corpus reads ONE
hand-maintained folder while ~18 roots sit unindexed.

What this does differently from dex-ingest.py, and why:

  1. WALKS EVERY KNOWN ROOT, not just OneDrive\\DDL_Ingest.
  2. STAMPS REAL PROVENANCE. The live corpus carries `source_file` (a path
     relative to the drop folder) and nothing else -- 383k chunks that cannot
     say which of the 18 sources they came from. That is precisely why nobody
     can keep track of what is what. Every chunk here carries `source_path`
     (absolute) and `source_root` (which source it came from).
  3. TAGS INJECTION RISK AT INGEST. Per Reed Vane's 2026-08-06 security
     reclass, a BOOT/PROFILE-class document retrieved mid-answer is a second
     system prompt, not a citation. We still ingest it -- the Operator wants
     everything -- but it is labelled so retrieval can exclude it. Curation
     later needs no re-ingest.
  4. NEVER HYDRATES CLOUD PLACEHOLDERS. iCloudDrive is 81% placeholder and
     OneDrive 60%. Opening those would pull ~77GB over the network. They are
     counted and skipped, never opened.
  5. NON-DESTRUCTIVE. Writes a new collection. Nothing existing is dropped.

Usage:
    python dex-ingest-everything.py --dry-run
    python dex-ingest-everything.py --roots ddl-canon,reborn-cowork
    python dex-ingest-everything.py --limit 500
"""

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import chromadb
import requests

# ---------------------------------------------------------------- constants
# Single source of truth. Measured 2026-08-14: I originally hardcoded
# nomic-embed-text (768 dims) copied from archive/standalone-utils/, which is
# LEGACY. The live query path uses mxbai-embed-large (1024). The mismatch is
# invisible at ingest and only surfaces at query time as a dimension error --
# 78,460 chunks were written before it did. Import, never restate.
from dex_core import CHROMA_DIR, EMBED_MODEL, embed as core_embed

COLLECTION = "ddl_everything_v2"

CHUNK_CHARS = 3200
CHUNK_OVERLAP = 400
MAX_FILE_BYTES = 6_000_000

TEXTY = {
    ".md", ".txt", ".json", ".csv", ".tsv", ".yml", ".yaml", ".html", ".htm",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".sql", ".sh", ".ps1", ".bat",
    ".toml", ".ipynb", ".log", ".srt", ".vtt", ".cs", ".bas", ".rtf",
}

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "AppData",
    ".next", "dist", "build", ".cache", "site-packages", "chroma",
    "chromadb", ".dex-jr", ".pytest_cache", ".mypy_cache", "_lkg",
    # personnel/ is excluded by the Canon Steward's ruling
    # (DDL-3008:20260813T143000Z-cr02, revised 2026-08-14). The REASON changed
    # in the revision -- relevance, not privacy -- but the exclusion stands.
    # Caught 2026-08-14 mid-run: 270 chunks from personnel paths had already
    # landed because this list never carried it. Those are recorded for Operator
    # disposition rather than dropped -- dex-rag Rule 8 forbids dropping chunks
    # without approval, and a compliance gap does not authorise a second
    # violation to fix the first.
    "personnel",
}

# Which source each root is. Keys are the short names accepted by --roots.
ROOTS = {
    "reborn-cowork":  (r"C:\Users\dexjr\ddl-wings\reborn-cowork", "governance"),
    # TWO canon copies exist and they have DIVERGED. Measured 2026-08-14:
    #   dexjr : no .git,  49 .md, newest 2026-08-06  <- newer edits, no history
    #   dkitc : git+remote, 133 .md, newest 2026-07-24 <- more material, versioned
    # CHANGELOG.md differs between them and each holds files the other lacks.
    # This config originally named only the dexjr copy, so the corpus would
    # have held the smaller, unversioned, divergent half of canon while
    # reporting full coverage against its own file list. Both are ingested;
    # content-hash dedupe collapses the overlap and source_path records which
    # copy each surviving chunk came from. WHICH ONE IS AUTHORITATIVE IS NOT
    # OURS TO DECIDE -- routed to Ezra Locke (DDL-3008), Canon Steward.
    "ddl-canon":      (r"C:\Users\dexjr\ddl-canon",               "governance"),
    "ddl-canon-git":  (r"C:\Users\dkitc\ddl-canon",               "governance"),
    "dex-rag":        (r"C:\Users\dexjr\dex-rag",                 "project_export"),
    "03_Work":        (r"C:\Users\dexjr\03_Work",                 "document"),
    "dex-universe":   (r"C:\Users\dexjr\99_DexUniverseArchive",   "project_export"),
    "sesslog-dexjr":  (r"C:\Users\dexjr\DDL_SessionLogs",         "thread_save"),
    "quarantine":     (r"C:\Users\dexjr\_quarantine-20260807",    "unknown"),
    "ddl-vault":      (r"C:\Users\dkitc\DDL-Vault",               "document"),
    "ddl-external":   (r"C:\Users\dkitc\DDL_External",            "document"),
    "sesslog-dkitc":  (r"C:\Users\dkitc\DDL_SessionLogs",         "thread_save"),
    "my-drive":       (r"C:\Users\dkitc\My Drive",                "document"),
    "onedrive":       (r"C:\Users\dkitc\OneDrive",                "document"),
    "icloud":         (r"C:\Users\dkitc\iCloudDrive",             "document"),
}

# Filenames whose PURPOSE is to instruct a model. Ingested, but labelled.
INSTRUCTIONAL_STEMS = (
    "boot", "profile", "modelfile", "claude.md", "agents.md", "gemini.md",
    "system-prompt", "systemprompt", "persona", "first-prompt", "prompt",
)


def injection_class(p: Path) -> str:
    """instructional | governance | content -- a retrieval-time filter hint."""
    stem = p.name.lower()
    if any(stem.startswith(s) or f"-{s}" in stem or f"_{s}" in stem
           for s in INSTRUCTIONAL_STEMS):
        return "instructional"
    if stem.endswith(".md") and any(
        k in stem for k in ("charter", "governance", "std-", "authority", "mission")
    ):
        return "governance"
    return "content"


def is_placeholder(st) -> bool:
    """True for OneDrive/iCloud files not actually on disk. Never open these."""
    a = getattr(st, "st_file_attributes", 0)
    return bool(a & 0x1000 or a & 0x400000)  # OFFLINE | RECALL_ON_DATA_ACCESS


def chunk_text(t: str):
    t = (t or "").strip()
    if not t:
        return []
    if len(t) <= CHUNK_CHARS:
        return [t]
    out, start, n = [], 0, len(t)
    while start < n:
        end = min(n, start + CHUNK_CHARS)
        if end < n:
            brk = t.rfind("\n\n", start + CHUNK_CHARS // 2, end)
            if brk > start:
                end = brk
        piece = t[start:end].strip()
        if piece:
            out.append(piece)
        if end >= n:
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return out


def embed(text: str):
    """Delegate to dex_core.embed -- it already does adaptive truncation.

    I hand-rolled a halving-retry here before reading dex_core. It worked, and
    it was a second implementation of a function that already existed and was
    already correct. Rule 3: read first, build second.

    Returns None if the chunk could not be embedded, so one bad chunk cannot
    abort a multi-hour run.
    """
    try:
        v = core_embed(text)
        return v if v else None
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", default="all",
                    help="comma-separated root names, or 'all'")
    ap.add_argument("--limit", type=int, default=0, help="max files (0 = no cap)")
    ap.add_argument("--dry-run", action="store_true",
                    help="scan and report, embed nothing")
    ap.add_argument("--collection", default=COLLECTION)
    args = ap.parse_args()

    selected = (list(ROOTS) if args.roots == "all"
                else [r.strip() for r in args.roots.split(",") if r.strip()])
    unknown = [r for r in selected if r not in ROOTS]
    if unknown:
        sys.exit(f"unknown root(s): {unknown}\nvalid: {list(ROOTS)}")

    run_id = "everything_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    col = None if args.dry_run else client.get_or_create_collection(args.collection)

    # Resume support. A 337k-chunk run takes hours; without this, any restart
    # re-embeds everything already present. Deterministic ids make the upsert
    # idempotent, but idempotent is not free -- measured 2026-08-14, a restart
    # spent 25 minutes re-embedding 511 files it already had.
    seen_hashes = set()
    if col is not None:
        have = col.count()
        off = 0
        while off < have:
            g = col.get(limit=2000, offset=off, include=["metadatas"])
            if not g["metadatas"]:
                break
            for m in g["metadatas"]:
                fh = m.get("file_hash")
                if fh:
                    seen_hashes.add(fh)
            off += 2000
        if seen_hashes:
            print(f"resume: {len(seen_hashes):,} files already ingested, skipping\n")

    stats = {
        "scanned": 0, "ingested": 0, "chunks": 0, "skipped_placeholder": 0,
        "skipped_dupe": 0, "skipped_big": 0, "skipped_unreadable": 0,
        "skipped_unembeddable": 0,
        "by_root": {}, "by_class": {},
    }

    print(f"run_id={run_id}  collection={args.collection}"
          f"{'  [DRY RUN]' if args.dry_run else ''}\n")

    for name in selected:
        root_path, src_type = ROOTS[name]
        root = Path(root_path)
        if not root.is_dir():
            print(f"  ABSENT  {name}")
            continue
        r_files = r_chunks = r_ph = 0

        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                p = Path(dirpath) / fn
                # **This tool's own output must not become its own input.**
                #
                # `dex-rag` is a scanned root, `.json` is in TEXTY, and every run
                # writes `ingest-report-<run_id>.json` into this directory. Each
                # ingest was therefore embedding the previous ingest's report
                # into the corpus that Dex Jr answers from.
                #
                # Measured 2026-08-15: 1 chunk of 399,940. **The mechanism is
                # confirmed and the contamination is one chunk** -- stated with
                # its size because a real defect reported without its magnitude
                # is its own kind of false alarm.
                #
                # **This is fixed on principle and on cost, not on projected
                # harm, and the distinction is one I got wrong first.**
                #
                # I initially justified it by writing that an ingest report is
                # "a document made almost entirely of filenames", so the corpus
                # would fill with directory listings of itself. **I had not
                # opened one.** They are 556-2078 byte stats blobs -- run_id,
                # timestamp, counters. No filenames. The projected harm does not
                # exist, and each future run adds roughly half a kilobyte.
                #
                # A tool should not ingest its own output regardless. But the
                # reason is "it is wrong and the fix is three lines", not a
                # retrieval failure I invented to make the fix sound urgent.
                #
                # Excluded on READ rather than by moving the write, so anything
                # that expects the report in the working directory keeps working.
                #
                # Generalised from the knowledge-graph extractor, which had the
                # same defect at 4.4% of all edges and made one status class
                # unreachable. The rule that finds both: **does anything this
                # tool writes land under anything it reads?**
                if fn.startswith("ingest-report-") and p.suffix.lower() == ".json":
                    continue
                if p.suffix.lower() not in TEXTY:
                    continue
                stats["scanned"] += 1
                try:
                    st = p.stat()
                except OSError:
                    stats["skipped_unreadable"] += 1
                    continue
                if is_placeholder(st):
                    stats["skipped_placeholder"] += 1
                    r_ph += 1
                    continue
                if st.st_size > MAX_FILE_BYTES or st.st_size == 0:
                    stats["skipped_big"] += 1
                    continue
                try:
                    raw = p.read_bytes()
                except OSError:
                    stats["skipped_unreadable"] += 1
                    continue

                fhash = hashlib.sha256(raw).hexdigest()[:16]
                if fhash in seen_hashes:
                    stats["skipped_dupe"] += 1
                    continue
                seen_hashes.add(fhash)

                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        text = raw.decode("utf-8-sig")
                    except UnicodeDecodeError:
                        text = raw.decode("latin-1", errors="replace")

                pieces = chunk_text(text)
                if not pieces:
                    continue

                cls = injection_class(p)
                stats["by_class"][cls] = stats["by_class"].get(cls, 0) + 1

                if not args.dry_run:
                    ids, embs, metas, docs = [], [], [], []
                    for i, piece in enumerate(pieces):
                        vec = embed(piece)
                        if vec is None:
                            stats["skipped_unembeddable"] += 1
                            continue
                        ids.append(f"{fhash}_{i}")
                        embs.append(vec)
                        docs.append(piece)
                        metas.append({
                            # --- provenance: the whole point of this rebuild
                            "source_path": str(p),
                            "source_root": name,
                            "source_type": src_type,
                            "ingest_run_id": run_id,
                            "ingested_at": now,
                            # --- retrieval-time curation hint
                            "injection_class": cls,
                            # --- ordinary chunk fields
                            "filename": p.name,
                            "file_type": p.suffix.lower(),
                            "file_hash": fhash,
                            "chunk_index": i,
                            "total_chunks": len(pieces),
                            "char_count": len(piece),
                            "mtime": datetime.fromtimestamp(
                                st.st_mtime, timezone.utc
                            ).strftime("%Y-%m-%d"),
                        })
                    if not ids:
                        continue
                    col.upsert(ids=ids, embeddings=embs,
                               documents=docs, metadatas=metas)

                stats["ingested"] += 1
                stats["chunks"] += len(pieces)
                r_files += 1
                r_chunks += len(pieces)

                if stats["ingested"] % 100 == 0:
                    print(f"    ... {stats['ingested']:,} files, "
                          f"{stats['chunks']:,} chunks")

                if args.limit and stats["ingested"] >= args.limit:
                    print("\n[limit reached]")
                    break
            if args.limit and stats["ingested"] >= args.limit:
                break

        stats["by_root"][name] = {"files": r_files, "chunks": r_chunks,
                                  "placeholders_skipped": r_ph}
        print(f"  {r_files:>6,} files  {r_chunks:>7,} chunks  "
              f"{r_ph:>6,} placeholders skipped   {name}")
        if args.limit and stats["ingested"] >= args.limit:
            break

    print("\n" + "=" * 66)
    for k in ("scanned", "ingested", "chunks", "skipped_placeholder",
              "skipped_dupe", "skipped_big", "skipped_unreadable",
              "skipped_unembeddable"):
        print(f"  {k:<22} {stats[k]:>10,}")
    print(f"  by injection_class     {stats['by_class']}")
    if not args.dry_run:
        print(f"\n  collection '{args.collection}' now holds {col.count():,} chunks")

    # Report name carries the run_id: a fixed name means a concurrent or
    # later run silently clobbers an earlier one's stats. Measured 2026-08-14
    # -- a dry run finishing second overwrote the real run's report and sent
    # me looking for a bug in the walk that was never there.
    Path(f"ingest-report-{run_id}.json").write_text(
        json.dumps({"run_id": run_id, "generated_utc": now, "stats": stats},
                   indent=2),
        encoding="utf-8",
    )
    print(f"  wrote ingest-report-{run_id}.json")


if __name__ == "__main__":
    main()
