"""
dex-acquire.py v1.0
Batch URL acquisition with Dex Jr. quality evaluation.
Reuses dex-fetch logic. New capability: evaluate before ingest.

USAGE:
  python dex-acquire.py --topic "Munger cognitive biases" --urls urls.txt --auto-ingest
  python dex-acquire.py --topic "SOX compliance" --urls urls.txt --review-only
  python dex-acquire.py --topic "Kimball dimensional modeling" --urls urls.txt --auto-ingest --collection ext_canon
  python dex-acquire.py --from-plan acquisition-plan.json

QUALITY GATE:
  7/10 or higher → INGEST (if --auto-ingest)
  5-6/10         → FLAG FOR REVIEW
  Below 5        → SKIP

GOVERNANCE:
  --auto-ingest requires explicit flag. Default is --review-only.
  Every decision logged with reasoning.
  Source attribution header prepended to every ingested file.
"""

import argparse
import json
import os
import re
import sys
import time
import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
import chromadb
import ollama

# ── Config ────────────────────────────────────────────────────────────────────

CHROMA_PATH = r"C:\Users\dkitc.dex-jr\chromadb"
EMBED_MODEL  = "nomic-embed-text"
EVAL_MODEL   = "dexjr"
CHUNK_SIZE   = 1000
CHUNK_OVERLAP = 100
QUALITY_AUTO_INGEST = 7    # auto-ingest threshold
QUALITY_FLAG        = 5    # flag-for-review threshold (below = skip)
REQUEST_TIMEOUT     = 30
REQUEST_DELAY       = 1.5  # seconds between fetches (polite crawling)

LOG_FILE = "dex-acquire-log.jsonl"

# ── ChromaDB ──────────────────────────────────────────────────────────────────

def get_collection(name: str):
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        return client.get_or_create_collection(name=name)
    except Exception as e:
        print(f"  [ERROR] ChromaDB collection '{name}': {e}")
        sys.exit(1)

# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_url(url: str) -> tuple[str, int]:
    """Fetch URL, strip HTML to plain text. Returns (text, char_count)."""
    headers = {"User-Agent": "Mozilla/5.0 (DexJr RAG Acquisition; DDL Research)"}
    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        # Remove nav, footer, scripts, styles
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # Collapse excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        return text.strip(), len(text)
    except requests.RequestException as e:
        return "", 0

# ── Evaluate ──────────────────────────────────────────────────────────────────

EVAL_PROMPT_TEMPLATE = """You are evaluating external web content for ingestion into Dex Jr.'s RAG corpus.

TOPIC: {topic}

CONTENT (first 3000 chars):
{content_preview}

SOURCE: {url}

Evaluate this content on these criteria:
1. RELEVANCE: How directly relevant is this to the topic? (0-10)
2. QUALITY: Is the content factual, structured, and citable? (0-10)
3. REDUNDANCY: Might this duplicate content already in the corpus? (estimate low/medium/high)
4. USABILITY: Can this be chunked and retrieved meaningfully? (0-10)

Respond in this EXACT format:
RELEVANCE: [score]
QUALITY: [score]
REDUNDANCY: [low/medium/high]
USABILITY: [score]
OVERALL: [average of relevance, quality, usability rounded to 1 decimal]
DECISION: [INGEST / FLAG / SKIP]
REASON: [one sentence explaining the decision]"""

def evaluate_content(url: str, text: str, topic: str) -> dict:
    """Ask Dex Jr. to evaluate content quality and relevance."""
    if not text:
        return {
            "overall": 0, "decision": "SKIP",
            "reason": "Empty content — page may require JavaScript or blocked fetch.",
            "relevance": 0, "quality": 0, "redundancy": "unknown", "usability": 0
        }

    preview = text[:3000]
    prompt = EVAL_PROMPT_TEMPLATE.format(
        topic=topic, content_preview=preview, url=url
    )

    try:
        response = ollama.chat(
            model=EVAL_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1}
        )
        raw = response["message"]["content"]
        return parse_evaluation(raw)
    except Exception as e:
        return {
            "overall": 0, "decision": "FLAG",
            "reason": f"Evaluation failed: {e}",
            "relevance": 0, "quality": 0, "redundancy": "unknown", "usability": 0
        }

