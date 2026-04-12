"""Step 33a — structure-aware re-chunker + 10K subset builder.

Reconstructs document texts from dex_canon chunks (deduping overlap),
re-chunks using a structure-aware splitter targeted at ~400 tokens
(~1600 chars), and re-embeds with mxbai-embed-large into a new
collection `dex_canon_mxbai_rechunk_test`.

Read-only against live collections. Creates one new collection.
"""
from __future__ import annotations
import json
import re
import sys
import time

import chromadb
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"
OLLAMA = "http://localhost:11434"
MODEL = "mxbai-embed-large"
SOURCE_COL = "dex_canon"
TEST_COL = "dex_canon_mxbai_rechunk_test"
STEP32_COL = "dex_canon_mxbai_test"

# Chunker config (structure-aware, 400 token target)
CHARS_PER_TOKEN = 4
TARGET_TOKENS = 400
OVERLAP_TOKENS = 50
MIN_TOKENS = 50
TARGET_CHARS = TARGET_TOKENS * CHARS_PER_TOKEN   # 1600
OVERLAP_CHARS = OVERLAP_TOKENS * CHARS_PER_TOKEN  # 200
MIN_CHARS = MIN_TOKENS * CHARS_PER_TOKEN          # 200

# Embedding truncation safety for mxbai's 512-token context
MXBAI_MAX_CHARS = 1200
BATCH_SIZE = 8   # best throughput per _step33a_batching_probe.py
TARGET_CHUNK_COUNT = 10_000

# Identifier patterns for extra file inclusion
IDENT_PAT = re.compile(r"^(STD-|CR-|ADR-|PRO-|OBS-|SYS-)[A-Z0-9-]+(\.txt|\.md)?$")

SEPARATOR_RE = re.compile(r"^\s*=+\s*$", re.MULTILINE)
HEADER_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)


# ── text reconstruction ────────────────────────────────────────────
def dedupe_overlap(prev: str, cur: str, max_overlap: int = 300) -> str:
    """Return cur with its longest-matching prefix against prev-suffix stripped."""
    if not prev or not cur:
        return cur
    limit = min(len(prev), len(cur), max_overlap)
    # find longest k ≤ limit s.t. prev[-k:] == cur[:k]
    for k in range(limit, 20, -1):
        if prev[-k:] == cur[:k]:
            return cur[k:]
    return cur


def reconstruct_document(src_col, source_file: str) -> str:
    got = src_col.get(where={"source_file": source_file},
                      include=["documents", "metadatas"])
    ids = got.get("ids", []) or []
    docs = got.get("documents", []) or []
    # chunk ids end with `_cN` — sort by N
    def idx(cid: str) -> int:
        m = re.search(r"_c(\d+)$", cid)
        return int(m.group(1)) if m else 0
    ordered = sorted(zip(ids, docs), key=lambda x: idx(x[0]))
    out = []
    prev = ""
    for _, d in ordered:
        d = d or ""
        if not out:
            out.append(d)
        else:
            out.append(dedupe_overlap(prev, d))
        prev = d
    return "".join(out)


# ── structure-aware chunker ────────────────────────────────────────
def _split_on(text: str, pattern: re.Pattern) -> list[str]:
    """Split text on pattern, keeping the boundary attached to the
    chunk that follows (so headers stay at the top of their section)."""
    parts = []
    last = 0
    for m in pattern.finditer(text):
        if m.start() > last:
            parts.append(text[last:m.start()])
        last = m.start()
    if last < len(text):
        parts.append(text[last:])
    return [p for p in parts if p.strip()]


def _split_section(section: str, target: int) -> list[str]:
    """Sub-split a section that exceeds target using paragraph →
    sentence → hard-cut priorities."""
    if len(section) <= target:
        return [section]
    out: list[str] = []
    # paragraphs
    paras = re.split(r"\n\s*\n", section)
    buf = ""
    for p in paras:
        if not p.strip():
            continue
        candidate = (buf + "\n\n" + p) if buf else p
        if len(candidate) <= target:
            buf = candidate
        else:
            if buf:
                out.append(buf)
            if len(p) <= target:
                buf = p
            else:
                # sentence split
                sents = re.split(r"(?<=[.!?])\s+(?=[A-Z])", p)
                sbuf = ""
                for s in sents:
                    if len(sbuf) + len(s) + 1 <= target:
                        sbuf = (sbuf + " " + s) if sbuf else s
                    else:
                        if sbuf:
                            out.append(sbuf)
                        if len(s) <= target:
                            sbuf = s
                        else:
                            # hard cut
                            for i in range(0, len(s), target):
                                out.append(s[i:i + target])
                            sbuf = ""
                if sbuf:
                    buf = sbuf
                else:
                    buf = ""
    if buf:
        out.append(buf)
    return out


