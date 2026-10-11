"""dex_photo_word_boxes: the right photos are read, hidden ones never, a done one is not redone, and it stops on time.

Silas Reeve / DDL-3004 / 2026-10-10
"""
import json
from datetime import datetime

import dex_photo_word_boxes as wb


def make(tmp_path):
    lib, ocr = tmp_path / "lib", tmp_path / "ocr"
    lib.mkdir()
    rows = [{"sha256": "aa01", "file": "images/aa01.png", "pile": "text", "words": 40},
            {"sha256": "bb02", "file": "images/bb02.png", "pile": "no-text", "words": 0},
            {"sha256": "cc03", "file": "images/cc03.png", "pile": "low-confidence", "words": 3},      # a stray few words: no text
            {"sha256": "dd04", "file": "images/dd04.png", "pile": "text", "words": 12},               # hidden
            {"sha256": "ee05", "file": "images/ee05.png", "pile": "low-confidence", "words": 9},
            {"sha256": "ff06", "file": "images/ff06.png", "pile": "text", "words": 30},               # hidden then unhidden
            {"sha256": "ab07", "file": "images/ab07.png", "pile": "text", "words": 30}]               # already done
    (lib / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (lib / "app-state.jsonl").write_text("".join(json.dumps(r) + "\n" for r in [
        {"sha256": "dd04", "hidden": True}, {"sha256": "ff06", "hidden": True}, {"sha256": "ff06", "hidden": False},
        {"sha256": "aa01", "graveyard": True}]), encoding="utf-8")
    done = ocr / "boxes" / "ab" / "ab07.json"
    done.parent.mkdir(parents=True)
    done.write_text("{}", encoding="utf-8")
    return lib, ocr


def test_jobs_are_photos_with_words_that_are_not_hidden_and_not_done(tmp_path):
    lib, ocr = make(tmp_path)
    todo, n = wb.jobs(lib, ocr)
    assert [src.replace("\\", "/").rsplit("/", 1)[1] for src, _ in todo] == ["aa01.png", "ee05.png", "ff06.png"]   # graveyard is not hidden
    assert n == {"photos": 7, "no_words": 2, "hidden_skipped": 1, "already_done": 1, "to_do": 3}
    assert all(dst.replace("\\", "/").endswith(f"boxes/{name[:2]}/{name}.json") for (_, dst), name in zip(todo, ["aa01", "ee05", "ff06"]))


def test_words_of_drops_layout_rows_and_keeps_text_confidence_and_box():
    d = {"text": ["", "Hello", " ", "DDL-3004"], "conf": [-1, 91.26, 95, "88.5"], "left": [0, 10, 0, 70], "top": [0, 5, 0, 6],
         "width": [100, 50, 0, 90], "height": [40, 12, 0, 13]}
    assert wb.words_of(d) == [["Hello", 91.3, 10, 5, 50, 12], ["DDL-3004", 88.5, 70, 6, 90, 13]]


def test_stop_time_is_the_next_such_time():
    now = datetime(2026, 10, 10, 22, 30)
    assert wb.stop_time("03:30", now) == datetime(2026, 10, 11, 3, 30)        # tonight's 03:30 is tomorrow
    assert wb.stop_time("23:00", now) == datetime(2026, 10, 10, 23, 0)
    assert wb.stop_time("22:30", now) == datetime(2026, 10, 11, 22, 30)       # exactly now means the next one
    assert wb.stop_time(None, now) is None


def fake_work(job):
    return "unreadable" if "ee05" in job[0] else "read"


class Clock:
    def __init__(self, times):
        self.times = list(times)

    def __call__(self):
        return self.times.pop(0) if len(self.times) > 1 else self.times[0]


def test_run_counts_what_it_did(tmp_path):
    lib, ocr = make(tmp_path)
    lines = []
    out = wb.run(lib, ocr, workers=1, batch=2, log=lines.append, work=fake_work)
    assert (out["read"], out["unreadable"], out["left"], out["stopped_for_time"]) == (2, 1, 0, False)
    assert lines[-1].startswith("DONE ")


def test_run_stops_at_the_time_and_says_what_is_left(tmp_path):
    lib, ocr = make(tmp_path)
    early, late = datetime(2026, 10, 10, 23, 0), datetime(2026, 10, 11, 3, 31)
    # clock: once for the stop time, once before batch 1 (early), then late for everything after
    out = wb.run(lib, ocr, workers=1, batch=2, until="03:30", log=lambda s: None, work=fake_work, clock=Clock([early, early, late]))
    assert out["stopped_for_time"] is True
    assert out["read"] + out["unreadable"] == 2 and out["left"] == 1          # one batch of two ran, one photo left
