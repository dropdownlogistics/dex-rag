"""Photographs that arrived through a chat export are photographs, not chats.

Operator, 2026-10-10: the car photo "was in chats". The first sort put every image from a Google Chat or
Hangouts export in the album `chats`, whatever it showed. This moves the ones with no words (fewer than
five read) to photos/<year>, taking the year from a date in the file name where there is one
(File-2015-03-08(5).jpg), else photos/undated. Images with words stay in `chats`.
Labels only: no image file is touched. Run with --apply to write; without it, it only counts.
"""
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\dexjr\dex-rag")
import dex_photo_albums as al

LIB = Path(r"D:\DDL_Corpus\library")
APPLY = "--apply" in sys.argv
MIN_WORDS = 5
DATE = re.compile(r"(?<!\d)((?:19|20)\d{2})[-_.](0[1-9]|1[0-2])[-_.](0[1-9]|[12]\d|3[01])(?!\d)")

index = {r["sha256"]: r for r in map(json.loads, (LIB / "index.jsonl").open(encoding="utf-8"))}
labels = [json.loads(l) for l in (LIB / "labels.jsonl").open(encoding="utf-8")]
albums = [json.loads(l) for l in (LIB / "albums.jsonl").open(encoding="utf-8")]
have = {a["id"] for a in albums}

moved = collections.Counter()
stay = 0
for lab in labels:
    if lab["albums"] != ["chats"]:
        continue
    r = index[lab["sha256"]]
    wordless = r["pile"] == "no-text" or (r["pile"] == "low-confidence" and r["words"] < MIN_WORDS)
    if not wordless:
        stay += 1
        continue
    years = {m.group(1) for p in r["was_at"] for m in DATE.finditer(p.rsplit("/", 1)[-1])}
    target = f"photos/{min(years)}" if years else "photos/undated"
    moved[target] += 1
    lab["albums"] = [target]

print(f"chats: {stay:,} stay (they have words); {sum(moved.values()):,} are photographs and move:")
for k, v in sorted(moved.items()):
    print(f"  {v:>6,}  {k}{'' if k in have else '   (new album)'}")
if APPLY:
    for name in sorted(set(moved) - have):
        albums.append({"id": name, "name": name, "title": al.title(name), "note": "", "origin": [], "made": "relabel 2026-10-10", "at": al._now()})
    al._write(LIB / "albums.jsonl", sorted(albums, key=lambda a: a["id"]))
    al._write(LIB / "labels.jsonl", labels)
    print("written.")
else:
    print("(counted only; nothing written)")
