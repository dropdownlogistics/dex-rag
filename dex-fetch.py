"""
DEX JR WEB FETCH — v1.0
Fetches a web page, strips HTML, feeds content to Dex Jr.

Usage:
  python dex-fetch.py "https://dropdownlogistics.com/council/1010"
  python dex-fetch.py "https://dropdownlogistics.com/council/1010" --ask "Does this page follow CottageHumble?"
  python dex-fetch.py "https://dropdownlogistics.com/council/1010" --ask "What's missing?" --rag
  python dex-fetch.py "https://dropdownlogistics.com/council/1010" --raw
  python dex-fetch.py "https://dropdownlogistics.com/council/1010" --save fetched/council-1010.txt
  python dex-fetch.py --sitemap "https://dropdownlogistics.com" --save fetched/full-site/

Modes:
  (default)   Fetch page, strip HTML, send to Dex Jr. with question
  --raw       Just fetch and display the stripped text (no LLM)
  --ask       Ask Dex Jr. a specific question about the page
  --rag       Also retrieve RAG context for comparison
  --save      Save stripped text to file
  --ingest    Save stripped text to canon folder for ingestion
  --sitemap   Crawl sitemap and fetch all pages

Dropdown Logistics — Chaos -> Structured -> Automated
Web Fetch v1.0 | 2026-03-07
"""

import os
import sys
import re
import json
import time
import argparse
import datetime
import requests
from html.parser import HTMLParser

# -----------------------------
# CONFIG
# -----------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "dex-fetch-log.jsonl")

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
DEFAULT_MODEL = "dexjr"

CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"
CANON_COLLECTION = "dex_canon"
EMBED_MODEL = "nomic-embed-text"
CANON_DIR = r"C:\Users\dexjr\99_DexUniverseArchive\00_Archive\DDL-Standards-Canon"

TOP_K = 5

# Governance context for page analysis
PAGE_GOVERNANCE = """You are Dex Jr. (Seat 1010), analyzing a web page from dropdownlogistics.com.

DESIGN SYSTEM — COTTAGEHHUMBLE:
- Dark mode: #0A0A0C bg, #111114 surface, #E8E6E3 text, #FFD43B accent
- Fonts: Space Grotesk (headings), Source Serif 4 (body), JetBrains Mono (code)
- BANNED: #ffffff backgrounds, Inter font, Arial, light mode on dark pages
- BANNED: Nested layouts, unsanctioned nav modifications
- Wings: DDL (crimson), D&A (amber), DexVerse (violet), Dossiers (green), Products (blue)

SITE ARCHITECTURE:
- Framework: Next.js 14, static export, Vercel
- Navigation: SiteNav with 5 wing tabs, contextual dropdowns
- Templates: CHRONICLE, ATLAS, LEDGER, DOSSIER, CONSOLE, CODEX
- Search: Cmd+K modal with page search + deep RAG search

When analyzing a page, check for:
1. CottageHumble compliance (fonts, colors, layout)
2. Content completeness (is anything missing or placeholder?)
3. Navigation correctness (does it fit the wing model?)
4. Governance alignment (does content match DDL standards?)
5. Accessibility and readability
6. Mobile considerations

Be specific. Cite exact elements. If something violates the design system, name it."""