def parse_evaluation(raw: str) -> dict:
    """Parse Dex Jr.'s structured evaluation response."""
    result = {
        "relevance": 0, "quality": 0, "redundancy": "unknown",
        "usability": 0, "overall": 0, "decision": "FLAG", "reason": ""
    }
    try:
        for line in raw.strip().splitlines():
            if line.startswith("RELEVANCE:"):
                result["relevance"] = float(line.split(":")[1].strip())
            elif line.startswith("QUALITY:"):
                result["quality"] = float(line.split(":")[1].strip())
            elif line.startswith("REDUNDANCY:"):
                result["redundancy"] = line.split(":")[1].strip().lower()
            elif line.startswith("USABILITY:"):
                result["usability"] = float(line.split(":")[1].strip())
            elif line.startswith("OVERALL:"):
                result["overall"] = float(line.split(":")[1].strip())
            elif line.startswith("DECISION:"):
                result["decision"] = line.split(":")[1].strip().upper()
            elif line.startswith("REASON:"):
                result["reason"] = line.split(":", 1)[1].strip()
    except Exception:
        pass

    # Apply quality gate thresholds to override model decision if needed
    score = result["overall"]
    if score >= QUALITY_AUTO_INGEST:
        result["decision"] = "INGEST"
    elif score >= QUALITY_FLAG:
        result["decision"] = "FLAG"
    else:
        result["decision"] = "SKIP"

    return result

# ── Chunk + Ingest ────────────────────────────────────────────────────────────

def build_header(url: str, topic: str, score: float, fetch_date: str) -> str:
    """Standard source attribution header for every ingested document."""
    domain = urlparse(url).netloc
    return (
        f"SOURCE: {url}\n"
        f"DOMAIN: {domain}\n"
        f"TOPIC: {topic}\n"
        f"QUALITY_SCORE: {score}/10\n"
        f"FETCH_DATE: {fetch_date}\n"
        f"INGESTED_BY: dex-acquire.py v1.0\n"
        f"{'='*60}\n\n"
    )

