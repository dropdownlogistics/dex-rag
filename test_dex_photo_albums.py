"""dex_photo_albums: albums are rows, a photo's albums are labels, and nothing here touches an image file.

Silas Reeve / DDL-3004 / 2026-10-10
"""
import json

import pytest

import dex_photo_albums as al


def test_one_naming_style():
    assert al.style("process/ModelScreens") == "process/model-screens"
    assert al.style("process/_loose") == "process/loose"
    assert al.style("process/Uncategorized") == "process/uncategorized"
    assert al.style("photos/2015") == "photos/2015"
    assert al.style(" PC Snips / Work_Laptop ") == "pc-snips/work-laptop"
    assert al.style("process/DDLAppPassword_files") == "process/ddlapp-password-files"
    assert al.style(al.style("process/ModelScreens")) == "process/model-screens"      # styling twice changes nothing
    assert al.title("process/model-screens") == "Process / Model screens"


def test_photo_ids_grow_until_every_one_is_different():
    assert al.id_length(["aaaaaaaaaa11", "bbbbbbbbbb22"]) == 10
    assert al.id_length(["aaaaaaaaaa11", "aaaaaaaaaa12", "bbbbbbbbbb22"]) == 12
    assert al.photo_id("0123456789abcdef", 10) == "P-0123456789"


def make(tmp_path):
    rows = [{"sha256": "a" * 10 + "01", "album": "process/ModelScreens"}, {"sha256": "b" * 10 + "02", "album": "process/ModelScreens"},
            {"sha256": "c" * 10 + "03", "album": "pc-snips"}, {"sha256": "d" * 10 + "04", "album": "process/_loose"}]
    (tmp_path / "index.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "x.png").write_bytes(b"an image")
    return tmp_path


def read(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]


def test_init_builds_albums_and_labels_in_the_one_style(tmp_path):
    lib = make(tmp_path)
    assert al.init(lib) == {"albums": 3, "photos": 4, "id_hex_digits": 10}
    albums = read(lib / "albums.jsonl")
    assert [(a["id"], a["origin"], a["made"]) for a in albums] == [
        ("pc-snips", ["pc-snips"], "first sort"), ("process/loose", ["process/_loose"], "first sort"),
        ("process/model-screens", ["process/ModelScreens"], "first sort")]
    labels = read(lib / "labels.jsonl")
    assert labels[0] == {"sha256": "a" * 10 + "01", "photo_id": "P-aaaaaaaaaa", "albums": ["process/model-screens"]}
    assert al.counts(lib) == [("pc-snips", "Pc snips", 1), ("process/loose", "Process / Loose", 1),
                              ("process/model-screens", "Process / Model screens", 2)]


def test_init_refuses_to_overwrite_edited_albums(tmp_path):
    lib = make(tmp_path)
    al.init(lib)
    al.put(lib, "P-cccccccccc", "process/loose")
    before = (lib / "labels.jsonl").read_text(encoding="utf-8")
    with pytest.raises(al.AlbumError, match="already exists"):
        al.init(lib)
    assert (lib / "labels.jsonl").read_text(encoding="utf-8") == before


def test_adding_an_album_is_a_row_not_a_folder(tmp_path):
    lib = make(tmp_path)
    al.init(lib)
    before = sorted(p.relative_to(lib).as_posix() for p in lib.rglob("*"))
    row = al.add(lib, "trips/kansas-city", note="2024")
    assert (row["id"], row["title"], row["note"], row["made"]) == ("trips/kansas-city", "Trips / Kansas city", "2024", "added")
    assert sorted(p.relative_to(lib).as_posix() for p in lib.rglob("*")) == before        # no new file or folder
    assert ("trips/kansas-city", "Trips / Kansas city", 0) in al.counts(lib)
    with pytest.raises(al.AlbumError, match="already exists"):
        al.add(lib, "trips/kansas-city")
    with pytest.raises(al.AlbumError, match="did you mean 'trips/kansas-city-2'"):
        al.add(lib, "Trips/Kansas City 2")


def test_put_moves_or_adds_a_label_and_never_touches_the_image(tmp_path):
    lib = make(tmp_path)
    al.init(lib)
    al.add(lib, "favourites")
    assert al.put(lib, "P-aaaaaaaaaa", "pc-snips")["albums"] == ["pc-snips"]                 # moved: one album
    assert al.put(lib, "P-aaaaaaaaaa", "favourites", also=True)["albums"] == ["favourites", "pc-snips"]
    assert al.put(lib, "b" * 10 + "02", "favourites", also=True)["albums"] == ["favourites", "process/model-screens"]   # by sha too
    assert dict((n, c) for n, _, c in al.counts(lib)) == {"pc-snips": 2, "process/loose": 1, "process/model-screens": 1, "favourites": 2}
    assert (lib / "images" / "x.png").read_bytes() == b"an image"
    with pytest.raises(al.AlbumError, match="no album"):
        al.put(lib, "P-aaaaaaaaaa", "nowhere")
    with pytest.raises(al.AlbumError, match="matches 0 photos"):
        al.put(lib, "P-zzzzzzzzzz", "favourites")
