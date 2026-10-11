"""
dex_photo_graph_export.py -- the photo rows the private work graph is built from. No words, no paths, no hidden photo.

For Lena Marsh / DDL-3005 (gaminglaptop-cowork/work/WORK-GRAPH/PHOTO_ALBUM_GRAPH_v0.1.md), on the
Operator's "yes to both" (2026-10-10): photos go into the PRIVATE graph only, and a photo marked hidden
stays out of everything, the private graph included.

One JSON Lines file, one row per photo:
    photo_id, albums, width, height, bytes, pile, has_text, taken, taken_source, place, source,
    in_graveyard, twin_of, looks_like (photo ids), kind_suggestion, ids_found
Left out on purpose:
    - every hidden photo, entirely. A row never written cannot leak.
    - the words read from the image (they stay in the search index on Reborn)
    - `was_at`, the old file paths and names
    - the sha256 (the photo id is its first ten digits; the graph does not need the rest)
`kind_suggestion` is a guess from the words and is named as one. `ids_found` is empty until the
identifier patterns are agreed with Lena; it is present so the shape does not change later.

The file is plain JSON and contains album names and dates, which are personal. It is written where
--out says and nowhere else; putting it in git is a separate, deliberate step into an encrypted path.

    python dex_photo_graph_export.py --library D:\\DDL_Corpus\\library --out C:\\Users\\dexjr\\dex-data\\album\\graph-export.jsonl
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
    library = Path(library)
    index = load_jsonl(library / "index.jsonl")
    labels = {r["sha256"]: r for r in load_jsonl(library / "labels.jsonl")}
    facts = {r["sha256"]: r for r in load_jsonl(library / "facts.jsonl")}
    copies = {r["sha256"]: r for r in load_jsonl(library / "copies.jsonl")}
    hidden, grave = states(library)
    pid = {sha: lab["photo_id"] for sha, lab in labels.items()}
    rows, stats = [], collections.Counter()
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
        rows.append({
            "photo_id": lab["photo_id"], "albums": lab["albums"], "width": r.get("width"), "height": r.get("height"),
            "bytes": r.get("bytes"), "pile": pile, "has_text": pile != "no-text",
            "taken": f.get("taken"), "taken_source": f.get("taken_source", "none") if f.get("taken") else "none",
            "place": f.get("place"), "source": f.get("source", "corpus"), "in_graveyard": sha in grave,
            "twin_of": keeper if c and c["why"] == "same-words" else None,
            "looks_like": keeper if c and c["why"] == "looks-same" else None,
            "kind_suggestion": kind if kind and kind != "unsorted" and pile != "no-text" else None,
            "ids_found": [],
        })
        stats["exported"] += 1
    return rows, dict(stats)


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
    print(f"  fields             {', '.join(rows[0]) if rows else '(none)'}")


if __name__ == "__main__":
    sys.exit(main())
