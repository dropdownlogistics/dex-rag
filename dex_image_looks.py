"""
dex_image_looks.py -- find images that LOOK the same but are not the same bytes.

Operator, 2026-10-10: "I'd almost guarantee there's a lot of that" (duplicates). Exact copies are
already counted once by dex_ocr_batch.py, and re-saved screenshots with identical words are marked
by dex_ocr_sort.py. This finds the rest: the same picture at another size, or saved again as a
JPEG, with no words to compare. It MARKS; it never moves, renames or deletes anything.

How: each distinct image gets two small fingerprints of how it looks, made from a 17x16 and a
16x16 greyscale thumbnail: which neighbouring cells get brighter left to right (256 bits), and
which cells are brighter than the image's average (256 bits). Two images are look-alikes only if
BOTH fingerprints nearly match (at most MAX_BITS of 256 differ in each) AND their shapes match
(width/height within 2%). One fingerprint alone is not trusted: two different mostly-white
screenshots can share one.

Images whose words were read clearly need MORE than the look: two chat screens with different
messages look the same at 16x16 and are not duplicates. For a pair of those, the words must agree
as well (WORDS_AGREE of the distinct words shared). The first run (2026-10-10) left them out
altogether, which is why re-captured screenshots still showed twice in the album.

Writes under the OCR folder:
    looks.jsonl          one row per image fingerprinted: sha256, the two fingerprints, width, height
    looks-groups.jsonl   one row per group of look-alikes: the sha256s, largest image first
Resumable: an image already in looks.jsonl is not opened again. A STOP file ends the run cleanly.

    python dex_image_looks.py --ocr C:\\Users\\dexjr\\dex-data\\ocr --root D:\\DDL_Corpus\\raw
"""
import argparse
import collections
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

MAX_BITS = 10            # of 256, per fingerprint
SHAPE_TOLERANCE = 0.02
MAX_PIXELS = 120_000_000
PILES_COMPARED = ("no-text", "low-confidence", "text")
WORDS_AGREE = 0.85


def fingerprints(im):
    """(gradient bits, average bits) as two 64-hex-digit strings, from a PIL image. Pure."""
    from PIL import Image, ImageOps
    g = ImageOps.exif_transpose(im).convert("L")
    a = np.asarray(g.resize((17, 16), Image.LANCZOS), dtype=np.int16)
    grad = (a[:, 1:] > a[:, :-1]).flatten()
    b = np.asarray(g.resize((16, 16), Image.LANCZOS), dtype=np.float32)
    avg = (b > b.mean()).flatten()
    return np.packbits(grad).tobytes().hex(), np.packbits(avg).tobytes().hex(), g.size


def _work(job):
    sha, path = job
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    try:
        with Image.open(path) as im:
            im.draft("L", (256, 256))               # JPEGs decode small; other formats ignore this
            g, a, (w, h) = fingerprints(im)
            with Image.open(path) as full:
                fw, fh = full.size
        return {"sha256": sha, "grad": g, "avg": a, "width": fw, "height": fh, "shape": round(w / h, 4)}
    except Exception as e:                          # recorded with its reason, never dropped
        return {"sha256": sha, "error": type(e).__name__}


def bits(hexes):
    """(n, 256) array of 0/1 from fingerprint hex strings."""
    raw = np.frombuffer(bytes.fromhex("".join(hexes)), dtype=np.uint8).reshape(len(hexes), 32)
    return np.unpackbits(raw, axis=1)


def words_agree(a, b, need=WORDS_AGREE):
    """Share of distinct words two texts have in common (of all the distinct words in either). Pure."""
    import re
    A, B = set(re.findall(r"[a-z0-9]+", a.lower())), set(re.findall(r"[a-z0-9]+", b.lower()))
    if not A or not B:
        return False
    return len(A & B) / len(A | B) >= need


