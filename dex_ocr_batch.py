"""
dex_ocr_batch.py -- read the text out of a backlog of images, once each, into plain files.

Operator: "we have a gigantic backlog of images we need to go through" (Silas Reeve / DDL-3004's
session, 2026-10-10). Engine: Tesseract, already on Reborn; same settings as dex/tools/ocr.py
(EXIF rotation applied, greyscale, small images upscaled). Nothing is installed by this script.

What it writes, all under --out, and nowhere else:
    results.jsonl          one row per DISTINCT image (by sha256 of its bytes): size, words,
                           mean confidence, a class, seconds, engine. No image text.
    paths.jsonl            one row per file seen: its root, its path under the root, its sha256.
                           A second copy of an image adds a row here and is not read again.
    text/<ab>/<sha256>.txt the text, only for images classed "text" or "low".
It never writes beside the images, never moves or changes them, never ingests, and prints
counts only. Files that exist only in the cloud are counted and skipped, not downloaded.

Classes:  text   enough confident words to be worth searching
          low    words were found but confidence is poor: kept, flagged, never passed off as read
          none   no usable text (a photo, a drawing)
          unsupported / unreadable   the file could not be opened as an image; reason recorded

Resumable: an image whose sha256 is already in results.jsonl is skipped. A file named STOP in
--out ends the run cleanly.

    python dex_ocr_batch.py --root D:\\DDL_Corpus\\raw --out C:\\Users\\dexjr\\dex-data\\ocr --dry-run
    python dex_ocr_batch.py --root D:\\DDL_Corpus\\raw --out C:\\Users\\dexjr\\dex-data\\ocr --limit 300
"""
import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

TESSERACT = os.environ.get("DEX_TESSERACT", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".heic"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "site-packages"}
CLOUD_ONLY = 0x1000 | 0x40000 | 0x400000       # offline, recall on open, recall on data access
MAX_BYTES = 40 * 1024 * 1024
MAX_PIXELS = 60_000_000
UPSCALE_BELOW = 1200
TEXT_MIN_WORDS = 5
TEXT_MIN_CONF = 60.0


def classify(words, conf):
    """Pure: the class for a word count and a mean confidence."""
    if words == 0:
        return "none"
    if words >= TEXT_MIN_WORDS and conf >= TEXT_MIN_CONF:
        return "text"
    return "low"


def lines_from_data(d):
    """Text rebuilt from Tesseract's word table, one line per detected line, and the
    confidences of the words kept. Words with no confidence (-1) are layout rows, not words."""
    lines, confs, cur, last = [], [], [], None
    for i, w in enumerate(d["text"]):
        c = float(d["conf"][i])
        if not w.strip() or c < 0:
            continue
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        if last is not None and key != last:
            lines.append(" ".join(cur))
            cur = []
        cur.append(w)
        confs.append(c)
        last = key
    if cur:
        lines.append(" ".join(cur))
    return "\n".join(lines), confs


def read_image(path):
    """OCR one file. Returns a dict with no path in it; text is under "_text" (never logged)."""
    import pytesseract
    from PIL import Image, ImageOps, UnidentifiedImageError
    pytesseract.pytesseract.tesseract_cmd = TESSERACT
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    t0 = time.time()
    out = {"words": 0, "confidence": 0.0, "_text": ""}
    try:
        with Image.open(path) as im:
            im.load()
            out["width"], out["height"] = im.size
            g = ImageOps.exif_transpose(im).convert("L")
    except UnidentifiedImageError:
        return dict(out, **{"class": "unsupported", "reason": "not an image Pillow can open",
                            "seconds": round(time.time() - t0, 2)})
    except (OSError, ValueError, Image.DecompressionBombError) as e:
        return dict(out, **{"class": "unreadable", "reason": type(e).__name__,
                            "seconds": round(time.time() - t0, 2)})
    if max(g.size) < UPSCALE_BELOW:
        k = UPSCALE_BELOW / max(g.size)
        g = g.resize((max(1, int(g.width * k)), max(1, int(g.height * k))))
    try:
        d = pytesseract.image_to_data(g, output_type=pytesseract.Output.DICT)
    except (pytesseract.TesseractError, RuntimeError) as e:
        return dict(out, **{"class": "unreadable", "reason": f"tesseract: {type(e).__name__}",
                            "seconds": round(time.time() - t0, 2)})
    text, confs = lines_from_data(d)
    words = len(confs)
    conf = round(sum(confs) / words, 1) if words else 0.0
    return dict(out, words=words, confidence=conf, _text=text, seconds=round(time.time() - t0, 2),
                **{"class": classify(words, conf)})


def _work(job):
    """Hash then read, in a worker process. job = (path, bytes on disk)."""
    path, size = job
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
    except OSError as e:
        return path, None, {"class": "unreadable", "reason": type(e).__name__, "words": 0,
                            "confidence": 0.0, "_text": "", "seconds": 0.0}
    return path, h.hexdigest(), None


