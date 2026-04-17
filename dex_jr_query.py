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
import os
import re
import sys
from pathlib import Path
from typing import Any

import chromadb
import requests

from dex_core import (
    CHROMA_DIR, OLLAMA_HOST, EMBED_MODEL, GEN_MODEL,
    EMBED_TRUNC_LEVELS, get_live_collections,
)
from dex_weights import calculate_weight, score_result

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_COLLECTIONS = get_live_collections()
DEFAULT_TOP_K = 3
DEFAULT_MERGE_N = 5
CHUNK_PREVIEW_CHARS = 300

# B3: governance-identifier pattern. All-caps by convention. Matches e.g.
# STD-DDL-SWEEPREPORT-001, CR-INGEST-PIPELINE-001, ADR-CORPUS-001,
# PRO-BACKUP-001, OBS-DJ-004, SYS-BRIDGE-001. Case-sensitive.
IDENTIFIER_PATTERN = re.compile(
    r"\b(?:STD|CR|ADR|PRO|OBS|SYS)(?:-[A-Z0-9]+){2,}\b"
)
PREFILTER_PER_ID = 5  # max chunks returned per detected identifier per collection
BODY_MATCH_PER_ID = 3  # max body-contains chunks per identifier per collection


def eprint(*args: Any, **kwargs: Any) -> None:
    print(*args, file=sys.stderr, **kwargs)


def embed(question: str) -> list[float]:
    """Delegate to dex_core.embed() — adaptive truncation for mxbai."""
    from dex_core import embed as _core_embed
    return _core_embed(question)


def generate(prompt: str) -> str:
    r = requests.post(
        f"{OLLAMA_HOST}/api/generate",
        json={"model": GEN_MODEL, "prompt": prompt, "stream": False},
        timeout=300,
    )
    r.raise_for_status()
    return r.json()["response"]


def extract_identifiers(query_text: str) -> list[str]:
    """Return deduplicated, order-preserved list of identifier-like tokens."""
    seen: list[str] = []
    for m in IDENTIFIER_PATTERN.finditer(query_text or ""):
        tok = m.group(0)
        if tok not in seen:
            seen.append(tok)
    return seen


def prefilter_by_source_file(
    client: chromadb.api.ClientAPI,
    identifiers: list[str],
    collection_names: list[str],
    per_id: int = PREFILTER_PER_ID,
) -> list[dict]:
    """For each identifier, look up chunks whose source_file matches common
    filename variants. Returns chunks in identifier-order, collection-order."""
    hits: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()
    for ident in identifiers:
        variants = [f"{ident}.txt", f"{ident}.md", f"{ident} Draft.txt"]
        for name in collection_names:
            try:
                col = client.get_collection(name)
            except Exception:
                continue
            try:
                got = col.get(
                    where={"source_file": {"$in": variants}},
                    limit=per_id,
                    include=["documents", "metadatas"],
                )
            except Exception as e:
                eprint(f"  [warn] prefilter get failed on {name}: {e}")
                continue
            ids = got.get("ids", []) or []
            docs = got.get("documents", []) or []
            metas = got.get("metadatas", []) or []
            for cid, doc, md in zip(ids, docs, metas):
                md = md or {}
                key = (name, cid)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                src = md.get("source_file") or md.get("filename") or "<unknown>"
                tag = (
                    "prefilter_filename_match_draft"
                    if src.endswith(" Draft.txt")
                    else "prefilter_filename_match"
                )
                hits.append({
                    "collection": name,
                    "source_file": src,
                    "ingest_run_id": md.get("ingest_run_id", ""),
                    "distance": 0.0,
                    "text": doc or "",
                    "retrieval_source": tag,
                    "matched_identifier": ident,
                })
    return hits


