#!/usr/bin/env python3
"""AB-0029 test: run the gate against a fixture NOBODY WROTE FOR IT.

dex-bridge-log.jsonl holds 58 distinct queries the Operator actually asked,
recorded 2026-03 to 2026-04 -- months before this gate existed. They are real
questions, so every single one must reach retrieval. Any CONVERSATIONAL verdict
here is a false refusal against evidence the author had no hand in shaping.

My own self-test is the author's fixtures judged by the author's tool. This one
is at least a step further out.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, r"C:\Users\dexjr\dex-rag")
from dex_query_gate import classify, SUBSTANTIVE

log = Path(r"C:\Users\dexjr\dex-rag\dex-bridge-log.jsonl")
queries = []
seen = set()
for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
    if not line.strip():
        continue
    try:
        q = json.loads(line).get("query")
    except Exception:
        continue
    if q and q not in seen:
        seen.add(q)
        queries.append(q)

print(f"{len(queries)} distinct real queries from the bridge log\n")
bad = []
for q in queries:
    outcome, why = classify(q)
    if outcome != SUBSTANTIVE:
        bad.append((q, outcome, why))

if bad:
    print(f"FALSE REFUSALS — {len(bad)} real queries the gate would block:")
    for q, o, w in bad:
        print(f"  [{o}] {q[:70]!r}\n      {w}")
else:
    print("  0 false refusals — every real query reaches retrieval.")

print(f"\n{len(queries)-len(bad)}/{len(queries)} passed through correctly")

# The other direction, on the same foreign data: nothing in a real query log
# should be a greeting, so a gate that passed EVERYTHING would also score 100%.
# Prove the gate is still capable of refusing, using inputs from outside its
# own fixture list.
outside = ["yo", "cheers", "roger", "no problem", "see ya", "kk", "gm"]
caught = sum(1 for q in outside if classify(q)[0] != SUBSTANTIVE)
print(f"control: {caught}/{len(outside)} conversational inputs still refused")
print("  (without this, a gate that passed everything would look perfect above)")
sys.exit(1 if bad or caught != len(outside) else 0)
