#!/usr/bin/env python3
"""
dex-clone-audit.py -- report which ddl-org clones on this machine are unenforced.

The wing-isolation pre-commit hook is enforced by `core.hooksPath`, which lives
in `.git/config`. That is per-clone and is NEVER cloned. So a fresh clone of
ddl-org has ZERO wing enforcement until somebody remembers to run
install-hooks.ps1 -- and nothing anywhere fails loudly when they don't.

Verified 2026-07-31: a clone without hooksPath accepted a commit writing into
another wing's directory. It went straight through.

This is the interim mitigation while server-side enforcement is decided. It only
detects; it changes nothing. Two of three Reborn clones were unenforced on
2026-07-30 and it was found by accident.

  python dex-clone-audit.py           # human-readable
  python dex-clone-audit.py --quiet   # print only problems
  python dex-clone-audit.py --json    # machine-readable

Exit codes:  0 = all clones enforced   1 = at least one is not   2 = none found
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Where ddl-org checkouts are expected to live on this machine.
SEARCH_ROOTS = [
    Path(r"C:\Users\dexjr"),
    Path(r"C:\Users\dexjr\ddl-wings"),
    Path(r"C:\Users\dkitc"),
]
MAX_DEPTH = 2
REMOTE_MARKER = "ddl-org"


def git(repo: Path, *args) -> str:
    try:
        r = subprocess.run(["git", "-C", str(repo), *args],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def find_clones(extra_roots: list[Path] | None = None) -> list[Path]:
    seen, out = set(), []
    for root in SEARCH_ROOTS + list(extra_roots or []):
        if not root.is_dir():
            continue
        for depth in range(MAX_DEPTH + 1):
            for git_dir in root.glob("/".join(["*"] * depth + [".git"])):
                repo = git_dir.parent.resolve()
                if repo in seen:
                    continue
                seen.add(repo)
                if REMOTE_MARKER in git(repo, "remote", "get-url", "origin"):
                    out.append(repo)
    return sorted(out)


def audit(repo: Path) -> dict:
    hooks = git(repo, "config", "--local", "--get", "core.hooksPath")
    wing_file = repo / ".ddl-wing"
    wing = ""
    if wing_file.is_file():
        try:
            wing = wing_file.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            wing = "<unreadable>"

    problems = []
    if not hooks:
        problems.append("core.hooksPath UNSET — commits are NOT checked")
    elif not (repo / hooks).is_dir():
        problems.append(f"core.hooksPath='{hooks}' but that directory is missing")
    if not wing:
        # Not fatal on its own: the hook fails closed on a missing .ddl-wing.
        # It is only dangerous when combined with hooks being off.
        problems.append("no .ddl-wing" + ("" if hooks else " (and no hook to catch it)"))
    elif wing and not (repo / wing).is_dir():
        problems.append(f".ddl-wing says '{wing}' but no such wing directory exists")

    return {"path": str(repo), "wing": wing or None, "hooksPath": hooks or None,
            "enforced": bool(hooks) and (repo / hooks).is_dir() if hooks else False,
            "problems": problems}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="only show clones with problems")
    ap.add_argument("--root", action="append", default=[],
                    help="extra directory to scan (repeatable). Makes the detector testable.")
    a = ap.parse_args()

    clones = find_clones([__import__('pathlib').Path(r) for r in a.root])
    if not clones:
        print("no ddl-org clones found under the known roots", file=sys.stderr)
        return 2

    rows = [audit(c) for c in clones]
    bad = [r for r in rows if r["problems"]]
    unenforced = [r for r in rows if not r["enforced"]]

    if a.json:
        print(json.dumps({"clones": rows, "unenforced": len(unenforced)}, indent=2))
        return 1 if unenforced else 0

    for r in rows:
        if a.quiet and not r["problems"]:
            continue
        mark = "OK  " if not r["problems"] else "WARN"
        print(f"[{mark}] {r['path']}")
        print(f"         wing={r['wing'] or '<none>'}  hooks={r['hooksPath'] or '<UNSET>'}")
        for p in r["problems"]:
            print(f"         !! {p}")

    print(f"\n{len(rows)} clone(s); {len(unenforced)} with enforcement OFF.")
    if unenforced:
        print("\nA clone with hooks off will accept a commit into ANY wing.")
        print("Fix each one from inside it:   .\\install-hooks.ps1")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
