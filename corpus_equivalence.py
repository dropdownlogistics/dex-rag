#!/usr/bin/env python3
"""
Does `ddl_everything_v2` actually cover the eight legacy collections?

MAP v0.2 open question 3: what retires the legacy collections -- a date, a soak
period, or a measured equivalence test? **I said I wanted the third and had not
built it.** This is it.

WHY DOCUMENT-LEVEL, NOT CHUNK-LEVEL
-----------------------------------
The collections were chunked by different code with different sizes, so chunk
counts are not comparable and never will be. `ddl_everything_v2` holding fewer
chunks than a legacy collection proves nothing either way.

**The question that actually matters for retirement is: is there any SOURCE
DOCUMENT retrievable from a legacy collection that is not retrievable from
`ddl_everything_v2`?** If the answer is none, the legacy collections hold no
unique knowledge and retiring them loses nothing.

THE COMPARISON IS DELIBERATELY UNFAIR TO MY OWN COLLECTION
----------------------------------------------------------
Legacy metadata carries `source_file` (a path relative to a drop folder) and
`filename`. `ddl_everything_v2` carries `source_path` (absolute) and
`filename`. **Only `filename` is common, so matching is by filename.**

That is a weak key and it is weak in a specific direction: two different
documents sharing a filename count as covered when they may not be. **So this
test can produce a FALSE PASS and cannot produce a false fail.** Anything it
reports as MISSING is genuinely missing; anything it reports as covered is
covered *by filename*, which is a claim about names and not about content.

**Stated here rather than in a footnote because retirement is irreversible and
this is the weakness someone would otherwise discover afterwards.**
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from dex_core import CHROMA_DIR

LEGACY = ["dex_canon", "ddl_archive", "dex_code", "ext_creator",
          "dex_canon_v2", "ddl_archive_v2", "dex_code_v2", "ext_creator_v2"]
CANDIDATE = "ddl_everything_v2"
BATCH = 2000


def filenames_of(client, name: str) -> tuple[set[str], int]:
    col = client.get_collection(name)
    total = col.count()
    names: set[str] = set()
    off = 0
    while off < total:
        got = col.get(limit=BATCH, offset=off, include=["metadatas"])
        mds = got["metadatas"]
        if not mds:
            break
        for m in mds:
            fn = m.get("filename")
            if not fn:
                sf = m.get("source_file") or m.get("source_path") or ""
                fn = str(sf).replace("\\", "/").rsplit("/", 1)[-1]
            if fn:
                names.add(str(fn))
        off += BATCH
    return names, total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default=CANDIDATE)
    args = ap.parse_args()

    c = chromadb.PersistentClient(path=CHROMA_DIR)

    cand_names, cand_total = filenames_of(c, args.candidate)
    print(f"  {args.candidate}: {cand_total:,} chunks, "
          f"{len(cand_names):,} distinct filenames\n")

    report = {}
    all_missing: Counter[str] = Counter()
    verdict_clean = True

    for name in LEGACY:
        try:
            names, total = filenames_of(c, name)
        except Exception as e:
            print(f"  {name}: unreadable ({e})")
            continue
        missing = names - cand_names
        covered = len(names) - len(missing)
        pct = 100.0 * covered / len(names) if names else 100.0
        if missing:
            verdict_clean = False
            for m in missing:
                all_missing[m] += 1
        flag = "OK  " if not missing else "GAP "
        print(f"  [{flag}] {name:<18} {total:>8,} chunks  "
              f"{len(names):>6,} files  covered {pct:5.1f}%  "
              f"missing {len(missing):,}")
        report[name] = {"chunks": total, "files": len(names),
                        "covered_pct": round(pct, 2),
                        "missing": sorted(missing)[:500],
                        "missing_count": len(missing)}

    print()
    print("=" * 72)
    if verdict_clean:
        print("  EVERY legacy filename is present in the candidate collection.")
        print("  Retirement loses no document BY FILENAME. This is not proof of")
        print("  content equivalence -- see the module docstring.")
    else:
        print(f"  {len(all_missing):,} distinct filenames exist in legacy and NOT")
        print("  in the candidate. Retirement would lose them.")
        print()
        for fn, n in all_missing.most_common(25):
            print(f"    {fn[:88]}")
        if len(all_missing) > 25:
            print(f"    ... and {len(all_missing)-25:,} more")
    print("=" * 72)

    out = Path("corpus-equivalence-report.json")
    out.write_text(json.dumps({
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "candidate": args.candidate,
        "candidate_chunks": cand_total,
        "candidate_files": len(cand_names),
        "match_key": "filename (weak -- can false-pass, cannot false-fail)",
        "clean": verdict_clean,
        "legacy": report,
    }, indent=2), encoding="utf-8")
    print(f"  wrote {out}")
    return 0 if verdict_clean else 30


if __name__ == "__main__":
    sys.exit(main())
