"""dex_ocr_sort: a bin needs two distinct signals, ties go to the first bin listed, and every score is kept.

Silas Reeve / DDL-3004 / 2026-10-10
"""
import json

import dex_ocr_sort as so


def test_two_distinct_signals_make_a_bin_and_one_does_not():
    assert so.sort_text("Open the workbook and fix the formula")[0] == "spreadsheet"
    assert so.sort_text("the formula for a good life")[0] == "unsorted"
    assert so.sort_text("formula formula formula")[0] == "unsorted"        # one signal three times is one signal


def test_signals_match_whole_words_only():
    assert so.sort_text("important definitions were returned")[1] == {}        # not import, def, return
    assert so.sort_text("def run(): return 1  # import os")[0] == "code-terminal"


def test_case_and_line_breaks_do_not_matter():
    b, scores, _ = so.sort_text("USAGE\nLIMITS\n\nContext   Window 62% used")
    assert b == "ai-usage-meter" and scores["ai-usage-meter"] == 2


def test_the_higher_score_wins_and_all_scores_are_kept():
    b, scores, _ = so.sort_text("ChatGPT wrote a vlookup formula in Excel for the pivot")
    assert b == "spreadsheet" and scores == {"ai-chat": 1, "spreadsheet": 4}


def test_a_tie_goes_to_the_bin_listed_first():
    b, scores, _ = so.sort_text("claude and chatgpt on linkedin and reddit")
    assert scores == {"ai-chat": 2, "social": 2} and b == "ai-chat"


def test_phone_is_a_flag_not_a_bin():
    b, scores, phone = so.sort_text("9:41 T-Mobile LTE")
    assert (b, scores, phone) == ("unsorted", {}, True)
    assert so.sort_text("no carrier words here")[2] is False


def test_pile_names():
    assert [so.pile_of(c) for c in ("text", "low", "none", "unsupported", "unreadable")] == \
        ["text", "low-confidence", "no-text", "not-opened", "not-opened"]


def make(tmp_path):
    o = tmp_path / "ocr"
    (o / "text" / "aa").mkdir(parents=True)
    res = [{"sha256": "aa1", "class": "unsupported", "words": 0, "confidence": 0.0},
           {"sha256": "aa1", "class": "text", "words": 9, "confidence": 91.0},      # retried: the last row counts
           {"sha256": "aa2", "class": "text", "words": 5, "confidence": 80.0},      # its text file is missing
           {"sha256": "bb1", "class": "none", "words": 0, "confidence": 0.0},
           {"sha256": "cc1", "class": "low", "words": 3, "confidence": 20.0}]
    (o / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in res), encoding="utf-8")
    paths = [{"root": "r", "rel_path": "a/first.png", "sha256": "aa1"}, {"root": "r", "rel_path": "b/copy.png", "sha256": "aa1"},
             {"root": "r", "rel_path": "a/two.png", "sha256": "aa2"}, {"root": "r", "rel_path": "x.png", "sha256": None},
             {"root": "r", "rel_path": "p.jpg", "sha256": "bb1"}, {"root": "r", "rel_path": "l.jpg", "sha256": "cc1"}]
    (o / "paths.jsonl").write_text("".join(json.dumps(r) + "\n" for r in paths), encoding="utf-8")
    (o / "text" / "aa" / "aa1.txt").write_text("Usage limits\nContext window\nT-Mobile LTE\n", encoding="utf-8")
    return o


