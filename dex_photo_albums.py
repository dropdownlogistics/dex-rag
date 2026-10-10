"""
dex_photo_albums.py -- the album index for the photo library: albums are lenses, not folders.

Operator, 2026-10-10: "the albums are the lenses". Every photo is stored once (dex_photo_library.py).
An album is a row in albums.jsonl; a photo's albums are a row in labels.jsonl. Putting a photo in
an album, or in two, changes a label and never copies or moves a file.

    <library>/albums.jsonl   one row per album: id, name, title, note, origin (the old folder label)
    <library>/labels.jsonl   one row per photo: sha256, photo_id, albums [album ids]
    <library>/index.jsonl    (read only here) the copy record written by dex_photo_library.py

Album names are one style: lower case, words joined by hyphens, "/" between a group and its
album (process/model-screens). Photo ids are "P-" plus the first hex digits of the photo's
content hash, as many as it takes for every id in the library to be different (at least 10).

`init` builds both files from the index's first-proposal labels. It refuses to overwrite an
existing labels.jsonl: once the Operator has edited albums, those edits are the record.

    python dex_photo_albums.py --library D:\\DDL_Corpus\\library init
    python dex_photo_albums.py --library D:\\DDL_Corpus\\library list
    python dex_photo_albums.py --library D:\\DDL_Corpus\\library add "trips/kansas-city" --title "Kansas City"
"""
import argparse
import collections
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

MIN_ID_HEX = 10
NAME_OK = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*(/[a-z0-9]+(-[a-z0-9]+)*)*$")


class AlbumError(ValueError):
    pass


def style(label):
    """One naming style for an album label: 'process/ModelScreens' -> 'process/model-screens'. Pure."""
    parts = []
    for part in label.strip().strip("/").split("/"):
        p = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", part)          # ModelScreens -> Model-Screens
        p = re.sub(r"[^A-Za-z0-9]+", "-", p).strip("-").lower()
        if p:
            parts.append(p)
    return "/".join(parts)


def title(name):
    return " / ".join(w.replace("-", " ").capitalize() for w in name.split("/"))


def id_length(shas, minimum=MIN_ID_HEX):
    """The fewest hex digits (at least `minimum`) at which every sha in the library has its own prefix."""
    n = minimum
    while len({s[:n] for s in shas}) != len(set(shas)):
        n += 1
    return n


def photo_id(sha, n=MIN_ID_HEX):
    return f"P-{sha[:n]}"


def _rows(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def _write(path, rows):
    tmp = Path(str(path) + ".part")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(path)


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def init(library):
    library = Path(library)
    if (library / "labels.jsonl").exists():
        raise AlbumError("labels.jsonl already exists: it holds the albums as edited, and init would overwrite them")
    index = _rows(library / "index.jsonl")
    n = id_length([r["sha256"] for r in index])
    origins = collections.defaultdict(set)
    labels = []
    for r in index:
        name = style(r["album"])
        origins[name].add(r["album"])
        labels.append({"sha256": r["sha256"], "photo_id": photo_id(r["sha256"], n), "albums": [name]})
    albums = [{"id": name, "name": name, "title": title(name), "note": "", "origin": sorted(o),
               "made": "first sort", "at": _now()} for name, o in sorted(origins.items())]
    _write(library / "albums.jsonl", albums)
    _write(library / "labels.jsonl", labels)
    return {"albums": len(albums), "photos": len(labels), "id_hex_digits": n}


def add(library, name, title_text="", note=""):
    library = Path(library)
    name = name.strip()
    if not NAME_OK.match(name):
        raise AlbumError(f"album name {name!r} is not in the one style (like process/model-screens); "
                         f"did you mean {style(name)!r}?")
    albums = _rows(library / "albums.jsonl")
    if any(a["id"] == name for a in albums):
        raise AlbumError(f"album {name!r} already exists")
    row = {"id": name, "name": name, "title": title_text or title(name), "note": note, "origin": [],
           "made": "added", "at": _now()}
    _write(library / "albums.jsonl", albums + [row])
    return row


def put(library, photo, album, also=False):
    """Put a photo (by photo id or sha256) in an album. also=True adds the album; False makes it the only one."""
    library = Path(library)
    if not any(a["id"] == album for a in _rows(library / "albums.jsonl")):
        raise AlbumError(f"no album {album!r}; add it first")
    labels = _rows(library / "labels.jsonl")
    hit = [r for r in labels if photo in (r["photo_id"], r["sha256"])]
    if len(hit) != 1:
        raise AlbumError(f"{photo!r} matches {len(hit)} photos, expected 1")
    hit[0]["albums"] = sorted(set(hit[0]["albums"]) | {album}) if also else [album]
    _write(library / "labels.jsonl", labels)
    return hit[0]


def counts(library):
    library = Path(library)
    c = collections.Counter()
    for r in _rows(library / "labels.jsonl"):
        c.update(r["albums"])
    return [(a["id"], a["title"], c.get(a["id"], 0)) for a in _rows(library / "albums.jsonl")]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", required=True, type=Path)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("list")
    a_add = sub.add_parser("add")
    a_add.add_argument("name")
    a_add.add_argument("--title", default="")
    a_add.add_argument("--note", default="")
    a = ap.parse_args()
    try:
        if a.cmd == "init":
            print(init(a.library))
        elif a.cmd == "add":
            print(add(a.library, a.name, a.title, a.note))
        for name, t, n in counts(a.library):
            print(f"  {n:>7,}  {name:<34} {t}")
    except AlbumError as e:
        sys.exit(f"REFUSED: {e}")


if __name__ == "__main__":
    main()
