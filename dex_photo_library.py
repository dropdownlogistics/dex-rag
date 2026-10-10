"""
dex_photo_library.py -- one photo library in the corpus: one copy of each distinct image, and an index.

Operator, 2026-10-10: "in the corpus, we have a photo library, I don't want the stuff to be scattered
about", and then the album idea: screenshots go to an intake folder, a model organises them, and an
album app built on the graph gives search and quick access, outside iCloud Photos.

This is the foundation for that. It COPIES; it never moves, renames or deletes a source file.

    <library>/images/<ab>/<sha256><.ext>   the image, named by its content, so one copy can exist
    <library>/index.jsonl                  one row per image: album, every place it used to live,
                                           size, shape, what the OCR pass found, twins, look-alikes

Albums are LABELS in the index, not folders, so regrouping is an edit to the index and an image
can be found by where it came from as well as by what it is. The label is a first proposal made
from the source folder and the OCR pile; the Operator's own DirectScreens folder names are kept
exactly.

Reads what dex_ocr_batch.py, dex_ocr_sort.py and dex_image_looks.py wrote. Images set aside by the
sort (album art) are not copied. Each copy is verified by sha256 after writing. Resumable; a STOP
file in the library ends a run cleanly.

    python dex_photo_library.py --ocr C:\\Users\\dexjr\\dex-data\\ocr --root D:\\DDL_Corpus\\raw --library D:\\DDL_Corpus\\library
"""
import argparse
import collections
import hashlib
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DIRECT = "icloud/Documents/02_Dex/01_Production/DirectScreens/"
# Which of an image's old homes names it best: lower is better. First match wins.
HOME_RANK = [
    (0, DIRECT),
    (1, "onedrive/Pictures/Screenshots/"),
    (5, "icloud/Documents/02_Dex/03_iMazingExports/"),
    (5, "icloud/Documents/05_DirectIngest/"),
    (5, "icloud/Documents/04_DDL_Ingest/"),
    (2, "icloud/Documents/02_Dex/01_Production/"),
    (3, "icloud/"),
    (5, "onedrive/99_DexUniverseArchive/"),
    (3, "onedrive/"),
    (4, "dex-universe/"),
    (4, "google-takeout/Takeout/"),
    (7, "google-takeout/Takeout-20230506T150450Z/"),
]
CHAT_MARKS = ("/Google Chat/", "/Hangouts/")
PHONE_MARKS = ("/03_iMazingExports/", "/Dex_iOS/", "/evidencelocker/", "/Screenshots/", "/screens/")


def home_rank(rel):
    for r, prefix in HOME_RANK:
        if rel.startswith(prefix):
            return r
    return 4


def best_home(paths):
    return sorted(paths, key=lambda p: (home_rank(p), len(p), p))[0]


