"""
dex_private_search.py -- search over the plain-file private store that dex-private-rebuild.py writes.

Operator approval: _shared/OPERATOR-DECISIONS.md in ddl-org, 2026-10-10 (layout revised; telemetry
kept). The Operator said "switch v2" on 2026-10-12 (Reed Vane, DDL-2004:20261012T150001Z-a2e6): the
Dex server's private answers come from here through `Resident`, while the file named in dex.py says
"v2". The old Chroma collection is untouched and is the fallback.

Layout, as decided:
  - the full vectors stay on disk (float32, unit length, 1024 wide), read through a memory map;
  - a SHORTLIST matrix is held in memory: the first PREFIX dimensions of every row, float32,
    re-normalised, one contiguous block. Size follows the row count read at load (rows x 256 x 4
    bytes) and is checked against free memory first: about 6.8 GiB at the ~7.1 M rows the 2026-10-10
    build is projected to reach (Wren Keeler's measurement; the embedder splits seven chunks in ten,
    so the store has about twice the rows first assumed);
  - a question scores every row against the shortlist matrix, keeps the best SHORTLIST rows, then
    re-scores exactly those rows against their full vectors. The final order is exact for every
    row that reached the shortlist. A row can only be missed if it fell outside the shortlist.

Telemetry (the Operator's condition): every search appends one row of numbers to a JSONL log --
timings, sizes, the ids returned. A sampled fraction of searches ALSO run the exact full scan and
record how far the fast answer differs from it. No question text and no chunk text is ever logged.
`summary()` turns a day of rows into the lines the morning briefing prints.

    python dex_private_search.py --store D:\\DDL_Private\\search\\proof-orphan --selftest 200
    python dex_private_search.py --store <dir> --ask "a question" -k 10
"""
import argparse
import hashlib
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

DIM = 1024
PREFIX = 256
# 5000 at width 256 is Wren Keeler's ruling of 2026-10-11 (reborn-studio/work/retrieval/RULING-20261011-shortlist.md):
# at 1000 two of her 26 questions lost a chunk that belongs in the top 4. It holds only while production
# fetches 4. Whoever raises the fetch depth re-runs her measurement first; above 4 her answer is width 512.
SHORTLIST = 5000
SAMPLE_EVERY = 20          # one search in this many also runs the exact scan
SCAN_BLOCK = 200_000       # rows per block in the exact scan (bounds memory, not the result)
# mxbai's documented query form. NOT applied by default: nothing in dex-rag uses it today, and
# turning it on changes what is retrieved (dex-rag rule 10: the Operator's call, after a measurement
# on a real question set). --mxbai-prefix turns it on for one run so the two can be compared.
MXBAI_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class StoreError(Exception):
    """The store on disk is not what build.json or the row counts say it is."""


def _now():
    return datetime.now(timezone.utc)


def _unit(a):
    n = np.linalg.norm(a, axis=-1, keepdims=True)
    if not np.all(n > 0):
        raise StoreError("zero-length vector")
    return a / n


