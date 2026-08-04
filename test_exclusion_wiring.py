#!/usr/bin/env python3
"""
test_exclusion_wiring.py -- prove the gate is actually IN the pipeline.

test_dex_exclusions.py proves the exclusion module works. This proves
dex-ingest.py and dex-sweep.py actually call it, which is a different claim.
A perfect module nobody invokes protects nothing.

BOTH DIRECTIONS, per the dispatch:
  - a file that should be excluded, excluded
  - a file that should pass, passing
  - refusal when the list is unusable
  - and proof the negative tests actually executed

WHAT THIS DELIBERATELY DOES NOT DO: run a real ingest. Writing to a live
collection is CLAUDE.md Rule 5 / Rule 8 territory. Scan-level behaviour is
tested by calling scan_archive() directly; the refusal paths are tested as
real subprocesses because they exit before ChromaDB is ever imported.

    python test_exclusion_wiring.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from dex_exclusions import parse_exclusions  # noqa: E402

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"\n          {detail}" if detail and not cond else ""))


def load_hyphenated(name: str, filename: str):
    """dex-ingest.py / dex-sweep.py have hyphens, so plain import won't do."""
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def build_tree(tmp: Path) -> Path:
    """A miniature source tree with material that must and must not survive."""
    root = tmp / "src"
    (root / "ok").mkdir(parents=True)
    (root / "SEQUESTERED_DO_NOT_INGEST").mkdir(parents=True)
    (root / "nested" / "16_personal_legal").mkdir(parents=True)

    (root / "ok" / "notes.txt").write_text("legitimate corpus material", encoding="utf-8")
    (root / "ok" / "more.md").write_text("also fine", encoding="utf-8")
    (root / "SEQUESTERED_DO_NOT_INGEST" / "exhibit.txt").write_text("SECRET", encoding="utf-8")
    (root / "nested" / "16_personal_legal" / "payroll.txt").write_text("SECRET", encoding="utf-8")
    (root / "ok" / "mail.mbox").write_text("SECRET", encoding="utf-8")
    return root


