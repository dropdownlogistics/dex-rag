"""
dex_photo_facts.py -- the facts about each library photo that the album's row needs and the copy record lacks.

Iris Wright's row (D-mail DDL-3015:20261010T183127Z-5dec, ruled with the Operator): `taken` with its
source, `placeholder`, `excerpt`, `place`, `source`, `hidden`. This fills the ones a machine can fill
without guessing, into <library>/facts.jsonl, one row per photo:

    taken         when the picture was taken, "YYYY-MM-DDTHH:MM:SS" or "YYYY-MM-DD", or null
    taken_source  "file"  the date the camera wrote inside the image
                  "name"  a date in one of the file's old names (chat exports carry one)
                  "none"  no trustworthy date. The file's modified time is NOT used: for exported
                          photos it is the export date, which put 3,895 photos in 2026 (brief v0.1).
    place         {"lat": .., "lon": ..} when the image carries coordinates, else null. No name: turning
                  coordinates into a place name needs a lookup this tool does not do.
    placeholder   the image's average colour as "#rrggbb", for a tile to show while it loads
    excerpt       the first EXCERPT_WORDS words read from it, only when at least MIN_WORDS were read
    source        "corpus" (the Operator's own images). Seat screenshots will be "git"; the two never mix.
    hidden        false. Set by the Operator in the app, never by this tool; an existing true is kept.

Rewritten whole each run from what is on disk; a photo already in facts.jsonl is not opened again
unless --redo. Reads the library and the OCR text; writes only facts.jsonl. Prints counts only.

    python dex_photo_facts.py --library D:\\DDL_Corpus\\library --ocr C:\\Users\\dexjr\\dex-data\\ocr
"""
import argparse
import collections
import json
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

EXCERPT_WORDS = 20
MIN_WORDS = 5
NAME_DATE = re.compile(r"(?<!\d)((?:19|20)\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])(?!\d)")
# A clock time written straight after that date: "2026-10-10 220641", "2026-09-25 14 03 22", "20140719_101500".
NAME_TIME = re.compile(r"^[ _T-]([01]\d|2[0-3])[ .:_-]?([0-5]\d)[ .:_-]?([0-5]\d)(?!\d)")
EXIF_DATE = re.compile(r"^(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})")
FIRST_YEAR, MAX_PIXELS = 1990, 200_000_000


def date_from_names(paths, this_year):
    """The earliest plausible date written in any of a photo's old file names, or None: YYYY-MM-DD, or
    YYYY-MM-DDTHH:MM:SS when a clock time is written straight after it (the machine's own local time, the
    same as a camera's). The earliest day wins; on that day a name with a time beats one without.
    Only the file name is read, not its folders: a folder called 2026-09-25 says when it was filed."""
    found = []
    for p in paths:
        name = p.rsplit("/", 1)[-1]
        for hit in NAME_DATE.finditer(name):
            y, m, d = hit.groups()
            if FIRST_YEAR <= int(y) <= this_year:
                t = NAME_TIME.match(name[hit.end():])
                found.append((f"{y}-{m}-{d}", not t, "T%s:%s:%s" % t.groups() if t else ""))
    if not found:
        return None
    day, _, clock = min(found)
    return day + clock


def exif_taken(raw, this_year):
    """'YYYY-MM-DDTHH:MM:SS' from an EXIF date string, or None if it is empty, zero or implausible."""
    m = EXIF_DATE.match(str(raw or "").strip())
    if not m:
        return None
    y, mo, d, h, mi, s = m.groups()
    if not (FIRST_YEAR <= int(y) <= this_year and 1 <= int(mo) <= 12 and 1 <= int(d) <= 31):
        return None
    return f"{y}-{mo}-{d}T{h}:{mi}:{s}"