def body_match_by_identifier(
    client: chromadb.api.ClientAPI,
    identifiers: list[str],
    collection_names: list[str],
    per_id: int = BODY_MATCH_PER_ID,
) -> list[dict]:
    """For each identifier, look up chunks whose body contains the identifier
    string (case-sensitive $contains). Fallback for when the identifier is
    discussed inside a file whose filename doesn't match the identifier."""
    hits: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()
    for ident in identifiers:
        for name in collection_names:
            try:
                col = client.get_collection(name)
            except Exception:
                continue
            try:
                got = col.get(
                    where_document={"$contains": ident},
                    limit=per_id,
                    include=["documents", "metadatas"],
                )
            except Exception as e:
                eprint(f"  [warn] body-match get failed on {name}: {e}")
                continue
            ids = got.get("ids", []) or []
            docs = got.get("documents", []) or []
            metas = got.get("metadatas", []) or []
            for cid, doc, md in zip(ids, docs, metas):
                md = md or {}
                key = (name, cid)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                hits.append({
                    "id": cid,
                    "collection": name,
                    "source_file": md.get("source_file") or md.get("filename") or "<unknown>",
                    "ingest_run_id": md.get("ingest_run_id", ""),
                    "distance": 0.0,
                    "text": doc or "",
                    "retrieval_source": "prefilter_body_match",
                    "matched_identifier": ident,
                })
    return hits


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
        # chroma includes ids by default, outside `include`
        res_ids_raw = res.get("ids") or [[]]
        res.setdefault("ids", res_ids_raw)
        ids = res.get("ids", [[]])[0]
        for cid, doc, md, dist in zip(ids, docs, metas, dists):
            md = md or {}
            hits.append({
                "id": cid,
                "collection": name,
                "source_file": md.get("source_file") or md.get("filename") or "<unknown>",
                "ingest_run_id": md.get("ingest_run_id", ""),
                "distance": float(dist),
                "text": doc or "",
                "retrieval_source": "vector",
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
        "Critical: do not invent numbered items, protocols, triggers, standards, "
        "or structural elements that are not explicitly listed with their numbers "
        "or names in the context. If the context says '5 triggers,' do not "
        "synthesize a sixth. If the context names specific items (Trigger 1, "
        "Trigger 2, etc.), only reference those specific items by their stated "
        "numbers. If the context does not specify a number or name, say 'the "
        "context does not specify' rather than inferring one.\n\n"
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
        rsrc = c.get("retrieval_source", "vector")
        is_prefilter = rsrc.startswith("prefilter_")
        if rsrc == "prefilter_body_match":
            tag = " [BODY MATCH]"
        elif is_prefilter:
            tag = " [PREFILTER MATCH]"
        else:
            tag = ""
        dist_str = "n/a (prefilter)" if is_prefilter else f"{c['distance']:.4f}"
        w_str = f", weight: {c['weight']:.3f}, score: {c['weighted_score']:.4f}" if "weight" in c else ""
        lines.append(
            f"### {i}. {c['source_file']}{tag} (collection: {c['collection']}, "
            f"distance: {dist_str}{w_str})"
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
    use_prefilter = not getattr(args, "no_prefilter", False)

    try:
        client = chromadb.PersistentClient(path=CHROMA_DIR)
    except Exception as e:
        eprint(f"ERROR: ChromaDB open failed: {e}")
        return 2

    prefilter_hits: list[dict] = []
    body_hits: list[dict] = []
    if use_prefilter:
        idents = extract_identifiers(args.question)
        if idents:
            try:
                prefilter_hits = prefilter_by_source_file(client, idents, collections)
            except Exception as e:
                eprint(f"  [warn] prefilter step failed, falling through: {e}")
                prefilter_hits = []
            # B2 fallback: for identifiers with zero filename hits, run body-contains
            matched_idents = {h.get("matched_identifier") for h in prefilter_hits}
            body_idents = [i for i in idents if i not in matched_idents]
            if body_idents:
                try:
                    body_hits = body_match_by_identifier(client, body_idents, collections)
                except Exception as e:
                    eprint(f"  [warn] body-match step failed, falling through: {e}")
                    body_hits = []

    try:
        embedding = embed(args.question)
    except requests.RequestException as e:
        eprint(f"ERROR: Ollama unreachable for embeddings: {e}")
        return 1

    try:
        vector_hits = search_collections(client, embedding, collections, args.top_k)
    except Exception as e:
        eprint(f"ERROR: ChromaDB query failed: {e}")
        return 2

    # Merge: filename-prefilter, then body-match, then vector; dedupe by (collection, id)
    seen: set[tuple[str, str]] = set()
    merged_all: list[dict] = []
    for c in prefilter_hits + body_hits + vector_hits:
        key = (c["collection"], c.get("id", c["source_file"] + c["text"][:32]))
        if key in seen:
            continue
        seen.add(key)
        merged_all.append(c)

    # Step 49: apply source weighting from dex_weights.py
    for c in merged_all:
        md = c.get("metadata") or {}
        # Build metadata dict from hit fields for weight calculation
        if not md:
            md = {
                "file_type": c.get("file_type", ""),
                "filename": c.get("filename", c.get("source_file", "")),
                "source_file": c.get("source_file", ""),
                "status": c.get("status", ""),
            }
        w = calculate_weight(c["collection"], md)
        c["weight"] = round(w, 4)
        c["weighted_score"] = score_result(c.get("distance", 0.0), w)

    # Rank by weighted_score descending (prefilter hits with distance=0 still rank highest)
    merged_all.sort(key=lambda x: x["weighted_score"], reverse=True)
    merged = merged_all[:DEFAULT_MERGE_N]

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
            no_answer=False, format="plain", no_prefilter=False,
        )
        rc = run_query(ns)
        steps.append(("Canonical test query", rc == 0, f"rc={rc}"))
    except Exception as e:
        steps.append(("Canonical test query", False, str(e)))

    # 5. B3 canary: identifier prefilter must surface its own document
    try:
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        idents = extract_identifiers("What is STD-DDL-SWEEPREPORT-001?")
        prefilter_ok = False
        note = ""
        if idents == ["STD-DDL-SWEEPREPORT-001"]:
            hits = prefilter_by_source_file(client, idents, DEFAULT_COLLECTIONS)
            match = any(
                h["source_file"].startswith("STD-DDL-SWEEPREPORT-001")
                for h in hits
            )
            prefilter_ok = match
            note = f"{len(hits)} prefilter hits" if match else "no matching chunks"
        else:
            note = f"regex miss: {idents}"
        steps.append(("B3 canary: STD-DDL-SWEEPREPORT-001 prefilter", prefilter_ok, note))
    except Exception as e:
        steps.append(("B3 canary: STD-DDL-SWEEPREPORT-001 prefilter", False, str(e)))

    # 6. B2 canary: body-contains fallback must surface identifier in chunk body
    try:
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        body_hits = body_match_by_identifier(
            client, ["CR-OPERATOR-CAPACITY-001"], DEFAULT_COLLECTIONS
        )
        ok = any(
            h.get("retrieval_source") == "prefilter_body_match"
            and "CR-OPERATOR-CAPACITY-001" in (h.get("text") or "")
            for h in body_hits
        )
        note = f"{len(body_hits)} body-match hits" if ok else "no body-match chunks"
        steps.append(("B2 canary: CR-OPERATOR-CAPACITY-001 body-match", ok, note))
    except Exception as e:
        steps.append(("B2 canary: CR-OPERATOR-CAPACITY-001 body-match", False, str(e)))

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
    p.add_argument("--no-prefilter", action="store_true",
                   help="Disable B3 identifier pre-filter (compare against pure vector retrieval)")
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