def test_run_writes_one_row_per_distinct_image_with_the_last_result(tmp_path):
    o = make(tmp_path)
    rows = {r["sha256"]: r for r in so.run(o)}
    assert len(rows) == 4
    assert rows["aa1"] == {"sha256": "aa1", "pile": "text", "bin": "ai-usage-meter", "scores": {"ai-usage-meter": 2},
                           "phone": True, "words": 9, "confidence": 91.0, "copies": 2, "twin_of": None}
    assert rows["aa2"]["bin"] == "text-file-missing"
    assert (rows["bb1"]["pile"], rows["bb1"]["bin"]) == ("no-text", None)
    assert (rows["cc1"]["pile"], rows["cc1"]["bin"]) == ("low-confidence", None)
    on_disk = [json.loads(x) for x in (o / "bins.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sorted(r["sha256"] for r in on_disk) == ["aa1", "aa2", "bb1", "cc1"]


def test_report_has_counts_and_paths_but_no_image_text(tmp_path):
    o = make(tmp_path)
    so.run(o)
    rep = (o / "SORT-REPORT.md").read_text(encoding="utf-8")
    assert "Distinct images: 4" in rep and "| ai-usage-meter | 1 | 1 | 9 |" in rep
    assert "`a/first.png`" in rep and "b/copy.png" not in rep
    assert "1 images are classed text but their text file is missing" in rep
    assert "62%" not in rep and "Context window" not in rep
    assert "| `a` | 2 | 2 | 0 | 0 | 0 | 0 | 0 |" in rep           # aa1 (binned) and aa2 (file missing): neither is "unsorted"
    assert "| `(top)` | 2 | 0 | 0 | 1 | 1 | 0 | 0 |" in rep
    assert "Files seen: 5. Distinct images (identical bytes counted once): 4. Exact copies: 1." in rep


def test_set_aside_needs_every_copy_under_the_folder():
    assert so.set_aside(["onedrive/Music/a/cover.jpg", "onedrive/Music/b/cover.jpg"]) == "album-art"
    assert so.set_aside(["onedrive/Music/a/cover.jpg", "icloud/Documents/shot.jpg"]) is None
    assert so.set_aside(["onedrive/Musical/notes.png"]) is None
    assert so.set_aside([]) is None


def test_text_key_ignores_case_spacing_and_punctuation_but_not_words_or_order():
    assert so.text_key("Usage  Limits:\n62% used!") == so.text_key("usage limits 62 used")
    assert so.text_key("usage limits") != so.text_key("limits usage")
    assert so.text_key("usage limits") != so.text_key("usage limit")


def test_album_art_is_set_aside_and_text_twins_are_marked_not_removed(tmp_path):
    o = tmp_path / "ocr"
    (o / "text" / "aa").mkdir(parents=True)
    res = [{"sha256": "aa3", "class": "text", "words": 4, "confidence": 90.0},
           {"sha256": "aa1", "class": "text", "words": 4, "confidence": 90.0},
           {"sha256": "aa2", "class": "text", "words": 4, "confidence": 90.0},
           {"sha256": "aa9", "class": "text", "words": 4, "confidence": 90.0},
           {"sha256": "bb1", "class": "none", "words": 0, "confidence": 0.0}]
    (o / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in res), encoding="utf-8")
    paths = [{"root": "r", "rel_path": "shots/1.png", "sha256": "aa1"}, {"root": "r", "rel_path": "shots/2.png", "sha256": "aa2"},
             {"root": "r", "rel_path": "shots/3.png", "sha256": "aa3"},
             {"root": "r", "rel_path": "onedrive/Music/x/cover.png", "sha256": "aa9"},
             {"root": "r", "rel_path": "onedrive/Music/x/art.jpg", "sha256": "bb1"}]
    (o / "paths.jsonl").write_text("".join(json.dumps(r) + "\n" for r in paths), encoding="utf-8")
    for sha, t in (("aa1", "Usage limits\nContext window"), ("aa2", "different words entirely here"),
                   ("aa3", "USAGE LIMITS - context   window."), ("aa9", "Usage limits\nContext window")):
        (o / "text" / "aa" / f"{sha}.txt").write_text(t + "\n", encoding="utf-8")
    rows = {r["sha256"]: r for r in so.run(o)}
    assert len(rows) == 5                                            # nothing dropped
    assert (rows["aa1"]["twin_of"], rows["aa2"]["twin_of"], rows["aa3"]["twin_of"]) == (None, None, "aa1")
    assert (rows["aa9"]["pile"], rows["aa9"]["bin"], rows["aa9"]["twin_of"]) == ("set-aside", "album-art", None)
    assert (rows["bb1"]["pile"], rows["bb1"]["bin"]) == ("set-aside", "album-art")
    rep = (o / "SORT-REPORT.md").read_text(encoding="utf-8")
    assert "Text twins: 1 of the 3 text images" in rep and "| set-aside | 2 |" in rep
