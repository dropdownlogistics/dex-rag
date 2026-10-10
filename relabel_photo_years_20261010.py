"""One-off: put each photograph in the year it was TAKEN.

The first sort used the file's modified time for the year, which for exported photos is the export date
(3,895 landed in photos/2026). dex_photo_facts.py has since read the real dates. This moves every photo
whose only album is a photos/<year> or photos/undated album to photos/<year it was taken>, or to
photos/undated when no trustworthy date exists. Photos in any other album are not touched.
Labels only; no image file is touched. A copy of the labels is kept first. --apply writes.
Silas Reeve / DDL-3004 / 2026-10-10
"""
import collections
import json
import shutil
import sys
from pathlib import Path

import dex_photo_albums as al

LIB = Path(r"D:\DDL_Corpus\library")
APPLY = "--apply" in sys.argv

facts = {r["sha256"]: r for r in map(json.loads, (LIB / "facts.jsonl").open(encoding="utf-8"))}
labels = [json.loads(l) for l in (LIB / "labels.jsonl").open(encoding="utf-8")]
albums = [json.loads(l) for l in (LIB / "albums.jsonl").open(encoding="utf-8")]
have = {a["id"] for a in albums}

moves, same, skipped = collections.Counter(), 0, 0
for lab in labels:
    if len(lab["albums"]) != 1 or not lab["albums"][0].startswith("photos/"):
        continue
    f = facts.get(lab["sha256"])
    if f is None:
        skipped += 1
        continue
    target = f"photos/{f['taken'][:4]}" if f["taken"] else "photos/undated"
    if target == lab["albums"][0]:
        same += 1
        continue
    moves[(lab["albums"][0], target)] += 1
    lab["albums"] = [target]

after = collections.Counter(lab["albums"][0] for lab in labels if len(lab["albums"]) == 1 and lab["albums"][0].startswith("photos/"))
print(f"already in the right year: {same:,}; moving: {sum(moves.values()):,}; no facts row (left alone): {skipped}")
print("year albums after the move:")
for k, v in sorted(after.items()):
    print(f"  {v:>6,}  {k}{'' if k in have else '   (new album)'}")
if APPLY:
    for f in ("labels.jsonl", "albums.jsonl"):
        shutil.copyfile(LIB / f, LIB / f.replace(".jsonl", ".before-year-relabel-20261010.jsonl"))
    for name in sorted(set(after) - have):
        albums.append({"id": name, "name": name, "title": al.title(name), "note": "", "origin": [], "made": "relabel 2026-10-10", "at": al._now()})
    al._write(LIB / "albums.jsonl", sorted(albums, key=lambda a: a["id"]))
    al._write(LIB / "labels.jsonl", labels)
    print("written.")
else:
    print("(counted only; nothing written)")
