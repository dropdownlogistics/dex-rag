"""Can the Waypoint tests fail? Each mutation breaks one promise in waypoint.py; the tests must then fail.

    python mutations_waypoint.py        # exits 1 if any mutation survives

The file is restored after every mutation, and at the end whatever happens.  Silas Reeve / DDL-3004 / 2026-10-12
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = HERE / "waypoint.py"
MUTATIONS = [
    ("a credential is not masked", "        out.append(MASK)\n", "        out.append(body[a:b])\n"),
    ("a seat's deny list is ignored", "        if denied(c, deny):\n", "        if False and denied(c, deny):\n"),
    ("filters are ignored", "        if not _passes(c, parsed):\n", "        if False:\n"),
    ("the query text is logged", '"tool": "search", "seat": seat,', '"tool": "search", "seat": seat, "q": query,'),
    ("the snippet is not capped", "(s[:SNIPPET_CHARS] + ", "(s + "),
    ("k is not clamped", "    k = max(1, min(k, MAX_K))\n", "    k = max(1, k)\n"),
    ("an empty query is searched", '    if not parsed["meaning"].strip():\n', "    if False:\n"),
    ("exact terms are claimed as applied", "    not_applied = ([f'\"{e}\" (exact)' for e in parsed[\"exact\"]] + ", "    not_applied = ([] + "),
    ("the depth caveat is dropped", "    if k > RULED_DEPTH:\n", "    if False:\n"),
    ("the embed header is shown", '    body = HEADER.sub("", text or "", count=1)\n', '    body = text or ""\n'),
]


def main():
    original = TARGET.read_bytes()
    text = original.decode("utf-8")
    survived = []
    try:
        for name, old, new in MUTATIONS:
            if text.count(old) != 1:
                print(f"NOT APPLIED  {name}: the line to change was found {text.count(old)} times")
                survived.append(name)
                continue
            TARGET.write_bytes(text.replace(old, new).encode("utf-8"))
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "test_waypoint.py"], cwd=HERE, capture_output=True, text=True)
            caught = r.returncode != 0
            print(f"{'caught  ' if caught else 'SURVIVED'}  {name}")
            if not caught:
                survived.append(name)
    finally:
        TARGET.write_bytes(original)
    print(f"{len(MUTATIONS) - len(survived)} of {len(MUTATIONS)} caught")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
