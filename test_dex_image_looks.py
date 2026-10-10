"""dex_image_looks: a resized or re-saved copy is a look-alike; a different picture is not, even a similar one.

Pictures are generated here from seeded noise blurred into shapes, so they have structure the
way photos do.  Silas Reeve / DDL-3004 / 2026-10-10
"""
import json

import numpy as np
from PIL import Image, ImageFilter

import dex_image_looks as lk


def picture(seed, size=(800, 600)):
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 255, size=(12, 16, 3), dtype=np.uint8)
    return Image.fromarray(small).resize(size, Image.BICUBIC).filter(ImageFilter.GaussianBlur(3))


def row(sha, im):
    g, a, (w, h) = lk.fingerprints(im)
    return {"sha256": sha, "grad": g, "avg": a, "width": im.width, "height": im.height, "shape": round(w / h, 4)}


def test_fingerprints_are_256_bits_each():
    g, a, size = lk.fingerprints(picture(1))
    assert len(g) == 64 and len(a) == 64 and size == (800, 600)


def test_a_resized_and_a_resaved_copy_group_with_the_original_largest_first(tmp_path):
    p = picture(1)
    p.save(tmp_path / "re.jpg", quality=60)
    rows = [row("small", p.resize((400, 300))), row("orig", p), row("jpeg", Image.open(tmp_path / "re.jpg")),
            row("other", picture(2)), row("third", picture(3))]
    assert lk.groups(rows) == [["jpeg", "orig", "small"]]          # 800x600 twice (sha order), then 400x300


def test_different_pictures_do_not_group():
    assert lk.groups([row(f"p{i}", picture(i)) for i in range(40)]) == []


def test_same_look_but_another_shape_is_not_a_look_alike():
    p = picture(1)
    stretched = p.resize((800, 400))                                 # same content, squashed
    assert lk.groups([row("a", p), row("b", stretched)]) == []
    assert lk.groups([row("a", p), row("b", stretched)], tol=1.0) == [["a", "b"]]   # the shape rule is what refused


def test_both_fingerprints_must_agree():
    a, b = row("a", picture(1)), row("b", picture(2))
    b_same_grad = dict(b, grad=a["grad"])                            # one fingerprint equal, the other not
    assert lk.groups([a, b_same_grad]) == []
    b_same_avg = dict(b, avg=a["avg"])
    assert lk.groups([a, b_same_avg]) == []
    assert lk.groups([a, dict(b, grad=a["grad"], avg=a["avg"])]) == [["a", "b"]]


def test_a_small_edit_is_tolerated_and_the_limit_is_real():
    p = picture(1)
    edited = p.copy()
    edited.paste((255, 255, 255), (700, 520, 800, 600))             # a corner stamped white: about 2% of the area
    a, b = row("a", p), row("b", edited)
    d = int((lk.bits([a["grad"]]) != lk.bits([b["grad"]])).sum())
    assert 0 < d <= lk.MAX_BITS
    assert lk.groups([a, b]) == [["a", "b"]]
    assert lk.groups([a, b], max_bits=d - 1) == []


def test_failed_rows_are_left_out_of_groups_not_matched():
    p = picture(1)
    assert lk.groups([row("a", p), {"sha256": "x", "error": "OSError"}, row("b", p.resize((400, 300)))]) == [["a", "b"]]


def test_run_compares_only_the_no_text_and_low_piles_and_resumes(tmp_path):
    root, ocr = tmp_path / "root", tmp_path / "ocr"
    root.mkdir(); ocr.mkdir()
    p = picture(1)
    p.save(root / "a.png"); p.resize((400, 300)).save(root / "b.png"); p.save(root / "t.png"); picture(2).save(root / "c.png")
    (root / "bad.png").write_bytes(b"nope")
    bins = [("sa", "no-text"), ("sb", "low-confidence"), ("st", "text"), ("sc", "no-text"), ("sx", "no-text"), ("sm", "set-aside")]
    (ocr / "bins.jsonl").write_text("".join(json.dumps({"sha256": s, "pile": pile}) + "\n" for s, pile in bins), encoding="utf-8")
    paths = [("sa", "a.png"), ("sb", "b.png"), ("st", "t.png"), ("sc", "c.png"), ("sx", "bad.png"), ("sm", "a.png")]
    (ocr / "paths.jsonl").write_text("".join(json.dumps({"root": "r", "rel_path": p_, "sha256": s}) + "\n" for s, p_ in paths), encoding="utf-8")
    quiet = lambda *a: None
    s = lk.run(ocr, str(root), workers=2, log=quiet)
    assert (s["compared_piles"], s["opened"], s["failed"], s["groups"], s["extra_copies"]) == (4, 4, 1, 1, 1)
    g = [json.loads(x) for x in (ocr / "looks-groups.jsonl").read_text(encoding="utf-8").splitlines()]
    assert g == [{"keep_candidate": "sa", "look_alikes": ["sb"]}]    # the text image and the set-aside one are not compared
    s = lk.run(ocr, str(root), workers=2, log=quiet)
    assert (s["opened"], s["already_done"], s["groups"]) == (0, 4, 1)
