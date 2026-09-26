#!/usr/bin/env python3
"""
Recover documents whose ONLY surviving copy is chunks in a legacy collection.

WHY THIS EXISTS
---------------
The corpus equivalence test (`corpus_equivalence.py`) was written to answer
whether the eight legacy collections could be retired. It answered NO, and for
a reason nobody predicted:

    170 filenames exist in the legacy collections and not in
    ddl_everything_v2 -- and those files DO NOT EXIST ON DISK ANYWHERE.

`ddl_everything_v2` ingests from disk, so it could never have contained them.
Their source files are gone. **The embedded chunks are the last copy**, and
they include `CR-CORPUS-VISION-001-SYNTH.txt` -- a full ten-seat council
synthesis on DDL corpus architecture from 2026-03-14.

My earlier recommendation was to record the legacy collections in the
EvidenceLocker and drop them after a soak period. **That would have destroyed
the only remaining copy of 170 documents.** The measured test is the only
reason that is not what happened.

WHAT THIS RECOVERS, AND WHAT IT CANNOT
--------------------------------------
Chunks were written with overlap. Concatenating them reproduces the overlap
region twice, so **reconstruction is APPROXIMATE and every output file says so
in its own header.** This does not recreate the original file; it recovers the
readable content of one.

**Nothing is deleted, dropped or modified.** Read-only against the collections;
writes new files to a recovery directory. Retirement remains a separate
decision requiring Operator approval under dex-rag Rule 8, and this script does
not make it safer -- it makes the loss visible and recoverable first.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from dex_core import CHROMA_DIR

LEGACY = ["dex_canon", "ddl_archive", "dex_code", "ext_creator",
          "dex_canon_v2", "ddl_archive_v2", "dex_code_v2", "ext_creator_v2"]
CANDIDATE = "ddl_everything_v2"
OUT = Path(r"D:\ORPHAN_RECOVERY")
BATCH = 2000

SAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def collection_filenames(client, name):
    col = client.get_collection(name)
    total = col.count()
    names = set()
    off = 0
    while off < total:
        got = col.get(limit=BATCH, offset=off, include=["metadatas"])
        mds = got["metadatas"]
        if not mds:
            break
        for m in mds:
            fn = m.get("filename")
            if fn:
                names.add(str(fn))
        off += BATCH
    return names


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    c = chromadb.PersistentClient(path=CHROMA_DIR)
    have = collection_filenames(c, CANDIDATE)
    print(f"  {CANDIDATE}: {len(have):,} distinct filenames")

    orphans: dict[str, str] = {}   # filename -> collection holding it
    for name in LEGACY:
        try:
            for fn in collection_filenames(c, name) - have:
                orphans.setdefault(fn, name)
        except Exception as e:
            print(f"  {name}: unreadable ({e})")
    print(f"  orphaned filenames (in legacy, not on disk, not in candidate): "
          f"{len(orphans):,}\n")

    if args.dry_run:
        for fn, src in sorted(orphans.items())[:30]:
            print(f"    {src:<16} {fn[:80]}")
        print(f"\n  DRY RUN -- nothing written")
        return 0

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    written = 0
    failed = []
    manifest = []

    for fn, src in sorted(orphans.items()):
        col = c.get_collection(src)
        # Page until exhausted. A hardcoded limit here is not a cap on effort,
        # it is a silent truncation reported as data loss.
        #
        # Measured 2026-08-15: `limit=5000` truncated Reddit_comments.txt at
        # 5,000 of 6,066 chunks, and the INCOMPLETE banner then told the reader
        # 1,066 chunks were missing FROM THE COLLECTION. They were present; the
        # query never asked for them. **A tool reporting its own limitation as a
        # property of the data is the failure this whole session has been
        # about**, and it appeared inside the recovery written to prevent a
        # different instance of it.
        docs, mds, off = [], [], 0
        while True:
            got = col.get(where={"filename": fn}, limit=BATCH, offset=off,
                          include=["documents", "metadatas"])
            if not got["documents"]:
                break
            docs.extend(got["documents"])
            mds.extend(got["metadatas"])
            off += BATCH
        if not docs:
            failed.append(fn)
            continue
        pairs = sorted(zip(mds, docs),
                       key=lambda t: int(t[0].get("chunk_index") or 0))
        body = "\n".join(d for _, d in pairs)
        expected = int(pairs[0][0].get("total_chunks") or len(pairs))

        header = (
            f"<<< RECOVERED FROM CHUNKS -- APPROXIMATE RECONSTRUCTION >>>\n"
            f"filename        : {fn}\n"
            f"recovered_from  : collection `{src}`\n"
            f"recovered_at    : {now}\n"
            f"chunks_found    : {len(pairs)} of {expected} expected\n"
            f"source_file     : {pairs[0][0].get('source_file', '')}\n"
            f"\n"
            f"THIS IS NOT THE ORIGINAL FILE. Chunks were written with overlap,\n"
            f"so text at chunk boundaries appears twice. The original does not\n"
            f"exist on disk; these chunks were its last surviving copy.\n"
            f"{'!' * 68}\n"
            f"INCOMPLETE: {expected - len(pairs)} chunk(s) missing.\n"
            f"{'!' * 68}\n" if len(pairs) < expected else ""
        )
        safe = SAFE.sub("_", fn)[:150]
        (outdir / f"{safe}.recovered.txt").write_text(header + "\n" + body,
                                                      encoding="utf-8")
        written += 1
        manifest.append({"filename": fn, "collection": src,
                         "chunks_found": len(pairs), "chunks_expected": expected,
                         "complete": len(pairs) >= expected})

    (outdir / "RECOVERY-MANIFEST.json").write_text(json.dumps({
        "generated_utc": now, "recovered": written,
        "unrecoverable": failed, "files": manifest,
    }, indent=2), encoding="utf-8")

    incomplete = [m for m in manifest if not m["complete"]]
    print(f"  recovered      {written:>5}")
    print(f"  INCOMPLETE     {len(incomplete):>5}  (fewer chunks than total_chunks)")
    print(f"  unrecoverable  {len(failed):>5}")
    print(f"\n  wrote {outdir}")
    print("\n  Nothing was deleted or modified. Retirement is still an Operator")
    print("  decision under Rule 8; this only makes the loss recoverable first.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