def rechunk(text: str) -> list[str]:
    if not (text or "").strip():
        return []
    text = text.strip()

    # Strategy 1: split on ===== separator lines.
    sections = re.split(r"\n\s*=+\s*\n", text)
    sections = [s.strip() for s in sections if s.strip()]

    # Strategy 2 (within each section): split further on markdown headers.
    pieces: list[str] = []
    for s in sections:
        hdr_pieces = _split_on(s, HEADER_RE)
        if hdr_pieces:
            pieces.extend(hdr_pieces)
        else:
            pieces.append(s)

    # Strategy 3: enforce size cap via paragraph/sentence/hard-cut.
    sized: list[str] = []
    for p in pieces:
        sized.extend(_split_section(p, TARGET_CHARS))

    # Merge small neighbors
    merged: list[str] = []
    for c in sized:
        c = c.strip()
        if not c:
            continue
        if merged and len(merged[-1]) < MIN_CHARS and \
                len(merged[-1]) + len(c) + 2 <= TARGET_CHARS * 2:
            merged[-1] = merged[-1] + "\n\n" + c
        else:
            merged.append(c)

    # Apply overlap: prepend last OVERLAP_CHARS of prev chunk to next
    if len(merged) <= 1:
        return merged
    out = [merged[0]]
    for i in range(1, len(merged)):
        tail = merged[i - 1][-OVERLAP_CHARS:]
        # Only add overlap if it won't inflate beyond target+overlap
        out.append(tail + "\n" + merged[i])
    return out


# ── embedding ──────────────────────────────────────────────────────
def embed_batch(texts: list[str]) -> list[list[float]] | None:
    for lim in (MXBAI_MAX_CHARS, 900, 600, 300):
        trimmed = [(t or "")[:lim] for t in texts]
        try:
            r = requests.post(f"{OLLAMA}/api/embed",
                              json={"model": MODEL, "input": trimmed},
                              timeout=300)
            if r.status_code == 200:
                return r.json()["embeddings"]
        except Exception:
            continue
    return None


