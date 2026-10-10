"""
dex-private-rebuild.py -- the private search store, rebuilt as plain files.

Operator approval: retrieval rethink, 2026-10-04 (exact search, ~1,500-char chunks that carry
their title and path, plain files instead of Chroma); ddl-corpus added as a root, 2026-10-09
(_shared/OPERATOR-DECISIONS.md in ddl-org). This writes a NEW store beside the live one. It
never opens Chroma, never touches ddl_private_v1, and nothing answers from its output until the
Operator says to switch.

Why it exists, measured on the live store:
  - chunks are 3,200 chars and dex_core.embed embeds the first 1,200, so 62% of each chunk
    was never searchable;
  - a chunk's vector knew nothing of the file it came from;
  - Chroma's HNSW index missed mid-rank neighbours that exact scoring finds.

What it does differently:
  - STRICT EMBED. The text sent to the model is the text stored. Ollama is called with
    truncate=false; text over the model's context is split in half and retried, never cut.
  - Every chunk is embedded with a two-line header: its file name and its path under the root.
  - Output is two kinds of file per shard, in --out:
        chunks-NNNN.jsonl   one row per chunk: id, text, provenance
        vectors-NNNN.f32    the same rows' vectors, float32, unit length, row-major
    plus files.jsonl (one row per source file read, with its outcome) and build.json.
    Row k of a chunks file is row k of its vectors file. Exact search is one matrix product.

Resumable: a file whose content hash is already in files.jsonl is skipped.

    python dex-private-rebuild.py --out D:\\DDL_Private\\search\\v2 --roots orphan --dry-run
    python dex-private-rebuild.py --out D:\\DDL_Private\\search\\v2
"""
import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests

import memguard
from dex_core import EMBED_MODEL, OLLAMA_HOST

_spec = importlib.util.spec_from_file_location(
    "ingest_everything", Path(__file__).with_name("dex-ingest-everything.py"))
ie = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ie)

CHUNK_CHARS = 1500
CHUNK_OVERLAP = 200
MIN_SPLIT_CHARS = 200          # below this an over-context piece is recorded, not split again
BATCH = 32
SHARD_ROWS = 50_000
DIM = 1024                     # mxbai-embed-large; checked against the first vector

# The live private roots, plus ddl-corpus (google-takeout, orphan-recovery).
ROOTS = dict(ie.PRIVATE_ROOTS)
ROOTS["corpus"] = (r"C:\Users\dexjr\ddl-corpus", "private")
SKIP_DIRS = ie.SKIP_DIRS | ie.PRIVATE_SKIP
# Canon Steward's condition on the 170 recovered documents (Ezra Locke / DDL-3008): every chunk
# from them says so, so nothing cites recovered text as if it were the original.
RECOVERED_MARK = "/corpus/orphan-recovery/"


