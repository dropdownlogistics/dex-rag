"""
dex_hash_tree.py -- sha256 of every file under a folder, one JSON line per file. Read-only on the tree.

    {"p": path relative to the root, with forward slashes, "s": bytes, "h": sha256, "m": mtime (UTC, seconds)}

The same row shape Reed Vane used for the Surface manifests (2026-10-13), so two machines' lists can be
joined on "h". A file that cannot be read gets a row with "h": null and "error": its exception name, so
the count of rows is always the count of files seen and a failure is never a silent gap.

    python dex_hash_tree.py --root D:\\DDL_Corpus\\raw --out <file.jsonl> [--until HH:MM]

Resumable: rows already in --out (same p, s and m) are kept and not re-read. --until stops cleanly at a
local clock time so a long run stays out of the nightly window.

Silas Reeve / DDL-3004 / 2026-10-13
"""
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

BLOCK = 4 * 1024 * 1024


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(BLOCK), b""):
            h.update(block)
    return h.hexdigest()


def walk(root):
    """(relative path, absolute path, size, mtime) for every file under root, in sorted order."""
    root = Path(root)
    for base, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files):
            full = os.path.join(base, name)
            try:
                st = os.stat(full)
            except OSError:
                yield os.path.relpath(full, root).replace("\\", "/"), full, None, None
                continue
            yield os.path.relpath(full, root).replace("\\", "/"), full, st.st_size, int(st.st_mtime)


def deadline(until, start=None):
    """The next time the local clock reads `until` (HH:MM) after `start`, or None. Started at 20:10 with
    --until 03:30, the deadline is 03:30 tomorrow, not "already past because 20 is more than 3"."""
    if not until:
        return None
    start = start or datetime.now()
    hh, mm = (int(x) for x in until.split(":"))
    d = start.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return d if d > start else d + timedelta(days=1)


def past(stop_at, now=None):
    return stop_at is not None and (now or datetime.now()) >= stop_at


def run(root, out, until=None, log=print, every=5000):
    out = Path(out)
    done = {}
    if out.exists():
        for line in out.open(encoding="utf-8"):
            try:
                r = json.loads(line)
                done[r["p"]] = (r.get("s"), r.get("m"))
            except (ValueError, KeyError):
                continue
    stats = {"files": 0, "bytes": 0, "kept": 0, "hashed": 0, "errors": 0, "stopped_early": False}
    stop_at = deadline(until)
    t0 = time.time()
    with out.open("a", encoding="utf-8", newline="\n") as f:
        for rel, full, size, mtime in walk(root):
            stats["files"] += 1
            if size is not None and done.get(rel) == (size, mtime):
                stats["kept"] += 1
                stats["bytes"] += size
                continue
            if past(stop_at):
                stats["stopped_early"] = True
                break
            row = {"p": rel, "s": size, "h": None, "m": mtime}
            try:
                if size is None:
                    raise OSError("stat failed")
                row["h"] = sha256_of(full)
                stats["hashed"] += 1
                stats["bytes"] += size
            except Exception as e:                      # named in the row, never dropped
                row["error"] = type(e).__name__
                stats["errors"] += 1
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            if stats["hashed"] % every == 0 and stats["hashed"]:
                f.flush()
                log(f"  ... {stats['files']:,} files, {stats['bytes'] / 2**30:.1f} GiB, {time.time() - t0:.0f} s")
    stats["seconds"] = round(time.time() - t0, 1)
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--until", help="stop at this local time, HH:MM")
    a = ap.parse_args()
    if not a.root.is_dir():
        sys.exit(f"not a folder: {a.root}")
    print(json.dumps(run(a.root, a.out, a.until), sort_keys=True))


if __name__ == "__main__":
    main()
