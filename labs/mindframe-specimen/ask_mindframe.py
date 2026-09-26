#!/usr/bin/env python
"""
ask_mindframe.py -- MindFrame x Dex Jr specimen (v0.1)

Thin CLI loop: question -> weighted corpus retrieval (MindFrame-scoped)
-> ddl-intel generation -> answer with source citations.

Uses the Reborn API at localhost:8765. Experimental -- not canon, not product.

Usage:
    python ask_mindframe.py                     # interactive mode
    python ask_mindframe.py "What is MindFrame?" # single query
    python ask_mindframe.py --evidence "..."     # show raw retrieval chunks
    python ask_mindframe.py --retrieve-only "..."# retrieval only, no generation
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
import time

import requests

# Force UTF-8 stdout on Windows (corpus text contains Unicode)
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

API_BASE = "http://localhost:8765"
DEFAULT_TOP_K = 8
DEFAULT_THRESHOLD = 0.45  # tighter than API default to keep results relevant

MINDFRAME_SYSTEM_PROMPT = textwrap.dedent("""\
    You are answering questions about MindFrame, a modular persona-calibration
    framework built by Dave Kitchens as part of the DDL system. MindFrame has
    six core modules (CraniumCartographer, ProficiencyStack, ToneprintShaper,
    PersonaCompiler, ContinuityIntegrator, MetaInterpreter), four calibration
    engines (Full, Quick, CompanionImport, ProgramExecution), and five programs
    (AI Proficiency Mapping, Cognitive Scan, Teach Me Like I'm 5, Brainstormer,
    Socratic Navigator).

    Answer ONLY from the retrieved context below. If the context does not contain
    the answer, say so -- do not improvise or hallucinate details. Cite source
    files when possible. Be precise and direct.
""")


def check_api() -> bool:
    """Verify the Reborn API is reachable."""
    try:
        r = requests.get(f"{API_BASE}/health", timeout=5)
        data = r.json()
        if data.get("status") not in ("ok", "degraded"):
            return False
        return True
    except (requests.ConnectionError, requests.Timeout):
        return False


def retrieve(query: str, top_k: int = DEFAULT_TOP_K,
             threshold: float = DEFAULT_THRESHOLD) -> list[dict]:
    """Retrieve MindFrame-relevant chunks from the corpus."""
    resp = requests.post(f"{API_BASE}/retrieve", json={
        "query": query,
        "n_results": top_k,
        "threshold": threshold,
    }, timeout=30)
    resp.raise_for_status()
    return resp.json().get("chunks", [])


def ask(query: str, top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_THRESHOLD) -> dict:
    """RAG query: retrieve + generate via ddl-intel model."""
    resp = requests.post(f"{API_BASE}/ask", json={
        "query": query,
        "n_results": top_k,
        "threshold": threshold,
    }, timeout=120)
    resp.raise_for_status()
    return resp.json()


def format_evidence(chunks: list[dict]) -> str:
    """Format raw retrieval chunks for --evidence display."""
    lines = []
    for c in chunks:
        fp = c.get("file_path", "?")
        # Show just the filename
        fname = fp.replace("\\", "/").split("/")[-1]
        dist = c.get("distance", 0)
        tier = c.get("tier", "?")
        text = c.get("text", "")
        # Truncate long chunks for display
        if len(text) > 300:
            text = text[:297] + "..."
        lines.append(f"  [{c.get('rank', '?')}] dist={dist:.4f} | tier={tier} | {fname}")
        lines.append(f"      {text}")
        lines.append("")
    return "\n".join(lines)


def format_sources(chunks: list[dict]) -> str:
    """Format source citations (compact)."""
    seen = set()
    lines = []
    for c in chunks:
        fp = c.get("file_path", "?")
        fname = fp.replace("\\", "/").split("/")[-1]
        if fname not in seen:
            seen.add(fname)
            dist = c.get("distance", 0)
            lines.append(f"  - {fname} (dist={dist:.4f})")
    return "\n".join(lines)


def run_query(query: str, evidence: bool = False,
              retrieve_only: bool = False) -> None:
    """Execute a single query and print results."""
    t0 = time.monotonic()

    if retrieve_only:
        chunks = retrieve(query)
        elapsed = (time.monotonic() - t0) * 1000
        if not chunks:
            print("\n  No relevant chunks found.\n")
            return
        print(f"\n  Retrieved {len(chunks)} chunks ({elapsed:.0f}ms):\n")
        print(format_evidence(chunks))
        return

    result = ask(query)
    elapsed = (time.monotonic() - t0) * 1000

    print(f"\n{result.get('answer', '(no answer)')}\n")
    print(f"--- Sources ({elapsed:.0f}ms) ---")
    print(format_sources(result.get("sources", [])))

    if evidence:
        print(f"\n--- Evidence (raw chunks) ---\n")
        print(format_evidence(result.get("sources", [])))

    print()


def interactive_loop(evidence: bool = False) -> None:
    """Run the interactive REPL."""
    print("\n  Ask MindFrame (Dex Jr specimen v0.1)")
    print("  Type a question, or 'quit' to exit.")
    print("  Prefix with /e to toggle evidence, /r for retrieve-only.\n")

    while True:
        try:
            query = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            break

        retrieve_only = False
        show_evidence = evidence

        if query.startswith("/e "):
            show_evidence = not evidence
            query = query[3:].strip()
        elif query.startswith("/r "):
            retrieve_only = True
            query = query[3:].strip()

        if not query:
            continue

        try:
            run_query(query, evidence=show_evidence, retrieve_only=retrieve_only)
        except requests.ConnectionError:
            print("  [ERROR] API unreachable. Is reborn_api.py running on 8765?\n")
        except requests.HTTPError as e:
            print(f"  [ERROR] API returned {e.response.status_code}: {e.response.text}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ask MindFrame -- corpus-grounded MindFrame Q&A via Dex Jr")
    parser.add_argument("query", nargs="?", default=None,
                        help="Single query (omit for interactive mode)")
    parser.add_argument("--evidence", "-e", action="store_true",
                        help="Show raw retrieval chunks with scores")
    parser.add_argument("--retrieve-only", "-r", action="store_true",
                        help="Retrieval only, no generation")
    parser.add_argument("--top-k", "-k", type=int, default=DEFAULT_TOP_K,
                        help=f"Number of chunks to retrieve (default: {DEFAULT_TOP_K})")
    args = parser.parse_args()

    if not check_api():
        print("  [ERROR] Reborn API not reachable at localhost:8765.", file=sys.stderr)
        print("  Start it: cd C:\\Users\\dkitc\\ddl-intel && python reborn_api.py", file=sys.stderr)
        sys.exit(1)

    if args.query:
        run_query(args.query, evidence=args.evidence,
                  retrieve_only=args.retrieve_only)
    else:
        interactive_loop(evidence=args.evidence)


if __name__ == "__main__":
    main()
