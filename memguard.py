"""
memguard.py -- a heavy job asks before it starts: is there room for me?

Why: 2026-10-03, 18:17-18:23. Two scoring processes each opened four Chroma collections,
took about 21.6 GB between them on a 32 GB machine, and Dex's live server stopped answering
for six minutes. Nothing refused, because nothing asked.

A job that loads a store, a model or a large matrix calls `require()` first, naming what it
needs and what must be left for everything else. Below that, it does not start, and says why
in numbers. A check that cannot run (no way to read memory on this platform) REFUSES: an
unknown is not a pass.

    from memguard import require
    require(need_gb=4.0, what="private rebuild")        # raises Refused, or returns the reading

    python memguard.py --need 4 --what "scoring run"    # exit 0 room, 1 refused, 2 cannot tell

It reads physical memory only, once, at start. It does not watch a running job, and it does
not know what another job is about to take: two jobs that both check and then both load can
still collide. One heavy job at a time is still the rule; this catches the case where the
machine is already full.
"""
from __future__ import annotations

import argparse
import ctypes
import sys

GIB = 1024 ** 3
# Left for Dex's server, Ollama's loaded model and Windows itself after this job has taken its
# share. Measured 2026-10-09 with Dex idle and no heavy job: 15.8 GiB free of 31.9.
DEFAULT_RESERVE_GB = 6.0


class Refused(Exception):
    """There is not enough free memory for this job. Carries the numbers."""


class Unknown(Refused):
    """Free memory could not be read, so the job is refused rather than waved through."""


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def read() -> tuple[float, float]:
    """(free GiB, total GiB) of physical memory. Raises Unknown if it cannot be read."""
    try:
        st = _MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            raise OSError("GlobalMemoryStatusEx returned 0")
        return st.ullAvailPhys / GIB, st.ullTotalPhys / GIB
    except Exception as e:  # noqa: BLE001 -- any failure to read is the same answer: unknown
        raise Unknown(f"free memory could not be read ({type(e).__name__}: {e}); refusing, not guessing") from e


def require(need_gb: float, what: str, reserve_gb: float = DEFAULT_RESERVE_GB, reader=read) -> dict:
    """Return the reading if `need_gb` fits with `reserve_gb` left over; otherwise raise Refused."""
    if not (isinstance(need_gb, (int, float)) and need_gb > 0):
        raise ValueError("need_gb must be a positive number: say what the job needs")
    if not (isinstance(reserve_gb, (int, float)) and reserve_gb >= 0):
        raise ValueError("reserve_gb must be zero or more")
    free, total = reader()
    reading = {"what": what, "free_gb": round(free, 1), "total_gb": round(total, 1),
               "need_gb": float(need_gb), "reserve_gb": float(reserve_gb),
               "left_after_gb": round(free - need_gb, 1)}
    if free - need_gb < reserve_gb:
        raise Refused(
            f"{what}: not starting. Free memory is {free:.1f} GiB of {total:.1f}; this job needs "
            f"{need_gb:.1f} and {reserve_gb:.1f} must stay free for Dex and the model, so it needs "
            f"{need_gb + reserve_gb:.1f} free. Short by {need_gb + reserve_gb - free:.1f} GiB. "
            f"Close the other heavy job, or run this later.")
    return reading


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Is there room for a heavy job?")
    ap.add_argument("--need", type=float, required=True, help="GiB this job will take")
    ap.add_argument("--reserve", type=float, default=DEFAULT_RESERVE_GB, help="GiB that must stay free")
    ap.add_argument("--what", default="heavy job")
    a = ap.parse_args(argv)
    try:
        r = require(a.need, a.what, a.reserve)
    except Unknown as e:
        print(f"REFUSED (unknown): {e}", file=sys.stderr)
        return 2
    except Refused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1
    print(f"room: {r['free_gb']} GiB free of {r['total_gb']}; {r['what']} takes {r['need_gb']}, "
          f"leaving {r['left_after_gb']} (reserve {r['reserve_gb']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
