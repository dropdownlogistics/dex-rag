"""
dex_photo_word_boxes.py -- read each photo that has words once more and keep where every word is.

The first OCR pass kept the text and threw the layout away. Three things need the layout: the graph's
`ids_found` (an id read from a photo counts only with its word confidence, Lena Marsh's rule), search
that can show where on a photo it matched, and the review page's "where it fired". One pass, kept.

    <ocr>/boxes/<ab>/<sha256>.json     {"w": W, "h": H, "words": [[text, conf, x, y, w, h], ...]}
        W, H: the upright picture as read (after any upscale). x, y, w, h: pixels in that picture.
        conf: Tesseract's word confidence, 0-100.

This is the same material as <ocr>/text/ (the words read from the Operator's own photos) and lives
beside it, on Reborn, outside git. A photo marked hidden is skipped: its words are not copied anywhere
new. Photos with no words are skipped. A photo already done is skipped, so a stopped run resumes.

It reads D: heavily. --until HH:MM (local) stops it cleanly; the nightly sweep starts at 04:00 and
nothing of this should be reading D: then.

    python dex_photo_word_boxes.py --library D:\\DDL_Corpus\\library --ocr C:\\Users\\dexjr\\dex-data\\ocr --until 03:30
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import dex_ocr_batch as ob

MIN_WORDS = 5


def words_of(d):
    """[[text, conf, x, y, w, h], ...] from Tesseract's word table. Layout rows (conf -1) and blanks are dropped."""
    out = []
    for i, w in enumerate(d["text"]):
        c = float(d["conf"][i])
        if not w.strip() or c < 0:
            continue
        out.append([w, round(c, 1), int(d["left"][i]), int(d["top"][i]), int(d["width"][i]), int(d["height"][i])])
    return out


def read(path):
    """{"w","h","words"} for one image, or None if it cannot be read. Same preparation as dex_ocr_batch.read_image."""
    import pytesseract
    from PIL import Image, ImageOps, UnidentifiedImageError
    pytesseract.pytesseract.tesseract_cmd = ob.TESSERACT
    Image.MAX_IMAGE_PIXELS = ob.MAX_PIXELS
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    try:
        with Image.open(path) as im:
            im.load()
            g = ImageOps.exif_transpose(im).convert("L")
        if max(g.size) < ob.UPSCALE_BELOW:
            k = ob.UPSCALE_BELOW / max(g.size)
            g = g.resize((max(1, int(g.width * k)), max(1, int(g.height * k))))
        d = pytesseract.image_to_data(g, output_type=pytesseract.Output.DICT)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, pytesseract.TesseractError, RuntimeError):
        return None
    return {"w": g.width, "h": g.height, "words": words_of(d)}


def _work(job):
    src, dst = job
    r = read(src)
    if r is None:
        return "unreadable"
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(dst) + ".part")
    tmp.write_text(json.dumps(r, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, dst)
    return "read"


def hidden_shas(library):
    out = set()
    f = Path(library) / "app-state.jsonl"
    if f.exists():
        for l in f.open(encoding="utf-8"):
            r = json.loads(l)
            if r.get("hidden") is True:
                out.add(r["sha256"])
            elif r.get("hidden") is False:
                out.discard(r["sha256"])
    return out


def jobs(library, ocr):
    """(to do, counts). Photos with words, not hidden, not already done."""
    library, ocr = Path(library), Path(ocr)
    hidden = hidden_shas(library)
    todo, n = [], {"photos": 0, "no_words": 0, "hidden_skipped": 0, "already_done": 0}
    for l in (library / "index.jsonl").open(encoding="utf-8"):
        r = json.loads(l)
        n["photos"] += 1
        sha = r["sha256"]
        if r["pile"] == "no-text" or r.get("words", 0) < MIN_WORDS:
            n["no_words"] += 1
        elif sha in hidden:
            n["hidden_skipped"] += 1
        elif (ocr / "boxes" / sha[:2] / f"{sha}.json").exists():
            n["already_done"] += 1
        else:
            todo.append((str(library / r["file"]), str(ocr / "boxes" / sha[:2] / f"{sha}.json")))
    n["to_do"] = len(todo)
    return todo, n


def stop_time(until, now=None):
    """The next local HH:MM at or after now, as a datetime. None means no stop."""
    if not until:
        return None
    now = now or datetime.now()
    h, m = (int(x) for x in until.split(":"))
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return t if t > now else t + timedelta(days=1)


def run(library, ocr, workers=3, until=None, batch=48, log=print, work=_work, clock=datetime.now):
    todo, n = jobs(library, ocr)
    stop = stop_time(until, clock())
    log(f"{json.dumps(n)} stop_at={stop.isoformat(timespec='minutes') if stop else None}")
    done, t0, result = 0, time.time(), {"read": 0, "unreadable": 0}
    stopped = False
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i in range(0, len(todo), batch):
            if stop and clock() >= stop:
                stopped = True
                break
            for r in ex.map(work, todo[i:i + batch], chunksize=4):
                result[r] += 1
            done = min(i + batch, len(todo))
            if (i // batch) % 10 == 0:
                rate = done / max(time.time() - t0, 1e-6)
                log(f"{done:,}/{len(todo):,}  {rate:.2f}/s  {clock().isoformat(timespec='seconds')}")
    out = dict(n, **result, stopped_for_time=stopped, left=len(todo) - result["read"] - result["unreadable"])
    log("DONE " + json.dumps(out))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", required=True, type=Path)
    ap.add_argument("--ocr", required=True, type=Path)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--until", help="local HH:MM to stop at")
    a = ap.parse_args()
    run(a.library, a.ocr, a.workers, a.until, log=lambda s: print(s, flush=True))


if __name__ == "__main__":
    sys.exit(main())