# ── main ───────────────────────────────────────────────────────────
def main():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    src = client.get_collection(SOURCE_COL)

    # 1. Collect source_files to re-chunk
    # From Step 32's test collection (union of source_files)
    step32 = client.get_collection(STEP32_COL)
    s32 = step32.get(include=["metadatas"])
    step32_files = sorted({(m or {}).get("source_file") for m in s32["metadatas"]
                           if (m or {}).get("source_file")})
    print(f"Step 32 source_files: {len(step32_files)}")

    # Plus files whose name looks like a governance identifier — paged scan
    extra: set[str] = set()
    PAGE = 2000
    seen_sources: set[str] = set()
    for off in range(0, 100_000, PAGE):
        try:
            page = src.get(include=["metadatas"], limit=PAGE, offset=off)
        except Exception as e:
            print(f"  [warn] page {off} failed: {e}")
            break
        metas = page.get("metadatas") or []
        if not metas:
            break
        for m in metas:
            sf = (m or {}).get("source_file") or ""
            if sf in seen_sources:
                continue
            seen_sources.add(sf)
            if IDENT_PAT.match(sf):
                extra.add(sf)
        if len(metas) < PAGE:
            break
    print(f"Identifier-named files: {len(extra)}  (seen {len(seen_sources)} unique sources)")
    selected_files = sorted(set(step32_files) | extra)
    print(f"Selected files for rechunk: {len(selected_files)}")

    # 2. Reconstruct + rechunk
    print("\nReconstructing documents + re-chunking...")
    rechunked: list[dict] = []  # list of {id, text, source_file, ingest_run_id}
    per_file_counts: dict[str, int] = {}
    for sf in selected_files:
        try:
            text = reconstruct_document(src, sf)
            if not text.strip():
                continue
            # Also grab ingest_run_id for metadata
            sample = src.get(where={"source_file": sf}, limit=1,
                             include=["metadatas"])
            smeta = (sample.get("metadatas") or [{}])[0] or {}
            ingest_run_id = smeta.get("ingest_run_id", "")
            new_chunks = rechunk(text)
            per_file_counts[sf] = len(new_chunks)
            for i, ch in enumerate(new_chunks):
                rechunked.append({
                    "id": f"rechunk_{abs(hash(sf)):016x}_c{i}",
                    "text": ch,
                    "source_file": sf,
                    "ingest_run_id": ingest_run_id,
                })
        except Exception as e:
            print(f"  [warn] {sf}: {e}")
            continue

    # Fill with additional general content if we're under target
    if len(rechunked) < TARGET_CHUNK_COUNT:
        print(f"  at {len(rechunked)} chunks; expanding with general sample...")
        have_files = set(selected_files)
        # Reuse already-seen source files from the earlier paged scan
        ordered_pool = [sf for sf in seen_sources if sf and sf not in have_files]
        for sf in ordered_pool:
            if len(rechunked) >= TARGET_CHUNK_COUNT:
                break
            try:
                text = reconstruct_document(src, sf)
                if not text.strip():
                    continue
                sample = src.get(where={"source_file": sf}, limit=1,
                                 include=["metadatas"])
                smeta = (sample.get("metadatas") or [{}])[0] or {}
                ingest_run_id = smeta.get("ingest_run_id", "")
                new_chunks = rechunk(text)
                per_file_counts[sf] = len(new_chunks)
                for i, ch in enumerate(new_chunks):
                    rechunked.append({
                        "id": f"rechunk_{abs(hash(sf)):016x}_c{i}",
                        "text": ch,
                        "source_file": sf,
                        "ingest_run_id": ingest_run_id,
                    })
                    if len(rechunked) >= TARGET_CHUNK_COUNT:
                        break
            except Exception:
                continue

    # Cap to target
    if len(rechunked) > TARGET_CHUNK_COUNT * 1.15:
        rechunked = rechunked[:TARGET_CHUNK_COUNT]

    print(f"\nTotal re-chunked units: {len(rechunked)}")
    lens = [len(r["text"]) for r in rechunked]
    print(f"  len min/mean/max (chars): {min(lens)}/{sum(lens)//len(lens)}/{max(lens)}")
    tok_est = [l // CHARS_PER_TOKEN for l in lens]
    print(f"  est tokens min/mean/max: {min(tok_est)}/{sum(tok_est)//len(tok_est)}/{max(tok_est)}")

    # 3. Create/reset target collection
    try:
        client.delete_collection(TEST_COL)
        print(f"  dropped existing {TEST_COL}")
    except Exception:
        pass
    tcol = client.create_collection(
        TEST_COL,
        metadata={
            "description": "B1 pre-migration validation: re-chunked + mxbai",
            "test_only": "true",
            "embedding_model": MODEL,
            "chunker_version": "structure_aware_400tok_v1",
            "parent_collection": SOURCE_COL,
        },
    )
    print(f"  created {TEST_COL}")

    # 4. Embed + upsert in batches
    print(f"\nEmbedding {len(rechunked)} chunks batch={BATCH_SIZE}...")
    t0 = time.time()
    skipped = 0
    for i in range(0, len(rechunked), BATCH_SIZE):
        batch = rechunked[i:i + BATCH_SIZE]
        texts = [b["text"] for b in batch]
        embs = embed_batch(texts)
        if embs is None:
            skipped += len(batch)
            continue
        ids = [b["id"] for b in batch]
        docs = [b["text"] for b in batch]
        metas = [{"source_file": b["source_file"],
                  "ingest_run_id": b["ingest_run_id"],
                  "chunker_version": "structure_aware_400tok_v1"}
                 for b in batch]
        tcol.upsert(ids=ids, embeddings=embs, documents=docs, metadatas=metas)
        done = min(i + BATCH_SIZE, len(rechunked))
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        eta = (len(rechunked) - done) / rate if rate > 0 else 0
        if done % (BATCH_SIZE * 10) == 0 or done == len(rechunked):
            print(f"  {done}/{len(rechunked)}  rate={rate:.1f} c/s  "
                  f"eta={eta:.0f}s  skipped={skipped}")

    elapsed = time.time() - t0
    rate = len(rechunked) / elapsed if elapsed > 0 else 0
    print("\n" + "=" * 60)
    print(f"DONE  {len(rechunked)} chunks  elapsed={elapsed:.0f}s  rate={rate:.2f} c/s")
    print(f"Skipped (all truncation levels failed): {skipped}")
    print("=" * 60)

    # 5. Quality spot check: 10 random re-chunks
    import random
    random.seed(42)
    sample = random.sample(rechunked, min(10, len(rechunked)))
    spot = []
    for s in sample:
        t = s["text"]
        head = t[:80].replace("\n", " ")
        mid_word = (bool(t) and t[0].isalnum()
                    and not t[0].isupper()
                    and not t.startswith(("#", "=", "-", "*")))
        tok = len(t) // CHARS_PER_TOKEN
        spot.append({"source_file": s["source_file"], "chars": len(t),
                     "est_tokens": tok, "starts_mid_word": mid_word,
                     "head": head})
    print("\nSpot check (10 random re-chunks):")
    for s in spot:
        mw = "MID-WORD" if s["starts_mid_word"] else "ok"
        print(f"  [{mw}] tok~{s['est_tokens']:>4}  src={s['source_file'][:60]}")
        print(f"      HEAD: {s['head']}")

    out = {
        "n_source_files": len(selected_files),
        "total_rechunks": len(rechunked),
        "skipped": skipped,
        "elapsed_sec": round(elapsed, 1),
        "chunks_per_sec": round(rate, 2),
        "char_min": min(lens), "char_mean": sum(lens)//len(lens), "char_max": max(lens),
        "chunker_config": {
            "target_tokens": TARGET_TOKENS, "overlap_tokens": OVERLAP_TOKENS,
            "min_tokens": MIN_TOKENS, "chars_per_token": CHARS_PER_TOKEN,
        },
        "spot_check": spot,
    }
    with open("_step33a_rechunk_builder.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)


if __name__ == "__main__":
    main()
