"""Resident: a store opened once in the background; it refuses to answer until it is open, and says why.

Temp stores of seeded random vectors only.  Silas Reeve / DDL-3004 / 2026-10-12
"""
import json
import threading

import numpy as np
import pytest

import dex_private_search as ps
from test_dex_private_search import DIM, PREFIX, make_store


def resident(d, **kw):
    rng = np.random.default_rng(3)
    q = rng.normal(size=DIM).astype(np.float32)
    return ps.Resident(d, embed=lambda t: q, open_store=kw.pop("open_store", lambda: ps.Store(d, prefix=PREFIX, dim=DIM)), **kw), q


def test_the_shipped_shortlist_is_the_ruled_one():
    assert ps.SHORTLIST == 5000 and ps.PREFIX == 256


def test_it_refuses_before_it_is_opened_and_while_it_opens(tmp_path):
    d = make_store(tmp_path)
    gate = threading.Event()

    def slow():
        gate.wait(5)
        return ps.Store(d, prefix=PREFIX, dim=DIM)
    r, _ = resident(d, open_store=slow)
    with pytest.raises(ps.NotReady, match="has not been opened"):
        r.ask("x", 4)
    r.start()
    assert r.state == "loading"
    with pytest.raises(ps.NotReady, match="still opening"):
        r.ask("x", 4)
    gate.set()
    assert r.wait(10) == "ready"
    assert len(r.ask("x", 4)[0]) == 4


def test_ready_answers_are_the_stores_own_best_rows_with_their_text(tmp_path):
    d = make_store(tmp_path)
    r, q = resident(d, shortlist=500)                         # a shortlist of everything: the answer is exact
    assert r.start().wait(10) == "ready"
    chunks, rec = r.ask("anything", 4)
    store = ps.Store(d, prefix=PREFIX, dim=DIM)
    want, scores = store.exact(q / np.linalg.norm(q), 4)
    assert [c["id"] for c in chunks] == [f"row-{int(i)}" for i in want]
    assert [round(c["score"], 4) for c in chunks] == [round(float(s), 4) for s in scores]
    assert all(c["text"].startswith("é text ") for c in chunks)
    assert rec["k"] == 4 and rec["shortlist"] == 500 and rec["rows"] == 500
    row = json.loads((d / "search-telemetry.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert "text" not in json.dumps(row) and set(row) >= {"at", "rows", "k", "shortlist_ms", "rescore_ms", "top_rows"}
    st = r.status()
    assert st["state"] == "ready" and st["rows"] == 500 and st["prefix"] == PREFIX and st["shortlist"] == 500


def test_a_store_that_will_not_open_is_failed_and_named(tmp_path):
    r, _ = resident(tmp_path / "nothing-here", open_store=lambda: ps.Store(tmp_path / "nothing-here", prefix=PREFIX, dim=DIM))
    assert r.start().wait(10) == "failed"
    with pytest.raises(ps.NotReady, match="did not open .*StoreError"):
        r.ask("x", 4)
    assert r.status()["error"].startswith("StoreError")


def test_the_query_prefix_reaches_the_embedder_and_bare_stays_bare(tmp_path, monkeypatch):
    d = make_store(tmp_path)
    q = np.random.default_rng(3).normal(size=DIM).astype(np.float32)
    seen = []
    monkeypatch.setattr(ps, "ollama_embed", lambda question, prefix="": (seen.append(prefix + question), q)[1])
    for pre, want in ((ps.MXBAI_QUERY_PREFIX, ps.MXBAI_QUERY_PREFIX + "where is it"), ("", "where is it")):
        r = ps.Resident(d, open_store=lambda: ps.Store(d, prefix=PREFIX, dim=DIM), query_prefix=pre)
        assert r.start().wait(10) == "ready"
        r.ask("where is it", 4)
        assert seen[-1] == want and r.status()["query_prefix"] is bool(pre)


def test_start_twice_opens_once(tmp_path):
    d = make_store(tmp_path)
    opened = []

    def once():
        opened.append(1)
        return ps.Store(d, prefix=PREFIX, dim=DIM)
    r, _ = resident(d, open_store=once)
    r.start(); r.start()
    r.wait(10); r.start()
    assert opened == [1]
