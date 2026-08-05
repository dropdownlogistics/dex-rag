#!/usr/bin/env python3
"""
test_ledger_integrity.py -- prove dex-ledger.py's guards FIRE, not merely that
a clean run is clean.

A tool whose safety rests on an invariant has to demonstrate the invariant
failing. Otherwise "the accounting checked out" is indistinguishable from
"the accounting was never evaluated" -- which is precisely the false
confirmation dex-reconcile.py's integrity_check() was written to kill, and the
same class of defect as reading a 404 as proof of absence.

Each test below breaks something on purpose and asserts the tool notices.

  python test_ledger_integrity.py
"""

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("dex_ledger", HERE / "dex-ledger.py")
L = importlib.util.module_from_spec(spec)
# Must be in sys.modules BEFORE exec_module: @dataclass resolves annotations
# via sys.modules[cls.__module__], which is None for an unregistered module.
sys.modules["dex_ledger"] = L
spec.loader.exec_module(L)

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))


print("\ndex-ledger integrity tests — do the guards actually fire?\n")

# -------------------------------------------------------------------------
print("1. Accounting invariant")
# -------------------------------------------------------------------------
t = L.Tally()
t.files_seen = 5
t.counts[L.D_MATERIALIZED] = 5
try:
    t.check()
    check("balanced tally passes", True)
except L.AccountingError:
    check("balanced tally passes", False, "raised on a correct tally")

t = L.Tally()
t.files_seen = 5
t.counts[L.D_MATERIALIZED] = 4      # one file vanished from the account
try:
    t.check()
    check("UNBALANCED tally RAISES", False, "silently accepted a lost file")
except L.AccountingError as exc:
    check("UNBALANCED tally RAISES", True)
    check("  error names the difference", "difference 1" in str(exc), str(exc)[:80])

t = L.Tally()
try:
    t.record(L.Entry(path="x", disposition="invented_state"))
    check("unknown disposition RAISES", False, "accepted a disposition not in the account")
except L.AccountingError:
    check("unknown disposition RAISES", True)

# -------------------------------------------------------------------------
print("\n2. Hydration guard")
# -------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    real = Path(td) / "real.txt"
    real.write_text("content", encoding="utf-8")

    # The guard must refuse on disposition alone -- it does not re-stat, so a
    # caller cannot talk it into reading by presenting a real path.
    for bad in (L.D_PLACEHOLDER, L.D_EMPTY, L.D_UNREADABLE, L.D_EXCLUDED, L.D_SYMLINK):
        try:
            L._read_guarded(str(real), bad)
            check(f"refuses to open when disposition={bad}", False,
                  "OPENED a file it should have refused")
        except L.HydrationRefused:
            check(f"refuses to open when disposition={bad}", True)

    try:
        h = L._read_guarded(str(real), L.D_MATERIALIZED)
        import hashlib
        check("reads MATERIALIZED and hashes correctly",
              h == hashlib.sha256(b"content").hexdigest())
    except Exception as exc:
        check("reads MATERIALIZED and hashes correctly", False, str(exc))

# -------------------------------------------------------------------------
print("\n3. Placeholder classification — the constants trap")
# -------------------------------------------------------------------------
# The whole guard rests on these being literal. If someone "cleans up" the
# module by sourcing them from `stat`, they silently become 0 and every
# placeholder classifies as materialized. Assert the values directly.
import stat as _stat
check("RECALL_ON_DATA_ACCESS is literal, not from stat",
      L.FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS == 0x00400000)
check("RECALL_ON_OPEN is literal, not from stat",
      L.FILE_ATTRIBUTE_RECALL_ON_OPEN == 0x00040000)
check("  (confirming the trap is real: stat lacks these)",
      not hasattr(_stat, "FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS"))
check("mask catches OFFLINE", bool(L.NOT_MATERIALIZED_MASK & 0x1000))
check("mask catches RECALL_ON_OPEN", bool(L.NOT_MATERIALIZED_MASK & 0x40000))
check("mask catches RECALL_ON_DATA_ACCESS", bool(L.NOT_MATERIALIZED_MASK & 0x400000))
# The real measured value from OneDrive placeholders on this machine.
check("real measured placeholder attrs 0x401620 classify as placeholder",
      bool(0x401620 & L.NOT_MATERIALIZED_MASK))
# A normal local file must NOT trip it.
check("plain ARCHIVE file 0x20 classifies as materialized",
      not (0x20 & L.NOT_MATERIALIZED_MASK))

# -------------------------------------------------------------------------
print("\n4. Exclusions are attributable, not silent")
# -------------------------------------------------------------------------
check("returns the RULE that matched",
      L._match_exclusion("a/b/secret.key", "secret.key", ["*.key"]) == "*.key")