class Store:
    """An opened store: full vectors memory-mapped, the shortlist matrix in memory."""

    def __init__(self, path, prefix=PREFIX, dim=DIM, memcheck=None, drop_live=False):
        """`drop_live` leaves out the highest-numbered shard: while a build is running that is the one
        still being written, and its chunks file can be behind its vectors file. Scoring a growing
        store without it is safe; chunk() on the live shard is not (Wren Keeler, 2026-10-11)."""
        self.path = Path(path)
        self.dim, self.prefix = dim, prefix
        chunk_files = sorted(self.path.glob("chunks-*.jsonl"))
        if drop_live:
            chunk_files = chunk_files[:-1]
        if not chunk_files:
            raise StoreError(f"no chunks-*.jsonl in {self.path}" + (" besides the live shard" if drop_live else ""))
        self.chunk_files, self.maps, self.starts = chunk_files, [], []
        total, files = 0, []
        for c in chunk_files:
            v = c.with_name(c.name.replace("chunks-", "vectors-").replace(".jsonl", ".f32"))
            if not v.exists():
                raise StoreError(f"{c.name} has no {v.name}")
            size = v.stat().st_size
            if size % (dim * 4):
                raise StoreError(f"{v.name} is {size} bytes, not a whole number of {dim}-wide rows")
            n = size // (dim * 4)
            self.starts.append(total)
            files.append((v, n))
            total += n
        mapped = lambda: [np.memmap(v, dtype=np.float32, mode="r", shape=(n, dim)) if n else
                          np.zeros((0, dim), dtype=np.float32) for v, n in files]
        self.maps = mapped()
        self.n = total
        if memcheck is not None:                       # e.g. memguard.require
            memcheck(self.n * prefix * 4 / 2**30)
        self.short = np.empty((self.n, prefix), dtype=np.float32)
        for start, m in zip(self.starts, self.maps):
            for i in range(0, len(m), SCAN_BLOCK):
                block = np.asarray(m[i:i + SCAN_BLOCK, :prefix])
                self.short[start + i:start + i + len(block)] = _unit(block)
        # Building the shortlist touched every page of every vectors file, and those pages stay counted
        # in this process's working set (17 GiB for 3.6 M rows) for as long as the maps live. Map the
        # files again and let the first maps go: the pages return to the file cache, where the system
        # can reuse them, and a search only pulls in the rows it re-scores.
        block = m = None
        self.maps = mapped()
        self._offsets = {}

    # -- rows ------------------------------------------------------------------------------
    def _locate(self, row):
        if not 0 <= row < self.n:
            raise IndexError(row)
        s = int(np.searchsorted(self.starts, row, side="right")) - 1
        return s, row - self.starts[s]

    def vectors(self, rows):
        """Full vectors for `rows`, in the order asked. Read one shard at a time, not one row at a time:
        the per-row loop was the shortlist's whole latency cost (Wren Keeler's measurement, 2026-10-11)."""
        rows = np.asarray(rows, dtype=np.int64)
        out = np.empty((len(rows), self.dim), dtype=np.float32)
        if len(rows) == 0:
            return out
        if rows.min() < 0 or rows.max() >= self.n:
            raise IndexError(int(rows.min() if rows.min() < 0 else rows.max()))
        shard = np.searchsorted(self.starts, rows, side="right") - 1
        for s in np.unique(shard):
            at = np.nonzero(shard == s)[0]
            local = rows[at] - self.starts[s]
            order = np.argsort(local, kind="stable")           # ascending reads from the memory map
            out[at[order]] = self.maps[s][local[order]]
        return out

    def _shard_offsets(self, s):
        """Byte offset of each row of a chunks file. Refuses a file whose row count differs
        from its vectors file: row k of one must be row k of the other."""
        if s not in self._offsets:
            offs, pos = [], 0
            with open(self.chunk_files[s], "rb") as f:
                for line in f:
                    offs.append(pos)
                    pos += len(line)
            if len(offs) != len(self.maps[s]):
                raise StoreError(f"{self.chunk_files[s].name} has {len(offs)} rows, "
                                 f"its vectors file has {len(self.maps[s])}")
            self._offsets[s] = offs
        return self._offsets[s]

    def chunk(self, row):
        s, k = self._locate(int(row))
        with open(self.chunk_files[s], "rb") as f:
            f.seek(self._shard_offsets(s)[k])
            return json.loads(f.readline().decode("utf-8"))

    # -- scoring ---------------------------------------------------------------------------
    def exact(self, q, k):
        """The reference answer: every row scored against its full vector. (rows, scores)."""
        best_r, best_s = np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float32)
        for start, m in zip(self.starts, self.maps):
            for i in range(0, len(m), SCAN_BLOCK):
                sc = np.asarray(m[i:i + SCAN_BLOCK]) @ q
                best_r = np.concatenate([best_r, np.arange(start + i, start + i + len(sc))])
                best_s = np.concatenate([best_s, sc])
                if len(best_s) > k:
                    keep = np.argpartition(-best_s, k - 1)[:k]
                    best_r, best_s = best_r[keep], best_s[keep]
        return _ordered(best_r, best_s, k)

    def fast(self, q, k, shortlist=SHORTLIST):
        """Shortlist on the prefix, exact re-score of the shortlist. (rows, scores, timings)."""
        t0 = time.perf_counter()
        qp = _unit(q[:self.prefix])
        sc = self.short @ qp
        m = min(max(shortlist, k), self.n)
        cand = np.argpartition(-sc, m - 1)[:m] if m < self.n else np.arange(self.n)
        t1 = time.perf_counter()
        cand = np.sort(cand)                                  # disk order for the re-read
        full = self.vectors(cand) @ q
        rows, scores = _ordered(cand, full, k)
        t2 = time.perf_counter()
        return rows, scores, {"shortlist_ms": (t1 - t0) * 1000, "rescore_ms": (t2 - t1) * 1000}


def _ordered(rows, scores, k):
    """Best k, highest score first; equal scores in row order so two runs agree."""
    order = np.lexsort((rows, -scores))[:k]
    return rows[order].astype(np.int64), scores[order].astype(np.float32)


def agreement(fast_rows, exact_rows):
    """How far the fast answer is from the exact one, as numbers only."""
    f, e = [int(x) for x in fast_rows], [int(x) for x in exact_rows]
    missed = [r for r in e if r not in set(f)]
    return {"k": len(e), "missed": len(missed), "same_order": f == e,
            "top1_same": bool(f and e and f[0] == e[0]),
            "worst_missed_rank": (min(e.index(r) for r in missed) + 1) if missed else None}


