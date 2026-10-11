"""dex_photo_facts: a taken-date says where it came from, and the file's modified time is never one.

Silas Reeve / DDL-3004 / 2026-10-10
"""
import json
import os
import time

from PIL import Image

import dex_photo_facts as pf


def test_dates_from_file_names_only_and_only_plausible_ones():
    assert pf.date_from_names(["google-takeout/Chat/File-2015-03-08(5).jpg"], 2026) == "2015-03-08"
    assert pf.date_from_names(["a/IMG_20140719_101500.jpg", "b/2016-01-02 copy.jpg"], 2026) == "2014-07-19T10:15:00"   # earliest wins
    assert pf.date_from_names(["s/Screenshot 2026-10-10 220641.png"], 2026) == "2026-10-10T22:06:41"
    assert pf.date_from_names(["s/2026-09-25 14 03 22 - Some Chat - IMG_0001.png"], 2026) == "2026-09-25T14:03:22"
    assert pf.date_from_names(["a/2015-03-08.jpg", "b/2015-03-08 09.30.00.jpg", "c/2015-03-08 08.00.00.jpg"], 2026) == "2015-03-08T08:00:00"   # a time beats none
    assert pf.date_from_names(["x/2015-03-08 256199.jpg", "x/2015-03-08 1015001.jpg", "x/2015-03-08 (3).jpg"], 2026) == "2015-03-08"   # not a clock time
    assert pf.date_from_names(["icloud/_catchall/2026-09-25/shot.png"], 2026) is None      # a folder date is when it was filed
    assert pf.date_from_names(["x/File-2031-01-01.jpg", "x/1985-01-01.jpg", "x/2015-13-40.jpg"], 2026) is None
    assert pf.date_from_names(["x/IMG_1234567890123.jpg"], 2026) is None                   # digits inside a longer number
    assert pf.date_from_names([], 2026) is None


def test_exif_dates_are_parsed_and_junk_is_refused():
    assert pf.exif_taken("2015:03:08 14:07:11", 2026) == "2015-03-08T14:07:11"
    for junk in ("0000:00:00 00:00:00", "", None, "2031:01:01 00:00:00", "1970:01:01 00:00:00", "not a date", "2015:13:01 00:00:00"):
        assert pf.exif_taken(junk, 2026) is None


def test_gps_to_decimal_with_hemispheres_and_refusals():
    north_west = {1: "N", 2: (39.0, 5.0, 59.0), 3: "W", 4: (94.0, 34.0, 42.0)}
    assert pf.gps_decimal(north_west) == {"lat": 39.099722, "lon": -94.578333}
    assert pf.gps_decimal({1: "S", 2: (33.0, 52.0, 0.0), 3: "E", 4: (151.0, 12.0, 0.0)}) == {"lat": -33.866667, "lon": 151.2}
    assert pf.gps_decimal({1: "N", 2: (0.0, 0.0, 0.0), 3: "E", 4: (0.0, 0.0, 0.0)}) is None    # null island is no place
    assert pf.gps_decimal({1: "N", 2: (39.0, 5.0)}) is None
    assert pf.gps_decimal({}) is None


def test_excerpt_needs_five_words():
    assert pf.excerpt_of("one two three four") is None
    assert pf.excerpt_of("  one two\nthree four five  ") == "one two three four five"
    assert pf.excerpt_of(" ".join(str(i) for i in range(40))) == " ".join(str(i) for i in range(20))
    assert pf.excerpt_of(None) is None


