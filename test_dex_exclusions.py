#!/usr/bin/env python3
"""
test_dex_exclusions.py -- prove the refusal actually refuses.

The whole value of dex_exclusions is that it STOPS. A test suite that only
checks the happy path would pass just as well against a module that never
refuses anything, which is precisely the defect it is supposed to prevent.

So every failure mode is exercised in a REAL SUBPROCESS with the exit code
captured directly -- not through a pipe, which is how a blocked hook reported
PASS earlier this week (`cmd | tail` returns tail's status, not cmd's).

Each negative case also asserts on a DISTINGUISHING substring. Asserting only
"exit != 0" would pass if the module died of an unrelated ImportError, which
would look identical to working correctly.

    python test_dex_exclusions.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE = HERE / "dex_exclusions.py"

sys.path.insert(0, str(HERE))
from dex_exclusions import (  # noqa: E402
    ExclusionsUnusable,
    parse_exclusions,
    load_exclusions,
)

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"\n          {detail}" if detail and not cond else ""))


def run_loader(path: Path | str) -> tuple[int, str]:
    """Run the module in a subprocess against `path`. Returns (exit_code, output).

    Exit code comes straight from the child process. No shell, no pipe chain.
    """
    env = dict(os.environ, DDL_INGEST_EXCLUSIONS=str(path))
    r = subprocess.run(
        [sys.executable, str(MODULE)],
        env=env, capture_output=True, text=True, timeout=60,
    )
    return r.returncode, (r.stdout + r.stderr)


def valid_doc(**over) -> dict:
    doc = {
        "version": 1,
        "exclude_paths": [r"C:\seq\SEQUESTERED_DO_NOT_INGEST"],
        "exclude_dir_names": ["16_personal_legal"],
        "exclude_filename_patterns": ["*.mbox"],
    }
    doc.update(over)
    return doc


def write(tmp: Path, name: str, content) -> Path:
    p = tmp / name
    p.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return p


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="exclusion-test-"))

    print("\nREFUSAL CASES -- each must exit 2 for its own stated reason\n")

    # 1. missing
    code, out = run_loader(tmp / "does-not-exist.json")
    check("missing file exits 2", code == 2, f"exit={code}")
    check("missing file says so", "does not exist" in out, out[:300])

    # 2. empty
    p = write(tmp, "empty.json", "")
    code, out = run_loader(p)
    check("empty file exits 2", code == 2, f"exit={code}")
    check("empty file says so", "file is empty" in out, out[:300])

    # 3. whitespace only -- distinct from truly empty, same refusal
    p = write(tmp, "ws.json", "   \n\t\n  ")
    code, out = run_loader(p)
    check("whitespace-only exits 2", code == 2, f"exit={code}")

    # 4. malformed JSON
    p = write(tmp, "bad.json", "{ this is not json")
    code, out = run_loader(p)
    check("malformed JSON exits 2", code == 2, f"exit={code}")
    check("malformed JSON says so", "not valid JSON" in out, out[:300])

    # 5. no rules -- THE core refusal
    p = write(tmp, "norules.json", valid_doc(
        exclude_paths=[], exclude_dir_names=[], exclude_filename_patterns=[]))
    code, out = run_loader(p)
    check("zero rules exits 2", code == 2, f"exit={code}")
    check("zero rules says an empty list is not a policy",
          "no rules" in out, out[:300])

    # 6. a directory, not a file
    d = tmp / "adir.json"
    d.mkdir()
    code, out = run_loader(d)
    check("directory exits 2", code == 2, f"exit={code}")

    # 7. the shipped example file must be REFUSED
    example = HERE / "ingest-exclusions.example.json"
    check("example file exists in repo", example.exists())
    if example.exists():
        code, out = run_loader(example)
        check("example file is refused", code == 2, f"exit={code}")
        check("example file refused for placeholders",
              "REPLACE_ME" in out or "placeholder" in out, out[:300])

    # 8. wrong schema version
    p = write(tmp, "v99.json", valid_doc(version=99))
    code, out = run_loader(p)
    check("unknown schema version exits 2", code == 2, f"exit={code}")

    # 9. empty-string rule -- must refuse rather than guess
    p = write(tmp, "emptyrule.json", valid_doc(exclude_dir_names=["", "x"]))
    code, out = run_loader(p)
    check("empty rule string exits 2", code == 2, f"exit={code}")

    # 10. relative path where absolute is required
    p = write(tmp, "rel.json", valid_doc(exclude_paths=["relative\\path"]))
    code, out = run_loader(p)
    check("relative exclude_path exits 2", code == 2, f"exit={code}")

    # 11. a path smuggled in as a dir name
    p = write(tmp, "dirpath.json", valid_doc(exclude_dir_names=[r"a\b"]))
    code, out = run_loader(p)
    check("path-shaped dir_name exits 2", code == 2, f"exit={code}")

    # ---- proof the harness can detect a pass, not just report one ----
    print("\nCONTROL -- a valid file must NOT be refused\n")
    good = write(tmp, "good.json", valid_doc())
    code, out = run_loader(good)
    check("valid file exits 0", code == 0, f"exit={code} out={out[:300]}")
    check("valid file reports its digest", "digest" in out, out[:300])

    print("\nMATCHING\n")
    ex = parse_exclusions(json.dumps(valid_doc()), Path("t"))

    check("sequestered dir itself is excluded",
          ex.excludes(r"C:\seq\SEQUESTERED_DO_NOT_INGEST"))
    check("file under sequestered dir is excluded",
          ex.excludes(r"C:\seq\SEQUESTERED_DO_NOT_INGEST\Exhibit_A.pdf"))
    check("deep file under sequestered dir is excluded",
          ex.excludes(r"C:\seq\SEQUESTERED_DO_NOT_INGEST\a\b\c\d.pdf"))
    check("matching is case-insensitive",
          ex.excludes(r"c:\SEQ\sequestered_do_not_ingest\x.pdf"))
    check("forward slashes match too",
          ex.excludes("C:/seq/SEQUESTERED_DO_NOT_INGEST/x.pdf"))

    check("dir NAME matches at any depth -- survives relocation",
          ex.excludes(r"D:\somewhere\else\16_personal_legal\payroll.msg"))

    check("filename pattern matches",
          ex.excludes(r"C:\anything\All mail Including Spam and Trash-002.mbox"))

    check("an ordinary file is eligible",
          not ex.excludes(r"C:\Users\dkitc\iCloudDrive\Documents\05_DirectIngest\notes.txt"))

    # A sibling whose name merely starts with an excluded dir's name must NOT
    # be caught -- prefix matching without a separator boundary is a classic
    # over-exclusion bug and would silently drop legitimate material.
    check("prefix sibling is NOT over-excluded",
          not ex.excludes(r"C:\seq\SEQUESTERED_DO_NOT_INGEST_NOTES\readme.txt"),
          "boundary bug: prefix match without separator")

    check("reason() explains rather than just refusing",
          "16_personal_legal" in (ex.reason(r"D:\x\16_personal_legal\p.msg") or ""))
    check("reason() is None when eligible", ex.reason(r"C:\x\notes.txt") is None)

    print("\nDIGEST\n")
    a = parse_exclusions(json.dumps(valid_doc()), Path("t"))
    b = parse_exclusions(json.dumps(valid_doc()), Path("other"))
    check("digest is stable across identical content", a.digest == b.digest)

    reordered = valid_doc(exclude_filename_patterns=["*.mbox"])
    reordered["exclude_dir_names"] = ["16_personal_legal"]
    pretty = parse_exclusions(json.dumps(reordered, indent=4), Path("t"))
    check("digest ignores formatting", a.digest == pretty.digest)

    changed = parse_exclusions(
        json.dumps(valid_doc(exclude_filename_patterns=["*.mbox", "*.har"])), Path("t"))
    check("digest changes when a rule is added", a.digest != changed.digest)

    moved = parse_exclusions(json.dumps({
        "version": 1,
        "exclude_paths": [r"C:\seq\SEQUESTERED_DO_NOT_INGEST"],
        "exclude_dir_names": ["*.mbox", "16_personal_legal"],
        "exclude_filename_patterns": [],
    }), Path("t"))
    check("digest changes when a rule moves between kinds", a.digest != moved.digest)

    print("\nTHE REAL LIST IN FORCE\n")
    real = load_exclusions(quiet=True)
    check("real list loads", real.rule_count > 0, f"rules={real.rule_count}")
    check("real list excludes the sequestered directory",
          real.excludes(r"C:\Users\dkitc\iCloudDrive\Documents\SEQUESTERED_DO_NOT_INGEST\Exhibit_A_Beth_Epperson_Contract.pdf"))
    check("real list excludes the 6.4GB mailbox",
          real.excludes(r"C:\Users\dkitc\OneDrive\02_DexUniverse_v4.0\DirectIngestCopy_6.29.26\All mail Including Spam and Trash-002.mbox"))
    check("real list still admits ordinary corpus material",
          not real.excludes(r"C:\Users\dkitc\iCloudDrive\Documents\05_DirectIngest\00_sorted\06_ltke_content\notes.txt"))
    print(f"\n  digest in force: {real.digest}")

    print("\n" + "=" * 62)
    print(f"  {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print(f"    FAILED: {f}")
    print("=" * 62 + "\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