# -----------------------------
# HTML STRIPPING
# -----------------------------
class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self.skip_tags = {'script', 'style', 'head', 'meta', 'link', 'noscript'}
        self.current_skip = False
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.current_skip = True
            self.skip_depth += 1
        elif tag in ('br', 'hr'):
            self.result.append('\n')
        elif tag in ('p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'tr', 'section', 'article'):
            self.result.append('\n')

    def handle_endtag(self, tag):
        if tag in self.skip_tags:
            self.skip_depth -= 1
            if self.skip_depth <= 0:
                self.current_skip = False
                self.skip_depth = 0
        elif tag in ('p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'tr', 'section', 'article'):
            self.result.append('\n')

    def handle_data(self, data):
        if not self.current_skip:
            text = data.strip()
            if text:
                self.result.append(text)

    def get_text(self):
        raw = ' '.join(self.result)
        # Clean up whitespace
        raw = re.sub(r'\n\s*\n', '\n\n', raw)
        raw = re.sub(r'  +', ' ', raw)
        return raw.strip()

def strip_html(html_content):
    stripper = HTMLStripper()
    stripper.feed(html_content)
    return stripper.get_text()

# -----------------------------
# FETCH
# -----------------------------
def fetch_page(url, timeout=30):
    try:
        headers = {
            'User-Agent': 'DexJr-Fetch/1.0 (DDL Local AI; +https://dropdownlogistics.com)',
        }
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        return {
            "html": r.text,
            "status": r.status_code,
            "content_type": r.headers.get('content-type', ''),
            "size": len(r.text),
            "error": None,
        }
    except Exception as e:
        return {"html": None, "status": 0, "content_type": "", "size": 0, "error": str(e)}

# -----------------------------
# RAG RETRIEVAL
# -----------------------------
def retrieve_context(query, top_k=TOP_K):
    try:
        import chromadb
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        collection = client.get_collection(CANON_COLLECTION)
        r = requests.post(
            OLLAMA_EMBED_URL,
            json={"model": EMBED_MODEL, "prompt": query},
            timeout=60,
        )
        r.raise_for_status()
        embedding = r.json().get("embedding")
        if not embedding:
            return ""
        results = collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            include=["documents", "metadatas"],
        )
        chunks = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                source = meta.get("source_file", "unknown")
                chunks.append(f"[Source: {source}]\n{doc[:400]}")
        return "\n\n".join(chunks)
    except Exception as e:
        print(f"  [WARN] RAG retrieval failed: {e}")
        return ""

# -----------------------------
# LLM QUERY
# -----------------------------
def ask_dexjr(page_text, question, rag_context="", model=DEFAULT_MODEL):
    prompt_parts = [PAGE_GOVERNANCE]

    if rag_context:
        prompt_parts.append(f"\nRAG CONTEXT (from DDL corpus):\n{rag_context}")

    prompt_parts.append(f"\nPAGE CONTENT:\n{page_text[:12000]}")
    prompt_parts.append(f"\nQUESTION:\n{question}")
    prompt_parts.append("\nAnalyze the page content and answer the question. Be specific. Cite exact elements from the page.")

    prompt = "\n".join(prompt_parts)

    try:
        start = time.time()
        r = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_ctx": 16384},
            },
            timeout=180,
        )
        r.raise_for_status()
        elapsed = time.time() - start
        return {
            "response": r.json().get("response", "[No response]"),
            "elapsed": round(elapsed, 1),
            "error": None,
        }
    except Exception as e:
        return {"response": None, "elapsed": 0, "error": str(e)}

# -----------------------------
# SITEMAP CRAWL
# -----------------------------
def crawl_sitemap(base_url, save_dir):
    """Fetch sitemap.xml and crawl all pages."""
    os.makedirs(save_dir, exist_ok=True)

    sitemap_url = f"{base_url.rstrip('/')}/sitemap.xml"
    print(f"  Fetching sitemap: {sitemap_url}")

    result = fetch_page(sitemap_url)
    if result["error"]:
        # Try sitemap-0.xml (common for Next.js)
        sitemap_url = f"{base_url.rstrip('/')}/sitemap-0.xml"
        print(f"  Trying: {sitemap_url}")
        result = fetch_page(sitemap_url)

    if result["error"]:
        print(f"  ERROR: Could not fetch sitemap: {result['error']}")
        print(f"  Falling back to known routes...")
        return []

    # Extract URLs from sitemap XML
    urls = re.findall(r'<loc>(.*?)</loc>', result["html"])
    print(f"  Found {len(urls)} URLs in sitemap")

    fetched = []
    for i, url in enumerate(urls):
        print(f"  [{i+1}/{len(urls)}] {url}...", end=" ", flush=True)
        page = fetch_page(url)
        if page["error"]:
            print(f"ERROR")
            continue

        text = strip_html(page["html"])
        if len(text) < 50:
            print(f"EMPTY")
            continue

        # Save
        slug = url.replace(base_url, "").strip("/").replace("/", "_") or "index"
        filename = f"{slug}.txt"
        filepath = os.path.join(save_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"URL: {url}\n")
            f.write(f"FETCHED: {datetime.datetime.now().isoformat()}\n")
            f.write(f"SIZE: {len(text)} chars\n\n")
            f.write(text)

        fetched.append({"url": url, "file": filename, "chars": len(text)})
        print(f"OK ({len(text)} chars)")
        time.sleep(0.5)  # Be polite

    print(f"\n  Crawled {len(fetched)} pages → {save_dir}")
    return fetched

# -----------------------------
# SAVE / INGEST
# -----------------------------
def save_text(text, url, filepath):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"URL: {url}\n")
        f.write(f"FETCHED: {datetime.datetime.now().isoformat()}\n")
        f.write(f"SIZE: {len(text)} chars\n\n")
        f.write(text)
    print(f"  Saved to: {filepath}")

