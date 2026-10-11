"""dex_photo_graph_export: no hidden photo, no words, no paths, and nothing that points at a hidden photo.

Silas Reeve / DDL-3004 / 2026-10-10
"""
import json

import dex_photo_graph_export as ge


def make(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    w = lambda name, rows: (lib / name).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    idx = lambda sha, **o: {"sha256": sha, "width": 4, "height": 3, "bytes": 10, "pile": "text", "bin": "ai-chat", "words": 9,
                            "was_at": ["secret-folder/Private Name.png"], "name": "Private Name.png", **o}
    w("index.jsonl", [idx("aaaaaaaaaa01"), idx("bbbbbbbbbb02"), idx("cccccccccc03", pile="low-confidence", words=2),
                      idx("dddddddddd04", bin="unsorted"), idx("eeeeeeeeee05")])
    w("labels.jsonl", [{"sha256": s, "photo_id": "P-" + s[:10], "albums": [a]} for s, a in
                       (("aaaaaaaaaa01", "process/systems"), ("bbbbbbbbbb02", "trips/kansas-city"), ("cccccccccc03", "photos/2015"),
                        ("dddddddddd04", "unorganized"))])                                    # eeee has no label
    w("facts.jsonl", [{"sha256": "aaaaaaaaaa01", "taken": "2015-03-08", "taken_source": "name", "place": {"lat": 1.5, "lon": 2.5},
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


def test_hidden_photos_are_left_out_entirely_and_nothing_points_at_one(tmp_path):
    rows, stats = ge.build(make(tmp_path))
    by = {r["photo_id"]: r for r in rows}
    assert sorted(by) == ["P-aaaaaaaaaa", "P-cccccccccc", "P-dddddddddd"]
    assert stats == {"exported": 3, "hidden_left_out": 1, "no_label": 1}
    text = json.dumps(rows)
    assert "bbbbbbbbbb" not in text and "kansas" not in text                  # the hidden photo, its id and its album
    assert by["P-aaaaaaaaaa"]["twin_of"] is None and by["P-dddddddddd"]["looks_like"] is None   # their keeper is hidden
    assert by["P-cccccccccc"]["looks_like"] == "P-aaaaaaaaaa"                 # a visible keeper is named by its photo id


def test_no_words_no_paths_no_sha(tmp_path):
    rows, _ = ge.build(make(tmp_path))
    text = json.dumps(rows)
    for leak in ("must never be exported", "secret-folder", "Private Name", "was_at", "excerpt", "sha256", "aaaaaaaaaa01"):
        assert leak not in text, leak
    assert set(rows[0]) == {"photo_id", "albums", "width", "height", "bytes", "pile", "has_text", "taken", "taken_source", "place",
                            "source", "in_graveyard", "twin_of", "looks_like", "kind_suggestion", "ids_found"}


def test_fields_say_what_they_know(tmp_path):
    by = {r["photo_id"]: r for r in ge.build(make(tmp_path))[0]}
    a, c, d = by["P-aaaaaaaaaa"], by["P-cccccccccc"], by["P-dddddddddd"]
    assert (a["taken"], a["taken_source"], a["place"], a["kind_suggestion"]) == ("2015-03-08", "name", {"lat": 1.5, "lon": 2.5}, "ai-chat")
    assert (c["taken"], c["taken_source"]) == (None, "none")                  # no date means source none, whatever the facts row said
    assert (c["pile"], c["has_text"], c["kind_suggestion"]) == ("no-text", False, None)        # two stray words is no text
    assert (d["in_graveyard"], d["kind_suggestion"], d["taken_source"]) == (True, None, "none")   # catch-all kind is no kind
    assert all(r["ids_found"] == [] for r in by.values())
