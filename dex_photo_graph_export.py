"""
dex_photo_graph_export.py -- the photo rows the private work graph is built from. No words, no paths, no hidden photo.

For Lena Marsh / DDL-3005 (gaminglaptop-cowork/work/WORK-GRAPH/PHOTO_ALBUM_GRAPH_v0.1.md), on the
Operator's "yes to both" (2026-10-10): photos go into the PRIVATE graph only, and a photo marked hidden
stays out of everything, the private graph included.

The format is hers (her EDIT of 2026-10-10, "built, waiting on the export"). One JSON Lines file:
    {"row": "album", "id", "title", "count", "note"}        one per album; count is of the photos exported here
    {"row": "photo", "photo_id", "albums", "pile", "kind", "has_text", "words", "confidence", "width",
     "height", "bytes", "modified", "taken", "date_source", "from_phone", "twin_of", "looks_like",
     "hidden", "ids_found", "about", "in_graveyard", "has_place"}
Where my names differed from hers I use hers: `kind` (a guess from the words, null when there is none)
and `date_source` ("file" | "name" | "none": where `taken` came from; never the modified time).
Two fields are mine and optional to her: `in_graveyard` and `has_place`.

Left out on purpose:
    - every hidden photo, entirely. Her reader also honours `hidden: true`, but a row never written
      cannot leak, so no exported row is ever hidden and the field is always false.
    - the words read from the image, and the excerpt (they stay in the search index on Reborn)
    - `was_at`, the old file paths and names
    - the sha256 (the photo id is its first ten digits; the graph does not need the rest)
    - the coordinates. `has_place` says a photo carries one; where is not needed by any graph link yet.
`ids_found` and `about` are empty lists until identifiers are read with their word confidence and
until someone or something says what a photo is about. They are present so the shape does not change.

The file holds album names and dates, which are personal. It is written where --out says and nowhere
else. Its home is ddl-vault/private/photo-album/photos.jsonl, in a repo git-crypt encrypts whole.

    python dex_photo_graph_export.py --library D:\\DDL_Corpus\\library --out C:\\Users\\dexjr\\ddl-vault\\private\\photo-album\\photos.jsonl
"""
import argparse
import collections
import json
import os
import sys
from pathlib import Path

MIN_WORDS = 5


def load_jsonl(p):
    p = Path(p)
    return [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()] if p.exists() else []


def states(library):
    """(hidden shas, graveyard shas) as the album app last recorded them."""
    hidden, grave = set(), set()
    for r in load_jsonl(Path(library) / "app-state.jsonl"):
        for field, bag in (("hidden", hidden), ("graveyard", grave)):
            if r.get(field) is True:
                bag.add(r["sha256"])
            elif r.get(field) is False:
                bag.discard(r["sha256"])
    return hidden, grave


def build(library):
    """(rows, stats). Album rows first, then photo rows in index order."""
    library = Path(library)
    index = load_jsonl(library / "index.jsonl")
    labels = {r["sha256"]: r for r in load_jsonl(library / "labels.jsonl")}
    facts = {r["sha256"]: r for r in load_jsonl(library / "facts.jsonl")}
    copies = {r["sha256"]: r for r in load_jsonl(library / "copies.jsonl")}
    hidden, grave = states(library)
    pid = {sha: lab["photo_id"] for sha, lab in labels.items()}
    photos, stats, in_album = [], collections.Counter(), collections.Counter()
    for r in index:
        sha = r["sha256"]
        lab = labels.get(sha)
        if lab is None:
            stats["no_label"] += 1
            continue
        if sha in hidden:
            stats["hidden_left_out"] += 1
            continue
        f = facts.get(sha, {})
        c = copies.get(sha)
        keeper = pid.get(c["keeper"]) if c and c["keeper"] not in hidden else None     # never point at a hidden photo
        pile = r["pile"]
        if pile == "low-confidence" and r.get("words", 0) < MIN_WORDS:
            pile = "no-text"
        kind = r.get("bin")
        taken = f.get("taken")
        photos.append({
            "row": "photo", "photo_id": lab["photo_id"], "albums": list(lab["albums"]), "pile": pile,
            "kind": kind if kind and kind != "unsorted" and pile != "no-text" else None,
            "has_text": pile != "no-text", "words": r.get("words", 0) if pile != "no-text" else 0,
            "confidence": r.get("confidence") if pile != "no-text" else None,
            "width": r.get("width"), "height": r.get("height"), "bytes": r.get("bytes"), "modified": r.get("modified"),
            "taken": taken, "date_source": (f.get("taken_source") or "none") if taken else "none",
            "from_phone": bool(r.get("phone")),
            "twin_of": keeper if c and c["why"] == "same-words" else None,
            "looks_like": keeper if c and c["why"] == "looks-same" else None,
            "hidden": False, "ids_found": [], "about": [],
            "in_graveyard": sha in grave, "has_place": bool(f.get("place")),
        })
        for a in lab["albums"]:
            in_album[a] += 1
        stats["photos"] += 1
    known = {a["id"]: a for a in load_jsonl(library / "albums.jsonl")}
    albums = [{"row": "album", "id": a, "title": known.get(a, {}).get("title") or a, "count": in_album[a],
               "note": known.get(a, {}).get("note", "")} for a in sorted(set(known) | set(in_album))]
    stats["albums"] = len(albums)
    return albums + photos, dict(stats)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    rows, stats = build(a.library)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(a.out) + ".part")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, a.out)
    for k, v in sorted(stats.items()):
        print(f"  {k:<18} {v:>8,}")
    photo = next((r for r in rows if r["row"] == "photo"), None)
    print(f"  photo fields       {', '.join(photo) if photo else '(none)'}")


if __name__ == "__main__":
    sys.exit(main())
