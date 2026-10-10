"""dex_ocr_batch: each distinct image is read once, text goes only under --out, nothing is passed off as read.

Images are drawn here with Pillow, so the tests need Tesseract on the machine (it is on Reborn)
and nothing else.  Silas Reeve / DDL-3004 / 2026-10-10
"""
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

import dex_ocr_batch as ob

pytestmark = pytest.mark.skipif(not Path(ob.TESSERACT).exists(), reason="Tesseract is not installed here")
SENTENCE = "The quarterly ledger closes on Friday morning"


def text_image(path, text=SENTENCE, size=(1600, 300)):
    im = Image.new("RGB", size, "white")
    ImageDraw.Draw(im).text((40, 100), text, fill="black", font=ImageFont.truetype("arial.ttf", 56))
    im.save(path)


def blank_image(path, colour="white"):
    Image.new("RGB", (800, 600), colour).save(path)


def rows(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]


def quiet(*a):
    pass


def test_classify_boundaries():
    assert ob.classify(0, 0.0) == "none"
    assert ob.classify(5, 60.0) == "text"
    assert ob.classify(4, 99.0) == "low"
    assert ob.classify(50, 59.9) == "low"
    assert ob.classify(1, 10.0) == "none"          # a stray mark on a photograph
    assert ob.classify(4, 59.9) == "none"
    assert ob.classify(5, 10.0) == "low"


def test_lines_are_rebuilt_and_layout_rows_are_not_words():
    d = {"text": ["", "Hello", "world", "  ", "second", "line"],
         "conf": ["-1", "96.0", "90", "95", "80.5", "-1"],
         "block_num": [1, 1, 1, 1, 1, 1], "par_num": [1, 1, 1, 1, 1, 1], "line_num": [0, 1, 1, 1, 2, 2]}
    text, confs = ob.lines_from_data(d)
    assert text == "Hello world\nsecond" and confs == [96.0, 90.0, 80.5]


def test_a_clear_sentence_is_read_and_classed_text(tmp_path):
    p = tmp_path / "a.png"
    text_image(p)
    r = ob.read_image(str(p))
    assert r["class"] == "text" and r["words"] == 7 and r["confidence"] >= 80
    assert r["_text"] == SENTENCE and (r["width"], r["height"]) == (1600, 300)


def test_a_blank_image_is_none_and_a_non_image_is_unsupported(tmp_path):
    blank_image(tmp_path / "b.png")
    assert ob.read_image(str(tmp_path / "b.png"))["class"] == "none"
    (tmp_path / "c.png").write_bytes(b"this is not a picture")
    r = ob.read_image(str(tmp_path / "c.png"))
    assert r["class"] == "unsupported" and r["words"] == 0 and r["_text"] == ""


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    (root / ".git").mkdir()
    text_image(root / "one.png")
    shutil.copy(root / "one.png", root / "sub" / "copy-of-one.png")
    text_image(root / "sub" / "two.png", "Another line about invoices and receipts today")
    blank_image(root / "photo.jpg", "grey")
    (root / "broken.png").write_bytes(b"nope")
    (root / "notes.txt").write_text(SENTENCE, encoding="utf-8")
    text_image(root / ".git" / "hidden.png")
    return root, tmp_path / "out"


def test_run_reads_each_distinct_image_once_and_records_every_path(tree):
    root, out = tree
    s = ob.run([str(root)], out, workers=2, log=quiet)
    assert s["seen"] == 5                                  # the .txt and the .git image are not counted
    assert (s["read"], s["duplicate_copy"], s["text"], s["none"], s["unsupported"]) == (4, 1, 2, 1, 1)
    res, pth = rows(out / "results.jsonl"), rows(out / "paths.jsonl")
    assert len(res) == 4 and len({r["sha256"] for r in res}) == 4
    assert sorted(p["rel_path"] for p in pth) == ["broken.png", "one.png", "photo.jpg", "sub/copy-of-one.png", "sub/two.png"]
    by_path = {p["rel_path"]: p["sha256"] for p in pth}
    assert by_path["one.png"] == by_path["sub/copy-of-one.png"]
    assert all(r["engine"].startswith("tesseract 5") and r["bytes"] > 0 for r in res)