def ingest_text(text, url):
    """Save to canon folder for next ingestion sweep."""
    os.makedirs(CANON_DIR, exist_ok=True)
    slug = url.replace("https://", "").replace("http://", "").replace("/", "_").rstrip("_")
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"WebFetch_{slug}_{ts}.txt"
    filepath = os.path.join(CANON_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"URL: {url}\n")
        f.write(f"FETCHED: {datetime.datetime.now().isoformat()}\n")
        f.write(f"SIZE: {len(text)} chars\n\n")
        f.write(text)
    print(f"  Ingested to corpus: {filepath}")

# -----------------------------
# LOGGING
# -----------------------------
def log_fetch(url, text_length, question, response_length, elapsed):
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "url": url,
        "text_chars": text_length,
        "question": question[:200] if question else None,
        "response_chars": response_length,
        "elapsed": elapsed,
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except:
        pass

# -----------------------------
# DISPLAY
# -----------------------------
def display_result(url, text, question, result, rag_used):
    print()
    print("=" * 70)
    print(f"  DEX JR WEB FETCH — Page Analysis")
    print("=" * 70)
    print(f"  URL: {url}")
    print(f"  Page text: {len(text)} chars")
    print(f"  RAG: {'Active' if rag_used else 'Off'}")
    if question:
        print(f"  Question: {question[:80]}")
    print("=" * 70)
    print()

    if result and result.get("response"):
        print(result["response"])
    elif result and result.get("error"):
        print(f"  ERROR: {result['error']}")

    print()
    print("=" * 70)
    if result:
        print(f"  Elapsed: {result.get('elapsed', 0)}s")
    print(f"  Log: {LOG_FILE}")
    print("=" * 70)

# -----------------------------
# MAIN
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Dex Jr Web Fetch v1.0")
    parser.add_argument("url", nargs="?", default=None, help="URL to fetch")
    parser.add_argument("--ask", default=None, help="Question to ask about the page")
    parser.add_argument("--rag", action="store_true", help="Also retrieve RAG context")
    parser.add_argument("--raw", action="store_true", help="Just show stripped text")
    parser.add_argument("--save", default=None, help="Save stripped text to file")
    parser.add_argument("--ingest", action="store_true", help="Save to corpus for ingestion")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LLM model to use")
    parser.add_argument("--sitemap", default=None, help="Crawl sitemap from base URL")
    parser.add_argument("--top", type=int, default=TOP_K, help="RAG chunks to retrieve")

    args = parser.parse_args()

    # Sitemap crawl mode
    if args.sitemap:
        save_dir = args.save or os.path.join(SCRIPT_DIR, "fetched", "site-crawl")
        crawl_sitemap(args.sitemap, save_dir)
        return

    if not args.url:
        parser.print_help()
        return

    url = args.url

    # Fetch
    print(f"\n  Fetching: {url}...")
    page = fetch_page(url)
    if page["error"]:
        print(f"  ERROR: {page['error']}")
        return

    # Strip HTML
    text = strip_html(page["html"])
    print(f"  Stripped: {len(text)} chars of text content")

    if len(text) < 50:
        print(f"  WARNING: Very little text content found. Page may be JS-rendered.")
        print(f"  (Next.js static export pages should have pre-rendered HTML)")

    # Save if requested
    if args.save:
        save_text(text, url, args.save)

    # Ingest if requested
    if args.ingest:
        ingest_text(text, url)

    # Raw mode — just show text
    if args.raw:
        print(f"\n{'─'*70}")
        print(text[:5000])
        if len(text) > 5000:
            print(f"\n... [{len(text) - 5000} more chars]")
        print(f"{'─'*70}")
        log_fetch(url, len(text), None, 0, 0)
        return

    # Default question if none provided
    question = args.ask or "Analyze this page. Check CottageHumble compliance, content completeness, navigation correctness, and governance alignment. List any issues found."

    # RAG context
    rag_context = ""
    if args.rag:
        print(f"  Retrieving RAG context...")
        rag_context = retrieve_context(question, top_k=args.top)
        if rag_context:
            print(f"  Retrieved {len(rag_context)} chars of context.")

    # Ask Dex Jr.
    print(f"  Asking Dex Jr....")
    result = ask_dexjr(text, question, rag_context, model=args.model)

    # Display
    display_result(url, text, question, result, bool(rag_context))

    # Log
    log_fetch(url, len(text), question, len(result.get("response", "")) if result.get("response") else 0, result.get("elapsed", 0))

if __name__ == "__main__":
    main()
