"""dex_photo_graph_export: Lena's row format; no hidden photo, no words, no paths, and nothing that points at a hidden photo.

Silas Reeve / DDL-3004 / 2026-10-10
"""
import json
import re

import dex_photo_graph_export as ge


def make(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    w = lambda name, rows: (lib / name).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    idx = lambda sha, **o: {"sha256": sha, "width": 4, "height": 3, "bytes": 10, "pile": "text", "bin": "ai-chat", "words": 9,
                            "confidence": 91.5, "phone": True, "modified": "2026-03-02T14:07:11Z",
                            "was_at": ["secret-folder/Private Name.png"], "name": "Private Name.png", **o}
    w("index.jsonl", [idx("aaaaaaaaaa01"), idx("bbbbbbbbbb02"), idx("cccccccccc03", pile="low-confidence", words=2, phone=False),
                      idx("dddddddddd04", bin="unsorted"), idx("eeeeeeeeee05")])
    w("labels.jsonl", [{"sha256": s, "photo_id": "P-" + s[:10], "albums": a} for s, a in
                       (("aaaaaaaaaa01", ["process/systems", "photos/2015"]), ("bbbbbbbbbb02", ["trips/kansas-city"]), ("cccccccccc03", ["photos/2015"]),
                        ("dddddddddd04", ["unorganized"]))])                                  # eeee has no label
    w("albums.jsonl", [{"id": "process/systems", "title": "Process / Systems", "note": "n"}, {"id": "photos/2015", "title": "2015", "note": ""},
                       {"id": "trips/kansas-city", "title": "Kansas City", "note": ""}, {"id": "empty", "title": "Empty", "note": ""}])
    w("facts.jsonl", [{"sha256": "aaaaaaaaaa01", "taken": "2015-03-08", "taken_source": "name", "place": {"lat": 7.25, "lon": 8.75},
                       "excerpt": "words that must never be exported", "source": "corpus"},
                      {"sha256": "cccccccccc03", "taken": None, "taken_source": "name", "place": None, "excerpt": None, "source": "corpus"}])
    w("copies.jsonl", [{"sha256": "aaaaaaaaaa01", "keeper": "bbbbbbbbbb02", "why": "same-words"},
                       {"sha256": "cccccccccc03", "keeper": "aaaaaaaaaa01", "why": "looks-same"},
                       {"sha256": "dddddddddd04", "keeper": "bbbbbbbbbb02", "why": "looks-same"}])
    w("app-state.jsonl", [{"sha256": "bbbbbbbbbb02", "photo_id": "P-bbbbbbbbbb", "at": "x", "hidden": True},
                          {"sha256": "cccccccccc03", "photo_id": "P-cccccccccc", "at": "x", "hidden": True},
                          {"sha256": "cccccccccc03", "photo_id": "P-cccccccccc", "at": "x", "hidden": False},     # unhidden again
                          {"sha256": "dddddddddd04", "photo_id": "P-dddddddddd", "at": "x", "graveyard": True}])
    return lib


def split(rows):
    return [r for r in rows if r["row"] == "album"], {r["photo_id"]: r for r in rows if r["row"] == "photo"}


def test_hidden_photos_are_left_out_entirely_and_nothing_points_at_one(tmp_path):
    rows, stats = ge.build(make(tmp_path))
    albums, by = split(rows)
    assert sorted(by) == ["P-aaaaaaaaaa", "P-cccccccccc", "P-dddddddddd"]
    assert stats == {"photos": 3, "hidden_left_out": 1, "no_label": 1, "albums": 5}
    photo_text = json.dumps(list(by.values()))
    assert "bbbbbbbbbb" not in photo_text and "kansas" not in photo_text       # the hidden photo, its id and its album
    assert by["P-aaaaaaaaaa"]["twin_of"] is None and by["P-dddddddddd"]["looks_like"] is None   # their keeper is hidden
    assert by["P-cccccccccc"]["looks_like"] == "P-aaaaaaaaaa"                 # a visible keeper is named by its photo id
    assert all(r["hidden"] is False for r in by.values())                     # no exported row is ever hidden
    assert next(a for a in albums if a["id"] == "trips/kansas-city")["count"] == 0    # its only photo is hidden: the album shows none


def test_no_words_no_paths_no_sha_no_coordinates(tmp_path):
    rows, _ = ge.build(make(tmp_path))
    text = json.dumps(rows)
    for leak in ("must never be exported", "secret-folder", "Private Name", "was_at", "excerpt", "sha256", "aaaaaaaaaa01", '"text":', '"lat"', "7.25", "8.75", '"place"'):
        assert leak not in text, leak
    _, by = split(rows)
    assert set(by["P-aaaaaaaaaa"]) == {"row", "photo_id", "albums", "pile", "kind", "has_text", "words", "confidence", "width", "height", "bytes",
                                       "modified", "taken", "date_source", "from_phone", "twin_of", "looks_like", "hidden", "ids_found", "about",
                                       "in_graveyard", "has_place"}


def test_rows_meet_the_reader_s_required_fields(tmp_path):
    rows, _ = ge.build(make(tmp_path))
    albums, by = split(rows)
    assert rows[:len(albums)] == albums                                        # album rows come first
    for r in by.values():
        assert re.fullmatch(r"P-[0-9a-f]{10}", r["photo_id"]) and isinstance(r["albums"], list)
    assert [(a["id"], a["title"], a["count"], a["note"]) for a in albums] == [
        ("empty", "Empty", 0, ""), ("photos/2015", "2015", 2, ""), ("process/systems", "Process / Systems", 1, "n"),
        ("trips/kansas-city", "Kansas City", 0, ""), ("unorganized", "unorganized", 1, "")]   # an album only the labels know still gets a row


def test_fields_say_what_they_know(tmp_path):
    _, by = split(ge.build(make(tmp_path))[0])
    a, c, d = by["P-aaaaaaaaaa"], by["P-cccccccccc"], by["P-dddddddddd"]
    assert (a["taken"], a["date_source"], a["has_place"], a["kind"], a["from_phone"]) == ("2015-03-08", "name", True, "ai-chat", True)
    assert (a["words"], a["confidence"], a["modified"]) == (9, 91.5, "2026-03-02T14:07:11Z")
    assert (c["taken"], c["date_source"]) == (None, "none")                   # no date means source none, whatever the facts row said
    assert (c["pile"], c["has_text"], c["kind"], c["words"], c["confidence"]) == ("no-text", False, None, 0, None)   # two stray words is no text
    assert (d["in_graveyard"], d["kind"], d["date_source"], d["has_place"]) == (True, None, "none", False)   # catch-all kind is no kind
    assert all(r["ids_found"] == [] and r["about"] == [] for r in by.values())
