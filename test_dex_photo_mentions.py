"""dex_photo_mentions: clear ids only, hidden photos left out, graph names joined. Made-up library only."""
import json

import dex_photo_mentions as m

A, B, C, D = "aa" + "1" * 62, "bb" + "2" * 62, "cc" + "3" * 62, "dd" + "4" * 62


def library(tmp_path, hidden=()):
    lib, boxes = tmp_path / "lib", tmp_path / "boxes"
    lib.mkdir()
    shas = [A, B, C, D]
    (lib / "index.jsonl").write_text("".join(json.dumps({"sha256": s, "pile": "text"}) + "\n" for s in shas), encoding="utf-8")
    (lib / "labels.jsonl").write_text("".join(json.dumps({"sha256": s, "photo_id": f"P-{s[:10]}", "albums": ["x"]}) + "\n" for s in shas), encoding="utf-8")
    (lib / "app-state.jsonl").write_text("".join(json.dumps({"sha256": s, "hidden": True}) + "\n" for s in hidden), encoding="utf-8")
    words = {A: [["DDL-9001", 95.0, 0, 0, 1, 1], ["see", 99.0, 0, 0, 1, 1], ["STD-DEMO-001,", 90.0, 0, 0, 1, 1]],
             B: [["DDL-9001", 60.0, 0, 0, 1, 1]],                         # read poorly: no row
             C: [["DDL-9002", 99.0, 0, 0, 1, 1]],
             D: [["nothing", 99.0, 0, 0, 1, 1]]}
    for s, w in words.items():
        (boxes / s[:2]).mkdir(parents=True, exist_ok=True)
        (boxes / s[:2] / f"{s}.json").write_text(json.dumps({"w": 10, "h": 10, "words": w}), encoding="utf-8")
    return lib, boxes


def nodes(tmp_path):
    f = tmp_path / "nodes.csv"
    f.write_text("id,type,label,attrs\nperson:DDL-9001,person,Ada Marlow,{}\nmsg:1:DDL-9001,message,not this,{}\n"
                 "id:STD-DEMO-001,identifier,Demo standard,{}\nid:DDL-9001,identifier,loses to the person,{}\n", encoding="utf-8")
    return f


def test_clear_ids_get_a_row_with_the_graphs_name(tmp_path):
    lib, boxes = library(tmp_path)
    rows, stats = m.build(lib, boxes, m.graph_names(nodes(tmp_path)))
    by = {r["sha256"]: r for r in rows}
    assert set(by) == {A, C}                                              # B was read poorly, D names nothing
    assert by[A]["ids"] == [{"id": "DDL-9001", "conf": 95.0, "type": "person", "label": "Ada Marlow"},
                            {"id": "STD-DEMO-001", "conf": 90.0, "type": "identifier", "label": "Demo standard"}]
    assert by[C]["ids"] == [{"id": "DDL-9002", "conf": 99.0}]             # not in the graph: kept, with no name
    assert stats["ids_read_poorly"] == 1 and stats["ids_not_in_graph"] == 1 and stats["distinct_ids"] == 3


def test_a_hidden_photo_gets_no_row(tmp_path):
    lib, boxes = library(tmp_path, hidden=[A])
    rows, stats = m.build(lib, boxes)
    assert [r["sha256"] for r in rows] == [C] and stats["hidden_left_out"] == 1


def test_no_graph_file_still_gives_the_ids(tmp_path):
    lib, boxes = library(tmp_path)
    assert m.graph_names(tmp_path / "absent.csv") == {}
    rows, _ = m.build(lib, boxes)
    assert all(set(i) == {"id", "conf"} for r in rows for i in r["ids"])