def test_text_is_only_under_out_and_never_in_the_results_rows(tree):
    root, out = tree
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    ob.run([str(root)], out, workers=2, log=quiet)
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()) == before
    raw = (out / "results.jsonl").read_text(encoding="utf-8") + (out / "paths.jsonl").read_text(encoding="utf-8")
    assert "ledger" not in raw and "invoices" not in raw
    assert all("_text" not in r and "text" not in r for r in rows(out / "results.jsonl"))
    texts = sorted(out.glob("text/*/*.txt"))
    assert len(texts) == 2                                 # the two text images; nothing for the blank or the broken
    one = [r for r in rows(out / "paths.jsonl") if r["rel_path"] == "one.png"][0]["sha256"]
    assert (out / "text" / one[:2] / f"{one}.txt").read_text(encoding="utf-8") == SENTENCE + "\n"


def test_a_second_run_reads_nothing_and_adds_no_rows(tree):
    root, out = tree
    ob.run([str(root)], out, workers=2, log=quiet)
    a, b = (out / "results.jsonl").read_text(encoding="utf-8"), (out / "paths.jsonl").read_text(encoding="utf-8")
    s = ob.run([str(root)], out, workers=2, log=quiet)
    assert s["read"] == 0 and s["already_done"] == 5 and s["unreadable"] == 0   # 5 files, 4 distinct images
    assert (out / "results.jsonl").read_text(encoding="utf-8") == a
    assert (out / "paths.jsonl").read_text(encoding="utf-8") == b


def test_a_new_image_after_a_first_run_is_the_only_one_read(tree):
    root, out = tree
    ob.run([str(root)], out, workers=2, log=quiet)
    text_image(root / "three.png", "Completely different words appear on this page")
    s = ob.run([str(root)], out, workers=2, log=quiet)
    assert (s["read"], s["text"]) == (1, 1) and len(rows(out / "results.jsonl")) == 5


def test_stop_file_ends_the_run_before_anything_is_read(tree):
    root, out = tree
    out.mkdir()
    (out / "STOP").write_text("", encoding="utf-8")
    said = []
    s = ob.run([str(root)], out, workers=2, log=said.append)
    assert s["read"] == 0 and any("STOP" in x for x in said)


def test_dry_run_opens_nothing_and_writes_nothing(tree):
    root, out = tree
    s = ob.run([str(root)], out, dry_run=True, log=quiet)
    assert s["seen"] == 5 and s["would_read_at_most"] == 5 and not out.exists()


def test_cloud_only_and_oversize_files_are_counted_and_not_opened(tree, monkeypatch):
    root, out = tree
    monkeypatch.setattr(ob, "MAX_BYTES", 100)              # every drawn image is over this; broken.png is 4 bytes
    s = ob.run([str(root)], out, workers=2, log=quiet)
    assert s["too_big"] == 4 and s["read"] == 1 and s["unsupported"] == 1
    monkeypatch.setattr(ob, "CLOUD_ONLY", 0x20)            # the archive bit, which every new file here carries
    out2 = out.with_name("out2")
    s = ob.run([str(root)], out2, workers=2, log=quiet)
    assert s["cloud_only"] == 5 and s["read"] == 0
    assert rows(out2 / "paths.jsonl") == [] and rows(out2 / "results.jsonl") == []


def test_retry_reads_a_class_again_and_the_last_row_wins(tree):
    root, out = tree
    ob.run([str(root)], out, workers=2, log=quiet)
    broken = [p for p in rows(out / "paths.jsonl") if p["rel_path"] == "broken.png"][0]["sha256"]
    assert ob.latest(out / "results.jsonl")[broken]["class"] == "unsupported"
    s = ob.run([str(root)], out, workers=2, log=quiet, retry=("unsupported",))
    assert (s["read"], s["unsupported"], s["already_done"]) == (1, 1, 4)      # only that one is read again
    all_rows = rows(out / "results.jsonl")
    assert len(all_rows) == 5 and len(ob.latest(out / "results.jsonl")) == 4
    assert [r["sha256"] for r in all_rows].count(broken) == 2


def test_heic_is_read_when_the_opener_is_installed(tmp_path):
    pillow_heif = pytest.importorskip("pillow_heif")
    pillow_heif.register_heif_opener()
    im = Image.new("RGB", (1600, 300), "white")
    ImageDraw.Draw(im).text((40, 100), SENTENCE, fill="black", font=ImageFont.truetype("arial.ttf", 56))
    im.save(tmp_path / "shot.heic", quality=95)
    r = ob.read_image(str(tmp_path / "shot.heic"))
    assert r["class"] == "text" and r["words"] == 7
