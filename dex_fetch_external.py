"""
dex_fetch_external.py -- External content pipeline.

Reads external-sources.csv, fetches URLs with polite crawling,
extracts text, ingests into corpus.

Usage:
  python dex_fetch_external.py              # process due URLs
  python dex_fetch_external.py --dry-run    # show what would fetch
  python dex_fetch_external.py --add <url>  # add URL to CSV interactively
  python dex_fetch_external.py --status     # show fetch status summary

Step 60.2 | Authority: CLAUDE.md Rule 8, ADR-CORPUS-001
"""

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

import dex_core

# ── Constants ────────────────────────────────────────────────────────────────

USER_AGENT = "DexJr-Fetcher/1.0 (DDL Research; contact: operator@dropdownlogistics.com)"

# Rate limits (non-negotiable)
SAME_DOMAIN_DELAY = 5.0     # seconds between requests to same domain
DIFF_DOMAIN_DELAY = 2.0     # seconds between requests to different domains
MAX_URLS_PER_RUN = 50
MAX_PAGE_SIZE = 5 * 1024 * 1024        # 5 MB per page
MAX_TOTAL_FETCH = 50 * 1024 * 1024     # 50 MB total per run

# Chunking (matches dex-ingest.py defaults)
CHUNK_SIZE_CHARS = 1000
CHUNK_OVERLAP_CHARS = 100

# Frequency intervals
FREQUENCY_INTERVALS = {
    "daily":   timedelta(days=1),
    "weekly":  timedelta(days=7),
    "monthly": timedelta(days=30),
}

# Allowed target collections (NEVER dex_canon)
ALLOWED_COLLECTIONS = {"ext_creator", "ext_reference"}

# robots.txt cache (in-memory, per run; file cache for 24h)
ROBOTS_CACHE_DIR = os.path.join(dex_core.SCRIPT_DIR, ".robots_cache")

CSV_FIELDS = [
    "url", "source_name", "category", "target_collection",
    "frequency", "added_by", "status", "last_fetched", "etag",
]


# ── CSV I/O ──────────────────────────────────────────────────────────────────