def make(tmp_path):
    lib, ocr = tmp_path / "lib", tmp_path / "ocr"
    (lib / "images" / "aa").mkdir(parents=True)
    (ocr / "text" / "aa").mkdir(parents=True)
    exif = Image.Exif()
    sub = exif.get_ifd(0x8769)
    sub[36867] = "2014:07:19 10:15:00"
    exif[0x8769] = sub
    Image.new("RGB", (40, 30), (200, 10, 10)).save(lib / "images" / "aa" / "aa1.jpg", exif=exif)
    Image.new("RGB", (40, 30), (10, 10, 200)).save(lib / "images" / "aa" / "aa2.png")
    Image.new("RGB", (40, 30), (10, 200, 10)).save(lib / "images" / "aa" / "aa3.png")
    (lib / "images" / "aa" / "aa4.png").write_bytes(b"nope")
    old = time.time() - 5 * 365 * 86400
    for n in ("aa1.jpg", "aa2.png", "aa3.png"):
        os.utime(lib / "images" / "aa" / n, (old, old))                          # a modified time that must be ignored
    rows = [("aa1", ".jpg", ["cam/IMG_0001.jpg"], True, 9), ("aa2", ".png", ["chat/File-2015-03-08(5).png"], True, 3),
            ("aa3", ".png", ["shots/untitled.png"], False, 0), ("aa4", ".png", ["x/2016-05-05.png"], False, 0)]
    (lib / "index.jsonl").write_text("".join(json.dumps({"sha256": s, "file": f"images/aa/{s}{e}", "was_at": w, "has_text": t,
                                                          "words": n}) + "\n" for s, e, w, t, n in rows), encoding="utf-8")
    (ocr / "text" / "aa" / "aa1.txt").write_text("the quarterly ledger closes on friday morning\n", encoding="utf-8")
    (ocr / "text" / "aa" / "aa2.txt").write_text("ih oh\n", encoding="utf-8")
    return lib, ocr


def test_run_fills_each_fact_from_the_right_place(tmp_path):
    lib, ocr = make(tmp_path)
    s = pf.run(lib, ocr, workers=2, this_year=2026, log=lambda *a: None)
    f = {r["sha256"]: r for r in map(json.loads, (lib / "facts.jsonl").read_text(encoding="utf-8").splitlines())}
    assert (f["aa1"]["taken"], f["aa1"]["taken_source"]) == ("2014-07-19T10:15:00", "file")
    assert (f["aa2"]["taken"], f["aa2"]["taken_source"]) == ("2015-03-08", "name")
    assert (f["aa3"]["taken"], f["aa3"]["taken_source"]) == (None, "none")       # five years old by its file time: not used
    assert (f["aa4"]["taken"], f["aa4"]["taken_source"], f["aa4"]["error"]) == ("2016-05-05", "name", "UnidentifiedImageError")
    assert f["aa1"]["excerpt"] == "the quarterly ledger closes on friday morning" and f["aa2"]["excerpt"] is None
    assert f["aa2"]["placeholder"] == "#0a0ac8" and f["aa3"]["placeholder"] == "#0ac80a"
    assert all(r["source"] == "corpus" and r["hidden"] is False and r["place"] is None for r in f.values())
    assert (s["photos"], s["taken_from_file"], s["taken_from_name"], s["taken_from_none"], s["could_not_open"]) == (4, 1, 2, 1, 1)


def test_a_second_run_opens_nothing_and_keeps_a_hidden_mark(tmp_path):
    lib, ocr = make(tmp_path)
    pf.run(lib, ocr, workers=2, this_year=2026, log=lambda *a: None)
    rows = [json.loads(x) for x in (lib / "facts.jsonl").read_text(encoding="utf-8").splitlines()]
    rows[2]["hidden"] = True                                                       # the Operator hid one in the app
    (lib / "facts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    s = pf.run(lib, ocr, workers=2, this_year=2026, log=lambda *a: None)
    again = {r["sha256"]: r for r in map(json.loads, (lib / "facts.jsonl").read_text(encoding="utf-8").splitlines())}
    assert s["opened_this_run"] == 0 and again["aa3"]["hidden"] is True
    assert (again["aa1"]["taken"], again["aa2"]["taken"], again["aa2"]["taken_source"]) == ("2014-07-19T10:15:00", "2015-03-08", "name")
