"""dex_photo_thumbs: every photo gets a small picture, only odd formats get a view copy, nothing is written in the library.

Silas Reeve / DDL-3004 / 2026-10-10
"""
import json

from PIL import Image

import dex_photo_thumbs as th


def make(tmp_path):
    lib, out = tmp_path / "lib", tmp_path / "out"
    (lib / "images" / "aa").mkdir(parents=True)
    Image.new("RGB", (1200, 600), "navy").save(lib / "images" / "aa" / "aa1.png")
    Image.new("RGB", (600, 1800), "maroon").save(lib / "images" / "aa" / "aa2.tiff")
    Image.new("P", (50, 40)).save(lib / "images" / "aa" / "aa3.gif")
    (lib / "images" / "aa" / "aa4.jpg").write_bytes(b"not a picture")
    rows = [{"sha256": s, "file": f"images/aa/{s}{e}"} for s, e in (("aa1", ".png"), ("aa2", ".tiff"), ("aa3", ".gif"), ("aa4", ".jpg"), ("aa5", ".png"))]
    (lib / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return lib, out


def quiet(*a):
    pass


def test_which_formats_need_a_view_copy():
    assert [th.needs_view(e) for e in (".png", ".JPG", ".jpeg", ".webp", ".gif", ".heic", ".tiff", ".bmp")] == \
        [False, False, False, False, False, True, True, True]


def test_run_makes_thumbs_for_all_and_views_only_where_needed(tmp_path):
    lib, out = make(tmp_path)
    before = sorted(p.relative_to(lib).as_posix() for p in lib.rglob("*"))
    s = th.run(lib, out, workers=2, thumb_size=200, view_size=900, log=quiet)
    assert (s["photos"], s["made"], s["failed"], s["source_missing"]) == (5, 3, 1, 1)
    assert s["failure_reasons"] == {"UnidentifiedImageError": 1}
    assert sorted(p.relative_to(lib).as_posix() for p in lib.rglob("*")) == before          # the library is untouched
    made = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert made == ["card/aa/aa1.webp", "card/aa/aa2.webp", "card/aa/aa3.webp",
                    "thumb/aa/aa1.webp", "thumb/aa/aa2.webp", "thumb/aa/aa3.webp", "view/aa/aa2.jpg"]
    assert Image.open(out / "card/aa/aa1.webp").size == (1024, 512)                         # the open card: 1024 on the long edge, not cropped
    assert Image.open(out / "card/aa/aa2.webp").size == (341, 1024)
    assert Image.open(out / "card/aa/aa3.webp").size == (50, 40)
    assert Image.open(out / "thumb/aa/aa1.webp").size == (200, 100)                          # shape kept, longest side capped
    assert Image.open(out / "thumb/aa/aa2.webp").size == (67, 200)
    assert Image.open(out / "thumb/aa/aa3.webp").size == (50, 40)                            # never enlarged
    assert Image.open(out / "view/aa/aa2.jpg").size == (300, 900)


def test_a_second_run_makes_nothing(tmp_path):
    lib, out = make(tmp_path)
    th.run(lib, out, workers=2, log=quiet)
    s = th.run(lib, out, workers=2, log=quiet)
    assert (s["already_made"], s["made"], s["failed"]) == (3, 0, 1)                         # the broken one is tried again, and fails again


def test_redo_thumbs_remakes_them_at_the_new_size_and_leaves_cards_alone(tmp_path):
    lib, out = make(tmp_path)
    th.run(lib, out, workers=2, thumb_size=200, log=quiet)
    card_time = (out / "card/aa/aa1.webp").stat().st_mtime_ns
    s = th.run(lib, out, workers=2, thumb_size=100, redo_thumbs=True, log=quiet)
    assert Image.open(out / "thumb/aa/aa1.webp").size == (100, 50) and s["made"] == 3
    assert (out / "card/aa/aa1.webp").stat().st_mtime_ns == card_time
