"""dex_hash_tree: every file gets a row, a real sha256, and a failure is a row and not a gap. Temp files only."""
import hashlib
import json
from datetime import datetime

import dex_hash_tree as ht


def tree(tmp_path):
    root = tmp_path / "root"
    (root / "a" / ".git").mkdir(parents=True)
    (root / "a" / "one.txt").write_bytes(b"one")
    (root / "a" / ".git" / "HEAD").write_bytes(b"ref: refs/heads/main\n")          # hidden folders are files too
    (root / "empty.bin").write_bytes(b"")
    (root / "b").mkdir()
    (root / "b" / "big.bin").write_bytes(b"x" * (ht.BLOCK + 7))                    # more than one read block
    return root


def rows(out):
    return [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]


def test_every_file_gets_a_row_with_its_real_hash(tmp_path):
    root, out = tree(tmp_path), tmp_path / "out.jsonl"
    stats = ht.run(root, out, log=lambda *_: None)
    got = {r["p"]: r for r in rows(out)}
    assert set(got) == {"a/.git/HEAD", "a/one.txt", "b/big.bin", "empty.bin"} and stats["files"] == 4 and stats["hashed"] == 4
    assert got["a/one.txt"]["h"] == hashlib.sha256(b"one").hexdigest() and got["a/one.txt"]["s"] == 3
    assert got["empty.bin"]["h"] == hashlib.sha256(b"").hexdigest()
    assert got["b/big.bin"]["h"] == hashlib.sha256(b"x" * (ht.BLOCK + 7)).hexdigest()
    assert stats["bytes"] == 3 + 21 + 0 + ht.BLOCK + 7 and stats["errors"] == 0


def test_a_second_run_keeps_what_it_has_and_rereads_what_changed(tmp_path):
    root, out = tree(tmp_path), tmp_path / "out.jsonl"
    ht.run(root, out, log=lambda *_: None)
    (root / "a" / "one.txt").write_bytes(b"one more")
    stats = ht.run(root, out, log=lambda *_: None)
    assert stats["kept"] == 3 and stats["hashed"] == 1
    assert rows(out)[-1] == {"p": "a/one.txt", "s": 8, "h": hashlib.sha256(b"one more").hexdigest(), "m": rows(out)[-1]["m"]}


def test_a_file_that_cannot_be_read_is_a_row_with_no_hash(tmp_path, monkeypatch):
    root, out = tree(tmp_path), tmp_path / "out.jsonl"
    real = ht.sha256_of

    def flaky(path):
        if path.endswith("one.txt"):
            raise PermissionError("no")
        return real(path)
    monkeypatch.setattr(ht, "sha256_of", flaky)
    stats = ht.run(root, out, log=lambda *_: None)
    bad = [r for r in rows(out) if r["h"] is None]
    assert stats["errors"] == 1 and stats["files"] == 4 and len(rows(out)) == 4
    assert bad == [{"p": "a/one.txt", "s": 3, "h": None, "m": bad[0]["m"], "error": "PermissionError"}]


def test_until_stops_before_reading_more(tmp_path, monkeypatch):
    root, out = tree(tmp_path), tmp_path / "out.jsonl"
    evening = datetime(2026, 1, 1, 20, 10)
    stop = ht.deadline("03:30", evening)
    assert stop == datetime(2026, 1, 2, 3, 30)                           # tomorrow: an evening start is not "already past"
    assert ht.deadline("23:00", evening) == datetime(2026, 1, 1, 23, 0) and ht.deadline(None) is None
    assert not ht.past(stop, datetime(2026, 1, 1, 20, 11)) and not ht.past(stop, datetime(2026, 1, 2, 3, 29))
    assert ht.past(stop, datetime(2026, 1, 2, 3, 30)) and not ht.past(None)
    ht.run(root, out, until="03:30", log=lambda *_: None)                # a real deadline hours away: everything is read
    assert len(rows(out)) == 4
    out.unlink()
    monkeypatch.setattr(ht, "past", lambda stop_at, now=None: True)
    stats = ht.run(root, out, until="00:00", log=lambda *_: None)
    assert stats["stopped_early"] and stats["hashed"] == 0 and rows(out) == []