def exclusions_for(root: Path):
    doc = {
        "version": 1,
        "exclude_paths": [str(root / "SEQUESTERED_DO_NOT_INGEST")],
        "exclude_dir_names": ["16_personal_legal"],
        "exclude_filename_patterns": ["*.mbox"],
    }
    return parse_exclusions(json.dumps(doc), Path("test"))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="wiring-test-"))
    root = build_tree(tmp)
    ex = exclusions_for(root)

    print("\nDEX-INGEST: scan_archive filtering\n")
    ingest_mod = load_hyphenated("dex_ingest_mod", "dex-ingest.py")

    files, excluded = ingest_mod.scan_archive(root, {".txt", ".md", ".mbox"}, ex)
    names = sorted(f["filename"] for f in files)
    ex_paths = [e["path"] for e in excluded]

    check("eligible files survive", names == ["more.md", "notes.txt"], f"got {names}")
    check("sequestered dir contents excluded",
          not any("exhibit" in n for n in names))
    check("16_personal_legal contents excluded",
          not any("payroll" in n for n in names))
    check("mbox excluded by pattern",
          not any("mail.mbox" in n for n in names))
    check("exclusions were RECORDED, not just dropped", len(excluded) >= 3,
          f"recorded {len(excluded)}: {ex_paths}")
    check("each exclusion carries a reason",
          all(e.get("reason") for e in excluded))
    check("excluded dirs are pruned, not descended",
          any(e["kind"] == "directory" for e in excluded))

    # The boundary case: scan_archive must not require exclusions be optional.
    try:
        ingest_mod.scan_archive(root, {".txt"})  # type: ignore[call-arg]
        check("scan_archive REQUIRES exclusions (no silent full walk)", False,
              "call without exclusions succeeded -- a forgetful caller would walk everything")
    except TypeError:
        check("scan_archive REQUIRES exclusions (no silent full walk)", True)

    print("\nDEX-INGEST: startup refusal (real subprocess)\n")
    empty = tmp / "empty"
    empty.mkdir()
    bad = tmp / "nonexistent-list.json"

    env = dict(os.environ, DDL_INGEST_EXCLUSIONS=str(bad))
    r = subprocess.run(
        [sys.executable, str(HERE / "dex-ingest.py"), "--path", str(empty)],
        env=env, capture_output=True, text=True, timeout=180,
    )
    out = r.stdout + r.stderr
    check("dex-ingest exits 2 with no exclusion list", r.returncode == 2,
          f"exit={r.returncode}")
    check("dex-ingest says why", "INGEST REFUSED" in out, out[-400:])
    # Proves it died at the gate, not later: the backup pre-flight and the
    # banner both come after, so their absence locates the failure.
    check("dex-ingest refused BEFORE backup pre-flight",
          "Backup" not in out, out[-400:])
    check("dex-ingest refused BEFORE touching ChromaDB",
          "Existing chunks" not in out, out[-400:])

    print("\nDEX-SWEEP: refusal writes a human-visible alert\n")
    sweep_mod = load_hyphenated("dex_sweep_mod", "dex-sweep.py")

    # Redirect the sweep's outputs so the test never writes into OneDrive.
    alert_dir = tmp / "reports"
    alert_dir.mkdir()
    sweep_mod.SWEEP_REPORTS_DIR = str(alert_dir)
    sweep_mod.LOG_FILE = str(tmp / "sweep-log.jsonl")
    os.environ["DDL_INGEST_EXCLUSIONS"] = str(bad)

    raised = None
    try:
        sweep_mod.require_exclusions()
    except SystemExit as e:
        raised = e

    check("sweep refuses when list is unusable", raised is not None,
          "require_exclusions returned instead of exiting")
    check("sweep exits 2", raised is not None and raised.code == 2,
          f"code={getattr(raised, 'code', None)}")

    alerts = list(alert_dir.glob("SWEEP-FAILED-*.ALERT"))
    check("sweep wrote an alert file", len(alerts) == 1, f"found {alerts}")
    if alerts:
        body = alerts[0].read_text(encoding="utf-8")
        check("alert states nothing was ingested",
              "NO FILES WERE INGESTED" in body)
        check("alert states the reason", "does not exist" in body, body[:300])
        check("alert says how to fix", "TO FIX" in body)
        check("alert extension is NOT sweepable (won't be eaten by next sweep)",
              alerts[0].suffix not in sweep_mod.INGEST_EXTENSIONS,
              f"{alerts[0].suffix} is in INGEST_EXTENSIONS")

    logf = Path(sweep_mod.LOG_FILE)
    check("sweep logged the refusal", logf.exists())
    if logf.exists():
        entry = json.loads(logf.read_text(encoding="utf-8").strip().splitlines()[-1])
        check("refusal logged with a distinct outcome",
              entry.get("outcome") == "refused_exclusions_unusable",
              f"outcome={entry.get('outcome')}")
        check("refusal log carries a recovery hint", bool(entry.get("recovery_hint")))

    print("\nDEX-SWEEP: the passing direction\n")
    drop = tmp / "drop"
    drop.mkdir()
    (drop / "good.txt").write_text("keep me", encoding="utf-8")
    (drop / "secret.mbox").write_text("drop me", encoding="utf-8")
    (drop / "notes.md").write_text("keep me too", encoding="utf-8")

    sweep_mod.DROP_FOLDERS = [str(drop)]
    found, sw_excluded = sweep_mod.scan_drop_folders(ex)
    found_names = sorted(f["filename"] for f in found)

    check("sweep keeps eligible drop files",
          found_names == ["good.txt", "notes.md"], f"got {found_names}")
    check("sweep excludes the mbox before it is ever copied",
          any("secret.mbox" in e["path"] for e in sw_excluded),
          f"excluded={sw_excluded}")
    check("sweep records exclusion reasons",
          all(e.get("reason") for e in sw_excluded))

    print("\nDIGEST REACHES THE RUN LOG\n")
    check("dex-ingest defines an exclusion log", hasattr(ingest_mod, "EXCLUSION_LOG"))
    check("dex-ingest logs the digest field",
          "exclusion_digest" in Path(HERE / "dex-ingest.py").read_text(encoding="utf-8"))
    check("dex-sweep logs the digest field",
          "exclusion_digest" in Path(HERE / "dex-sweep.py").read_text(encoding="utf-8"))

    print("\n" + "=" * 62)
    print(f"  {len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"    FAILED: {f}")
    print("=" * 62 + "\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