def chunk_text(t):
    """Same shape as dex-ingest-everything.chunk_text, at this store's size."""
    t = (t or "").strip()
    if not t:
        return []
    if len(t) <= CHUNK_CHARS:
        return [t]
    out, start, n = [], 0, len(t)
    while start < n:
        end = min(n, start + CHUNK_CHARS)
        if end < n:
            brk = t.rfind("\n\n", start + CHUNK_CHARS // 2, end)
            if brk > start:
                end = brk
        piece = t[start:end].strip()
        if piece:
            out.append(piece)
        if end >= n:
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return out


def header(name, rel):
    return f"file: {name}\npath: {rel}\n\n"


class OverContext(Exception):
    pass


def embed_batch(texts):
    """Vectors for texts, or OverContext if any one is too long. Nothing is truncated."""
    r = requests.post(f"{OLLAMA_HOST}/api/embed",
                      json={"model": EMBED_MODEL, "input": texts, "truncate": False},
                      timeout=600)
    if r.status_code == 400 and "context length" in r.text:
        raise OverContext()
    r.raise_for_status()
    vecs = r.json()["embeddings"]
    if len(vecs) != len(texts):
        raise RuntimeError(f"embed returned {len(vecs)} vectors for {len(texts)} texts")
    return vecs


def split_piece(piece):
    """Two halves of an over-context piece, broken at whitespace near the middle."""
    mid = len(piece) // 2
    brk = -1
    for sep in ("\n", " "):
        # the break NEAREST the middle. (Until 2026-10-10 this took the last one in the window,
        # which sits near the three-quarter mark: lopsided halves, so more splits and more
        # slivers than needed. Found by test_dex_private_rebuild.py.)
        before = piece.rfind(sep, mid // 2, mid + 1)
        after = piece.find(sep, mid, mid + mid // 2)
        near = [b for b in (before, after) if b > 0]
        if near:
            brk = min(near, key=lambda b: abs(b - mid))
            break
    if brk <= 0:
        brk = mid
    return piece[:brk].strip(), piece[brk:].strip()


def embed_pieces(head, pieces, stats):
    """[(piece, vector, depth)] with every piece embedded whole under its header. A piece the
    model refuses is split and retried; one too small to split is counted and left out.
    depth is how many times the piece was halved to fit (0 = the chunker's own piece), so the
    store records its real chunk sizes and not only the size it aimed for (Wren Keeler, 2026-10-10)."""
    # Each piece carries its place in the document as a key: (i,) for the chunker's piece i,
    # key + (0,) and key + (1,) for its halves. Results are returned in key order, so chunk
    # numbers follow the document even when pieces are retried out of turn. (Until 2026-10-10
    # they were returned in the order the retries finished, which put a later piece's halves
    # ahead of an earlier one's. Found by test_dex_private_rebuild.py.)
    out, todo = [], [(p, 0, (i,)) for i, p in enumerate(pieces)]
    while todo:
        batch, todo = todo[:BATCH], todo[BATCH:]
        try:
            vecs = embed_batch([head + p for p, _, _ in batch])
            out.extend((key, p, v, d) for (p, d, key), v in zip(batch, vecs))
            continue
        except OverContext:
            pass
        for p, d, key in batch:              # find the long ones one at a time
            try:
                out.append((key, p, embed_batch([head + p])[0], d))
            except OverContext:
                if len(p) < MIN_SPLIT_CHARS:
                    stats["chunks_unembeddable"] += 1
                    continue
                a, b = split_piece(p)
                stats["chunks_split"] += 1
                todo = [(x, d + 1, key + (h,)) for h, x in enumerate((a, b)) if x] + todo
    out.sort(key=lambda t: t[0])
    return [(p, v, d) for _, p, v, d in out]


class Store:
    def __init__(self, out):
        self.out = out
        out.mkdir(parents=True, exist_ok=True)
        done = sorted(out.glob("chunks-*.jsonl"))
        self.shard = len(done)
        self.rows = 0
        self.total = 0
        for c in done:
            n = sum(1 for _ in c.open(encoding="utf-8"))
            v = c.with_name(c.name.replace("chunks-", "vectors-").replace(".jsonl", ".f32"))
            if v.stat().st_size != n * DIM * 4:
                sys.exit(f"refusing to resume: {c.name} has {n} rows, {v.name} does not match")
            self.total += n
        if done:                              # keep filling the last shard if it has room
            last = sum(1 for _ in done[-1].open(encoding="utf-8"))
            if last < SHARD_ROWS:
                self.shard, self.rows = len(done) - 1, last

    def add(self, rows, vecs):
        """Append one file's chunks. Vectors first, then rows, both flushed: a crash between
        them leaves a vectors file longer than its rows, which the resume check refuses."""
        a = np.asarray(vecs, dtype=np.float32)
        if a.ndim != 2 or a.shape[1] != DIM:
            raise RuntimeError(f"vector shape {a.shape}, expected (n, {DIM})")
        norms = np.linalg.norm(a, axis=1, keepdims=True)
        if not np.all(norms > 0):
            raise RuntimeError("zero vector from the embedder")
        a = a / norms
        if self.rows + len(rows) > SHARD_ROWS and self.rows:
            self.shard, self.rows = self.shard + 1, 0
        tag = f"{self.shard:04d}"
        with open(self.out / f"vectors-{tag}.f32", "ab") as f:
            f.write(a.tobytes())
            f.flush(); os.fsync(f.fileno())
        with open(self.out / f"chunks-{tag}.jsonl", "a", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush(); os.fsync(f.fileno())
        self.rows += len(rows)
        self.total += len(rows)


def main():
    global CHUNK_CHARS
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--roots", default="all", help=f"comma-separated from {list(ROOTS)}, or 'all'")
    ap.add_argument("--under", default=None, help="only files whose path contains this text")
    ap.add_argument("--limit", type=int, default=0, help="max files (0 = no cap)")
    ap.add_argument("--dry-run", action="store_true", help="scan, chunk and count; embed nothing")
    ap.add_argument("--chunk-chars", type=int, default=CHUNK_CHARS,
                    help="target chunk size; recorded in build.json")
    ap.add_argument("--pause", type=float, default=0.0,
                    help="seconds to sleep after each file (leave the GPU room for live answers)")
    args = ap.parse_args()

    CHUNK_CHARS = args.chunk_chars
    selected = list(ROOTS) if args.roots == "all" else [r.strip() for r in args.roots.split(",")]
    unknown = [r for r in selected if r not in ROOTS]
    if unknown:
        sys.exit(f"unknown root(s): {unknown}\nvalid: {list(ROOTS)}")

    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stats = {k: 0 for k in (
        "scanned", "files_indexed", "chunks", "chunks_split", "chunks_unembeddable",
        "skipped_placeholder", "skipped_dupe", "skipped_big", "skipped_empty",
        "skipped_unreadable", "skipped_excluded", "skipped_no_text", "skipped_already_built")}
    by_root = {}

    if not args.dry_run:
        # This job streams, so it needs little itself; the check is that the machine is not
        # already full when a two-day run starts beside Dex (memguard, the 2026-10-03 outage).
        try:
            room = memguard.require(need_gb=1.5, what="private-search rebuild")
        except memguard.Refused as e:
            sys.exit(f"REFUSED: {e}")
        print(f"memory: {room['free_gb']} GiB free of {room['total_gb']}\n")
    store = None if args.dry_run else Store(args.out)
    files_log = args.out / "files.jsonl"
    seen = set()
    if not args.dry_run and files_log.exists():
        for line in files_log.open(encoding="utf-8"):
            seen.add(json.loads(line)["file_hash"])
        print(f"resume: {len(seen):,} files already built, {store.total:,} chunks on disk\n")
    built_before = set(seen)

    t0 = time.time()
    stop = False
    for name in selected:
        root = Path(ROOTS[name][0])
        if not root.is_dir():
            print(f"  ABSENT  {name}")
            continue
        r_files = r_chunks = 0
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for fn in sorted(filenames):
                p = Path(dirpath) / fn
                if p.suffix.lower() not in ie.TEXTY:
                    continue
                if args.under and args.under not in p.as_posix():
                    continue
                stats["scanned"] += 1
                try:
                    st = p.stat()
                except OSError:
                    stats["skipped_unreadable"] += 1
                    continue
                if ie.is_placeholder(st):
                    stats["skipped_placeholder"] += 1
                    continue
                if ie.is_index_excluded(p):
                    stats["skipped_excluded"] += 1
                    continue
                why = ie.size_skip(st.st_size)
                if why:
                    stats[why] += 1
                    continue
                try:
                    raw = p.read_bytes()
                except OSError:
                    stats["skipped_unreadable"] += 1
                    continue
                fhash = hashlib.sha256(raw).hexdigest()[:16]
                if fhash in seen:
                    stats["skipped_already_built" if fhash in built_before else "skipped_dupe"] += 1
                    continue
                seen.add(fhash)
                try:
                    text = raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1", errors="replace")
                pieces = chunk_text(text)
                if not pieces:
                    stats["skipped_no_text"] += 1
                    continue

                rel = p.relative_to(root).as_posix()
                if not args.dry_run:
                    pairs = embed_pieces(header(p.name, rel), pieces, stats)
                    recovered = RECOVERED_MARK in "/" + rel
                    rows = []
                    for i, (piece, _, depth) in enumerate(pairs):
                        row = {"id": f"{fhash}_{i}", "text": piece, "split": depth, "filename": p.name,
                               "source_root": name, "rel_path": rel, "source_path": str(p),
                               "file_hash": fhash, "chunk_index": i, "total_chunks": len(pairs),
                               "injection_class": ie.injection_class(p),
                               "mtime": datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime("%Y-%m-%d")}
                        if recovered:
                            row["recovered_approximate"] = True
                        rows.append(row)
                    if rows:
                        store.add(rows, [v for _, v, _ in pairs])
                    with open(files_log, "a", encoding="utf-8", newline="\n") as f:
                        f.write(json.dumps({"file_hash": fhash, "source_root": name, "rel_path": rel,
                                            "chunks": len(rows),
                                            "chars": [len(piece) for piece, _, _ in pairs],
                                            "split": [d for _, _, d in pairs]}, ensure_ascii=False) + "\n")
                    n = len(rows)
                    if args.pause:
                        time.sleep(args.pause)
                else:
                    n = len(pieces)
                stats["files_indexed"] += 1
                stats["chunks"] += n
                r_files += 1
                r_chunks += n
                if stats["files_indexed"] % 500 == 0:
                    rate = stats["chunks"] / max(time.time() - t0, 1e-9)
                    print(f"    ... {stats['files_indexed']:,} files, {stats['chunks']:,} chunks, "
                          f"{rate:,.0f} chunks/s", flush=True)
                if args.limit and stats["files_indexed"] >= args.limit:
                    stop = True
                    break
                # A clean stop: a file named STOP in --out ends the run between two files, with
                # every row and its vector on disk. Killing the process instead can land between
                # a file's vectors and its rows, which the next start refuses.
                if not args.dry_run and (args.out / "STOP").exists():
                    print("\n[STOP file found: stopping cleanly. Delete it and run the same command to resume.]")
                    stop = True
                    break
            if stop:
                break
        by_root[name] = {"files": r_files, "chunks": r_chunks}
        print(f"  {r_files:>7,} files  {r_chunks:>9,} chunks   {name}", flush=True)
        if stop:
            print("\n[limit reached]")
            break

    print("\n" + "=" * 60)
    for k, v in stats.items():
        print(f"  {k:<24} {v:>10,}")
    if not args.dry_run:
        report = {"started_utc": started,
                  "finished_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "embed_model": EMBED_MODEL, "dim": DIM, "chunk_chars": CHUNK_CHARS,
                  "chunk_overlap": CHUNK_OVERLAP, "header": "file: <name>\\npath: <rel>\\n\\n",
                  "normalized": True, "strict_embed": True, "roots": selected,
                  "stats": stats, "by_root": by_root, "chunks_on_disk": store.total}
        with open(args.out / "build.json", "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(report) + "\n")
        print(f"\n  store {args.out} holds {store.total:,} chunks")


if __name__ == "__main__":
    main()
