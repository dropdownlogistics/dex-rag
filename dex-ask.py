#!/usr/bin/env python3
"""
dex-ask.py -- ask Dex Jr. a question and grade the answer in the same breath.

WHY THIS EXISTS
---------------
We built a retrieval eval, a query gate, and a fabrication detector, and then
never pointed any of them at an actual answer. Asking Dex a question and
reading the reply is how every previous assessment of him has been done, and
"it looked right" is not a measurement.

This runs the real query path (`dex_jr_query.py`, unchanged) and then applies
two checks the answer cannot pass by sounding confident:

  GROUNDING     every checkable specific in the answer must occur in the
                chunks he was actually given. `dex_groundcheck.py` -- proves
                invention, not correctness.

  CITATION      every cited source must have CONTRIBUTED. A chunk that
                grounds nothing and shares no meaningful vocabulary with the
                answer was retrieved, listed, and did no work.

WHY THE CITATION CHECK EARNS ITS PLACE
--------------------------------------
Measured on the first real query run through this path -- "What is the
Platinum Bounce recovery protocol?" -- Dex returned 5 chunks and cited all 5.
Two were `semantic-kernel` C# OpenAPI parser source at distances 0.90 and
0.92, retrieved from `dex_code_v2` and utterly unrelated to the question.

The answer was fine. The CITATION LIST was inflated by 40%. A reader counts
five sources and infers five sources supported it, which is the specific way
a citation launders a guess -- and it is invisible if you only check whether
the prose is grounded.

`dex_jr_query.py` applies no distance floor, so anything in the top-k is
cited regardless of how far away it is. That is the mechanism.

  python dex-ask.py "your question"
  python dex-ask.py "your question" --top-k 8 --collection dex_canon
  python dex-ask.py --file questions.txt          one per line, batch

Exit: 0 answer grounded and citations clean - 1 ungrounded specifics
      2 inflated citations only - 3 both - 4 query failed
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dex_groundcheck import check as ground_check, extract, _norm  # noqa: E402

QUERY_TOOL = HERE / "dex_jr_query.py"

# Words too common to prove a chunk contributed anything.
_COMMON = set("""the a an and or but if of to in on at for from with by as is are was
were be been being it its this that these those which who what when where how not no
you your we our they their he she them then than so such can could may might must
will would shall should do does did done have has had having i me my""".split())


def ask(question: str, top_k: int, collection: str | None) -> dict | None:
    cmd = [sys.executable, str(QUERY_TOOL), question, "--format", "json",
           "--top-k", str(top_k)]
    if collection:
        cmd += ["--collection", collection]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        print(f"  query failed (exit {r.returncode}): {r.stderr[-300:]}", file=sys.stderr)
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as exc:
        print(f"  query output was not JSON: {exc}", file=sys.stderr)
        return None


def contribution(chunk_text: str, answer: str) -> int:
    """How many distinctive words this chunk shares with the answer.

    Deliberately crude and deliberately NOT semantic: the claim is only
    "this chunk shares distinctive vocabulary with the answer", which is
    evidence it was read. Zero overlap is strong evidence it was not.
    """
    ct = {w for w in re.findall(r"[a-z]{4,}", chunk_text.lower()) if w not in _COMMON}
    at = {w for w in re.findall(r"[a-z]{4,}", answer.lower()) if w not in _COMMON}
    return len(ct & at)


def assess(res: dict, contrib_floor: int) -> dict:
    answer = res.get("answer") or ""
    chunks = res.get("chunks") or []
    context = "\n\n".join(c.get("text", "") for c in chunks)

    g = ground_check(answer, context)

    per_chunk = []
    for c in chunks:
        txt = c.get("text", "")
        # Which of the answer's grounded specifics does THIS chunk carry?
        owned = [s["value"] for s in g["grounded"] if _norm(s["value"]) in _norm(txt)]
        overlap = contribution(txt, answer)
        per_chunk.append({
            "source": c.get("source_file", "?"),
            "collection": c.get("collection", "?"),
            "distance": c.get("distance"),
            "specifics_supplied": len(owned),
            "word_overlap": overlap,
            "contributed": bool(owned) or overlap >= contrib_floor,
        })

    # An answer too short to contain anything cannot demonstrate that a chunk
    # contributed, so "0 of 5 contributed" would be an artifact of the ANSWER
    # rather than a finding about the citations.
    #
    # Measured 2026-08-06: when Dex role-plays a retrieved instruction he
    # replies "F4 caught." -- three words. Every chunk then scores zero
    # overlap and the tool reported 100% citation inflation, which is false.
    # The citations were never tested; there was nothing to test them against.
    #
    # UNMEASURABLE, not clean and not inflated. Same rule as everywhere else
    # here: "could not check" must never render as a result.
    words = len(re.findall(r"[a-z]{4,}", answer.lower()))
    measurable = words >= 25

    return {"grounding": g, "chunks": per_chunk,
            "citation_measurable": measurable,
            "answer_words": words,
            "inflated": [c for c in per_chunk if not c["contributed"]] if measurable else []}


def render(res: dict, a: dict) -> None:
    print("\n" + "=" * 74)
    print(f"  Q: {res.get('question','')}")
    print("=" * 74)
    ans = (res.get("answer") or "").strip()
    print("\n" + (ans[:1200] + ("\n  ...[truncated]" if len(ans) > 1200 else "")))

    g = a["grounding"]
    print("\n" + "-" * 74)
    print("  GROUNDING — do the answer's specifics occur in the retrieved chunks?")
    if g["ungrounded"]:
        print(f"    !! {len(g['ungrounded'])} of {g['checked']} specific(s) appear in NO chunk:")
        for s in g["ungrounded"]:
            print(f"       [{s['kind']}] {s['value']}")
        print("       A specific not in the source was not retrieved. Unverified.")
    else:
        print(f"    ok  all {g['checked']} checkable specific(s) occur in the chunks.")
    print("    (fabrication only — NOT whether the answer is correct or complete)")

    print("\n  CITATIONS — did every cited chunk actually contribute?")
    print(f"    {'dist':>6} {'spec':>5} {'words':>6}  source")
    for c in a["chunks"]:
        mark = "  " if c["contributed"] else "!!"
        d = f"{c['distance']:.3f}" if isinstance(c["distance"], (int, float)) else "?"
        print(f" {mark} {d:>6} {c['specifics_supplied']:>5} {c['word_overlap']:>6}  "
              f"{str(c['source'])[:52]}")
    if not a["citation_measurable"]:
        print(f"\n    ?? UNMEASURABLE — the answer is {a['answer_words']} content word(s).")
        print("       Too short to demonstrate that any chunk contributed, so the")
        print("       citations were NOT tested. This is not a clean result.")
    elif a["inflated"]:
        n = len(a["inflated"])
        print(f"\n    !! {n} of {len(a['chunks'])} cited source(s) contributed NOTHING "
              f"({100*n/max(len(a['chunks']),1):.0f}% inflation).")
        print("       Retrieved, listed as a citation, and did no work. A reader")
        print("       counting sources would overcount the support for this answer.")
    else:
        print("\n    ok  every cited source contributed to the answer.")
    print("=" * 74 + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="ask Dex Jr. and grade the answer")
    ap.add_argument("question", nargs="?")
    ap.add_argument("--file", type=Path, help="batch: one question per line")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--collection", default=None)
    ap.add_argument("--contrib-floor", type=int, default=4,
                    help="distinctive shared words below which a chunk counts as "
                         "having contributed nothing")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    qs = []
    if a.file:
        qs = [l.strip() for l in a.file.read_text(encoding="utf-8").splitlines()
              if l.strip() and not l.startswith("#")]
    elif a.question:
        qs = [a.question]
    else:
        ap.print_help()
        return 4

    worst = 0
    summary = []
    for q in qs:
        res = ask(q, a.top_k, a.collection)
        if res is None:
            worst = max(worst, 4)
            continue
        assessment = assess(res, a.contrib_floor)
        if a.json:
            print(json.dumps({"question": q, "assessment": assessment}, indent=2, default=str))
        else:
            render(res, assessment)

        ung = len(assessment["grounding"]["ungrounded"])
        inf = len(assessment["inflated"])
        summary.append((q, ung, inf, len(assessment["chunks"])))
        worst = max(worst, (1 if ung else 0) + (2 if inf else 0))

    if len(summary) > 1:
        print("=" * 74)
        print(f"  {'ungrnd':>7} {'inflated':>9}  question")
        for q, ung, inf, n in summary:
            print(f"  {ung:>7} {inf:>4}/{n:<4}  {q[:52]}")
        tot_i = sum(s[2] for s in summary)
        tot_c = sum(s[3] for s in summary)
        print(f"\n  citation inflation across the batch: {tot_i}/{tot_c} "
              f"({100*tot_i/max(tot_c,1):.0f}%)")
        print("=" * 74 + "\n")

    return worst


if __name__ == "__main__":
    sys.exit(main())