class Search:
    """Store plus telemetry. `embed` turns a question into a unit vector of width DIM."""

    def __init__(self, store, log_path, embed=None, sample_every=SAMPLE_EVERY, shortlist=SHORTLIST):
        self.store, self.embed = store, embed
        self.log_path = Path(log_path) if log_path else None
        self.sample_every, self.shortlist, self.count = sample_every, shortlist, 0

    def ask(self, question, k=10):
        t0 = time.perf_counter()
        q = np.asarray(self.embed(question), dtype=np.float32)
        return self.by_vector(q, k, embed_ms=(time.perf_counter() - t0) * 1000)

    def by_vector(self, q, k=10, embed_ms=None, force_sample=False):
        if q.shape != (self.store.dim,):
            raise ValueError(f"question vector shape {q.shape}, expected ({self.store.dim},)")
        q = _unit(q)
        rows, scores, t = self.store.fast(q, k, self.shortlist)
        self.count += 1
        rec = {"at": _now().strftime("%Y-%m-%dT%H:%M:%SZ"), "rows": self.store.n, "k": k,
               "shortlist": self.shortlist, "prefix": self.store.prefix,
               "embed_ms": None if embed_ms is None else round(embed_ms, 2),
               "shortlist_ms": round(t["shortlist_ms"], 2), "rescore_ms": round(t["rescore_ms"], 2),
               "top_rows": [int(r) for r in rows], "top_score": round(float(scores[0]), 4) if len(scores) else None,
               "sampled": False}
        if force_sample or (self.sample_every and self.count % self.sample_every == 0):
            t0 = time.perf_counter()
            e_rows, _ = self.store.exact(q, k)
            rec.update(sampled=True, exact_ms=round((time.perf_counter() - t0) * 1000, 2),
                       **agreement(rows, e_rows))
        self._log(rec)
        return rows, scores, rec

    def _log(self, rec):
        if self.log_path is None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec) + "\n")


class NotReady(Exception):
    """The resident store cannot answer yet, or at all. str() says which."""


class Resident:
    """A store opened once, in the background, and kept for the life of the process.

    Opening reads every vector to build the shortlist matrix (16 s for 3.6 M rows with the files in the
    page cache, longer cold), so it cannot be done per question. `state` is "idle", "loading", "ready"
    or "failed"; ask() raises NotReady in every state but "ready", so a caller can fall back and say why.
    """

    def __init__(self, path, log_path=None, shortlist=SHORTLIST, embed=None, memcheck=None, open_store=None, prefix=PREFIX,
                 query_prefix=""):
        self.path = Path(path)
        self.log_path = Path(log_path) if log_path else self.path / "search-telemetry.jsonl"
        self.shortlist, self.embed, self.memcheck = shortlist, embed, memcheck
        # The text put in front of every question before it is embedded: "" (bare) or MXBAI_QUERY_PREFIX.
        # Wren Keeler's v2 re-test (2026-10-16) favoured the prefix; the Operator said yes the same day.
        self.query_prefix = query_prefix
        self._open = open_store or (lambda: Store(self.path, prefix=prefix, memcheck=self.memcheck))
        self.state, self.error, self.search, self.opened_s = "idle", None, None, None
        self._lock, self._thread = threading.Lock(), None

    def start(self):
        """Begin opening the store if that has not been tried. Returns at once."""
        with self._lock:
            if self.state != "idle":
                return self
            self.state = "loading"
            self._thread = threading.Thread(target=self._load, name="private-search-open", daemon=True)
            self._thread.start()
        return self

    def _load(self):
        t0 = time.perf_counter()
        try:
            store = self._open()
            self.search = Search(store, self.log_path, embed=self.embed or (lambda t: ollama_embed(t, self.query_prefix)),
                                 shortlist=self.shortlist)
            self.opened_s = round(time.perf_counter() - t0, 1)
            self.state = "ready"
        except Exception as e:                                  # named, never swallowed: ask() reports it
            self.error = f"{type(e).__name__}: {e}"
            self.state = "failed"

    def wait(self, timeout=None):
        if self._thread is not None:
            self._thread.join(timeout)
        return self.state

    def ask(self, question, k):
        """([chunk dicts, best first, each with "score"], the telemetry row). One question at a time."""
        if self.state != "ready":
            raise NotReady({"idle": "the store has not been opened", "loading": "the store is still opening",
                            "failed": f"the store did not open ({self.error})"}[self.state])
        with self._lock:
            rows, scores, rec = self.search.ask(question, k)
            return [{**self.search.store.chunk(r), "score": float(s)} for r, s in zip(rows, scores)], rec

    def status(self):
        s = self.search.store if self.search else None
        return {"state": self.state, "error": self.error, "rows": s.n if s else None, "prefix": s.prefix if s else None,
                "shortlist": self.shortlist, "query_prefix": bool(self.query_prefix), "opened_s": self.opened_s,
                "shortlist_gib": round(s.short.nbytes / 2**30, 2) if s else None}


