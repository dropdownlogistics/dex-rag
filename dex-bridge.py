"""
DEX JR RAG BRIDGE - v1.2
Connects ChromaDB retrieval to Ollama generation.
v1.1: Source weighting via dex-weights.py
v1.2: Auto-ingest query+response to corpus after every run
      Fixed stray chat_url arg in get_embedding() (latent crash on --raw path)

Usage:  python dex-bridge.py "your question here"
        python dex-bridge.py "your question here" --raw
        python dex-bridge.py "your question here" --external
        python dex-bridge.py "your question here" --model llama3.1:8b
        python dex-bridge.py "your question here" --top 10
        python dex-bridge.py --interactive

Workflow:
  1. Takes user query
  2. Queries ChromaDB with tier-based source weighting
  3. Injects retrieved chunks as context into prompt
  4. Sends to Ollama (dexjr model by default)
  5. Returns grounded answer with source citations + provenance tag
  6. Logs everything to dex-bridge-log.jsonl
  7. Auto-ingests query+response transcript to canon corpus

Dropdown Logistics - Chaos -> Structured -> Automated
STD-RAG-001 | 2026-03-07
"""

import os
import sys
import json
import argparse
import datetime
import requests
import subprocess
import shutil

from dex_weights import weighted_query_with_provenance

# -----------------------------
# CONFIG
# -----------------------------
CHROMA_DIR       = r"C:\Users\dkitc\.dex-jr\chromadb"
CANON_COLLECTION = "dex_canon"
RAW_COLLECTION   = "ddl_archive"

OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
OLLAMA_CHAT_URL  = "http://localhost:11434/api/generate"
OLLAMA_CHAT_URL_LAPTOP = "http://192.168.0.210:11434/api/generate"

EMBED_MODEL      = "nomic-embed-text"
DEFAULT_MODEL    = "dexjr"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE   = os.path.join(SCRIPT_DIR, "dex-bridge-log.jsonl")

# Auto-ingest config
BRIDGE_INGEST_DIR = os.path.join(SCRIPT_DIR, "bridge-ingest")
INGEST_SCRIPT     = os.path.join(SCRIPT_DIR, "dex-ingest.py")

TOP_K            = 5
MAX_CONTEXT_CHARS = 6000

# -----------------------------
# CHROMADB SETUP (legacy raw path)
# -----------------------------
import chromadb

def get_client():
    return chromadb.PersistentClient(path=CHROMA_DIR)

# -----------------------------
# EMBEDDING (legacy, used by raw fallback)
# -----------------------------
def get_embedding(text):
    try:
        r = requests.post(
            OLLAMA_EMBED_URL,
            json={"model": EMBED_MODEL, "prompt": text},
            timeout=60,
        )
        r.raise_for_status()
        return r.json().get("embedding")
    except Exception as e:
        print(f"  [ERROR] Embedding failed: {e}")
        return None

# -----------------------------
# RETRIEVAL - WEIGHTED (default)
# -----------------------------
def retrieve(query, top_k=TOP_K, use_raw=False, include_external=False):
    """
    Returns (chunks, provenance_string).
    chunks: list of dicts with text, source, distance, label, weighted_score
    provenance: e.g. "[Sources: 3xCanon | 1xArchive | 1xExtCanon]"
    """
    if use_raw:
        # Legacy unweighted path - single collection
        embedding = get_embedding(query)
        if not embedding:
            return [], "[Sources: none]"
        client = get_client()
        collection = client.get_collection(RAW_COLLECTION)
        results = collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
        chunks = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                dist = results["distances"][0][i] if results["distances"] else None
                chunks.append({
                    "text":           doc,
                    "source":         meta.get("source_file", "unknown"),
                    "distance":       dist,
                    "label":          "Archive",
                    "weighted_score": None,
                })
        return chunks, "[Sources: Archive - unweighted]"

    # Weighted multi-collection path
    results, provenance = weighted_query_with_provenance(
        query_text=query,
        n_results=top_k,
        include_external=include_external
    )

    chunks = []
    for r in results:
        chunks.append({
            "text":           r["document"],
            "source":         r["source"],
            "distance":       r["distance"],
            "label":          r["label"],
            "weighted_score": r["weighted_score"],
            "file_type":      r.get("file_type", ""),
        })

    return chunks, provenance

