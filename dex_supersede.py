#!/usr/bin/env python3
"""
dex_supersede.py -- hide stale versions of edited files from retrieval, without
deleting anything.

WHY
---
dex-ingest-everything.py keys chunks as `<file_hash>_<i>`. Re-running it after a
file is edited ADDS the new version and leaves the old one retrievable, so Dex Jr
can answer from a document's past. Measured 2026-09-25 after the first refresh:
138 of 27,177 paths carry more than one version, 1,153 of 469,133 chunks.

WHAT IT DOES
------------
For every source_path with more than one file_hash, the CURRENT version is the
hash of the file on disk now (same formula as the ingest: sha256(raw)[:16]). If
the file no longer exists, the most recently ingested version is kept. Chunk ids
of every other version are written to `superseded_ids.json`. The query paths
(dex_jr_query.py, dex-openai-api.py) drop those ids from results.

WHAT IT DOES NOT DO
-------------------
It never writes to ChromaDB. Nothing is deleted or re-embedded (Rule 8, and the
Operator's standing "dedupe/delete only when we mean to"). Delete the sidecar and
retrieval is exactly as before. It also does NOT resolve duplicates across
different paths -- identical content is already skipped at ingest by hash.

Operator-approved 2026-09-25 as part of the Dex Jr upgrade (ddl-org
OPERATOR-DECISIONS). Re-run after every everything-ingest.

    python dex_supersede.py            # write superseded_ids.json, print summary
    python dex_supersede.py --dry-run  # summary only
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import chromadb

from dex_core import CHROMA_DIR

HERE = Path(__file__).resolve().parent
SIDECAR = HERE / "superseded_ids.json"
COLLECTION = "ddl_everything_v2"
PAGE = 5000


def disk_hash(path: str) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
    except OSError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    col = chromadb.PersistentClient(path=CHROMA_DIR).get_collection(COLLECTION)
    n = col.count()
    # path -> hash -> {"ids": [...], "ingested_at": latest}
    versions: dict[str, dict[str, dict]] = defaultdict(dict)
    off = 0
    while off < n:
        g = col.get(limit=PAGE, offset=off, include=["metadatas"])
        if not g["ids"]:
            break
        for cid, m in zip(g["ids"], g["metadatas"]):
            m = m or {}
            p, h = m.get("source_path"), m.get("file_hash")
            if not p or not h:
                continue
            v = versions[p].setdefault(h, {"ids": [], "ingested_at": ""})
            v["ids"].append(cid)
            v["ingested_at"] = max(v["ingested_at"], m.get("ingested_at", ""))
        off += PAGE

    stale_ids, decided = [], {"disk": 0, "latest_ingest": 0, "current_not_in_corpus": 0}
    for p, hv in versions.items():
        if len(hv) < 2:
            continue
        cur = disk_hash(p)
        if cur in hv:
            decided["disk"] += 1
        elif cur is None:
            cur = max(hv, key=lambda h: hv[h]["ingested_at"])
            decided["latest_ingest"] += 1
        else:
            # On disk, but that version was never ingested: every stored version
            # is stale, yet hiding all of them would make the file vanish.
            # Keep the newest stored one until the next ingest catches up.
            cur = max(hv, key=lambda h: hv[h]["ingested_at"])
            decided["current_not_in_corpus"] += 1
        for h, v in hv.items():
            if h != cur:
                stale_ids.extend(v["ids"])

    multi = sum(1 for hv in versions.values() if len(hv) > 1)
    print(f"{n:,} chunks · {len(versions):,} paths · {multi} with >1 version · "
          f"{len(stale_ids):,} stale chunks hidden")
    print(f"current version decided by: {decided}")
    if not a.dry_run:
        SIDECAR.write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "collection": COLLECTION, "chunks_at_generation": n,
            "paths_with_versions": multi, "ids": sorted(stale_ids)}, indent=0),
            encoding="utf-8")
        print(f"wrote {SIDECAR.name}")
    return 0


def load_superseded() -> frozenset[str]:
    """For query paths. Missing or unreadable sidecar -> nothing hidden."""
    try:
        return frozenset(json.loads(SIDECAR.read_text(encoding="utf-8"))["ids"])
    except (OSError, ValueError, KeyError):
        return frozenset()


if __name__ == "__main__":
    raise SystemExit(main())