check("returns '' when nothing matches",
      L._match_exclusion("a/b/ok.txt", "ok.txt", ["*.key"]) == "")
check("matches on relative path too",
      L._match_exclusion("private/x.txt", "x.txt", ["private/*"]) == "private/*")

# -------------------------------------------------------------------------
print("\n5. End-to-end on a real tree, including a truncated ledger")
# -------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "tree"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_text("aaa", encoding="utf-8")
    (root / "b.txt").write_text("bbb", encoding="utf-8")
    (root / "empty.txt").write_text("", encoding="utf-8")
    (root / "sub" / "c.log").write_text("ccc", encoding="utf-8")
    (root / "sub" / "skip.key").write_text("secret", encoding="utf-8")

    led = Path(td) / "led.jsonl"
    t = L.inventory(root, led, do_hash=True, exclude=["*.key"], progress_every=0)

    check("files_seen == 5", t.files_seen == 5, f"got {t.files_seen}")
    check("3 materialized", t.counts[L.D_MATERIALIZED] == 3, str(t.counts))
    check("1 empty", t.counts[L.D_EMPTY] == 1, str(t.counts))
    check("1 excluded", t.counts[L.D_EXCLUDED] == 1, str(t.counts))
    check("accounting balances", sum(t.counts.values()) == t.files_seen)

    recs = [json.loads(l) for l in led.read_text(encoding="utf-8").splitlines() if l.strip()]
    hdr = recs[0]
    check("ledger has a self-describing header", hdr.get("_ledger") == 1)
    excl = [r for r in recs if r.get("disposition") == L.D_EXCLUDED]
    check("excluded record names its rule",
          excl and excl[0].get("excluded_by") == "*.key")
    check("excluded file was NOT hashed", excl and not excl[0].get("sha256"))
    mats = [r for r in recs if r.get("disposition") == L.D_MATERIALIZED]
    check("materialized records carry sha256", all(r.get("sha256") for r in mats))

    # Re-reading a ledger must re-assert the invariant, so a ledger truncated
    # after the fact fails loudly instead of summarizing as if intact.
    t2 = L.read_summary(led)
    check("summary of intact ledger balances", t2.files_seen == 5)

    lines = led.read_text(encoding="utf-8").splitlines()

    # TRUNCATION. This is the case an internal balance check cannot catch: drop
    # trailing records and the file still parses, and its records still balance
    # against each other perfectly. It just describes a smaller tree than the
    # one that was walked. Only the footer distinguishes the two.
    cut_footer = Path(td) / "no_footer.jsonl"
    cut_footer.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    try:
        L.read_summary(cut_footer)
        check("ledger missing its footer RAISES", False,
              "summarized an incomplete ledger as if it were complete")
    except L.AccountingError as exc:
        check("ledger missing its footer RAISES", True)
        check("  error says not to trust it",
              "complete account" in str(exc).lower(), str(exc)[:90])

    # Footer present but records removed from the middle -- the nastier case,
    # because the file has a valid header AND a valid footer.
    doctored = Path(td) / "doctored.jsonl"
    doctored.write_text("\n".join(lines[:2] + lines[3:]) + "\n", encoding="utf-8")
    try:
        L.read_summary(doctored)
        check("footer/record COUNT MISMATCH raises", False,
              "accepted a ledger whose footer disagrees with its records")
    except L.AccountingError as exc:
        check("footer/record COUNT MISMATCH raises", True)
        check("  error quantifies the gap", "-1" in str(exc) or "+1" in str(exc),
              str(exc)[:90])

    # And the intact one still passes, so the checks above are not just
    # "read_summary always raises".
    check("intact ledger still summarizes cleanly",
          L.read_summary(led).files_seen == 5)

    # verify() against an unchanged tree
    d = L.verify(led, recheck_hash=True)
    check("verify finds no drift on unchanged tree",
          not d["gone"] and not d["hash_changed"] and not d["size_changed"],
          str({k: len(v) for k, v in d.items() if isinstance(v, list)}))

    # mutate a file, verify must catch it
    (root / "a.txt").write_text("MUTATED", encoding="utf-8")
    d = L.verify(led, recheck_hash=True)
    check("verify CATCHES a changed file",
          len(d["size_changed"]) + len(d["hash_changed"]) >= 1,
          str({k: len(v) for k, v in d.items() if isinstance(v, list)}))

    # delete a file, verify must catch it
    (root / "b.txt").unlink()
    d = L.verify(led, recheck_hash=False)
    check("verify CATCHES a deleted file", len(d["gone"]) == 1, str(d["gone"]))

# -------------------------------------------------------------------------
print(f"\n{'='*60}")
print(f"  {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("  FAILED:")
    for f in FAIL:
        print(f"    {f}")
print(f"{'='*60}\n")
sys.exit(1 if FAIL else 0)