# -----------------------------
# CONTEXT BUILDING
# -----------------------------
def build_context(chunks, provenance, max_chars=MAX_CONTEXT_CHARS):
    context_parts = [provenance, ""]
    total_chars = len(provenance)

    for i, chunk in enumerate(chunks):
        label = chunk.get("label", "")
        score = f" score={chunk['weighted_score']:.4f}" if chunk.get("weighted_score") else ""
        entry = f"[Source {i+1}: {chunk['source']} | {label}{score}]\n{chunk['text']}\n"
        if total_chars + len(entry) > max_chars:
            break
        context_parts.append(entry)
        total_chars += len(entry)

    return "\n".join(context_parts)

# -----------------------------
# GENERATION
# -----------------------------
def generate(query, context, model=DEFAULT_MODEL, chat_url=OLLAMA_CHAT_URL):
    prompt = f"""The following context was retrieved from the DDL knowledge base to help answer the question. Use this context to inform your answer. If the context does not contain relevant information, say so.

RETRIEVED CONTEXT:
{context}

QUESTION:
{query}

Answer based on the retrieved context and your governance training. Cite sources by number when referencing specific retrieved documents."""

    try:
        r = requests.post(
            chat_url,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_ctx": 8192,
                },
            },
            timeout=120,
        )
        r.raise_for_status()
        return r.json().get("response", "[No response]")
    except Exception as e:
        return f"[ERROR] Generation failed: {e}"

# -----------------------------
# AUTO-INGEST
# -----------------------------
def auto_ingest(query, response, provenance, sources):
    """Write query+response transcript to bridge-ingest folder and trigger fast canon ingest."""
    try:
        os.makedirs(BRIDGE_INGEST_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"bridge_{ts}.txt"
        filepath = os.path.join(BRIDGE_INGEST_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"DEX JR RAG BRIDGE - Query Transcript\n")
            f.write(f"{'='*60}\n")
            f.write(f"TIMESTAMP: {datetime.datetime.now().isoformat()}\n")
            f.write(f"PROVENANCE: {provenance}\n")
            f.write(f"SOURCES: {', '.join(sources)}\n")
            f.write(f"{'='*60}\n\n")
            f.write(f"QUERY:\n{query}\n\n")
            f.write(f"RESPONSE:\n{response}\n")

        if os.path.exists(INGEST_SCRIPT):
            subprocess.run(
                ["python", INGEST_SCRIPT, "--path", BRIDGE_INGEST_DIR, "--build-canon", "--fast"],
                capture_output=True, text=True, timeout=300
            )
    except Exception as e:
        print(f"  [WARN] Auto-ingest failed: {e}")

# -----------------------------
# LOGGING
# -----------------------------
def log_interaction(query, chunks, provenance, response, model, use_raw, include_external):
    entry = {
        "timestamp":        datetime.datetime.now().isoformat(),
        "query":            query,
        "model":            model,
        "collection":       RAW_COLLECTION if use_raw else CANON_COLLECTION,
        "include_external": include_external,
        "provenance":       provenance,
        "chunks_retrieved": len(chunks),
        "sources":          [c["source"] for c in chunks],
        "labels":           [c.get("label", "") for c in chunks],
        "weighted_scores":  [c.get("weighted_score") for c in chunks],
        "distances":        [c["distance"] for c in chunks],
        "response_length":  len(response),
        "response_preview": response[:200],
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"  [WARN] Logging failed: {e}")

# -----------------------------
# DISPLAY
# -----------------------------
def display_results(query, chunks, provenance, response, verbose=False):
    print()
    print("=" * 60)
    print(f" QUERY: {query}")
    print(f" {provenance}")
    print("=" * 60)
    print()

    if verbose:
        print("-" * 60)
        print(" RETRIEVED CONTEXT:")
        print("-" * 60)
        for i, chunk in enumerate(chunks):
            dist  = f"{chunk['distance']:.4f}" if chunk['distance'] is not None else "?"
            score = f"  weighted={chunk['weighted_score']:.4f}" if chunk.get("weighted_score") else ""
            label = chunk.get("label", "")
            print(f"\n  [{i+1}] [{label}] distance={dist}{score}")
            print(f"  source: {chunk['source']}")
            print(f"  {chunk['text'][:200]}...")
        print()
        print("-" * 60)

    print(" ANSWER:")
    print("-" * 60)
    print()
    print(response)
    print()
    print("-" * 60)
    print(f" Sources: {', '.join(c['source'] for c in chunks)}")
    print(f" Log: {LOG_FILE}")
    print("=" * 60)

# -----------------------------
# INTERACTIVE MODE
# -----------------------------
def interactive(model=DEFAULT_MODEL, use_raw=False, include_external=False,
                top_k=TOP_K, verbose=False):
    print()
    print("=" * 60)
    print(" DEX JR RAG BRIDGE - Interactive Mode v1.2")
    print(f" Model: {model} | Collection: {'archive' if use_raw else 'canon'}")
    ext_label = " + external" if include_external else ""
    print(f" Top-K: {top_k}{ext_label} | Type 'quit' to exit")
    print("=" * 60)
    print()

    while True:
        try:
            query = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "/bye"):
            print("Exiting.")
            break

        # Inline flags
        current_raw      = use_raw
        current_external = include_external
        if query.startswith("--raw "):
            current_raw = True
            query = query[6:].strip()
        if query.startswith("--external "):
            current_external = True
            query = query[11:].strip()

        chunks, provenance = retrieve(
            query, top_k=top_k,
            use_raw=current_raw,
            include_external=current_external
        )

        if not chunks:
            print(f"\n  [No relevant chunks found. Answering from system prompt only.]\n")
            response = generate(query, "[No context retrieved]", model=model)
            provenance = "[Sources: none]"
        else:
            context  = build_context(chunks, provenance)
            response = generate(query, context, model=model)

        display_results(query, chunks, provenance, response, verbose=verbose)
        log_interaction(query, chunks, provenance, response, model, current_raw, current_external)
        auto_ingest(query, response, provenance, [c["source"] for c in chunks])

