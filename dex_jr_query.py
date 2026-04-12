#!/usr/bin/env python
"""
dex_jr_query.py - CC -> Dex Jr. bridge (Mechanism 1).

Read-only CLI helper for retrieval + grounded generation against the
Dex Jr. corpus. Searches all 4 ChromaDB collections by default, feeds
retrieved chunks into qwen2.5-coder:7b for a grounded answer, and
outputs in markdown / json / plain.

Invokable from any directory. No writes. No ingests. No side effects
beyond HTTP calls to Ollama and reads against ChromaDB.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import chromadb
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"
OLLAMA_HOST = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"
GEN_MODEL = "qwen2.5-coder:7b"
DEFAULT_COLLECTIONS = ["dex_canon", "ddl_archive", "dex_code", "ext_creator"]
DEFAULT_TOP_K = 3
DEFAULT_MERGE_N = 5
CHUNK_PREVIEW_CHARS = 300


def eprint(*args: Any, **kwargs: Any) -> None:
    print(*args, file=sys.stderr, **kwargs)


def embed(question: str) -> list[float]:
    r = requests.post(
        f"{OLLAMA_HOST}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": question},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["embedding"]


def generate(prompt: str) -> str:
    r = requests.post(
        f"{OLLAMA_HOST}/api/generate",
        json={"model": GEN_MODEL, "prompt": prompt, "stream": False},
        timeout=300,
    )
    r.raise_for_status()
    return r.json()["response"]


def search_collections(
    client: chromadb.api.ClientAPI,
    embedding: list[float],
    collection_names: list[str],
    top_k: int,
) -> list[dict]:
    hits: list[dict] = []
    for name in collection_names:
        try:
            col = client.get_collection(name)
        except Exception as e:
            eprint(f"  [warn] skipping collection {name}: {e}")
            continue
        res = col.query(
            query_embeddings=[embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for doc, md, dist in zip(docs, metas, dists):
            md = md or {}
            hits.append({
                "collection": name,
                "source_file": md.get("source_file") or md.get("filename") or "<unknown>",
                "ingest_run_id": md.get("ingest_run_id", ""),
                "distance": float(dist),
                "text": doc or "",
            })
    hits.sort(key=lambda h: h["distance"])
    return hits


def build_prompt(question: str, chunks: list[dict]) -> str:
    context_blocks = []
    for i, c in enumerate(chunks, 1):
        context_blocks.append(
            f"[source {i}: {c['source_file']} (collection={c['collection']})]\n{c['text']}"
        )
    context = "\n\n".join(context_blocks) if context_blocks else "(no context retrieved)"
    return (
        "Answer the question using ONLY the provided context. If the context "
        "doesn't contain the answer, say so. Cite which source_file each claim "
        "comes from.\n\n"
        f"CONTEXT:\n{context}\n\n"
        f"QUESTION: {question}"
    )


def fmt_markdown(question: str, chunks: list[dict], answer: str | None) -> str:
    lines = ["# Dex Jr. Query", "", f"**Question:** {question}", ""]
    cols_seen = sorted({c["collection"] for c in chunks})
    lines.append(f"## Retrieved chunks ({len(chunks)} across {len(cols_seen)} collections)")
    lines.append("")
    for i, c in enumerate(chunks, 1):
        preview = c["text"][:CHUNK_PREVIEW_CHARS]
        if len(c["text"]) > CHUNK_PREVIEW_CHARS:
            preview += "..."
        lines.append(
            f"### {i}. {c['source_file']} (collection: {c['collection']}, "
            f"distance: {c['distance']:.4f})"
        )
        lines.append(preview)
        lines.append("")
    if answer is not None:
        lines.append("## Answer")
        lines.append(answer.strip())
        lines.append("")
        lines.append("## Citations")
        seen = []
        for c in chunks:
            key = (c["source_file"], c["ingest_run_id"])
            if key not in seen:
                seen.append(key)
                lines.append(f"- {c['source_file']} (ingest_run_id: {c['ingest_run_id']})")
    return "\n".join(lines)


def fmt_json(question: str, chunks: list[dict], answer: str | None) -> str:
    citations = []
    for c in chunks:
        if c["source_file"] not in citations:
            citations.append(c["source_file"])
    payload = {
        "question": question,
        "chunks": chunks,
        "answer": answer,
        "citations": citations,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def fmt_plain(answer: str | None) -> str:
    return (answer or "").strip()


def run_query(args: argparse.Namespace) -> int:
    collections = [args.collection] if args.collection else DEFAULT_COLLECTIONS
    skip_answer = args.raw or args.no_answer

    try:
        embedding = embed(args.question)
    except requests.RequestException as e:
        eprint(f"ERROR: Ollama unreachable for embeddings: {e}")
        return 1

    try:
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        hits = search_collections(client, embedding, collections, args.top_k)
    except Exception as e:
        eprint(f"ERROR: ChromaDB query failed: {e}")
        return 2

    merged = hits[:DEFAULT_MERGE_N]

    answer: str | None = None
    if not skip_answer:
        if not merged:
            eprint("  [info] No relevant context found in corpus.")
        prompt = build_prompt(args.question, merged)
        try:
            answer = generate(prompt)
        except requests.RequestException as e:
            eprint(f"ERROR: Ollama unreachable for generation: {e}")
            return 1

    if args.format == "markdown":
        print(fmt_markdown(args.question, merged, answer))
    elif args.format == "json":
        print(fmt_json(args.question, merged, answer))
    elif args.format == "plain":
        print(fmt_plain(answer) if not skip_answer else "\n".join(h["text"] for h in merged))
    return 0


def run_self_test() -> int:
    steps: list[tuple[str, bool, str]] = []

    # 1. Ollama reachable
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=10)
        r.raise_for_status()
        models = {m["name"] for m in r.json().get("models", [])}
        steps.append(("Ollama reachable", True, f"{len(models)} models"))
    except Exception as e:
        steps.append(("Ollama reachable", False, str(e)))
        models = set()

    # 2. Required models present
    want_embed = any(m.startswith(EMBED_MODEL) for m in models)
    want_gen = GEN_MODEL in models
    steps.append((f"Model present: {EMBED_MODEL}", want_embed, ""))
    steps.append((f"Model present: {GEN_MODEL}", want_gen, ""))

    # 3. ChromaDB reachable + collections readable
    all_cols_ok = True
    try:
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        for name in DEFAULT_COLLECTIONS:
            try:
                c = client.get_collection(name)
                n = c.count()
                steps.append((f"Collection {name}", True, f"{n:,} chunks"))
            except Exception as e:
                steps.append((f"Collection {name}", False, str(e)))
                all_cols_ok = False
    except Exception as e:
        steps.append(("ChromaDB reachable", False, str(e)))
        all_cols_ok = False

    # 4. Canonical test query
    test_q = "What is the name of the backup protocol?"
    try:
        ns = argparse.Namespace(
            question=test_q, top_k=2, collection=None, raw=False,
            no_answer=False, format="plain",
        )
        rc = run_query(ns)
        steps.append(("Canonical test query", rc == 0, f"rc={rc}"))
    except Exception as e:
        steps.append(("Canonical test query", False, str(e)))

    print("\nSELF-TEST RESULTS")
    print("=" * 60)
    all_ok = True
    for name, ok, note in steps:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        suffix = f"  ({note})" if note else ""
        print(f"  [{mark}] {name}{suffix}")
    print("=" * 60)
    print(f"  {'ALL PASS' if all_ok else 'FAILURES PRESENT'}")
    return 0 if all_ok else 1


def main() -> int:
    p = argparse.ArgumentParser(
        description="CC -> Dex Jr. bridge. Read-only RAG retrieval + grounded generation."
    )
    p.add_argument("question", nargs="?", default=None, help="Question text")
    p.add_argument("--top-k", type=int, default=DEFAULT_TOP_K,
                   help=f"Chunks per collection (default {DEFAULT_TOP_K})")
    p.add_argument("--collection", type=str, default=None,
                   help="Search a single collection (default: all 4)")
    p.add_argument("--raw", action="store_true",
                   help="Skip LLM generation; print retrieved chunks only")
    p.add_argument("--no-answer", action="store_true", help="Alias for --raw")
    p.add_argument("--format", choices=["markdown", "json", "plain"],
                   default="markdown", help="Output format")
    p.add_argument("--self-test", action="store_true",
                   help="Verify Ollama + ChromaDB connectivity and exit")
    args = p.parse_args()

    if args.self_test:
        return run_self_test()

    if not args.question:
        p.print_usage(sys.stderr)
        eprint("ERROR: question is required (or use --self-test)")
        return 2

    return run_query(args)


if __name__ == "__main__":
    sys.exit(main())
