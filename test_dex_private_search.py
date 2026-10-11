"""dex_private_search: the fast path returns what exact search returns, and says so in numbers.

Stores here are built in a temp folder from seeded random vectors, in the builder's file format,
so nothing depends on any real store.  Silas Reeve / DDL-3004 / 2026-10-10
"""
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

import dex_private_search as ps

DIM, PREFIX = 64, 16


def make_store(tmp_path, shard_sizes=(300, 200), seed=7, name="s"):
    rng = np.random.default_rng(seed)
    d = tmp_path / name
    d.mkdir()
    row = 0
    for i, n in enumerate(shard_sizes):
        v = rng.normal(size=(n, DIM)).astype(np.float32)
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        (d / f"vectors-{i:04d}.f32").write_bytes(v.tobytes())
        with open(d / f"chunks-{i:04d}.jsonl", "w", encoding="utf-8", newline="\n") as f:
            for _ in range(n):
                f.write(json.dumps({"id": f"row-{row}", "text": f"é text {row}"}, ensure_ascii=False) + "\n")
                row += 1
    return d


def open_store(d):
    return ps.Store(d, prefix=PREFIX, dim=DIM)


def brute(store, q, k):
    allv = store.vectors(range(store.n))
    sc = allv @ q
    order = np.lexsort((np.arange(store.n), -sc))[:k]
    return [int(x) for x in order]


def unit(rng):
    q = rng.normal(size=DIM).astype(np.float32)
    return q / np.linalg.norm(q)


def test_rows_are_counted_across_shards(tmp_path):
    s = open_store(make_store(tmp_path))
    assert s.n == 500 and s.starts == [0, 300]
    assert s.short.shape == (500, PREFIX) and s.short.flags["C_CONTIGUOUS"]


def test_chunk_row_k_is_vector_row_k_in_every_shard(tmp_path):
    s = open_store(make_store(tmp_path))
    for r in (0, 299, 300, 499):
        assert s.chunk(r)["id"] == f"row-{r}"
    with pytest.raises(IndexError):
        s.chunk(500)


def test_exact_matches_a_brute_force_scan(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "SCAN_BLOCK", 70)          # several blocks per shard, uneven
    s = open_store(make_store(tmp_path))
    rng = np.random.default_rng(1)
    for _ in range(10):
        q = unit(rng)
        rows, scores = s.exact(q, 12)
        assert [int(r) for r in rows] == brute(s, q, 12)
        assert list(scores) == sorted(scores, reverse=True)


def test_fast_with_a_shortlist_of_everything_is_exact(tmp_path):
    s = open_store(make_store(tmp_path))
    rng = np.random.default_rng(2)
    for _ in range(10):
        q = unit(rng)
        rows, _, _ = s.fast(q, 10, shortlist=s.n)
        assert [int(r) for r in rows] == brute(s, q, 10)


def test_fast_scores_are_full_vector_scores_not_prefix_scores(tmp_path):
    s = open_store(make_store(tmp_path))
    q = unit(np.random.default_rng(3))
    rows, scores, _ = s.fast(q, 5, shortlist=50)
    assert np.allclose(scores, s.vectors(rows) @ q, atol=1e-6)


def test_a_small_shortlist_can_miss_and_agreement_counts_it(tmp_path):
    s = open_store(make_store(tmp_path))
    rng = np.random.default_rng(4)
    missed = 0
    for _ in range(40):
        q = unit(rng)
        f, _, _ = s.fast(q, 10, shortlist=10)
        e, _ = s.exact(q, 10)
        a = ps.agreement(f, e)
        assert a["missed"] == len(set(int(x) for x in e) - set(int(x) for x in f))
        missed += a["missed"]
    assert missed > 0          # a 16-of-64 prefix with a shortlist of 10 does miss: the measure can fail


def test_the_shortlist_is_chosen_by_prefix_score_not_arbitrarily(tmp_path):
    """A shortlist of 100 from 500 picked at random would hold 20% of the true top 10."""
    s = open_store(make_store(tmp_path))
    rng = np.random.default_rng(8)
    found = 0
    for _ in range(40):
        q = unit(rng)
        f, _, _ = s.fast(q, 10, shortlist=100)
        found += 10 - ps.agreement(f, s.exact(q, 10)[0])["missed"]
    assert found / 400 > 0.5