def _ocr(job):
    path, sha = job
    return path, sha, read_image(path)


def scan(roots):
    """(root, path, stat) for every image file; cloud-only files are yielded with stat None."""
    for root in roots:
        for dp, dn, fn in os.walk(root):
            dn[:] = sorted(d for d in dn if d not in SKIP_DIRS)
            for f in sorted(fn):
                if os.path.splitext(f)[1].lower() not in IMAGE_EXT:
                    continue
                p = os.path.join(dp, f)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if getattr(st, "st_file_attributes", 0) & CLOUD_ONLY:
                    yield root, p, None
                else:
                    yield root, p, st


def below_normal():
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)


def engine_version():
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = TESSERACT
    return f"tesseract {pytesseract.get_tesseract_version()}"


def run(roots, out, limit=0, workers=4, dry_run=False, log=print):
    out = Path(out)
    stats = {k: 0 for k in ("seen", "cloud_only", "too_big", "already_done", "duplicate_copy", "read",
                            "text", "low", "none", "unsupported", "unreadable")}
    done = {}
    results, paths = out / "results.jsonl", out / "paths.jsonl"
    seen_paths = set()
    if not dry_run:
        (out / "text").mkdir(parents=True, exist_ok=True)
        if results.exists():
            for line in results.open(encoding="utf-8"):
                r = json.loads(line)
                done[r["sha256"]] = r["class"]
        if paths.exists():
            for line in paths.open(encoding="utf-8"):
                r = json.loads(line)
                seen_paths.add((r["root"], r["rel_path"]))
    engine = None if dry_run else engine_version()
    todo = []
    for root, p, st in scan(roots):
        stats["seen"] += 1
        if st is None:
            stats["cloud_only"] += 1
        elif st.st_size > MAX_BYTES:
            stats["too_big"] += 1
        else:
            todo.append((root, p, st.st_size))
    if dry_run:
        stats["would_read_at_most"] = len(todo)
        return stats

    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers, initializer=below_normal) as pool, \
            open(results, "a", encoding="utf-8", newline="\n") as rf, \
            open(paths, "a", encoding="utf-8", newline="\n") as pf:
        root_of = {p: root for root, p, _ in todo}
        size_of = {p: s for _, p, s in todo}
        CHUNK = max(workers * 8, 16)
        for i in range(0, len(todo), CHUNK):
            if (out / "STOP").exists():
                log("[STOP file found: stopping cleanly. Delete it and run the same command to resume.]")
                break
            if limit and stats["read"] >= limit:
                log("[limit reached]")
                break
            batch = [(p, s) for _, p, s in todo[i:i + CHUNK]]
            to_read, first_of = [], {}
            for p, sha, err in pool.map(_work, batch):
                rel = os.path.relpath(p, root_of[p]).replace(os.sep, "/")
                if (root_of[p], rel) not in seen_paths:
                    pf.write(json.dumps({"root": root_of[p], "rel_path": rel, "sha256": sha},
                                        ensure_ascii=False) + "\n")
                    seen_paths.add((root_of[p], rel))
                if sha is None:
                    stats["unreadable"] += 1
                elif sha in done:
                    stats["already_done"] += 1
                elif sha in first_of:
                    stats["duplicate_copy"] += 1
                else:
                    first_of[sha] = p
                    to_read.append((p, sha))
            for p, sha, r in pool.map(_ocr, to_read):
                text = r.pop("_text")
                if r["class"] in ("text", "low"):
                    d = out / "text" / sha[:2]
                    d.mkdir(exist_ok=True)
                    (d / f"{sha}.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
                row = {"sha256": sha, "bytes": size_of[p], "engine": engine,
                       "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **r}
                rf.write(json.dumps(row) + "\n")
                done[sha] = r["class"]
                stats["read"] += 1
                stats[r["class"]] += 1
            rf.flush(); pf.flush()
            if stats["read"] and (i // CHUNK) % 10 == 0:
                rate = stats["read"] / max(time.time() - t0, 1e-9)
                log(f"    ... {stats['read']:,} read, {rate:.1f} images/s, {stats['text']:,} with text")
    stats["seconds"] = round(time.time() - t0, 1)
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", action="append", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--limit", type=int, default=0, help="stop after about this many images read (0 = no cap)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true", help="count what would be read; open nothing")
    a = ap.parse_args()
    missing = [str(r) for r in a.root if not r.is_dir()]
    if missing:
        sys.exit(f"not a folder: {missing}")
    below_normal()
    stats = run([str(r) for r in a.root], a.out, a.limit, a.workers, a.dry_run)
    print()
    for k, v in stats.items():
        print(f"  {k:<20} {v:>10,}" if isinstance(v, int) else f"  {k:<20} {v:>10}")


if __name__ == "__main__":
    main()
