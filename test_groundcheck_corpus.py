#!/usr/bin/env python3
"""
test_groundcheck_corpus.py -- run the fabrication detector over REAL DDL prose.

My self-test uses fixtures I wrote, judged by a tool I wrote. Per AB-0029 that
is the weak tier. The corpus is a fixture nobody authored for this purpose and
predates it by months.

TWO DIRECTIONS, both derived from the corpus rather than invented:

  SELF   a chunk checked against ITSELF. Every specific it contains must be
         grounded, because the text and the source are the same string. Any
         ungrounded finding here is a FALSE POSITIVE in the extractor, and
         real prose contains punctuation, casing and formatting my fixtures
         never had.

  CROSS  a chunk checked against a DIFFERENT chunk. Specifics from document A
         are mostly absent from unrelated document B, so ungrounded findings
         SHOULD appear. If they do not, the detector is not detecting.

The cross direction is the control. Without it a detector that found nothing
would score a perfect 100% on the self direction and look flawless.

Read-only.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chromadb
from dex_core import CHROMA_DIR, suffixed
from dex_groundcheck import check, extract

N = 60


def main() -> int:
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    col = client.get_collection(suffixed("dex_canon"))
    got = col.get(limit=N * 3, include=["documents"])
    docs = [d for d in got["documents"] if d and len(d.strip()) > 300][:N]
    if len(docs) < 10:
        print("not enough usable chunks", file=sys.stderr)
        return 2

    print(f"corpus: {col.name}  ({col.count():,} chunks)")
    print(f"sample: {len(docs)} chunks of real DDL prose\n")

    # ---- SELF: text against itself. Ungrounded == false positive. ----
    fp_chunks, fp_total, specifics_total = 0, 0, 0
    worst = []
    for d in docs:
        r = check(d, d)
        specifics_total += r["checked"]
        if r["ungrounded"]:
            fp_chunks += 1
            fp_total += len(r["ungrounded"])
            worst.append((len(r["ungrounded"]), r["ungrounded"][:3]))

    print("SELF — every specific must be grounded (text == source)")
    print(f"  specifics extracted     {specifics_total:,}")
    print(f"  FALSE POSITIVES         {fp_total:,} across {fp_chunks} chunk(s)")
    if worst:
        worst.sort(reverse=True)
        for n, items in worst[:3]:
            print(f"    {n} in one chunk: {[i['value'][:40] for i in items]}")

    # ---- CROSS: unrelated text. Ungrounded SHOULD appear. ----
    rnd = random.Random(42)          # fixed seed: reruns are comparable
    detected, pairs = 0, 0
    for i, d in enumerate(docs):
        other = docs[(i + 1 + rnd.randrange(len(docs) - 1)) % len(docs)]
        if other is d:
            continue
        if not extract(d):
            continue                 # no specifics to find; not a fair pair
        pairs += 1
        if check(d, other)["ungrounded"]:
            detected += 1

    print("\nCROSS — unrelated source; ungrounded specifics SHOULD appear")
    print(f"  pairs with specifics    {pairs}")
    print(f"  detected as ungrounded  {detected}  ({100*detected/max(pairs,1):.0f}%)")

    fp_rate = 100 * fp_total / max(specifics_total, 1)
    det_rate = 100 * detected / max(pairs, 1)
    print("\n" + "=" * 66)
    print(f"  false-positive rate  {fp_rate:.2f}%   (specifics wrongly called invented)")
    print(f"  detection rate       {det_rate:.0f}%   (unrelated source caught)")

    ok = True
    if fp_total:
        print("\n  FAIL: a specific was called ungrounded against its own text.")
        print("        That is the extractor inventing findings, and it would")
        print("        train a reader to ignore the warning.")
        ok = False
    if det_rate < 80:
        print(f"\n  FAIL: only {det_rate:.0f}% of unrelated pairs were caught.")
        print("        A detector that rarely detects passes the self direction")
        print("        trivially and proves nothing.")
        ok = False
    if ok:
        print("\n  both directions hold on real prose.")
    print("=" * 66 + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
