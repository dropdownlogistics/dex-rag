#!/usr/bin/env python3
"""
dex-eval-retrieval.py -- can retrieval tell signal from noise, and is the
refusal threshold in the right place?

WHY THIS EXISTS
---------------
The corpus is about to be rebuilt from new sources. Nothing can currently say
whether a rebuild made retrieval BETTER or WORSE, so the new corpus would be
declared an improvement rather than measured as one -- the same defect the rest
of this repo's tooling was written to stop, applied at the top level.

A baseline has to be taken BEFORE the corpus is replaced. Afterwards the
before-state is gone and the comparison is impossible forever.

WHAT IT MEASURES
----------------
Three populations against a live collection:

  ON_DOMAIN   real questions lifted verbatim from dex-bridge-log.jsonl --
              questions this corpus was actually asked in practice
  OFF_DOMAIN  meaningful questions on subjects the corpus does not cover
  DEGENERATE  greetings and low-information strings

The interesting number is not any single distance. It is whether the
populations SEPARATE, because a threshold can only exist if they do.

WHAT IT FOUND ON FIRST RUN (2026-08-04, dex_canon_v2)
-----------------------------------------------------
  ON_DOMAIN vs OFF_DOMAIN   SEPARABLE   gap +0.083
  ON_DOMAIN vs DEGENERATE   OVERLAPPING gap -0.082

Distance thresholding works. It fails ONLY on low-information input, which
lands near the centroid of the embedding space and is therefore close to
everything.

  "Hello" scores 0.564.
  "What is the Platinum Bounce recovery protocol?" scores 0.630.

The greeting retrieves BETTER than a real question about the corpus's own
content. At the live MAX_DISTANCE of 0.62, "Hello" passes the refusal gate --
so the most likely first message to a phone endpoint returns five arbitrary
chunks for the model to answer from.

The fix is an INPUT GATE, not a threshold tune. Degenerate input has no
meaningful distance to measure, so measuring it harder will not help.

  python dex-eval-retrieval.py                    # measure and report
  python dex-eval-retrieval.py --save-baseline    # record for later comparison
  python dex-eval-retrieval.py --compare          # diff against the baseline

Exit: 0 separability holds - 1 ON/OFF separation lost - 2 regression vs baseline

Read-only. query() and count() only. Writes nothing to any collection.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dex_core import CHROMA_DIR, embed, suffixed, get_live_collections  # noqa: E402

BASELINE = Path(__file__).resolve().parent / "eval-retrieval-baseline.json"

# The threshold the live endpoint actually enforces. CITED, not chosen here --
# if this file picked its own number it would become a second declaration of a
# value that already exists in dex-openai-api.py.
LIVE_MAX_DISTANCE = 0.62

# Verbatim from dex-bridge-log.jsonl. Real questions, really asked.
# Not invented: a query set written by the same author as the corpus tests
# whether the corpus matches that author's phrasing, which is not the question.
ON_DOMAIN = [
    "What is the Platinum Bounce recovery protocol?",
    "What is AsBuiltGovernance?",
    "what is the DDL methodology",
    "What is the council",
    "What is the CottageHumble design system?",
    "What are Donella Meadows twelve leverage points for intervening in a system?",
    "Trace the evolution of MindFrame from v1.0 to v4.0",
    "What did the council say about Dex Jr calibration Round 3?",
    "How do Anaplan modules map to star schema fact tables?",
    "council review topics",
]

# Meaningful, well-formed, and about subjects the corpus does not hold.
OFF_DOMAIN = [
    "What is the melting point of tungsten carbide?",
    "Who won the 1974 FIFA World Cup final?",
    "Explain the Krebs cycle in cellular respiration",
    "How do I replace a timing belt on a 1998 Honda Civic?",
    "What are the tax implications of a Roth IRA conversion?",
    "Describe the plot of Wuthering Heights",
]

# Low information content. What a chat endpoint actually receives.
DEGENERATE = [
    "Hello", "hi", "hey", "ok", "thanks", "yes", "?", "test",
    "qqqq wwww eeee", "asdfgh jkl",
]


def best_distance(col, q: str) -> float:
    r = col.query(query_embeddings=[embed(q)], n_results=5, include=["distances"])
    ds = r["distances"][0]
    return min(ds) if ds else float("inf")


def measure(col) -> dict:
    out = {}
    for label, qs in (("on_domain", ON_DOMAIN),
                      ("off_domain", OFF_DOMAIN),
                      ("degenerate", DEGENERATE)):
        rows = [{"query": q, "distance": round(best_distance(col, q), 4)} for q in qs]
        ds = [r["distance"] for r in rows]
        out[label] = {
            "rows": rows,
            "min": round(min(ds), 4),
            "median": round(statistics.median(ds), 4),
            "max": round(max(ds), 4),
        }
    on, off, deg = out["on_domain"], out["off_domain"], out["degenerate"]
    out["separation"] = {
        # A positive gap means the worst on-domain result still beats the best
        # noise result, which is the only condition under which a threshold can
        # divide them at all.
        "on_vs_off_gap": round(off["min"] - on["max"], 4),
        "on_vs_degenerate_gap": round(deg["min"] - on["max"], 4),
        "on_off_separable": off["min"] > on["max"],
        "on_degenerate_separable": deg["min"] > on["max"],
        # Where a threshold COULD sit, if degenerate input is handled elsewhere.
        "suggested_threshold": round((on["max"] + off["min"]) / 2, 4) if off["min"] > on["max"] else None,
    }
    out["at_live_threshold"] = {
        "max_distance": LIVE_MAX_DISTANCE,
        "on_domain_refused": sum(1 for r in on["rows"] if r["distance"] > LIVE_MAX_DISTANCE),
        "on_domain_total": len(on["rows"]),
        "degenerate_accepted": sum(1 for r in deg["rows"] if r["distance"] <= LIVE_MAX_DISTANCE),
        "degenerate_total": len(deg["rows"]),
        "off_domain_accepted": sum(1 for r in off["rows"] if r["distance"] <= LIVE_MAX_DISTANCE),
        "off_domain_total": len(off["rows"]),
    }
    return out


def render(name: str, count: int, m: dict) -> None:
    print(f"\n{name}  ({count:,} chunks)")
    print("-" * 68)
    for label in ("on_domain", "off_domain", "degenerate"):
        g = m[label]
        print(f"  {label:<12} min {g['min']:.3f}   median {g['median']:.3f}   max {g['max']:.3f}")
    s = m["separation"]
    print()
    print(f"  on vs off-domain   gap {s['on_vs_off_gap']:+.3f}   "
          f"{'SEPARABLE' if s['on_off_separable'] else 'OVERLAPPING'}")
    print(f"  on vs degenerate   gap {s['on_vs_degenerate_gap']:+.3f}   "
          f"{'SEPARABLE' if s['on_degenerate_separable'] else 'OVERLAPPING'}")
    if s["suggested_threshold"] is not None:
        print(f"  a threshold at {s['suggested_threshold']:.3f} would divide on- from off-domain")
    t = m["at_live_threshold"]
    print()
    print(f"  at the LIVE MAX_DISTANCE = {t['max_distance']}:")
    print(f"    real questions REFUSED    {t['on_domain_refused']}/{t['on_domain_total']}")
    print(f"    greetings ACCEPTED        {t['degenerate_accepted']}/{t['degenerate_total']}")
    print(f"    off-domain ACCEPTED       {t['off_domain_accepted']}/{t['off_domain_total']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="measure retrieval separability")
    ap.add_argument("--collection", default=None, help="base name, default dex_canon")
    ap.add_argument("--save-baseline", action="store_true")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    target = suffixed(a.collection) if a.collection else suffixed("dex_canon")
    live = {c.name for c in client.list_collections()}
    if target not in live:
        print(f"collection not found: {target}", file=sys.stderr)
        return 1

    col = client.get_collection(target)
    m = measure(col)
    report = {"collection": target, "chunk_count": col.count(),
              "measured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              **m}

    if a.json:
        print(json.dumps(report, indent=2))
    else:
        render(target, col.count(), m)

    if a.save_baseline:
        BASELINE.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nbaseline written: {BASELINE}")
        print("Compare after any corpus rebuild with --compare.")

    if a.compare:
        if not BASELINE.exists():
            print(f"\nno baseline at {BASELINE} -- run --save-baseline first", file=sys.stderr)
            return 2
        old = json.loads(BASELINE.read_text(encoding="utf-8"))
        print(f"\nvs baseline taken {old['measured_at']} on {old['collection']} "
              f"({old['chunk_count']:,} chunks)")
        regressed = False
        for k in ("on_vs_off_gap", "on_vs_degenerate_gap"):
            o, n = old["separation"][k], m["separation"][k]
            arrow = "improved" if n > o else ("WORSE" if n < o else "unchanged")
            if n < o:
                regressed = True
            print(f"  {k:<24} {o:+.3f} -> {n:+.3f}   {arrow}")
        om, nm = old["on_domain"]["median"], m["on_domain"]["median"]
        print(f"  {'on_domain median':<24} {om:.3f} -> {nm:.3f}   "
              f"{'WORSE' if nm > om else 'improved' if nm < om else 'unchanged'}")
        if nm > om:
            regressed = True
        if regressed:
            print("\n  REGRESSION: retrieval got worse on at least one measure.")
            return 2

    return 0 if m["separation"]["on_off_separable"] else 1


if __name__ == "__main__":
    sys.exit(main())