def test_agreement_fields():
    a = ps.agreement([1, 2, 3], [1, 2, 3])
    assert a == {"k": 3, "missed": 0, "same_order": True, "top1_same": True, "worst_missed_rank": None}
    a = ps.agreement([2, 1, 9], [1, 2, 3])
    assert a == {"k": 3, "missed": 1, "same_order": False, "top1_same": False, "worst_missed_rank": 3}
    assert ps.agreement([5, 6], [7, 6])["worst_missed_rank"] == 1


def test_vectors_file_that_is_not_whole_rows_is_refused(tmp_path):
    d = make_store(tmp_path)
    with open(d / "vectors-0001.f32", "ab") as f:
        f.write(b"\0\0")
    with pytest.raises(ps.StoreError, match="whole number"):
        open_store(d)


def test_missing_vectors_file_is_refused(tmp_path):
    d = make_store(tmp_path)
    (d / "vectors-0001.f32").unlink()
    with pytest.raises(ps.StoreError, match="has no"):
        open_store(d)


def test_chunks_and_vectors_with_different_row_counts_are_refused(tmp_path):
    d = make_store(tmp_path)
    with open(d / "chunks-0000.jsonl", "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"id": "extra"}) + "\n")
    s = open_store(d)
    with pytest.raises(ps.StoreError, match="301 rows"):
        s.chunk(0)


def test_empty_folder_is_refused(tmp_path):
    with pytest.raises(ps.StoreError, match="no chunks"):
        open_store(tmp_path)


def test_memcheck_is_asked_for_the_shortlist_size_and_can_refuse(tmp_path):
    d = make_store(tmp_path)
    asked = []
    ps.Store(d, prefix=PREFIX, dim=DIM, memcheck=asked.append)
    assert asked == [pytest.approx(500 * PREFIX * 4 / 2**30)]

    def refuse(gb):
        raise RuntimeError("no room")
    with pytest.raises(RuntimeError, match="no room"):
        ps.Store(d, prefix=PREFIX, dim=DIM, memcheck=refuse)


def test_a_wrong_width_question_is_refused(tmp_path):
    s = ps.Search(open_store(make_store(tmp_path)), None)
    with pytest.raises(ValueError, match="shape"):
        s.by_vector(np.ones(DIM + 1, dtype=np.float32))


def test_every_search_logs_numbers_and_never_text(tmp_path):
    d = make_store(tmp_path)
    log = tmp_path / "t" / "log.jsonl"
    s = ps.Search(open_store(d), log, embed=lambda text: unit(np.random.default_rng(5)), sample_every=0)
    rows, _, _ = s.ask("a question with the word zebra in it", k=4)
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 and "zebra" not in lines[0] and "text" not in lines[0]
    rec = json.loads(lines[0])
    assert rec["top_rows"] == [int(r) for r in rows] and rec["rows"] == 500 and rec["k"] == 4
    assert rec["sampled"] is False and "missed" not in rec
    assert rec["embed_ms"] >= 0 and rec["shortlist_ms"] >= 0 and rec["rescore_ms"] >= 0
    datetime.strptime(rec["at"], "%Y-%m-%dT%H:%M:%SZ")


def test_sampling_runs_exact_on_every_nth_search_only(tmp_path):
    log = tmp_path / "log.jsonl"
    s = ps.Search(open_store(make_store(tmp_path)), log, sample_every=3, shortlist=40)
    rng = np.random.default_rng(6)
    for _ in range(7):
        s.by_vector(unit(rng), 5)
    recs = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert [r["sampled"] for r in recs] == [False, False, True, False, False, True, False]
    for r in recs:
        assert ("missed" in r) == r["sampled"] == ("exact_ms" in r)


def test_sampled_row_reports_the_real_difference(tmp_path):
    log = tmp_path / "log.jsonl"
    store = open_store(make_store(tmp_path))
    s = ps.Search(store, log, shortlist=10)
    rng = np.random.default_rng(4)
    for _ in range(40):
        q = unit(rng)
        rows, _, rec = s.by_vector(q, 10, force_sample=True)
        e, _ = store.exact(q, 10)
        assert rec["missed"] == len(set(int(x) for x in e) - set(int(x) for x in rows))


def _row(at, short=1.0, rescore=2.0, **kw):
    r = {"at": at.strftime("%Y-%m-%dT%H:%M:%SZ"), "shortlist_ms": short, "rescore_ms": rescore, "sampled": False}
    r.update(kw)
    return json.dumps(r)


def test_summary_counts_the_window_and_names_unreadable_rows(tmp_path):
    now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    log = tmp_path / "log.jsonl"
    log.write_text("\n".join([
        _row(now - timedelta(hours=25)),                                    # outside the window
        _row(now - timedelta(hours=24)),                                    # exactly on the edge: outside
        _row(now - timedelta(hours=23), short=10, rescore=5),
        _row(now - timedelta(hours=2), short=1, rescore=1, sampled=True, k=10, missed=0, top1_same=True),
        _row(now - timedelta(hours=1), short=100, rescore=50, sampled=True, k=10, missed=2, top1_same=False),
        "not json",
        json.dumps({"no": "timestamp"}),
        _row(now + timedelta(minutes=1)),                                   # the future: outside
    ]) + "\n", encoding="utf-8")
    s = ps.summary(log, now=now)
    assert s == {"searches": 3, "unreadable_rows": 2, "log": "read", "median_ms": 15.0, "p95_ms": 150.0,
                 "slowest_ms": 150.0, "sampled": 2, "sampled_with_a_miss": 1, "results_missed": 2,
                 "results_checked": 20, "top1_changed": 1}
    lines = ps.summary_lines(s)
    assert lines[0] == "private search: 3 searches, median 15.0 ms, 95th 150.0 ms, slowest 150.0 ms"
    assert lines[1] == "checked against exact search: 2 searches, 2 of 20 results missed, top result changed in 1"
    assert lines[2] == "telemetry rows that could not be read: 2"


def test_summary_with_no_log_and_with_nothing_sampled(tmp_path):
    assert ps.summary_lines(ps.summary(tmp_path / "none.jsonl")) == ["private search: no telemetry log yet"]
    now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
    log = tmp_path / "log.jsonl"
    log.write_text(_row(now - timedelta(hours=1)) + "\n", encoding="utf-8")
    lines = ps.summary_lines(ps.summary(log, now=now))
    assert lines[1] == "checked against exact search: none sampled in the window"
    log.write_text(_row(now - timedelta(hours=30)) + "\n", encoding="utf-8")
    assert ps.summary_lines(ps.summary(log, now=now)) == ["private search: 0 searches in the window (0 unreadable rows)"]


def test_vectors_come_back_in_the_order_asked_across_shards_with_repeats(tmp_path):
    d = make_store(tmp_path, shard_sizes=(300, 200, 50))
    st = ps.Store(d, prefix=PREFIX, dim=DIM)
    rows = [549, 0, 299, 300, 499, 500, 7, 7, 301, 2]             # out of order, every shard, shard edges, a repeat
    got = st.vectors(rows)
    for j, r in enumerate(rows):
        sh, k = st._locate(r)
        assert np.array_equal(got[j], np.asarray(st.maps[sh][k])), r
    assert st.vectors([]).shape == (0, DIM)
    for bad in ([550], [-1], [0, 9999]):
        with pytest.raises(IndexError):
            st.vectors(bad)


def test_drop_live_leaves_out_the_last_shard_only(tmp_path):
    d = make_store(tmp_path, shard_sizes=(300, 200, 50))
    assert ps.Store(d, prefix=PREFIX, dim=DIM).n == 550
    st = ps.Store(d, prefix=PREFIX, dim=DIM, drop_live=True)
    assert st.n == 500 and len(st.maps) == 2
    # a live shard whose chunks file is behind its vectors file does not stop a store opened without it
    with open(d / "chunks-0002.jsonl", "w", encoding="utf-8") as f:
        f.write("")
    assert ps.Store(d, prefix=PREFIX, dim=DIM, drop_live=True).chunk(499)["id"] == "row-499"
    one = make_store(tmp_path, shard_sizes=(10,), name="one")
    with pytest.raises(ps.StoreError, match="besides the live shard"):
        ps.Store(one, prefix=PREFIX, dim=DIM, drop_live=True)
