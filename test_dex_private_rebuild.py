"""dex-private-rebuild: a piece the model refuses is split, never cut, and the split is recorded.

The embedder is replaced by one that refuses any text over a set length, so nothing here needs
Ollama.  Silas Reeve / DDL-3004 / 2026-10-10
"""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("rebuild", Path(__file__).with_name("dex-private-rebuild.py"))
rb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rb)

HEAD = "file: a\npath: b\n\n"


@pytest.fixture
def limit(monkeypatch):
    calls = []

    def fake(texts, cap=[300]):
        calls.append(list(texts))
        if any(len(t) - len(HEAD) > cap[0] for t in texts):
            raise rb.OverContext()
        return [[float(len(t))] for t in texts]
    monkeypatch.setattr(rb, "embed_batch", fake)
    return calls


def words(n):
    return " ".join(f"w{i:04d}" for i in range(n))      # 6 chars per word with its space


def test_a_piece_that_fits_has_depth_zero(limit):
    stats = {"chunks_split": 0, "chunks_unembeddable": 0}
    out = rb.embed_pieces(HEAD, ["short one", "short two"], stats)
    assert [(p, d) for p, _, d in out] == [("short one", 0), ("short two", 0)]
    assert stats == {"chunks_split": 0, "chunks_unembeddable": 0}


def test_a_refused_piece_is_halved_until_it_fits_and_nothing_is_lost(limit):
    stats = {"chunks_split": 0, "chunks_unembeddable": 0}
    big = words(150)                                     # 899 chars against a cap of 300
    out = rb.embed_pieces(HEAD, ["fits", big], stats)
    by_depth = {}
    for p, v, d in out:
        by_depth.setdefault(d, []).append(p)
        assert v == [float(len(HEAD + p))]               # the vector is of the text that is stored
        assert len(p) <= 300
    assert by_depth[0] == ["fits"]
    assert set(by_depth) == {0, 2} and len(by_depth[2]) == 4
    assert stats["chunks_split"] == 3                    # one split of the whole, one of each half
    assert " ".join(by_depth[2]).split() == big.split()  # every word kept, in order, none twice


def test_chunks_come_back_in_document_order_whatever_was_retried(limit):
    stats = {"chunks_split": 0, "chunks_unembeddable": 0}
    pieces = ["alpha", words(150), "beta", words(90), "gamma"]
    out = rb.embed_pieces(HEAD, pieces, stats)
    assert " ".join(p for p, _, _ in out).split() == " ".join(pieces).split()
    assert [d for _, _, d in out] == [0, 2, 2, 2, 2, 0, 1, 1, 0]


def test_the_split_point_is_the_break_nearest_the_middle():
    a, b = rb.split_piece(words(100))                    # 599 chars; spaces every 6
    assert abs(len(a) - len(b)) <= 6
    a, b = rb.split_piece("x" * 100 + "\n" + "y" * 300 + " " + "z" * 198)   # newline at 100 is outside the window
    assert (len(a), len(b)) == (401, 198)                # the space at 401, not the middle of a word
    a, b = rb.split_piece("q" * 500)                     # no break anywhere: cut at the middle
    assert (len(a), len(b)) == (250, 250)


def test_a_piece_too_small_to_split_is_counted_not_stored(limit, monkeypatch):
    monkeypatch.setattr(rb, "MIN_SPLIT_CHARS", 400)
    stats = {"chunks_split": 0, "chunks_unembeddable": 0}
    out = rb.embed_pieces(HEAD, [words(60)], stats)      # 359 chars: refused, and under the minimum
    assert out == [] and stats == {"chunks_split": 0, "chunks_unembeddable": 1}
