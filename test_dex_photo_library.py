"""dex_photo_library: one verified copy of each image, sources untouched, albums as labels.

Silas Reeve / DDL-3004 / 2026-10-10
"""
import hashlib
import json

import dex_photo_library as pl

D = pl.DIRECT


def test_album_keeps_the_operators_folder_names():
    assert pl.album([D + "Systems/a.png"], "text") == "process/Systems"
    assert pl.album([D + "loose.png"], "text") == "process/_loose"
    assert pl.album(["icloud/Documents/02_Dex/03_iMazingExports/x/a.png", D + "ModelScreens/a.png"], "no-text") == "process/ModelScreens"


def test_album_for_the_other_sources():
    assert pl.album(["onedrive/Pictures/Screenshots/s.png"], "text") == "pc-snips"
    assert pl.album(["google-takeout/Takeout/Google Chat/Groups/g/i.jpg"], "no-text") == "chats"
    assert pl.album(["google-takeout/Takeout/Google Photos/Photos from 2014/i.jpg"], "no-text", "2026") == "photos/2014"
    assert pl.album(["icloud/Documents/01_Personal/i.jpg"], "no-text", "2019") == "photos/2019"
    assert pl.album(["icloud/Documents/01_Personal/i.jpg"], "no-text") == "photos/undated"
    assert pl.album(["icloud/Documents/02_Dex/03_iMazingExports/x/i.png"], "text") == "phone-screens"
    assert pl.album(["google-takeout/Takeout/Google Photos/Photos from 2014/i.jpg"], "text") == "unsorted"
    assert pl.album(["onedrive/Documents/report/fig.png"], "low-confidence") == "unsorted"


def test_best_home_prefers_the_deliberate_place_then_the_shorter_path():
    assert pl.best_home(["google-takeout/Takeout-20230506T150450Z/a.jpg", "google-takeout/Takeout/a.jpg"]) == "google-takeout/Takeout/a.jpg"
    assert pl.best_home(["icloud/Documents/x/deep/a.png", "icloud/Documents/a.png"]) == "icloud/Documents/a.png"
    assert pl.best_home(["icloud/Documents/05_DirectIngest/a.png", "onedrive/Documents/a.png"]) == "onedrive/Documents/a.png"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def make(tmp_path):
    root, ocr, lib = tmp_path / "raw", tmp_path / "ocr", tmp_path / "lib"
    ocr.mkdir()
    files = {D + "Systems/one.png": b"image-one", "icloud/Documents/02_Dex/03_iMazingExports/e/one-copy.png": b"image-one",
             "onedrive/Pictures/Screenshots/two.PNG": b"image-two", "onedrive/Music/lib/cover.jpg": b"album-art",
             "google-takeout/Takeout/Google Photos/Photos from 2015/p.jpg": b"a-photo", "icloud/Documents/gone.png": b"gone",
             "icloud/Documents/changed.png": b"changed-before"}
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    S = {k: sha(v) for k, v in (("one", b"image-one"), ("two", b"image-two"), ("art", b"album-art"), ("photo", b"a-photo"),
                                 ("gone", b"gone"), ("chg", b"changed-before"), ("bad", b"unopened"))}
    with open(ocr / "paths.jsonl", "w", encoding="utf-8") as f:
        for rel, data in files.items():
            f.write(json.dumps({"root": str(root), "rel_path": rel, "sha256": sha(data)}) + "\n")
        f.write(json.dumps({"root": str(root), "rel_path": "x/unhashed.png", "sha256": None}) + "\n")
    bins = [(S["one"], "text", "spreadsheet"), (S["two"], "low-confidence", None), (S["art"], "set-aside", "album-art"),
            (S["photo"], "no-text", None), (S["gone"], "text", "unsorted"), (S["chg"], "text", "unsorted"), (S["bad"], "not-opened", None)]
    (ocr / "bins.jsonl").write_text("".join(json.dumps({"sha256": s, "pile": p, "bin": b, "words": 7, "confidence": 88.0,
                                                         "phone": False, "twin_of": None}) + "\n" for s, p, b in bins), encoding="utf-8")
    (ocr / "results.jsonl").write_text("".join(json.dumps({"sha256": s, "class": "text", "width": 10, "height": 20}) + "\n"
                                                for s, _, _ in bins), encoding="utf-8")
    (ocr / "looks-groups.jsonl").write_text(json.dumps({"keep_candidate": S["photo"], "look_alikes": [S["two"]]}) + "\n", encoding="utf-8")
    (root / "icloud/Documents/gone.png").unlink()
    (root / "icloud/Documents/changed.png").write_bytes(b"changed-after")
    return root, ocr, lib, S


def quiet(*a):
    pass


