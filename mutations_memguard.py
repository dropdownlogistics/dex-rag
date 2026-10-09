"""Planted faults for memguard.py. Each must make test_memguard.py fail.

    python mutations_memguard.py        (from the dex-rag root, with the venv's python)

The file is restored afterwards, whatever happens. Silas Reeve / DDL-3004 / 2026-10-09
"""
import subprocess
import sys
from pathlib import Path

TARGET = Path("memguard.py")
TESTS = "test_memguard.py"

M = [
    ("reserve ignored", "if free - need_gb < reserve_gb:", "if free - need_gb < 0:"),
    ("exactly enough refused", "if free - need_gb < reserve_gb:", "if free - need_gb <= reserve_gb:"),
    ("need ignored", "if free - need_gb < reserve_gb:", "if free < reserve_gb:"),
    ("never refuses", "if free - need_gb < reserve_gb:", "if False:"),
    ("unknown passes", "        raise Unknown(f\"free memory could not be read", "        return 64.0, 64.0\n        raise Unknown(f\"free memory could not be read"),
    ("unknown is not a refusal", "class Unknown(Refused):", "class Unknown(Exception):"),
    ("zero need accepted", "isinstance(need_gb, (int, float)) and need_gb > 0", "isinstance(need_gb, (int, float)) and need_gb >= 0"),
    ("reading reports total as free", '"free_gb": round(free, 1)', '"free_gb": round(total, 1)'),
    ("message drops the shortfall", "Short by {need_gb + reserve_gb - free:.1f} GiB. ", ""),
    ("cli returns 0 on refusal", '        print(f"REFUSED: {e}", file=sys.stderr)\n        return 1', '        print(f"REFUSED: {e}", file=sys.stderr)\n        return 0'),
    ("cli returns 1 on unknown", '        print(f"REFUSED (unknown): {e}", file=sys.stderr)\n        return 2', '        print(f"REFUSED (unknown): {e}", file=sys.stderr)\n        return 1'),
    ("available replaced by total", "return st.ullAvailPhys / GIB, st.ullTotalPhys / GIB", "return st.ullTotalPhys / GIB * 2, st.ullTotalPhys / GIB"),
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