def album(paths, pile, year=None):
    """The proposed album label for an image, from where it lived and what the OCR pass found. Pure."""
    home = best_home(paths)
    if home.startswith(DIRECT):
        rest = home[len(DIRECT):].split("/")
        return "process/" + (rest[0] if len(rest) > 1 else "_loose")
    if home.startswith("onedrive/Pictures/Screenshots/"):
        return "pc-snips"
    if any(m in "/" + p for p in paths for m in CHAT_MARKS):
        return "chats"
    if pile == "no-text":
        m = re.search(r"Photos from (\d{4})", home)
        y = m.group(1) if m else year
        return f"photos/{y}" if y else "photos/undated"
    if any(m in "/" + p for p in paths for m in PHONE_MARKS):
        return "phone-screens"
    return "unsorted"


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load(ocr):
    ocr = Path(ocr)
    res = {}
    for line in (ocr / "results.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        res[r["sha256"]] = r                                  # the last row for an image is the current one
    bins = {}
    for line in (ocr / "bins.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        bins[r["sha256"]] = r
    paths = collections.defaultdict(list)
    for line in (ocr / "paths.jsonl").open(encoding="utf-8"):
        p = json.loads(line)
        if p["sha256"]:
            paths[p["sha256"]].append(p["rel_path"])
    group = {}
    lg = ocr / "looks-groups.jsonl"
    if lg.exists():
        for line in lg.open(encoding="utf-8"):
            g = json.loads(line)
            for s in [g["keep_candidate"]] + g["look_alikes"]:
                group[s] = g["keep_candidate"]
    return res, bins, paths, group


def run(ocr, root, library, limit=0, log=print):
    res, bins, paths, group = load(ocr)
    library = Path(library)
    (library / "images").mkdir(parents=True, exist_ok=True)
    index = library / "index.jsonl"
    done = set()
    if index.exists():
        for line in index.open(encoding="utf-8"):
            done.add(json.loads(line)["sha256"])
    stats = {k: 0 for k in ("distinct", "set_aside", "not_opened", "already_in_library", "copied",
                            "source_missing", "source_changed", "copy_failed", "bytes")}
    t0 = time.time()
    with open(index, "a", encoding="utf-8", newline="\n") as f:
        for sha in sorted(bins):
            b = bins[sha]
            stats["distinct"] += 1
            if b["pile"] == "set-aside":
                stats["set_aside"] += 1
                continue
            if b["pile"] == "not-opened":                      # not an image anything here could open
                stats["not_opened"] += 1
                continue
            if sha in done:
                stats["already_in_library"] += 1
                continue
            if limit and stats["copied"] >= limit:
                log("[limit reached]")
                break
            if (library / "STOP").exists():
                log("[STOP file found: stopping cleanly. Delete it and run the same command to resume.]")
                break
            ps = paths.get(sha, [])
            home = best_home(ps)
            src = next((os.path.join(root, p.replace("/", os.sep)) for p in sorted(ps, key=lambda p: (home_rank(p), len(p), p))
                        if os.path.exists(os.path.join(root, p.replace("/", os.sep)))), None)
            if src is None:
                stats["source_missing"] += 1
                continue
            if sha256_of(src) != sha:                          # the snapshot changed since it was read: do not guess
                stats["source_changed"] += 1
                continue
            ext = os.path.splitext(home)[1].lower()
            dest = library / "images" / sha[:2] / f"{sha}{ext}"
            dest.parent.mkdir(exist_ok=True)
            tmp = dest.with_suffix(dest.suffix + ".part")
            shutil.copyfile(src, tmp)
            if sha256_of(tmp) != sha:
                tmp.unlink()
                stats["copy_failed"] += 1
                continue
            os.replace(tmp, dest)
            st = os.stat(src)
            shutil.copystat(src, dest)
            r = res.get(sha, {})
            year = datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime("%Y")
            row = {"sha256": sha, "file": f"images/{sha[:2]}/{sha}{ext}", "bytes": st.st_size,
                   "width": r.get("width"), "height": r.get("height"),
                   "modified": datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "album": album(ps, b["pile"], year), "name": home.rsplit("/", 1)[-1],
                   "pile": b["pile"], "bin": b.get("bin"), "words": b.get("words", 0),
                   "confidence": b.get("confidence", 0.0), "phone": b.get("phone", False),
                   "twin_of": b.get("twin_of"), "looks_like": group.get(sha) if group.get(sha) != sha else None,
                   "has_text": b["pile"] in ("text", "low-confidence"), "was_at": sorted(ps)}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            done.add(sha)
            stats["copied"] += 1
            stats["bytes"] += st.st_size
            if stats["copied"] % 1000 == 0:
                log(f"    ... {stats['copied']:,} copied, {stats['bytes'] / 2**30:.1f} GiB, "
                    f"{stats['copied'] / max(time.time() - t0, 1e-9):.0f} images/s")
    stats["seconds"] = round(time.time() - t0, 1)
    return stats


def albums(library):
    c = collections.Counter()
    for line in (Path(library) / "index.jsonl").open(encoding="utf-8"):
        c[json.loads(line)["album"]] += 1
    return c


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ocr", required=True, type=Path)
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--library", required=True, type=Path)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    stats = run(a.ocr, str(a.root), a.library, a.limit)
    print()
    for k, v in stats.items():
        print(f"  {k:<20} {v:>14,}" if isinstance(v, int) else f"  {k:<20} {v:>14}")
    print("\n  albums:")
    for k, v in sorted(albums(a.library).items()):
        print(f"    {v:>7,}  {k}")


if __name__ == "__main__":
    sys.exit(main())