def test_run_copies_one_of_each_and_leaves_every_source_as_it_was(tmp_path):
    root, ocr, lib, S = make(tmp_path)
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    s = pl.run(ocr, str(root), lib, log=quiet)
    assert {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()} == before
    assert (s["distinct"], s["copied"], s["set_aside"], s["not_opened"], s["source_missing"], s["source_changed"]) == (7, 3, 1, 1, 1, 1)
    stored = sorted(p.relative_to(lib).as_posix() for p in (lib / "images").rglob("*") if p.is_file())
    assert stored == sorted(f"images/{S[k][:2]}/{S[k]}{e}" for k, e in (("one", ".png"), ("two", ".png"), ("photo", ".jpg")))
    for p in (lib / "images").rglob("*"):
        if p.is_file():
            assert sha(p.read_bytes()) == p.stem                 # the name is the content


def test_index_rows_say_what_and_where(tmp_path):
    root, ocr, lib, S = make(tmp_path)
    pl.run(ocr, str(root), lib, log=quiet)
    rows = {r["sha256"]: r for r in map(json.loads, (lib / "index.jsonl").read_text(encoding="utf-8").splitlines())}
    assert set(rows) == {S["one"], S["two"], S["photo"]}
    one = rows[S["one"]]
    assert (one["album"], one["name"], one["bin"], one["has_text"], one["bytes"]) == ("process/Systems", "one.png", "spreadsheet", True, 9)
    assert one["was_at"] == sorted([pl.DIRECT + "Systems/one.png", "icloud/Documents/02_Dex/03_iMazingExports/e/one-copy.png"])
    assert (rows[S["two"]]["album"], rows[S["two"]]["looks_like"]) == ("pc-snips", S["photo"])
    assert (rows[S["photo"]]["album"], rows[S["photo"]]["looks_like"], rows[S["photo"]]["has_text"]) == ("photos/2015", None, False)
    assert pl.albums(lib) == {"process/Systems": 1, "pc-snips": 1, "photos/2015": 1}


def test_a_second_run_copies_nothing_and_adds_no_rows(tmp_path):
    root, ocr, lib, S = make(tmp_path)
    pl.run(ocr, str(root), lib, log=quiet)
    idx = (lib / "index.jsonl").read_text(encoding="utf-8")
    s = pl.run(ocr, str(root), lib, log=quiet)
    assert (s["copied"], s["already_in_library"]) == (0, 3) and (lib / "index.jsonl").read_text(encoding="utf-8") == idx


def test_stop_file_and_limit(tmp_path):
    root, ocr, lib, S = make(tmp_path)
    assert pl.run(ocr, str(root), lib, limit=1, log=quiet)["copied"] == 1
    (lib / "STOP").write_text("", encoding="utf-8")
    said = []
    assert pl.run(ocr, str(root), lib, log=said.append)["copied"] == 0 and any("STOP" in x for x in said)


def test_a_copy_that_does_not_match_is_removed_and_counted(tmp_path, monkeypatch):
    root, ocr, lib, S = make(tmp_path)
    real = pl.shutil.copyfile

    def bad_copy(src, dst):
        real(src, dst)
        if "Systems" in str(src):                           # the DirectScreens copy of image one
            with open(dst, "ab") as f:
                f.write(b"!")
    monkeypatch.setattr(pl.shutil, "copyfile", bad_copy)
    s = pl.run(ocr, str(root), lib, log=quiet)
    assert (s["copy_failed"], s["copied"]) == (1, 2)
    assert not list((lib / "images").rglob("*.part")) and not (lib / "images" / S["one"][:2] / f"{S['one']}.png").exists()


def test_copies_file_lists_only_copies_whose_keeper_is_in_the_library(tmp_path):
    root, ocr, lib, S = make(tmp_path)
    pl.run(ocr, str(root), lib, log=quiet)                       # library holds one, two, photo
    bins = [json.loads(x) for x in (ocr / "bins.jsonl").read_text(encoding="utf-8").splitlines()]
    for b in bins:
        if b["sha256"] == S["one"]:
            b["twin_of"] = S["photo"]                            # a twin whose keeper is in the library
        if b["sha256"] == S["photo"]:
            b["twin_of"] = S["gone"]                             # a twin whose keeper never reached the library
    (ocr / "bins.jsonl").write_text("".join(json.dumps(b) + "\n" for b in bins), encoding="utf-8")
    counts = pl.write_copies(ocr, lib)                           # looks-groups: photo keeps, two looks like it
    rows = sorted((json.loads(x) for x in (lib / "copies.jsonl").read_text(encoding="utf-8").splitlines()), key=lambda r: r["why"])
    assert rows == [{"sha256": S["two"], "keeper": S["photo"], "why": "looks-same"},
                    {"sha256": S["one"], "keeper": S["photo"], "why": "same-words"}]
    assert counts == {"same-words": 1, "looks-same": 1}
    assert not (lib / "copies.jsonl.part").exists()
