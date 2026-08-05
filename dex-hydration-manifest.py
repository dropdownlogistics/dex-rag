#!/usr/bin/env python3
"""
dex-hydration-manifest.py -- decide what to download BEFORE anything downloads.

THE PROBLEM THIS SOLVES
-----------------------
81% of the corpus source is not on this machine: 6,459 of 7,931 ingestible
files, 7.68 GB, held as cloud placeholders by OneDrive and iCloud.

A pipeline pointed at those roots does not fail. It succeeds, slowly, pulling
gigabytes, and produces a corpus whose composition depends on which files
happened to be cached that day. That is worse than a crash, because it looks
like it worked.

So hydration must be a CONTROLLED OPERATION AGAINST A NAMED LIST, reviewable
before a single byte moves -- not a side effect of walking a tree.

WHAT IT DOES
------------
Reads the inventory ledgers (which recorded every file's disposition WITHOUT
reading any of them), and emits the explicit set to hydrate:

    placeholder  AND  ingestible extension  AND  not excluded

THE EXCLUSION GATE IS APPLIED HERE, and this is the point of the tool. The
ledgers were written with no exclusion rules, so the 6.39 GB mailbox and the
sequestered legal material are in them as ordinary records. Without this
filter the "obvious" hydration set is 7.68 GB and includes both. With it, the
mailbox drops out on the `*.mbox` pattern and the sequestered tree drops out
on both its path and its directory name.

It declares nothing: ingestible extensions are read from dex-ingest.py, and
the exclusion rules from the live exclusion list. A value baked in here would
become another disagreeing declaration.

FAILS CLOSED. No exclusion list, no manifest -- the same refusal as ingest,
for the same reason: an absent list is indistinguishable from one that failed
to load, and emitting a hydration set on that assumption is how sequestered
material gets pulled down.

  python dex-hydration-manifest.py --ledger A.jsonl --ledger B.jsonl
  python dex-hydration-manifest.py --ledger ... --out manifest.json

Exit: 0 manifest produced - 2 exclusion list unusable - 3 no ledger readable

Read-only. Reads ledgers and the exclusion list. Touches no source file.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dex_exclusions import load_exclusions  # noqa: E402


def ingestible_extensions() -> tuple[set[str], str]:
    """Cited from dex-ingest.py, never restated here."""
    spec = importlib.util.spec_from_file_location("dex_ingest_src", HERE / "dex-ingest.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["dex_ingest_src"] = m
    spec.loader.exec_module(m)
    return set(m.PHASE1_EXTENSIONS), "dex-ingest.py:PHASE1_EXTENSIONS"


def read_ledger(path: Path) -> tuple[list[dict], dict, str | None]:
    """Return (records, footer, problem). A ledger without its footer is
    treated as unusable -- truncation is otherwise undetectable, which is the
    defect its author found in his own first version."""
    records, footer, header = [], None, None
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    return [], {}, f"{path.name}: malformed JSON line"
                if o.get("_ledger"):
                    header = o
                elif o.get("_ledger_end"):
                    footer = o
                else:
                    records.append(o)
    except OSError as exc:
        return [], {}, f"{path.name}: {exc}"

    if footer is None:
        return [], {}, f"{path.name}: NO FOOTER -- ledger is truncated, refusing to use it"
    seen = footer.get("files_seen")
    if seen is not None and seen != len(records):
        return [], {}, (f"{path.name}: footer says {seen:,} files, found {len(records):,} "
                        "-- ledger does not describe the tree it walked")
    return records, footer, None


def main() -> int:
    ap = argparse.ArgumentParser(description="emit the explicit hydration set")
    ap.add_argument("--ledger", action="append", required=True, type=Path,
                    help="inventory ledger .jsonl (repeatable)")
    ap.add_argument("--out", type=Path, default=None, help="write manifest JSON here")
    ap.add_argument("--show", type=int, default=12, help="sample paths to print")
    a = ap.parse_args()

    # Fail closed before reading anything else.
    ex = load_exclusions()
    exts, ext_src = ingestible_extensions()
    print(f"[manifest] ingestible extensions cited from {ext_src} ({len(exts)})")

    hydrate = []
    skipped = defaultdict(lambda: {"files": 0, "bytes": 0})
    unreachable = defaultdict(lambda: {"files": 0, "bytes": 0})
    # dex-convert.py's actual dispatch, read from its source rather than
    # assumed. Anything outside BOTH this and PHASE1_EXTENSIONS has no path
    # into the corpus at all.
    convert_src = (HERE / "dex-convert.py").read_text(encoding="utf-8", errors="replace")
    CONVERTIBLE = {e for e in (".csv", ".html", ".json", ".vcf", ".mbox")
                   if f'ext == "{e}"' in convert_src or f"--mbox" in convert_src and e == ".mbox"}
    totals = {"records": 0, "already_local": 0, "not_ingestible": 0,
              "excluded": 0, "other_disposition": 0}
    problems = []

    for lp in a.ledger:
        recs, footer, prob = read_ledger(lp)
        if prob:
            problems.append(prob)
            continue
        print(f"[manifest] {lp.name}: {len(recs):,} records, "
              f"root={footer.get('root', '?')}")
        for r in recs:
            totals["records"] += 1
            disp, path, size = r.get("disposition"), r.get("path", ""), r.get("size", 0)
            ext = (r.get("ext") or "").lower()

            if disp == "materialized":
                totals["already_local"] += 1
                continue
            if disp != "placeholder":
                totals["other_disposition"] += 1
                continue
            if ext not in exts:
                totals["not_ingestible"] += 1
                # Not hydrating these is correct -- downloading a file nothing
                # can read spends bytes for no corpus. But omitting them
                # SILENTLY is the defect this project keeps meeting, so they
                # are counted, sized, and named as a gap.
                unreachable[ext]["files"] += 1
                unreachable[ext]["bytes"] += size
                continue
            why = ex.reason(path)
            if why:
                totals["excluded"] += 1
                skipped[why]["files"] += 1
                skipped[why]["bytes"] += size
                continue
            hydrate.append({"path": path, "size": size, "ext": ext})

    if problems:
        print("\nLEDGER PROBLEMS", file=sys.stderr)
        for p in problems:
            print(f"  !! {p}", file=sys.stderr)
    if not totals["records"]:
        print("no usable ledger", file=sys.stderr)
        return 3

    gb = sum(h["size"] for h in hydrate) / 1024**3
    by_ext = defaultdict(lambda: {"files": 0, "bytes": 0})
    for h in hydrate:
        by_ext[h["ext"]]["files"] += 1
        by_ext[h["ext"]]["bytes"] += h["size"]

    print("\n" + "=" * 70)
    print("  HYDRATION SET")
    print("=" * 70)
    print(f"  records examined        {totals['records']:>8,}")
    print(f"  already local           {totals['already_local']:>8,}  (nothing to do)")
    print(f"  not ingestible          {totals['not_ingestible']:>8,}")
    print(f"  EXCLUDED by policy      {totals['excluded']:>8,}")
    print(f"  other disposition       {totals['other_disposition']:>8,}")
    print(f"  --")
    print(f"  TO HYDRATE              {len(hydrate):>8,}   {gb:,.2f} GB")
    print()

    if skipped:
        print("  what the exclusion gate kept out, and why:")
        for why, s in sorted(skipped.items(), key=lambda kv: -kv[1]["bytes"]):
            print(f"    {s['files']:>5,} files  {s['bytes']/1024**3:>7,.2f} GB   {why}")
        print()

    if unreachable:
        ub = sum(v["bytes"] for v in unreachable.values())
        un = sum(v["files"] for v in unreachable.values())
        print(f"  NOT HYDRATED — no path into the corpus ({un:,} files, {ub/1024**3:,.2f} GB)")
        print("  Named rather than silently dropped. Hydrating these would spend")
        print("  bytes on files nothing can currently read.")
        for e, s in sorted(unreachable.items(), key=lambda kv: -kv[1]["bytes"])[:10]:
            has = "convertible" if e in CONVERTIBLE else "NO CONVERTER"
            print(f"    {e:<8} {s['files']:>6,} files  {s['bytes']/1024**3:>7,.2f} GB   {has}")
        print()

    print("  by extension:")
    for e, s in sorted(by_ext.items(), key=lambda kv: -kv[1]["bytes"])[:12]:
        print(f"    {e:<8} {s['files']:>6,} files  {s['bytes']/1024**3:>7,.2f} GB")

    big = sorted(hydrate, key=lambda h: -h["size"])[:a.show]
    if big:
        print(f"\n  largest {len(big)} in the set:")
        for h in big:
            print(f"    {h['size']/1024**2:>9,.1f} MB  {h['path']}")

    print("=" * 70)

    if a.out:
        a.out.write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "exclusion_digest": ex.digest,
            "exclusion_source": str(ex.source),
            "extensions_source": ext_src,
            "totals": totals,
            "hydrate_count": len(hydrate),
            "hydrate_bytes": sum(h["size"] for h in hydrate),
            "excluded_by_reason": {k: v for k, v in skipped.items()},
            "files": hydrate,
        }, indent=2), encoding="utf-8")
        print(f"\nmanifest written: {a.out}")
        print("Nothing has been downloaded. This is a proposal, reviewable before it runs.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