def groups(rows, max_bits=MAX_BITS, tol=SHAPE_TOLERANCE, agree=None):
    """Groups of look-alikes among fingerprint rows: lists of sha256, each list largest image first.
    Two images join a group only when both fingerprints and the shape agree."""
    rows = [r for r in rows if "grad" in r]
    if len(rows) < 2:
        return []
    G = bits([r["grad"] for r in rows]).astype(np.float32)
    A = bits([r["avg"] for r in rows]).astype(np.float32)
    shape = np.array([r["shape"] for r in rows], dtype=np.float32)
    gs, as_ = G.sum(1), A.sum(1)
    parent = list(range(len(rows)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    STEP = 2000
    for i in range(0, len(rows), STEP):
        # differing bits = ones(a) + ones(b) - 2 * shared ones
        dg = gs[i:i + STEP, None] + gs[None, :] - 2 * (G[i:i + STEP] @ G.T)
        da = as_[i:i + STEP, None] + as_[None, :] - 2 * (A[i:i + STEP] @ A.T)
        ds = np.abs(shape[i:i + STEP, None] - shape[None, :]) / shape[None, :]
        ii, jj = np.nonzero((dg <= max_bits) & (da <= max_bits) & (ds <= tol))
        for x, y in zip(ii + i, jj):
            if x < y and (agree is None or agree(rows[int(x)]["sha256"], rows[int(y)]["sha256"])):
                parent[find(int(x))] = find(int(y))
    by = collections.defaultdict(list)
    for k in range(len(rows)):
        by[find(k)].append(rows[k])
    out = []
    for members in by.values():
        if len(members) > 1:
            members.sort(key=lambda r: (-(r["width"] * r["height"]), r["sha256"]))
            out.append([r["sha256"] for r in members])
    out.sort(key=lambda g: (-len(g), g[0]))
    return out


def below_normal():
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)


def run(ocr, root, workers=6, limit=0, log=print):
    ocr = Path(ocr)
    piles = {}
    for line in (ocr / "bins.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        piles[r["sha256"]] = r["pile"]
    first = {}
    for line in (ocr / "paths.jsonl").open(encoding="utf-8"):
        p = json.loads(line)
        if p["sha256"] and p["sha256"] not in first:
            first[p["sha256"]] = os.path.join(root, p["rel_path"].replace("/", os.sep))
    looks = ocr / "looks.jsonl"
    done = {}
    if looks.exists():
        for line in looks.open(encoding="utf-8"):
            r = json.loads(line)
            done[r["sha256"]] = r
    want = [s for s, pile in sorted(piles.items()) if pile in PILES_COMPARED]
    todo = [(s, first[s]) for s in want if s not in done and s in first]
    if limit:
        todo = todo[:limit]
    stats = {"compared_piles": len(want), "already_done": len(want) - len([s for s in want if s not in done]),
             "opened": 0, "failed": 0}
    t0 = time.time()
    if todo:
        with ProcessPoolExecutor(max_workers=workers, initializer=below_normal) as pool, \
                open(looks, "a", encoding="utf-8", newline="\n") as f:
            CHUNK = workers * 16
            for i in range(0, len(todo), CHUNK):
                if (ocr / "STOP").exists():
                    log("[STOP file found: stopping cleanly. Delete it and run the same command to resume.]")
                    break
                for r in pool.map(_work, todo[i:i + CHUNK]):
                    f.write(json.dumps(r) + "\n")
                    done[r["sha256"]] = r
                    stats["opened"] += 1
                    stats["failed"] += "error" in r
                f.flush()
                if (i // CHUNK) % 20 == 0:
                    log(f"    ... {stats['opened']:,} of {len(todo):,}, {stats['opened'] / max(time.time() - t0, 1e-9):.1f} images/s")
    texts = {}

    def text_of(sha):
        if sha not in texts:
            f = ocr / "text" / sha[:2] / f"{sha}.txt"
            texts[sha] = f.read_text(encoding="utf-8") if f.exists() else ""
        return texts[sha]

    def agree(a, b):
        # Words are asked for only when BOTH images had their words read clearly.
        if piles.get(a) == "text" and piles.get(b) == "text":
            return words_agree(text_of(a), text_of(b))
        return True

    found = groups([done[s] for s in want if s in done], agree=agree)
    with open(ocr / "looks-groups.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for g in found:
            f.write(json.dumps({"keep_candidate": g[0], "look_alikes": g[1:]}) + "\n")
    stats.update(groups=len(found), images_in_groups=sum(map(len, found)),
                 extra_copies=sum(len(g) - 1 for g in found), largest_group=max(map(len, found), default=0),
                 seconds=round(time.time() - t0, 1))
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ocr", required=True, type=Path)
    ap.add_argument("--root", required=True, type=Path, help="the folder the OCR pass read (paths.jsonl is relative to it)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    below_normal()
    for k, v in run(a.ocr, str(a.root), a.workers, a.limit).items():
        print(f"  {k:<18} {v:>10,}" if isinstance(v, int) else f"  {k:<18} {v:>10}")


if __name__ == "__main__":
    sys.exit(main())