def read_csv() -> list[dict]:
    """Read external-sources.csv, return list of row dicts."""
    path = dex_core.EXTERNAL_SOURCES_CSV
    if not os.path.exists(path):
        print(f"[ERROR] CSV not found: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_csv(rows: list[dict]):
    """Write rows back to external-sources.csv."""
    path = dex_core.EXTERNAL_SOURCES_CSV
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


# ── Robots.txt ───────────────────────────────────────────────────────────────

def _robots_cache_path(domain: str) -> str:
    os.makedirs(ROBOTS_CACHE_DIR, exist_ok=True)
    safe = domain.replace(":", "_").replace("/", "_")
    return os.path.join(ROBOTS_CACHE_DIR, f"{safe}.json")


def check_robots(url: str) -> bool:
    """Return True if robots.txt allows fetching this URL.
    Caches per-domain for 24 hours. If unreachable, allow with caution."""
    parsed = urlparse(url)
    domain = parsed.netloc
    robots_url = f"{parsed.scheme}://{domain}/robots.txt"

    # Check file cache
    cache_path = _robots_cache_path(domain)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                cached = json.load(f)
            cached_at = datetime.fromisoformat(cached["cached_at"])
            if datetime.now(timezone.utc) - cached_at < timedelta(hours=24):
                rp = RobotFileParser()
                rp.parse(cached["lines"])
                return rp.can_fetch(USER_AGENT, url)
        except Exception:
            pass  # stale or corrupt cache, refetch

    # Fetch robots.txt
    try:
        resp = requests.get(robots_url, headers={"User-Agent": USER_AGENT}, timeout=10)
        if resp.status_code == 200:
            lines = resp.text.splitlines()
        else:
            lines = []  # no robots.txt = everything allowed
    except requests.RequestException:
        lines = []  # unreachable = proceed with caution

    # Cache
    try:
        with open(cache_path, "w") as f:
            json.dump({
                "domain": domain,
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "lines": lines,
            }, f)
    except Exception:
        pass

    rp = RobotFileParser()
    rp.parse(lines)
    return rp.can_fetch(USER_AGENT, url)


# ── Fetch ────────────────────────────────────────────────────────────────────

def fetch_url(url: str, etag: str = "", last_modified: str = "") -> dict:
    """Fetch a URL with proper headers. Returns dict with text, headers, status."""
    headers = {"User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    try:
        resp = requests.get(url, headers=headers, timeout=30, stream=True)

        # Check content length before downloading body
        content_length = resp.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_PAGE_SIZE:
            resp.close()
            return {"status": "skipped", "reason": f"too large ({int(content_length)} bytes)", "code": 0}

        if resp.status_code == 304:
            return {"status": "not_modified", "code": 304}

        if resp.status_code == 429:
            return {"status": "rate_limited", "code": 429}

        if resp.status_code == 403:
            return {"status": "forbidden", "code": 403}

        if resp.status_code >= 400:
            return {"status": "error", "reason": f"HTTP {resp.status_code}", "code": resp.status_code}

        resp.raise_for_status()

        # Read content with size cap
        content = resp.content[:MAX_PAGE_SIZE]
        content_type = resp.headers.get("Content-Type", "")

        return {
            "status": "ok",
            "code": resp.status_code,
            "content": content,
            "content_type": content_type,
            "etag": resp.headers.get("ETag", ""),
            "last_modified": resp.headers.get("Last-Modified", ""),
            "size": len(content),
        }
    except requests.RequestException as e:
        return {"status": "error", "reason": str(e), "code": 0}


# ── Text extraction ─────────────────────────────────────────────────────────

def extract_html(content: bytes) -> str:
    """Extract readable text from HTML content."""
    soup = BeautifulSoup(content, "html.parser")
    # Remove non-content elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def extract_text(content: bytes, content_type: str, url: str) -> str:
    """Extract text based on content type."""
    ct = content_type.lower()

    if "html" in ct or "xhtml" in ct:
        return extract_html(content)

    if "application/pdf" in ct or url.lower().endswith(".pdf"):
        # Try pdfplumber, fall back to PyPDF2, fall back to skip
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
            return "\n\n".join(pages).strip()
        except ImportError:
            pass
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(io.BytesIO(content))
            pages = [p.extract_text() or "" for p in reader.pages]
            return "\n\n".join(pages).strip()
        except ImportError:
            return ""  # no PDF library available

    if "text/plain" in ct or "text/csv" in ct:
        return content.decode("utf-8", errors="replace").strip()

    if "json" in ct:
        try:
            data = json.loads(content)
            return json.dumps(data, indent=2, ensure_ascii=False)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return ""

    # Unknown content type -- skip
    return ""


# ── Chunking ─────────────────────────────────────────────────────────────────

def chunk_text(text: str) -> list[str]:
    """Chunk text by character count with overlap."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE_CHARS
        chunks.append(text[start:end])
        start += CHUNK_SIZE_CHARS - CHUNK_OVERLAP_CHARS
    return chunks


# ── Ingest ───────────────────────────────────────────────────────────────────

def ingest_chunks(url: str, text: str, row: dict) -> int:
    """Chunk text and ingest into target collection. Returns chunk count."""
    base_name = row["target_collection"]
    if base_name not in ALLOWED_COLLECTIONS:
        print(f"    [BLOCKED] Collection '{base_name}' not in allowed list")
        return 0

    source_label = f"{row['source_name']} -- {url}"
    chunks = chunk_text(text)
    if not chunks:
        return 0

    collection = dex_core.get_collection(base_name)
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    fetch_date = datetime.now().strftime("%Y-%m-%d")

    ids, embeddings, documents, metadatas = [], [], [], []

    for i, chunk in enumerate(chunks):
        chunk_id = f"ext_{url_hash}_{i:04d}"
        try:
            emb = dex_core.embed(chunk)
        except Exception as e:
            print(f"    [WARN] Embedding failed for chunk {i}: {e}")
            continue

        ids.append(chunk_id)
        embeddings.append(emb)
        documents.append(chunk)
        metadatas.append({
            "source_file": source_label,
            "filename": urlparse(url).netloc,
            "file_type": "external_web",
            "category": row.get("category", ""),
            "added_by": row.get("added_by", ""),
            "fetch_date": fetch_date,
            "chunk_index": i,
            "total_chunks": len(chunks),
        })

    if ids:
        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    return len(ids)


# ── Scheduling logic ─────────────────────────────────────────────────────────

def is_due(row: dict) -> bool:
    """Check if a row's URL is due for fetching based on frequency."""
    status = row.get("status", "").strip()
    freq = row.get("frequency", "one-time").strip()
    last = row.get("last_fetched", "").strip()

    if status == "skipped":
        return False

    if freq == "one-time":
        return status == "pending"

    if not last:
        return True  # never fetched

    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        return True  # malformed date, treat as never fetched

    interval = FREQUENCY_INTERVALS.get(freq)
    if interval is None:
        return False

    return datetime.now() - last_dt >= interval


# ── Logging ──────────────────────────────────────────────────────────────────

def log_entry(entry: dict):
    """Append a structured log entry to dex-fetch-log.jsonl."""
    entry["timestamp"] = datetime.now().isoformat()
    try:
        with open(dex_core.FETCH_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"    [WARN] Log write failed: {e}")


# ── Rate limiter ─────────────────────────────────────────────────────────────

class RateLimiter:
    """Enforces per-domain and cross-domain rate limits."""

    def __init__(self):
        self._last_fetch: dict[str, float] = {}  # domain -> timestamp
        self._last_any: float = 0.0
        self._blocked_domains: set[str] = set()

    def block_domain(self, domain: str):
        self._blocked_domains.add(domain)

    def is_blocked(self, domain: str) -> bool:
        return domain in self._blocked_domains

    def wait(self, domain: str):
        now = time.time()

        # Cross-domain minimum
        since_any = now - self._last_any
        if since_any < DIFF_DOMAIN_DELAY:
            time.sleep(DIFF_DOMAIN_DELAY - since_any)

        # Same-domain minimum
        last_domain = self._last_fetch.get(domain, 0.0)
        since_domain = time.time() - last_domain
        if since_domain < SAME_DOMAIN_DELAY:
            time.sleep(SAME_DOMAIN_DELAY - since_domain)

        self._last_fetch[domain] = time.time()
        self._last_any = time.time()


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_status():
    """Print summary of external-sources.csv."""
    rows = read_csv()
    if not rows:
        print("  No entries in external-sources.csv")
        return

    pending = [r for r in rows if r["status"] == "pending"]
    fetched = [r for r in rows if r["status"] == "fetched"]
    failed = [r for r in rows if r["status"] == "failed"]
    skipped = [r for r in rows if r["status"] == "skipped"]
    due = [r for r in rows if is_due(r)]

    print()
    print("=" * 60)
    print("  EXTERNAL SOURCES STATUS")
    print("=" * 60)
    print(f"  Total entries:  {len(rows)}")
    print(f"  Pending:        {len(pending)}")
    print(f"  Fetched:        {len(fetched)}")
    print(f"  Failed:         {len(failed)}")
    print(f"  Skipped:        {len(skipped)}")
    print(f"  Due now:        {len(due)}")
    print()

    for r in rows:
        due_mark = " *DUE*" if is_due(r) else ""
        last = r.get("last_fetched", "")[:10] or "never"
        print(f"  [{r['status']:>8}] {r['target_collection']:>14} | {r['frequency']:>8} | {last} | {r['source_name'][:30]}{due_mark}")

    print()
    print("=" * 60)


def cmd_add(url: str):
    """Interactively add a URL to the CSV."""
    rows = read_csv()

    # Check for duplicates
    existing = [r for r in rows if r["url"] == url]
    if existing:
        print(f"  [SKIP] URL already in CSV: {existing[0]['source_name']}")
        return

    print(f"\n  Adding: {url}\n")

    source_name = input("  Source name: ").strip()
    category = input("  Category (e.g. technology, productivity): ").strip()

    print("  Target collection:")
    print("    1. ext_creator  (blogs, articles, commentary)")
    print("    2. ext_reference (standards, specs, docs)")
    choice = input("  Choice [1/2]: ").strip()
    target = "ext_reference" if choice == "2" else "ext_creator"

    print("  Frequency:")
    print("    1. one-time   2. daily   3. weekly   4. monthly")
    freq_choice = input("  Choice [1-4]: ").strip()
    freq_map = {"1": "one-time", "2": "daily", "3": "weekly", "4": "monthly"}
    frequency = freq_map.get(freq_choice, "one-time")

    added_by = input("  Added by (seat number or 'operator'): ").strip() or "operator"

    row = {
        "url": url,
        "source_name": source_name,
        "category": category,
        "target_collection": target,
        "frequency": frequency,
        "added_by": added_by,
        "status": "pending",
        "last_fetched": "",
        "etag": "",
    }
    rows.append(row)
    write_csv(rows)
    print(f"\n  Added to external-sources.csv ({len(rows)} total entries)")


def cmd_dry_run():
    """Show what would be fetched without actually fetching."""
    rows = read_csv()
    due = [r for r in rows if is_due(r)]

    print()
    print("=" * 60)
    print("  DRY RUN -- External Fetch")
    print("=" * 60)
    print(f"  Total entries: {len(rows)}")
    print(f"  Due for fetch: {len(due)}")
    print(f"  Would process: {min(len(due), MAX_URLS_PER_RUN)} (cap: {MAX_URLS_PER_RUN})")
    print()

    for i, r in enumerate(due[:MAX_URLS_PER_RUN], 1):
        print(f"  {i:3d}. [{r['frequency']:>8}] -> {r['target_collection']:>14} | {r['source_name']}")
        print(f"       {r['url'][:70]}")

    if len(due) > MAX_URLS_PER_RUN:
        print(f"\n  ... {len(due) - MAX_URLS_PER_RUN} more URLs will carry to next run")

    print()
    print("=" * 60)


def cmd_fetch():
    """Main fetch pipeline -- process due URLs."""
    rows = read_csv()
    due = [r for r in rows if is_due(r)]

    if not due:
        print("  No URLs due for fetching.")
        return

    batch = due[:MAX_URLS_PER_RUN]
    limiter = RateLimiter()
    total_bytes = 0
    stats = {"fetched": 0, "skipped": 0, "failed": 0, "not_modified": 0, "chunks": 0}

    print()
    print("=" * 60)
    print(f"  EXTERNAL FETCH -- {len(batch)} URLs")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)
    print()

    for i, row in enumerate(batch, 1):
        url = row["url"]
        domain = urlparse(url).netloc
        print(f"  [{i:02d}/{len(batch)}] {row['source_name']}")
        print(f"         {url[:70]}")

        # Domain blocked this run?
        if limiter.is_blocked(domain):
            print(f"         SKIPPED -- domain blocked (429 earlier)")
            row["status"] = "failed"
            log_entry({"url": url, "action": "skipped", "reason": "domain_blocked_429"})
            stats["skipped"] += 1
            continue

        # robots.txt check
        if not check_robots(url):
            print(f"         SKIPPED -- robots.txt disallows")
            row["status"] = "skipped"
            log_entry({"url": url, "action": "skipped", "reason": "robots.txt"})
            stats["skipped"] += 1
            continue

        # Rate limit
        limiter.wait(domain)

        # Fetch
        result = fetch_url(url, etag=row.get("etag", ""))

        if result["status"] == "not_modified":
            print(f"         304 Not Modified -- skipping")
            row["last_fetched"] = datetime.now().isoformat()
            log_entry({"url": url, "action": "not_modified", "code": 304})
            stats["not_modified"] += 1
            continue

        if result["status"] == "rate_limited":
            print(f"         429 -- blocking domain for rest of run")
            limiter.block_domain(domain)
            row["status"] = "failed"
            log_entry({"url": url, "action": "rate_limited", "code": 429})
            stats["failed"] += 1
            continue

        if result["status"] == "forbidden":
            print(f"         403 Forbidden -- marking skipped")
            row["status"] = "skipped"
            log_entry({"url": url, "action": "skipped", "reason": "403_forbidden", "code": 403})
            stats["skipped"] += 1
            continue

        if result["status"] in ("error", "skipped"):
            reason = result.get("reason", "unknown")
            print(f"         FAILED -- {reason}")
            row["status"] = "failed"
            log_entry({"url": url, "action": "failed", "reason": reason, "code": result.get("code", 0)})
            stats["failed"] += 1
            continue

        # Check total fetch budget
        size = result.get("size", 0)
        total_bytes += size
        if total_bytes > MAX_TOTAL_FETCH:
            print(f"         SKIPPED -- total fetch budget exceeded ({total_bytes // (1024*1024)}MB)")
            row["status"] = "failed"
            log_entry({"url": url, "action": "skipped", "reason": "total_budget_exceeded"})
            stats["skipped"] += 1
            break

        # Extract text
        text = extract_text(result["content"], result.get("content_type", ""), url)
        if not text or len(text) < 50:
            print(f"         SKIPPED -- no usable text extracted")
            row["status"] = "failed"
            log_entry({"url": url, "action": "failed", "reason": "empty_extraction", "code": result["code"]})
            stats["failed"] += 1
            continue

        print(f"         Extracted {len(text):,} chars -- ingesting...")

        # Validate target collection
        target = row.get("target_collection", "ext_creator")
        if target not in ALLOWED_COLLECTIONS:
            print(f"         BLOCKED -- collection '{target}' not allowed for external content")
            row["status"] = "failed"
            log_entry({"url": url, "action": "blocked", "reason": f"collection_{target}_not_allowed"})
            stats["failed"] += 1
            continue

        # Ingest
        chunks_added = ingest_chunks(url, text, row)
        print(f"         Ingested {chunks_added} chunks -> {dex_core.suffixed(target)}")

        # Update row
        row["status"] = "fetched"
        row["last_fetched"] = datetime.now().isoformat()
        row["etag"] = result.get("etag", "")

        log_entry({
            "url": url,
            "action": "fetched",
            "code": result["code"],
            "chars": len(text),
            "chunks": chunks_added,
            "collection": dex_core.suffixed(target),
            "size_bytes": size,
        })
        stats["fetched"] += 1
        stats["chunks"] += chunks_added

    # Write updated CSV
    write_csv(rows)

    # Summary
    print()
    print("=" * 60)
    print("  FETCH SUMMARY")
    print("=" * 60)
    print(f"  Fetched:       {stats['fetched']}")
    print(f"  Not modified:  {stats['not_modified']}")
    print(f"  Skipped:       {stats['skipped']}")
    print(f"  Failed:        {stats['failed']}")
    print(f"  Chunks added:  {stats['chunks']}")
    print(f"  Total data:    {total_bytes / 1024:.1f} KB")
    print(f"  Log: {dex_core.FETCH_LOG}")
    print("=" * 60)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="External content pipeline -- polite CSV-driven URL fetcher"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be fetched without fetching")
    parser.add_argument("--status", action="store_true",
                        help="Show fetch status summary")
    parser.add_argument("--add", metavar="URL",
                        help="Add a URL to external-sources.csv")
    args = parser.parse_args()

    if args.status:
        cmd_status()
    elif args.add:
        cmd_add(args.add)
    elif args.dry_run:
        cmd_dry_run()
    else:
        cmd_fetch()


if __name__ == "__main__":
    main()
