#!/usr/bin/env python3
"""
dex-hydrate.py -- pull the manifest's files down, and let a DIFFERENT tool say
whether it worked.

WHY THE VERIFICATION IS SPLIT OUT
---------------------------------
AB-0029 (ddl-canon, promoted 2026-08-05): *the environment that built it is the
worst possible judge of whether it works.* The supporting evidence orders
detection quality by DISTANCE from the build environment -- by hand
(author-adjacent), by instrument (author-built, still inside), by foreign
machine (outside entirely) -- and finds it improves monotonically with distance.

The naive executor hydrates a file, re-checks the attribute bit with the same
helper it used to decide, and reports success. That is the author's instrument
grading the author's work over the author's own inputs. It would report a clean
run for any failure mode both halves share -- e.g. a wrong attribute mask,
which is exactly the trap Python's missing stat constants set for this project
three days ago.

So this tool does NOT get to certify itself:

    hydration  ->  dex-hydrate.py   (this file)
    verdict    ->  dex-ledger.py    (different author, different code path,
                                     its own literal constants, its own tests)

`--verify` shells out to dex-ledger.py to re-inventory the tree and compares
dispositions. If the two disagree about what is now local, the disagreement is
the finding. A pass here means two independently-written classifiers agree,
which is a materially stronger claim than one of them repeating itself.

It is still inside the build environment -- both tools are ours and inherit our
blind spots. AB-0029 is explicit that only external evaluation has maximum
distance. This narrows the gap; it does not close it.

RESUMABILITY IS NOT A CONVENIENCE
---------------------------------
7,701 files across two cloud providers will not finish in one clean pass. A
half-finished hydration that reports success leaves the build reading a
partially-cached tree -- the exact failure this whole line of work exists to
prevent. So every file's outcome is journalled as it happens, and a re-run
skips what is already materialized rather than assuming the previous run
finished.

  python dex-hydrate.py --manifest M.json --dry-run     what would move, nothing moves
  python dex-hydrate.py --manifest M.json               hydrate, journal each outcome
  python dex-hydrate.py --manifest M.json --verify      + independent re-inventory

Exit: 0 all materialized - 1 some still not local - 2 bad usage
      3 the two classifiers DISAGREE - 4 manifest unusable
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Literal, for the reason dex-ledger.py documents at length: Python 3.12 does
# not define the recall constants, so getattr(stat, ...) silently yields 0 and
# classifies every placeholder as local. Measured placeholders here also lack
# FILE_ATTRIBUTE_OFFLINE, so that constant alone is not sufficient either.
FILE_ATTRIBUTE_OFFLINE               = 0x00001000
FILE_ATTRIBUTE_RECALL_ON_OPEN        = 0x00040000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
NOT_MATERIALIZED = (FILE_ATTRIBUTE_OFFLINE
                    | FILE_ATTRIBUTE_RECALL_ON_OPEN
                    | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS)


def is_local(path: str) -> bool | None:
    """True local, False placeholder, None cannot tell."""
    try:
        st = os.stat(path, follow_symlinks=False)
    except OSError:
        return None
    return not (getattr(st, "st_file_attributes", 0) & NOT_MATERIALIZED)


def hydrate_one(path: str, chunk: int = 1 << 20) -> tuple[bool, str]:
    """Force materialization by reading the whole file.

    Reading is what actually triggers the recall on both providers. Nothing
    is written, nothing is moved, and the file's content is discarded -- the
    download is the entire point and the side effect is the goal.
    """
    try:
        with open(path, "rb") as f:
            while f.read(chunk):
                pass
        return True, ""
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"


def independent_verify(paths: list[str], roots: set[str]) -> tuple[dict, str]:
    """Ask dex-ledger.py -- a different tool -- what is now local.

    Deliberately not a second call to is_local(). See the module docstring.
    """
    ledger_tool = HERE / "dex-ledger.py"
    if not ledger_tool.exists():
        return {}, f"dex-ledger.py not found at {ledger_tool}"

    wanted = set(os.path.normcase(p) for p in paths)
    verdict: dict[str, str] = {}
    tmp = Path(tempfile.mkdtemp(prefix="hydrate-verify-"))

    for i, root in enumerate(sorted(roots)):
        out = tmp / f"post-{i}.jsonl"
        r = subprocess.run(
            [sys.executable, str(ledger_tool), "--inventory", root,
             "--out", str(out), "--json"],
            capture_output=True, text=True, timeout=7200,
        )
        # exit 1 just means losses were recorded, which is expected here.
        if r.returncode not in (0, 1) or not out.exists():
            return {}, (f"dex-ledger.py failed on {root} "
                        f"(exit {r.returncode}): {r.stderr[-300:]}")
        with out.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "_ledger" in rec or "_ledger_end" in rec:
                    continue
                p = os.path.normcase(rec.get("path", ""))
                if p in wanted:
                    verdict[p] = rec.get("disposition", "?")
    return verdict, ""


def main() -> int:
    ap = argparse.ArgumentParser(description="hydrate the manifest's files")
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true",
                    help="re-inventory with dex-ledger.py and compare verdicts")
    ap.add_argument("--journal", type=Path, default=None)
    ap.add_argument("--limit", type=int, default=0, help="stop after N (for a trial run)")
    a = ap.parse_args()

    try:
        man = json.loads(a.manifest.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"manifest unusable: {exc}", file=sys.stderr)
        return 4

    files = man.get("files") or []
    if not files:
        print("manifest lists no files", file=sys.stderr)
        return 4

    print(f"manifest        {a.manifest}")
    print(f"generated       {man.get('generated_at')}")
    print(f"exclusion set   {str(man.get('exclusion_digest'))[:16]}...")
    print(f"files           {len(files):,}   "
          f"{man.get('hydrate_bytes', 0)/1024**3:,.2f} GB\n")

    # Resume: anything already local is skipped, not re-fetched.
    todo, already, unknown = [], 0, 0
    for f in files:
        s = is_local(f["path"])
        if s is True:
            already += 1
        elif s is None:
            unknown += 1
        else:
            todo.append(f)

    print(f"already local   {already:,}")
    if unknown:
        # These are not a hydration problem -- the manifest names files that
        # are no longer there. Measured 2026-08-05: 31 files present when the
        # ledger was walked had vanished ~20 hours later.
        #
        # The source tree changes underneath us, so a manifest is a SNAPSHOT
        # and ages. Saying "unstat-able" and moving on would let a stale
        # manifest quietly shrink the corpus while every count still balanced.
        pct = 100.0 * unknown / max(len(files), 1)
        print(f"GONE            {unknown:,}  ({pct:.1f}% of the manifest)")
        print(f"                present when the ledger was walked "
              f"({man.get('generated_at')}), absent now.")
        print(f"                The manifest has aged. Re-run dex-ledger.py and")
        print(f"                regenerate before treating it as the build input.")
    print(f"to hydrate      {len(todo):,}   "
          f"{sum(f['size'] for f in todo)/1024**3:,.2f} GB\n")

    if a.limit:
        todo = todo[:a.limit]
        print(f"--limit {a.limit}: trial run over {len(todo):,} file(s)\n")

    if a.dry_run:
        for f in todo[:15]:
            print(f"  would hydrate  {f['size']/1024:>9,.0f} KB  {f['path']}")
        if len(todo) > 15:
            print(f"  ... and {len(todo)-15:,} more")
        print("\ndry run — nothing was downloaded.")
        return 0

    journal = a.journal or a.manifest.with_suffix(".hydration-journal.jsonl")
    ok, failed, t0 = 0, [], time.time()
    with journal.open("a", encoding="utf-8") as j:
        j.write(json.dumps({"_run": 1, "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "manifest": str(a.manifest), "todo": len(todo)}) + "\n")
        for i, f in enumerate(todo, 1):
            got, err = hydrate_one(f["path"])
            if got:
                ok += 1
            else:
                failed.append({"path": f["path"], "error": err})
            j.write(json.dumps({"path": f["path"], "ok": got, "error": err}) + "\n")
            if i % 250 == 0 or i == len(todo):
                el = time.time() - t0
                print(f"  {i:>6,}/{len(todo):,}  ok={ok:,} failed={len(failed):,}  "
                      f"{el/60:,.1f} min")

    print(f"\nread {ok:,} file(s); {len(failed):,} failed. journal: {journal}")
    for f in failed[:10]:
        print(f"  FAILED  {f['path']}  {f['error']}")

    if not a.verify:
        print("\nNOT VERIFIED. Re-run with --verify to have dex-ledger.py")
        print("independently confirm what is actually local now.")
        return 1 if failed else 0

    # ---- the part that matters: a second, independent opinion ----
    print("\nverifying with dex-ledger.py (different tool, different code path)...")
    # Re-inventory the manifest's real roots. Drive anchors would make
    # dex-ledger.py walk all of C:\, which is not the claim being checked.
    roots = set()
    for f in files:
        p = Path(f["path"])
        for cand in (r"C:\Users\dkitc\OneDrive\02_DexUniverse_v4.0",
                     r"C:\Users\dkitc\iCloudDrive\Documents\05_DirectIngest"):
            if str(p).lower().startswith(cand.lower()):
                roots.add(cand)
    verdict, err = independent_verify([f["path"] for f in files], roots)
    if err:
        print(f"  verification could not run: {err}", file=sys.stderr)
        print("  Treating as UNVERIFIED rather than passed.", file=sys.stderr)
        return 1

    mine_local = {os.path.normcase(f["path"]) for f in files if is_local(f["path"])}
    # dex-ledger.py has SIX dispositions; "is the file local" is not the same
    # question as "is its disposition materialized".
    #
    # Measured 2026-08-05: the first full run reported 40 disagreements, all in
    # one direction. All 40 were ZERO-BYTE files. dex-ledger classifies those
    # as `empty` -- a distinct and correct answer, since a zero-byte file has
    # nothing to download. Counting only `materialized` made my comparator
    # treat a correct classification as a conflict.
    #
    # Neither classifier was wrong. The judge was. Worth keeping, because the
    # disagreement mechanism did its job: it refused to certify and sent me
    # looking, and what it found was a defect in the checker rather than in
    # either thing being checked.
    LOCAL_DISPOSITIONS = {"materialized", "empty"}
    theirs_local = {p for p, d in verdict.items() if d in LOCAL_DISPOSITIONS}

    only_mine = mine_local - theirs_local
    only_theirs = theirs_local - mine_local
    still_cloud = len(files) - len(theirs_local)

    print(f"  dex-ledger.py classified {len(verdict):,} of {len(files):,} manifest files")
    print(f"  both agree local        {len(mine_local & theirs_local):,}")
    print(f"  still not local         {still_cloud:,}")

    if only_mine or only_theirs:
        print("\n" + "=" * 70)
        print("  CLASSIFIER DISAGREEMENT — do not trust either verdict")
        print(f"    this tool says local, dex-ledger says not: {len(only_mine):,}")
        print(f"    dex-ledger says local, this tool says not: {len(only_theirs):,}")
        for p in list(only_mine)[:5] + list(only_theirs)[:5]:
            print(f"      {p}")
        print("  Two independently-written classifiers reading the same bits")
        print("  reached different conclusions. That is the finding.")
        print("=" * 70)
        return 3

    if still_cloud:
        # Distinguish "not downloaded yet" from "no longer exists". Telling
        # someone to re-run to resume a file that is gone is a small lie, and
        # it would have them chase a transfer that can never complete.
        gone_now = sum(1 for f in files if is_local(f["path"]) is None)
        pending = still_cloud - gone_now
        print()
        if pending > 0:
            print(f"  {pending:,} file(s) not yet local — re-run to resume.")
        if gone_now > 0:
            print(f"  {gone_now:,} file(s) no longer exist and cannot be hydrated.")
            print( "  The manifest has aged past its source. Regenerate it from a")
            print( "  fresh dex-ledger.py walk before using it as the build input.")
        return 1

    print("\n  both classifiers agree: every manifest file is materialized.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
