"""
dex_photo_thumbs.py -- small pictures for the album page, made once from the photo library.

    <out>/thumb/<ab>/<sha256>.webp   every photo, longest side THUMB px, for the grid
    <out>/view/<ab>/<sha256>.jpg     only photos a browser cannot show as they are (HEIC, TIFF, BMP),
                                     longest side VIEW px, for the opened photo

Reads <library>/index.jsonl and the library's images. Writes only under --out. EXIF rotation is
applied, then the EXIF is dropped (a thumbnail carries no location). Resumable: a file that exists
is not made again. A STOP file in --out ends the run cleanly. Sizes are parameters; the design may
ask for others (photo album brief v0.1, question to Iris Wright).

    python dex_photo_thumbs.py --library D:\\DDL_Corpus\\library --out C:\\Users\\dexjr\\dex-data\\album
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

THUMB = 360
VIEW = 2000
BROWSER_SHOWS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_PIXELS = 200_000_000


def needs_view(ext):
    return ext.lower() not in BROWSER_SHOWS


def paths_for(out, sha, ext):
    out = Path(out)
    return out / "thumb" / sha[:2] / f"{sha}.webp", (out / "view" / sha[:2] / f"{sha}.jpg") if needs_view(ext) else None


def _save(im, dest, size, fmt, **kw):
    from PIL import Image
    c = im.copy()
    c.thumbnail((size, size), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    c.save(tmp, fmt, **kw)
    os.replace(tmp, dest)


def _work(job):
    src, thumb, view, thumb_size, view_size = job
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    try:
        with Image.open(src) as im:
            im.seek(0)
            im = ImageOps.exif_transpose(im)
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA" if "transparency" in im.info or im.mode in ("LA", "PA") else "RGB")
            made = 0
            if not thumb.exists():
                _save(im, thumb, thumb_size, "WEBP", quality=78, method=4)
                made += 1
            if view is not None and not view.exists():
                _save(im.convert("RGB"), view, view_size, "JPEG", quality=88)
                made += 1
        return made, None
    except Exception as e:                          # counted with its reason; the page shows a placeholder
        return 0, type(e).__name__


def below_normal():
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)


def run(library, out, workers=6, thumb_size=THUMB, view_size=VIEW, limit=0, log=print):
    library, out = Path(library), Path(out)
    jobs = []
    stats = {"photos": 0, "already_made": 0, "made": 0, "failed": 0, "source_missing": 0}
    reasons = {}
    for line in (library / "index.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        stats["photos"] += 1
        src = library / r["file"]
        thumb, view = paths_for(out, r["sha256"], os.path.splitext(r["file"])[1])
        if thumb.exists() and (view is None or view.exists()):
            stats["already_made"] += 1
        elif not src.exists():
            stats["source_missing"] += 1
        else:
            jobs.append((src, thumb, view, thumb_size, view_size))
    if limit:
        jobs = jobs[:limit]
    t0 = time.time()
    if jobs:
        out.mkdir(parents=True, exist_ok=True)
        with ProcessPoolExecutor(max_workers=workers, initializer=below_normal) as pool:
            CHUNK = workers * 16
            for i in range(0, len(jobs), CHUNK):
                if (out / "STOP").exists():
                    log("[STOP file found: stopping cleanly. Delete it and run the same command to resume.]")
                    break
                for made, err in pool.map(_work, jobs[i:i + CHUNK]):
                    if err:
                        stats["failed"] += 1
                        reasons[err] = reasons.get(err, 0) + 1
                    else:
                        stats["made"] += 1
                if (i // CHUNK) % 20 == 0:
                    done = stats["made"] + stats["failed"]
                    log(f"    ... {done:,} of {len(jobs):,}, {done / max(time.time() - t0, 1e-9):.1f} photos/s")
    stats["seconds"] = round(time.time() - t0, 1)
    stats["failure_reasons"] = reasons
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--thumb", type=int, default=THUMB)
    ap.add_argument("--view", type=int, default=VIEW)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    below_normal()
    for k, v in run(a.library, a.out, a.workers, a.thumb, a.view, a.limit).items():
        print(f"  {k:<18} {v}")


if __name__ == "__main__":
    sys.exit(main())
