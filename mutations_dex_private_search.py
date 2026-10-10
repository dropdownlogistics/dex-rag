"""Planted faults for dex_private_search.py. Each must make test_dex_private_search.py fail.

    python mutations_dex_private_search.py        (from the dex-rag root)

The file is restored afterwards, whatever happens. Silas Reeve / DDL-3004 / 2026-10-10
"""
import subprocess
import sys
from pathlib import Path

TARGET = Path("dex_private_search.py")
TESTS = "test_dex_private_search.py"

M = [
    ("re-score skipped: prefix scores returned",
     "        full = self.vectors(cand) @ q\n", "        full = sc[cand]\n"),
    ("shortlist ignored: only k candidates kept",
     "        m = min(max(shortlist, k), self.n)", "        m = min(k, self.n)"),
    ("exact scan drops all but the last block",
     "                best_r = np.concatenate([best_r, np.arange(start + i, start + i + len(sc))])\n"
     "                best_s = np.concatenate([best_s, sc])",
     "                best_r = np.arange(start + i, start + i + len(sc))\n"
     "                best_s = sc"),
    ("exact scan forgets the shard start",
     "np.arange(start + i, start + i + len(sc))])", "np.arange(i, i + len(sc))])"),
    ("lowest scores first",
     "    order = np.lexsort((rows, -scores))[:k]", "    order = np.lexsort((rows, scores))[:k]"),
    ("row located in the wrong shard",
     'side="right")) - 1', 'side="left")) - 1'),
    ("partial vectors file accepted",
     "            if size % (dim * 4):", "            if False:"),
    ("missing vectors file skipped",
     "            if not v.exists():\n                raise StoreError(f\"{c.name} has no {v.name}\")",
     "            if not v.exists():\n                continue"),
    ("row-count mismatch accepted",
     "            if len(offs) != len(self.maps[s]):", "            if False:"),
    ("memory check never asked",
     "        if memcheck is not None:", "        if False:"),
    ("memory check asked for the wrong size",
     "            memcheck(self.n * prefix * 4 / 2**30)", "            memcheck(self.n * dim * 4 / 2**30)"),
    ("wrong-width question accepted",
     "        if q.shape != (self.store.dim,):", "        if False:"),
    ("question text logged",
     '               "sampled": False}', '               "sampled": False, "question": str(q[:3])}\n        rec["text"] = "x"'),
    ("every search sampled",
     "self.count % self.sample_every == 0):", "self.count % 1 == 0):"),
    ("never sampled",
     "self.count % self.sample_every == 0):", "False):"),
    ("missed always zero",
     '    return {"k": len(e), "missed": len(missed),', '    return {"k": len(e), "missed": 0,'),
    ("worst missed rank off by one",
     "(min(e.index(r) for r in missed) + 1)", "(min(e.index(r) for r in missed))"),
    ("top1 compared loosely",
     "bool(f and e and f[0] == e[0])", "bool(f and e and f[0] in e)"),
    ("window includes its old edge",
     "        if since < at <= now:", "        if since <= at <= now:"),
    ("window includes the future",
     "        if since < at <= now:", "        if since < at:"),
    ("unreadable rows dropped silently",
     "            bad += 1\n            continue", "            continue"),
    ("latency counts the shortlist only",
     'lat = sorted(r["shortlist_ms"] + r["rescore_ms"] for r in rows)', 'lat = sorted(r["shortlist_ms"] for r in rows)'),
    ("missed results counted over all rows",
     'results_missed=sum(r["missed"] for r in samp)', 'results_missed=sum(r.get("missed", 0) for r in samp[:1])'),
    ("top result change not reported",
     'top1_changed=sum(1 for r in samp if not r["top1_same"])', "top1_changed=0"),
    ("unreadable rows left out of the briefing lines",
     '    if s["unreadable_rows"]:\n        lines.append', '    if False:\n        lines.append'),
    ("shortlist rows not re-normalised",
     "self.short[start + i:start + i + len(block)] = _unit(block)", "self.short[start + i:start + i + len(block)] = block * 0 + 1"),
]


def main():
    orig = TARGET.read_text(encoding="utf-8")
    survivors = []
    try:
        for name, a, b in M:
            if orig.count(a) != 1:
                sys.exit(f"mutation {name!r}: its target text appears {orig.count(a)} times, expected 1")
            TARGET.write_text(orig.replace(a, b), encoding="utf-8", newline="\n")
            r = subprocess.run([sys.executable, "-m", "pytest", TESTS, "-q", "-x"], capture_output=True, text=True)
            killed = r.returncode != 0
            print(("killed   " if killed else "SURVIVED ") + name, flush=True)
            if not killed:
                survivors.append(name)
    finally:
        TARGET.write_text(orig, encoding="utf-8", newline="\n")
    print(f"\n{len(M) - len(survivors)} of {len(M)} killed; survivors: {survivors or 'none'}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
