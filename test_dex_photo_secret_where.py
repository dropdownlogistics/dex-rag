"""dex_photo_secret_where: boxes land on the words that matched, the text is rebuilt as the scan saw it, and no word is written.

Every "secret" here is made up for the test.  Silas Reeve / DDL-3004 / 2026-10-10
"""
import json

import dex_ocr_batch as ob
import dex_photo_secret_where as sw

FAKE_KEY = "sk-" + "TESTONLYnotarealkey0000"


def table(rows):
    """A Tesseract word table from (block, line, word, left, top, width, height, conf) rows."""
    d = {k: [] for k in ("text", "conf", "block_num", "par_num", "line_num", "left", "top", "width", "height")}
    for b, ln, w, l, t, wd, h, c in rows:
        for k, v in (("text", w), ("conf", c), ("block_num", b), ("par_num", 1), ("line_num", ln), ("left", l), ("top", t), ("width", wd), ("height", h)):
            d[k].append(v)
    return d


ROWS = [(1, 1, "", 0, 0, 1000, 500, -1),                        # a layout row, not a word
        (1, 1, "open", 100, 50, 80, 20, 91), (1, 1, "risk-register", 200, 50, 260, 20, 90),
        (1, 2, "token:", 100, 100, 100, 20, 88), (1, 2, FAKE_KEY, 220, 100, 500, 20, 80),
        (2, 1, "enter", 100, 300, 90, 20, 92), (2, 1, "one-time", 200, 300, 150, 22, 92), (2, 1, "code", 360, 302, 80, 20, 92)]


def test_text_is_rebuilt_exactly_as_the_first_reading_built_it():
    d = table(ROWS)
    text, words = sw.words_with_boxes(d)
    assert text == ob.lines_from_data(d)[0]
    assert [text[a:b] for a, b, *_ in words] == [r[2] for r in ROWS[1:]]


def test_boxes_cover_the_matched_words_and_only_those():
    text, words = sw.words_with_boxes(table(ROWS))
    boxes = sw.boxes_for(text, words, (1000, 500))
    by = {b["rule"]: b for b in boxes}
    assert sorted(by) == ["R1", "R2", "R3"]                      # the made-up key is also a mixed run; risk-register is nothing
    k = by["R2"]
    assert (k["x"], k["y"]) == (round(0.22 - sw.PAD, 4), round(0.2 - sw.PAD, 4))
    assert (k["w"], k["h"]) == (round(0.5 + 2 * sw.PAD, 4), round(0.04 + 2 * sw.PAD, 4))
    p = by["R1"]                                                 # "one-time code" is two words: one box round both
    assert abs(p["x"] - (0.2 - sw.PAD)) < 1e-4 and abs(p["w"] - (0.24 + 2 * sw.PAD)) < 1e-4
    assert abs(p["y"] - (0.6 - sw.PAD)) < 1e-4 and abs(p["h"] - (0.044 + 2 * sw.PAD)) < 1e-4
    assert all(set(b) == {"rule", "x", "y", "w", "h"} for b in boxes)


def test_boxes_stay_inside_the_picture():
    text, words = sw.words_with_boxes(table([(1, 1, FAKE_KEY, 0, 0, 1000, 500, 90)]))
    for b in sw.boxes_for(text, words, (1000, 500)):
        assert b["x"] >= 0 and b["y"] >= 0 and b["x"] + b["w"] <= 1.0001 and b["y"] + b["h"] <= 1.0001


def test_run_writes_a_row_per_flag_and_never_a_word(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    flags = [{"sha256": "aa01", "photo_id": "P-aa01", "rules": ["R2"], "strength": "strong", "flagged_at": "x"},
             {"sha256": "bb02", "photo_id": "P-bb02", "rules": ["R5", "R7"], "strength": "strong", "flagged_at": "x"},
             {"sha256": "cc03", "photo_id": "P-cc03", "rules": ["R3"], "strength": "medium", "flagged_at": "x"}]
    (lib / "review.jsonl").write_text("".join(json.dumps(f) + "\n" for f in flags), encoding="utf-8")
    (lib / "index.jsonl").write_text("".join(json.dumps({"sha256": f["sha256"], "file": f"images/{f['sha256']}.png"}) + "\n" for f in flags), encoding="utf-8")

    def fake(path):
        if "aa01" in path:
            text, words = sw.words_with_boxes(table(ROWS))
            return sw.boxes_for(text, words, (1000, 500))
        return [] if "bb02" in path else None

    stats = sw.run(lib, workers=1, locate=fake)
    assert stats == {"flagged": 3, "read_again": 2, "with_boxes": 1, "no_boxes": 1, "could_not_read": 1, "boxes": 3}
    written = (lib / "review-where.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(l) for l in written.splitlines()]
    assert [(r["photo_id"], r["read"], len(r["boxes"])) for r in rows] == [("P-aa01", True, 3), ("P-bb02", True, 0), ("P-cc03", False, 0)]
    for leak in (FAKE_KEY, "TESTONLY", "risk-register", "one-time", "token"):
        assert leak not in written, leak
    assert not (lib / "review-where.jsonl.part").exists()
