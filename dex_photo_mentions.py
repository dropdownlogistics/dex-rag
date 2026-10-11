"""
dex_photo_mentions.py -- which DDL ids each photo names, for the album app's "What it names" card.

Writes <library>/mentions.jsonl, one row per photo that names at least one id clearly:

    {"sha256": ..., "photo_id": "P-...", "ids": [{"id": "DDL-3012", "conf": 93.0, "type": "person", "label": "..."}]}

The ids are the ones dex_photo_ids.py reads from the word boxes (Lena's patterns, whole tokens). Only a
reading at MIN_CONF or better is kept, the same line her graph draws for a link. `type` and `label` come
from the work graph's nodes.csv when the id is a node there; an id the graph does not have is kept
without them, so the app can say so.

A hidden photo gets no row. Nothing but the ids is taken from the words. The file stays in the library
on Reborn and is not for git: a label can be a person's name.

    python dex_photo_mentions.py --library D:\\DDL_Corpus\\library --boxes C:\\Users\\dexjr\\dex-data\\ocr\\boxes
        [--nodes <WORK-GRAPH>\\out\\nodes.csv]

Silas Reeve / DDL-3004 / 2026-10-11
"""
import argparse
import collections
import csv
import json
import os
from pathlib import Path

import dex_photo_ids
from dex_photo_graph_export import load_jsonl, read_boxes, states

MIN_CONF = 80.0
NODE_TYPES = ("person", "identifier", "asset", "project", "decision", "quest", "concept")
DEFAULT_NODES = Path(r"C:\Users\dexjr\dex-data\ddl-org-ro\gaminglaptop-cowork\work\WORK-GRAPH\out\nodes.csv")


def graph_names(nodes_csv):
    """{"DDL-3012": {"type", "label"}} for every graph node whose id ends in a DDL id. Earlier types win."""
    out = {}
    if not nodes_csv or not Path(nodes_csv).exists():
        return out
    rank = {t: i for i, t in enumerate(NODE_TYPES)}
    with open(nodes_csv, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["type"] not in rank or ":" not in r["id"]:
                continue
            key = r["id"].split(":", 1)[1]
            if key not in out or rank[r["type"]] < rank[out[key]["type"]]:
                out[key] = {"type": r["type"], "label": r["label"]}
    return out


def build(library, boxes, names=None):
    """(rows, stats)."""
    library, names = Path(library), names or {}
    labels = {r["sha256"]: r for r in load_jsonl(library / "labels.jsonl")}
    hidden, _ = states(library)
    rows, stats = [], collections.Counter()
    for r in load_jsonl(library / "index.jsonl"):
        sha = r["sha256"]
        if sha not in labels:
            continue
        if sha in hidden:
            stats["hidden_left_out"] += 1
            continue
        words = read_boxes(boxes, sha)
        if not words:
            continue
        ids = []
        for hit in dex_photo_ids.ids_in(words):
            if hit["conf"] < MIN_CONF:
                stats["ids_read_poorly"] += 1
                continue
            known = names.get(hit["id"])
            stats["ids_in_graph" if known else "ids_not_in_graph"] += 1
            ids.append({**hit, **(known or {})})
        if ids:
            rows.append({"sha256": sha, "photo_id": labels[sha]["photo_id"], "ids": ids})
    stats["photos"] = len(rows)
    stats["distinct_ids"] = len({i["id"] for r in rows for i in r["ids"]})
    return rows, dict(stats)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", required=True, type=Path)
    ap.add_argument("--boxes", required=True, type=Path)
    ap.add_argument("--nodes", type=Path, default=DEFAULT_NODES)
    a = ap.parse_args()
    names = graph_names(a.nodes)
    rows, stats = build(a.library, a.boxes, names)
    out = a.library / "mentions.jsonl"
    tmp = out.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, out)
    print(json.dumps({"graph_names": len(names), **stats}, sort_keys=True))


if __name__ == "__main__":
    main()