def gps_decimal(gps):
    """{"lat","lon"} from an EXIF GPS block, or None. South and west are negative."""
    try:
        def dec(v, ref, neg):
            d, m, s = (float(x) for x in v)
            val = d + m / 60 + s / 3600
            return -val if str(ref).upper().startswith(neg) else val
        lat, lon = dec(gps[2], gps[1], "S"), dec(gps[4], gps[3], "W")
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None
    return {"lat": round(lat, 6), "lon": round(lon, 6)}


def excerpt_of(text):
    words = (text or "").split()
    return " ".join(words[:EXCERPT_WORDS]) if len(words) >= MIN_WORDS else None


def _work(job):
    sha, path, this_year = job
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    out = {"sha256": sha, "taken": None, "place": None, "placeholder": None}
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            sub = exif.get_ifd(0x8769) if exif else {}
            out["taken"] = exif_taken(sub.get(36867) or sub.get(36868), this_year)      # original, then digitised
            gps = exif.get_ifd(0x8825) if exif else {}
            out["place"] = gps_decimal(gps) if gps else None
            im.draft("RGB", (64, 64))
            r, g, b = im.convert("RGB").resize((1, 1)).getpixel((0, 0))
            out["placeholder"] = f"#{r:02x}{g:02x}{b:02x}"
    except Exception as e:                       # the row is still written, with what could not be read named
        out["error"] = type(e).__name__
    return out


def run(library, ocr, workers=8, redo=False, limit=0, this_year=None, log=print):
    library, ocr = Path(library), Path(ocr)
    this_year = this_year or time.gmtime().tm_year
    index = [json.loads(l) for l in (library / "index.jsonl").open(encoding="utf-8")]
    facts_file = library / "facts.jsonl"
    old = {}
    if facts_file.exists():
        for l in facts_file.open(encoding="utf-8"):
            r = json.loads(l)
            old[r["sha256"]] = r
    todo = [(r["sha256"], str(library / r["file"]), this_year) for r in index if redo or r["sha256"] not in old]
    if limit:
        todo = todo[:limit]
    read = {}
    t0 = time.time()
    if todo:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for i, r in enumerate(pool.map(_work, todo, chunksize=32), 1):
                read[r["sha256"]] = r
                if i % 4000 == 0:
                    log(f"    ... {i:,} of {len(todo):,}, {i / max(time.time() - t0, 1e-9):.0f} photos/s")
    rows, stats = [], collections.Counter()
    for r in index:
        sha = r["sha256"]
        seen = read.get(sha) or old.get(sha)
        if seen is None:
            stats["not_read_yet"] += 1
            continue
        taken, src = seen.get("taken"), "file"
        if seen.get("taken_source") in ("name", "none") and sha not in read:
            taken = None                                     # an old row's name-date is recomputed below
        if not taken:
            taken = date_from_names(r.get("was_at", []), this_year)
            src = "name" if taken else "none"
        words = r.get("words", 0)
        text = None
        if r.get("has_text") and words >= MIN_WORDS:
            f = ocr / "text" / sha[:2] / f"{sha}.txt"
            text = f.read_text(encoding="utf-8") if f.exists() else None
        row = {"sha256": sha, "taken": taken, "taken_source": src, "place": seen.get("place"),
               "placeholder": seen.get("placeholder"), "excerpt": excerpt_of(text), "source": "corpus",
               "hidden": bool(old.get(sha, {}).get("hidden", False))}
        if seen.get("error"):
            row["error"] = seen["error"]
            stats["could_not_open"] += 1
        rows.append(row)
        stats["taken_from_" + src] += 1
        stats["with_place"] += row["place"] is not None
        stats["with_excerpt"] += row["excerpt"] is not None
    tmp = library / "facts.jsonl.part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp, facts_file)
    stats["photos"] = len(rows)
    stats["opened_this_run"] = len(read)
    return dict(stats)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", required=True, type=Path)
    ap.add_argument("--ocr", required=True, type=Path)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    for k, v in sorted(run(a.library, a.ocr, a.workers, a.redo, a.limit).items()):
        print(f"  {k:<22} {v:>8,}")


if __name__ == "__main__":
    sys.exit(main())