def summary(log_path, now=None, hours=24):
    """A day of telemetry as numbers for the briefing. Unreadable rows are counted, never dropped."""
    now = now or _now()
    since = now - timedelta(hours=hours)
    rows, bad = [], 0
    p = Path(log_path)
    if not p.exists():
        return {"searches": 0, "unreadable_rows": 0, "log": "missing"}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
            at = datetime.strptime(r["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (ValueError, KeyError, TypeError):
            bad += 1
            continue
        if since < at <= now:
            rows.append(r)
    out = {"searches": len(rows), "unreadable_rows": bad, "log": "read"}
    if not rows:
        return out
    lat = sorted(r["shortlist_ms"] + r["rescore_ms"] for r in rows)
    samp = [r for r in rows if r.get("sampled")]
    out.update(median_ms=round(lat[len(lat) // 2], 1), p95_ms=round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 1),
               slowest_ms=round(lat[-1], 1), sampled=len(samp),
               sampled_with_a_miss=sum(1 for r in samp if r["missed"]),
               results_missed=sum(r["missed"] for r in samp),
               results_checked=sum(r["k"] for r in samp),
               top1_changed=sum(1 for r in samp if not r["top1_same"]))
    return out


def summary_lines(s):
    if s.get("log") == "missing":
        return ["private search: no telemetry log yet"]
    if not s["searches"]:
        return [f"private search: 0 searches in the window ({s['unreadable_rows']} unreadable rows)"]
    lines = [f"private search: {s['searches']} searches, median {s['median_ms']:.1f} ms, "
             f"95th {s['p95_ms']:.1f} ms, slowest {s['slowest_ms']:.1f} ms"]
    if s["sampled"]:
        lines.append(f"checked against exact search: {s['sampled']} searches, "
                     f"{s['results_missed']} of {s['results_checked']} results missed, "
                     f"top result changed in {s['top1_changed']}")
    else:
        lines.append("checked against exact search: none sampled in the window")
    if s["unreadable_rows"]:
        lines.append(f"telemetry rows that could not be read: {s['unreadable_rows']}")
    return lines


def ollama_embed(question, prefix=""):
    import requests
    from dex_core import EMBED_MODEL, OLLAMA_HOST
    r = requests.post(f"{OLLAMA_HOST}/api/embed",
                      json={"model": EMBED_MODEL, "input": [prefix + question], "truncate": False},
                      timeout=120)
    r.raise_for_status()
    return r.json()["embeddings"][0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", required=True, type=Path)
    ap.add_argument("--log", type=Path, default=None, help="telemetry JSONL (default: <store>/search-telemetry.jsonl)")
    ap.add_argument("--ask", default=None)
    ap.add_argument("-k", type=int, default=10)
    ap.add_argument("--selftest", type=int, default=0,
                    help="N searches using stored rows as questions, every one checked against exact; "
                         "prints numbers only and writes to a separate log")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--mxbai-prefix", action="store_true", help="embed the question in mxbai's query form")
    a = ap.parse_args()
    log = a.log or a.store / "search-telemetry.jsonl"
    if a.summary:
        print("\n".join(summary_lines(summary(log))))
        return
    import memguard
    t0 = time.perf_counter()
    store = Store(a.store, memcheck=lambda gb: memguard.require(need_gb=gb, what="private-search shortlist"))
    print(f"opened {store.n} rows in {time.perf_counter() - t0:.1f} s; shortlist {store.short.nbytes / 2**20:.0f} MiB")
    if a.selftest:
        tlog = a.store / "search-selftest.jsonl"
        s = Search(store, tlog)
        rng = np.random.default_rng(int(hashlib.sha256(str(a.store).encode()).hexdigest()[:8], 16))
        for r in rng.choice(store.n, size=min(a.selftest, store.n), replace=False):
            q = store.vectors([r])[0] + rng.normal(0, 0.02, store.dim).astype(np.float32)
            s.by_vector(q, a.k, force_sample=True)
        print("\n".join(summary_lines(summary(tlog))))
        return
    if a.ask:
        pre = MXBAI_QUERY_PREFIX if a.mxbai_prefix else ""
        s = Search(store, log, embed=lambda t: ollama_embed(t, pre))
        rows, scores, rec = s.ask(a.ask, a.k)
        for r, sc in zip(rows, scores):
            c = store.chunk(r)
            print(f"{sc:.4f}  {c['source_root']}/{c['rel_path']}  [{c['chunk_index'] + 1}/{c['total_chunks']}]")
        print({k: v for k, v in rec.items() if k != "top_rows"})


if __name__ == "__main__":
    sys.exit(main())