def chunk_text(text: str) -> list[str]:
    """Chunk text by character count with overlap."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks

def ingest_to_collection(url: str, text: str, topic: str,
                          score: float, collection_name: str) -> int:
    """Ingest content into specified ChromaDB collection. Returns chunk count."""
    fetch_date = datetime.now().strftime("%Y-%m-%d")
    header = build_header(url, topic, score, fetch_date)
    full_text = header + text

    chunks = chunk_text(full_text)
    if not chunks:
        return 0

    collection = get_collection(collection_name)
    domain = urlparse(url).netloc
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]

    ids, embeddings, metadatas, documents = [], [], [], []

    for i, chunk in enumerate(chunks):
        chunk_id = f"acq_{url_hash}_{i:04d}"
        try:
            emb_response = ollama.embeddings(model=EMBED_MODEL, prompt=chunk)
            embedding = emb_response["embedding"]
        except Exception as e:
            print(f"    [WARN] Embedding failed for chunk {i}: {e}")
            continue

        ids.append(chunk_id)
        embeddings.append(embedding)
        documents.append(chunk)
        metadatas.append({
            "source_file": url,
            "filename": domain,
            "file_type": "external_web",
            "tier": "external",
            "status": "acquired",
            "chunk_index": i,
            "file_hash": url_hash,
            "char_count": len(chunk),
            "folder": f"acquired/{topic[:30].replace(' ', '_')}",
            "total_chunks": len(chunks),
            "topic": topic,
            "quality_score": score,
            "fetch_date": fetch_date
        })

    if ids:
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )

    return len(ids)

# ── Save file ─────────────────────────────────────────────────────────────────

def save_to_folder(url: str, text: str, topic: str, score: float,
                   subfolder: str, base_dir: str) -> str:
    """Save acquired content as .txt file. Returns path."""
    domain = urlparse(url).netloc.replace(".", "_")
    path_slug = urlparse(url).path.strip("/").replace("/", "_")[:40]
    filename = f"{domain}_{path_slug}.txt" if path_slug else f"{domain}.txt"

    folder = Path(base_dir) / subfolder
    folder.mkdir(parents=True, exist_ok=True)
    filepath = folder / filename

    fetch_date = datetime.now().strftime("%Y-%m-%d")
    header = build_header(url, topic, score, fetch_date)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(header + text)

    return str(filepath)

# ── Logging ───────────────────────────────────────────────────────────────────

def log_result(entry: dict):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

# ── Report ────────────────────────────────────────────────────────────────────

def print_report(results: list[dict], topic: str, auto_ingest: bool, collection: str):
    ingested = [r for r in results if r["action"] == "INGESTED"]
    flagged  = [r for r in results if r["action"] == "FLAGGED"]
    skipped  = [r for r in results if r["action"] == "SKIPPED"]
    failed   = [r for r in results if r["action"] == "FAILED"]

    total_chunks = sum(r.get("chunks_added", 0) for r in ingested)

    print("\n" + "="*60)
    print("  DEX JR. ACQUISITION REPORT")
    print(f"  Topic: {topic}")
    print(f"  Mode: {'AUTO-INGEST' if auto_ingest else 'REVIEW ONLY'}")
    print(f"  Collection: {collection}")
    print(f"  Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60)
    print(f"\n  URLS PROCESSED: {len(results)}")
    print(f"  INGESTED:  {len(ingested)} ({total_chunks} chunks added)")
    print(f"  FLAGGED:   {len(flagged)}  (needs review)")
    print(f"  SKIPPED:   {len(skipped)}")
    print(f"  FAILED:    {len(failed)}")

    if ingested:
        print("\n  ── INGESTED ──────────────────────────────────────────")
        for r in ingested:
            print(f"  [{r['score']:4.1f}] {r['url'][:60]}")
            print(f"         {r['reason']}")
            print(f"         → {r.get('chunks_added', 0)} chunks")

    if flagged:
        print("\n  ── FLAGGED (review before ingest) ───────────────────")
        for r in flagged:
            print(f"  [{r['score']:4.1f}] {r['url'][:60]}")
            print(f"         {r['reason']}")
            if r.get("saved_to"):
                print(f"         Saved: {r['saved_to']}")

    if skipped:
        print("\n  ── SKIPPED ───────────────────────────────────────────")
        for r in skipped:
            print(f"  [{r['score']:4.1f}] {r['url'][:60]}")
            print(f"         {r['reason']}")

    if failed:
        print("\n  ── FAILED ────────────────────────────────────────────")
        for r in failed:
            print(f"  [----] {r['url'][:60]}")
            print(f"         {r['reason']}")

    print("\n" + "="*60)

# ── URL loading ───────────────────────────────────────────────────────────────

def load_urls(source: str) -> list[str]:
    """Load URLs from file (one per line) or JSON plan."""
    path = Path(source)
    if not path.exists():
        print(f"[ERROR] File not found: {source}")
        sys.exit(1)

    if source.endswith(".json"):
        with open(source) as f:
            plan = json.load(f)
        # Support {"urls": [...]} or [{"url": ..., "topic": ...}]
        if isinstance(plan, list):
            return [item["url"] if isinstance(item, dict) else item for item in plan]
        return plan.get("urls", [])

    with open(source) as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Batch URL acquisition with Dex Jr. quality evaluation"
    )
    parser.add_argument("--topic",       required=False, help="Topic for relevance evaluation")
    parser.add_argument("--urls",        help="File of URLs (one per line)")
    parser.add_argument("--from-plan",   help="JSON acquisition plan")
    parser.add_argument("--auto-ingest", action="store_true",
                        help="Automatically ingest content scoring 7+/10")
    parser.add_argument("--review-only", action="store_true",
                        help="Evaluate only, do not ingest (default)")
    parser.add_argument("--collection",  default="ext_archive",
                        help="ChromaDB collection (default: ext_archive)")
    parser.add_argument("--save-dir",    default="acquisitions",
                        help="Base directory to save flagged/reviewed files")
    args = parser.parse_args()

    # Validate
    if not args.urls and not args.from_plan:
        print("[ERROR] Provide --urls or --from-plan")
        sys.exit(1)
    if not args.topic and not args.from_plan:
        print("[ERROR] Provide --topic")
        sys.exit(1)

    # Load URLs
    source = args.urls or args.from_plan
    urls = load_urls(source)
    topic = args.topic or "general acquisition"
    auto_ingest = args.auto_ingest
    collection_name = args.collection

    # Create topic slug for folder structure
    topic_slug = re.sub(r'[^a-z0-9]+', '-', topic.lower()).strip('-')[:40]
    save_base = Path(args.save_dir) / topic_slug

    print(f"\n{'='*60}")
    print(f"  DEX JR. ACQUISITION — {topic.upper()}")
    print(f"  URLs: {len(urls)}")
    print(f"  Mode: {'AUTO-INGEST (7+/10)' if auto_ingest else 'REVIEW ONLY'}")
    print(f"  Collection: {collection_name}")
    print(f"{'='*60}\n")

    results = []

    for i, url in enumerate(urls, 1):
        print(f"  [{i:02d}/{len(urls)}] {url[:70]}")

        # Fetch
        text, char_count = fetch_url(url)
        if not text:
            print(f"         FAILED — empty response")
            result = {
                "url": url, "topic": topic, "action": "FAILED",
                "score": 0, "reason": "Empty response or fetch error",
                "timestamp": datetime.now().isoformat()
            }
            results.append(result)
            log_result(result)
            time.sleep(REQUEST_DELAY)
            continue

        print(f"         Fetched {char_count:,} chars — evaluating...")

        # Evaluate
        evaluation = evaluate_content(url, text, topic)
        score = evaluation["overall"]
        decision = evaluation["decision"]
        reason = evaluation["reason"]

        print(f"         Score: {score}/10 | Decision: {decision}")
        print(f"         {reason}")

        result = {
            "url": url, "topic": topic, "score": score,
            "decision": decision, "reason": reason,
            "char_count": char_count,
            "evaluation": evaluation,
            "timestamp": datetime.now().isoformat()
        }

        # Act on decision
        if decision == "INGEST" and auto_ingest:
            chunks_added = ingest_to_collection(
                url, text, topic, score, collection_name
            )
            result["action"] = "INGESTED"
            result["chunks_added"] = chunks_added
            result["collection"] = collection_name
            print(f"         → Ingested {chunks_added} chunks to {collection_name}")

        elif decision == "INGEST" and not auto_ingest:
            # Review-only: save to flagged folder for operator review
            saved = save_to_folder(url, text, topic, score, "02_ingested", str(save_base))
            result["action"] = "FLAGGED"
            result["saved_to"] = saved
            result["note"] = "Scored INGEST but --auto-ingest not set. Review and ingest manually."
            print(f"         → Saved to {saved} (review-only mode)")

        elif decision == "FLAG":
            saved = save_to_folder(url, text, topic, score, "04_flagged", str(save_base))
            result["action"] = "FLAGGED"
            result["saved_to"] = saved
            print(f"         → Saved to {saved} for operator review")

        else:  # SKIP
            saved = save_to_folder(url, text, topic, score, "03_skipped", str(save_base))
            result["action"] = "SKIPPED"
            result["saved_to"] = saved
            print(f"         → Skipped (score too low)")

        results.append(result)
        log_result(result)
        time.sleep(REQUEST_DELAY)

    # Save full report as JSON
    report_path = save_base / "99_acquisition_report.json"
    save_base.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump({
            "topic": topic,
            "collection": collection_name,
            "auto_ingest": auto_ingest,
            "run_date": datetime.now().isoformat(),
            "results": results
        }, f, indent=2)

    # Print human report
    print_report(results, topic, auto_ingest, collection_name)
    print(f"  Full report: {report_path}\n")


if __name__ == "__main__":
    main()
