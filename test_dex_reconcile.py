#!/usr/bin/env python3
"""
test_dex_reconcile.py -- guard the one invariant that makes the tool credible.

dex-reconcile.py is only trustworthy while it DECLARES NOTHING. The moment
someone writes `expected_dim = 1024` into it "just to be safe", it stops being a
reconciler and becomes the seventh disagreeing declaration -- the exact defect
it was written to detect, now wearing the uniform of the thing that detects it.

That failure would be invisible in the output. The report would look identical
and still be authoritative-sounding. So it is asserted here instead.

The first test walks the module's AST and fails if any corpus fact appears as a
literal in executable code. Prose in docstrings and comments is fine and
necessary -- the file has to be able to EXPLAIN the defect without ENCODING it.

    python test_dex_reconcile.py
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = HERE / "dex-reconcile.py"

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"\n          {detail}" if detail and not cond else ""))


def load():
    spec = importlib.util.spec_from_file_location("dex_reconcile_mod", TARGET)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["dex_reconcile_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


# Values that are FACTS ABOUT THE CORPUS. If any appears as a literal in
# executable code, the tool is asserting rather than measuring.
FORBIDDEN_STR = {"mxbai-embed-large", "nomic-embed-text"}
FORBIDDEN_INT = {768, 1024, 316109, 58919, 20416, 922, 253978, 291520}


def docstring_nodes(tree: ast.AST) -> set[int]:
    """id() of every Constant that is a docstring -- prose, not an assertion."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def main() -> int:
    print("\nTHE INVARIANT: the tool declares nothing\n")

    src = TARGET.read_text(encoding="utf-8")
    tree = ast.parse(src)
    docs = docstring_nodes(tree)

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or id(node) in docs:
            continue
        v = node.value
        if isinstance(v, str) and v in FORBIDDEN_STR:
            offenders.append(f"line {node.lineno}: string {v!r}")
        elif isinstance(v, bool):
            continue  # bool is a subclass of int; not a corpus fact
        elif isinstance(v, int) and v in FORBIDDEN_INT:
            offenders.append(f"line {node.lineno}: int {v}")

    check("no corpus fact appears as a literal in executable code",
          not offenders,
          "the tool is declaring, not measuring:\n          " + "\n          ".join(offenders))

    # Control: prove the scanner can actually find an offender. Without this,
    # a scanner that silently matched nothing would pass identically.
    probe = ast.parse("x = 1024\ny = 'nomic-embed-text'\n")
    probe_docs = docstring_nodes(probe)
    found = [n for n in ast.walk(probe)
             if isinstance(n, ast.Constant) and id(n) not in probe_docs
             and (n.value in FORBIDDEN_STR if isinstance(n.value, str)
                  else isinstance(n.value, int) and not isinstance(n.value, bool)
                  and n.value in FORBIDDEN_INT)]
    check("CONTROL: the scanner detects a planted violation", len(found) == 2,
          f"planted 2, found {len(found)} -- the scanner above proves nothing")

    check("docstrings are exempt (the file must explain the defect)",
          "nomic-embed-text" in src,
          "expected the prose to name the model it is reconciling")

    print("\nVERDICT LOGIC\n")
    mod = load()

    check("verdict marks exist for every verdict",
          set(mod.MARK) >= {"AGREE", "CONFLICT", "REFUTED", "UNMEASURABLE", "UNDECLARED"})

    # Declaration sources must be locations, never values.
    check("every declaration source is a (file, pattern) pair, not a value",
          all(hasattr(s, "path") and hasattr(s, "pattern") and s.pattern for s in mod.SOURCES))
    check("every source pattern captures a group",
          all("(" in s.pattern for s in mod.SOURCES))

    print("\nBEHAVIOUR AGAINST THE LIVE SYSTEM\n")
    r = subprocess.run([sys.executable, str(TARGET), "--json"],
                       capture_output=True, text=True, timeout=600)
    check("runs without crashing", r.returncode in (0, 1),
          f"exit={r.returncode} stderr={r.stderr[-400:]}")

    import json
    try:
        rep = json.loads(r.stdout)
        ok = True
    except Exception as e:  # noqa: BLE001
        ok = False
        rep = {}
        check("--json emits valid JSON", False, str(e))
    if ok:
        check("--json emits valid JSON", True)
        facts = {row["fact"] for row in rep["rows"]}
        check("reports on the embedding model", "embedding_model" in facts)
        check("reports on embedding dimensions", "embedding_dimensions" in facts)
        check("distinguishes live from legacy embedding space",
              "legacy_vs_live_embedding_space" in facts)
        check("checks live collections share one space",
              "live_collections_share_one_embedding_space" in facts)

        # Every declaration must carry a citation. A value without a source is
        # indistinguishable from one the tool made up.
        uncited = [d["value"] for row in rep["rows"] for d in row["declarations"]
                   if not d.get("where")]
        check("every declared value carries a file:line citation", not uncited,
              f"uncited: {uncited}")

        # Exit code must track findings, or the tool is unusable in automation.
        expected_exit = 1 if rep["finding_count"] else 0
        check("exit code tracks findings", r.returncode == expected_exit,
              f"finding_count={rep['finding_count']} exit={r.returncode}")

        chunk_rows = [x for x in rep["rows"] if x["fact"].startswith("chunk_floor")]
        check("chunk floors are checked per collection", len(chunk_rows) >= 1)
        # Regression guard: the first version matched floors by name PREFIX and
        # compared them against pre-rename collections, inventing chunk loss.
        bogus = [x for x in chunk_rows
                 if x["verdict"] == "REFUTED" and "below its declared floor" in x["detail"]
                 and "_v2" not in x["detail"]]
        check("chunk floors are not compared against pre-rename collections",
              not bogus, f"comparing against legacy: {[b['fact'] for b in bogus]}")

    print("\n" + "=" * 62)
    print(f"  {len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"    FAILED: {f}")
    print("=" * 62 + "\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
