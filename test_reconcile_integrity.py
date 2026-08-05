#!/usr/bin/env python3
"""
test_reconcile_integrity.py -- the reconciler must not be able to lie quietly.

A tool built to detect false confirmations must not be capable of producing
one. This suite exists because dex-reconcile COULD, and did:

  embedding_model is declared once in dex_core and twice in canon. The verdict
  logic asked "how many DISTINCT values did I collect?" With canon unreadable,
  exactly one value survived, and the tool reported

      AGREE — all sources say mxbai-embed-large

  Findings went 3 -> 0. Exit code 0. The night's most important finding
  vanished, and the output read as a clean bill of health.

That is the Select-String defect wearing a new hat: not a wrong answer, a
false confirmation. These tests are the regression guard.

    python test_reconcile_integrity.py
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = HERE / "dex-reconcile.py"

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"\n          {detail}" if detail and not cond else ""))


def fresh():
    """A fresh module instance -- these tests mutate SOURCES."""
    spec = importlib.util.spec_from_file_location("rec_i", TARGET)
    m = importlib.util.module_from_spec(spec)
    sys.modules["rec_i"] = m       # must precede exec_module for @dataclass
    spec.loader.exec_module(m)
    return m


def row(rep, fact):
    return next((r for r in rep["rows"] if r.fact == fact), None)


def main() -> int:
    print("\nTHE REGRESSION: a missing source must never read as agreement\n")

    m = fresh()
    base = m.build_report()
    r = row(base, "embedding_model")
    check("baseline detects the real canon conflict", r and r.verdict == "CONFLICT",
          f"got {r.verdict if r else 'no row'}")
    baseline_findings = len(base["findings"])

    m2 = fresh()
    m2.SOURCES = [s for s in m2.SOURCES if "ddl-canon" not in str(s.path)]
    deg = m2.build_report()
    r2 = row(deg, "embedding_model")
    check("with canon unreadable it does NOT report AGREE",
          r2 and r2.verdict != "AGREE", f"got {r2.verdict if r2 else 'no row'}")
    check("it reports UNCHECKED specifically",
          r2 and r2.verdict == "UNCHECKED", f"got {r2.verdict if r2 else 'no row'}")
    check("the detail names how many sources went unread",
          r2 and "could not be read" in r2.detail, r2.detail if r2 else "")
    check("the detail warns survivors may agree only by absence",
          r2 and "disagreeing one is missing" in r2.detail, r2.detail if r2 else "")

    print("\nPLANTED MISMATCH — it must catch a disagreement it has never seen\n")

    tmp = Path(tempfile.mkdtemp(prefix="rec-plant-"))
    planted = tmp / "planted_config.py"
    planted.write_text('EMBED_MODEL = "planted-wrong-model-9000"\n', encoding="utf-8")

    m3 = fresh()
    m3.SOURCES = list(m3.SOURCES) + [
        m3.Source("embedding_model", planted,
                  r'EMBED_MODEL\s*=\s*["\']([^"\']+)["\']', "PLANTED BY TEST")
    ]
    rep3 = m3.build_report()
    r3 = row(rep3, "embedding_model")
    check("planted disagreement is CAUGHT", r3 and r3.verdict == "CONFLICT",
          f"got {r3.verdict if r3 else 'no row'}")
    check("the planted value appears in the finding",
          r3 and "planted-wrong-model-9000" in r3.detail, r3.detail if r3 else "")
    check("the planted source is cited by path",
          r3 and any("planted_config" in d.where for d in r3.declarations))

    # Control: prove the harness can tell caught from not-caught. Without this,
    # a suite whose assertions never fire passes identically to a working one.
    m4 = fresh()
    clean = tmp / "agreeing_config.py"
    clean.write_text('EMBED_MODEL = "mxbai-embed-large"\n', encoding="utf-8")
    m4.SOURCES = [s for s in m4.SOURCES if "ddl-canon" not in str(s.path)] + [
        m4.Source("embedding_model", clean,
                  r'EMBED_MODEL\s*=\s*["\']([^"\']+)["\']', "agreeing source")
    ]
    rep4 = m4.build_report()
    r4 = row(rep4, "embedding_model")
    check("CONTROL: two AGREEING sources do not produce a CONFLICT",
          r4 and r4.verdict != "CONFLICT", f"got {r4.verdict if r4 else 'no row'}")

    print("\nUNCHECKED MUST NOT RENDER LIKE AGREEMENT\n")

    check("report separates findings from unchecked",
          "unchecked" in deg and isinstance(deg["unchecked"], list))
    check("an unchecked fact is listed as not reconciled",
          any(x.fact == "embedding_model" for x in deg["unchecked"]))
    check("degraded run reports FEWER findings than baseline (the trap)",
          len(deg["findings"]) < baseline_findings,
          f"{baseline_findings} -> {len(deg['findings'])}")
    check("...but does NOT therefore look clean — unchecked is non-empty",
          len(deg["unchecked"]) > 0,
          "fewer findings AND nothing flagged would be the false confirmation")

    print("\nEXIT CODES DISTINGUISH 'FOUND A PROBLEM' FROM 'COULD NOT LOOK'\n")

    r = subprocess.run([sys.executable, str(TARGET), "--json"],
                       capture_output=True, text=True, timeout=900)
    check("live run exits non-zero with real findings present", r.returncode in (1, 4),
          f"exit={r.returncode}")
    try:
        j = json.loads(r.stdout)
        check("--json still valid after the integrity changes", True)
        check("json exposes per-fact source coverage",
              all("sources_expected" in x for x in j["rows"]))
        check("json exposes unchecked_count", "unchecked_count" in j)
        check("exit 1 means findings", (r.returncode == 1) == (j["finding_count"] > 0),
              f"exit={r.returncode} findings={j['finding_count']}")
    except Exception as e:  # noqa: BLE001
        check("--json still valid after the integrity changes", False, str(e))

    print("\nMEASUREMENT-VS-MEASUREMENT IS A REAL COMPARISON\n")
    # Rows that compare two independent measurements must not be demoted to
    # SINGLE_SOURCE just because no declaration was involved. That bug was
    # introduced by the fix above and caught by running it.
    rr = row(base, "model_can_produce_LIVE_width[mxbai-embed-large]")
    check("a live probe vs a stored width counts as two evidence points",
          rr and rr.verdict != "SINGLE_SOURCE",
          f"got {rr.verdict if rr else 'no row'}")
    rc = row(base, "live_collections_share_one_embedding_space")
    check("several collections agreeing counts as a reconciliation",
          rc and rc.verdict != "SINGLE_SOURCE",
          f"got {rc.verdict if rc else 'no row'}")

    print("\n" + "=" * 64)
    print(f"  {len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"    FAILED: {f}")
    print("=" * 64 + "\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