# -----------------------------
# MAIN
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Dex Jr RAG Bridge v1.2 - Weighted Query + Generate + Auto-Ingest")
    parser.add_argument("query",         nargs="?", default=None, help="Question to ask")
    parser.add_argument("--raw",         action="store_true", help="Search archive instead of canon (unweighted)")
    parser.add_argument("--external",    action="store_true", help="Include ext_canon and ext_archive in search")
    parser.add_argument("--model",       default=DEFAULT_MODEL, help="Ollama model to use")
    parser.add_argument("--top",         type=int, default=TOP_K, help="Number of chunks to retrieve")
    parser.add_argument("--verbose",     action="store_true", help="Show retrieved chunks with scores")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    parser.add_argument("--node",        default="local", help="Inference node: local or laptop")
    parser.add_argument("--no-ingest",   action="store_true", help="Disable auto-ingest for this run")

    args = parser.parse_args()

    chat_url = OLLAMA_CHAT_URL_LAPTOP if args.node == "laptop" else OLLAMA_CHAT_URL

    if args.interactive:
        interactive(
            model=args.model,
            use_raw=args.raw,
            include_external=args.external,
            top_k=args.top,
            verbose=args.verbose
        )
        return

    if not args.query:
        parser.print_help()
        return

    # Retrieve
    chunks, provenance = retrieve(
        args.query,
        top_k=args.top,
        use_raw=args.raw,
        include_external=args.external
    )

    if not chunks:
        print(f"\n  [No relevant chunks found. Answering from system prompt only.]\n")
        response   = generate(args.query, "[No context retrieved]", model=args.model, chat_url=chat_url)
        provenance = "[Sources: none]"
    else:
        context  = build_context(chunks, provenance)
        response = generate(args.query, context, model=args.model, chat_url=chat_url)

    display_results(args.query, chunks, provenance, response, verbose=args.verbose)
    log_interaction(args.query, chunks, provenance, response, args.model, args.raw, args.external)

    if not args.no_ingest:
        auto_ingest(args.query, response, provenance, [c["source"] for c in chunks])

if __name__ == "__main__":
    main()
