"""
dex_photo_secret_where.py -- where on a flagged photo the possible-secret rules fired, as boxes.

The review page showed a whole dense screenshot and said "something shaped like a key". The Operator
(2026-10-10): "I can't read all of that and decide if there's something sensitive". This reads each
flagged photo again, keeps Tesseract's word boxes, runs the SAME rules as dex_photo_secret_scan.py over
the words, and writes the boxes of the words that matched. The album app draws them on the picture and
shows each at reading size. Reborn only.

    <library>/review-where.jsonl   one row per flagged photo:
        sha256, photo_id, read (true if the photo could be read again),
        boxes: [{rule, x, y, w, h}]   fractions of the upright picture, 0..1, rounded to 4 places
    NEVER written: the matched words, any other words, a crop. A box says where, not what.

A flagged photo with no boxes is still flagged. No box means one of: the rule was about where the photo
was kept (R5, R7); this reading differed from the first one; or the rule was fixed since the scan.
This tool changes no flag and hides or shows nothing.

    python dex_photo_secret_where.py --library D:\\DDL_Corpus\\library
"""
import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import dex_ocr_batch as ob
import dex_photo_secret_scan as ss

PAD = 0.004          # a little air round each box, as a fraction of the picture


def words_with_boxes(d):
    """(text, words). `text` is built exactly as dex_ocr_batch.lines_from_data builds it, so the rules
    see what the scan saw. words = [(start, end, left, top, width, height)] with offsets into text."""
    parts, words, pos, last = [], [], 0, None
    for i, w in enumerate(d["text"]):
        if not w.strip() or float(d["conf"][i]) < 0:
            continue
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        if last is not None:
            sep = "\n" if key != last else " "
            parts.append(sep)
            pos += 1
        parts.append(w)
        words.append((pos, pos + len(w), d["left"][i], d["top"][i], d["width"][i], d["height"][i]))
        pos += len(w)
        last = key
    return "".join(parts), words


def boxes_for(text, words, size):
    """One box per (rule, line of matched words), as fractions of a picture `size` = (width, height)."""
    W, H = size
    out = []
    for rule, a, b in ss.spots(text):
        hit = [w for w in words if w[0] < b and w[1] > a]
        if not hit:
            continue
        x0, y0 = min(w[2] for w in hit), min(w[3] for w in hit)
        x1, y1 = max(w[2] + w[4] for w in hit), max(w[3] + w[5] for w in hit)
        x, y = max(0.0, x0 / W - PAD), max(0.0, y0 / H - PAD)
        box = {"rule": rule, "x": round(x, 4), "y": round(y, 4),
               "w": round(min(1.0, x1 / W + PAD) - x, 4), "h": round(min(1.0, y1 / H + PAD) - y, 4)}
        if box not in out:
            out.append(box)
    return out


def locate(path):
    """Boxes for one image file, or None if it cannot be read. Same preparation as dex_ocr_batch.read_image."""
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
    text, words = words_with_boxes(d)
    return boxes_for(text, words, g.size)


def run(library, workers=4, log=print, locate=locate):
    library = Path(library)
    flags = [json.loads(l) for l in (library / "review.jsonl").open(encoding="utf-8") if l.strip()]
    files = {}
    for l in (library / "index.jsonl").open(encoding="utf-8"):
        r = json.loads(l)
        files[r["sha256"]] = r["file"]
    jobs = [(f, library / files[f["sha256"]]) for f in flags if f["sha256"] in files]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            found = list(ex.map(locate, [str(p) for _, p in jobs], chunksize=4))
    else:
        found = [locate(str(p)) for _, p in jobs]
    stats = {"flagged": len(flags), "read_again": 0, "with_boxes": 0, "no_boxes": 0, "could_not_read": 0, "boxes": 0}
    tmp = library / "review-where.jsonl.part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as out:
        for (f, _), boxes in zip(jobs, found):
            if boxes is None:
                stats["could_not_read"] += 1
            else:
                stats["read_again"] += 1
                stats["with_boxes" if boxes else "no_boxes"] += 1
                stats["boxes"] += len(boxes)
            out.write(json.dumps({"sha256": f["sha256"], "photo_id": f["photo_id"], "read": boxes is not None,
                                  "boxes": boxes or []}) + "\n")
    os.replace(tmp, library / "review-where.jsonl")
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", required=True, type=Path)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    for k, v in run(a.library, a.workers).items():
        print(f"  {k:<16} {v:>7,}")


if __name__ == "__main__":
    sys.exit(main())
