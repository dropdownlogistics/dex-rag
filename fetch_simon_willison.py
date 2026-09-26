"""
fetch_simon_willison.py
Fetches Simon Willison's blog posts for DDL ext_creator corpus.
Nominated by: Seat 1004 (Max Sullivan / Perplexity)
Target: C:/Users/dkitc/DDL_External/nominations/ext_creator/1004_SimonWillison/
"""

import requests
import re
import html
import os
import time
import json
from datetime import datetime

OUTPUT_DIR = r"C:\Users\dkitc\DDL_External\nominations\ext_creator\1004_SimonWillison"

# High-value post categories to fetch
# Simon's site has topic pages — we target AI/LLM/data tooling content
FEED_URLS = [
    "https://simonwillison.net/tags/ai/",
    "https://simonwillison.net/tags/llms/",
    "https://simonwillison.net/tags/datasette/",
    "https://simonwillison.net/tags/sqlite/",
    "https://simonwillison.net/tags/python/",
]

# Also fetch his TIL (Today I Learned) feed — high signal
TIL_FEED = "https://til.simonwillison.net/"

def clean_html(raw):
    """Strip HTML tags, decode entities, collapse whitespace."""
    # Remove script and style blocks
    raw = re.sub(r'<script[^>]*>.*?</script>', '', raw, flags=re.DOTALL)
    raw = re.sub(r'<style[^>]*>.*?</style>', '', raw, flags=re.DOTALL)
    # Remove all HTML tags
    raw = re.sub(r'<[^>]+>', '', raw)
    # Decode HTML entities
    raw = html.unescape(raw)
    # Collapse whitespace
    raw = re.sub(r'\n{3,}', '\n\n', raw)
    raw = re.sub(r'[ \t]{2,}', ' ', raw)
    return raw.strip()

def fetch_page(url, delay=1.5):
    """Fetch a URL with polite delay."""
    try:
        time.sleep(delay)
        r = requests.get(url, timeout=30, headers={
            'User-Agent': 'DDL-Corpus-Builder/1.0 (educational research)'
        })
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"  WARN: Failed to fetch {url}: {e}")
        return None

def extract_post_links(page_html, base="https://simonwillison.net"):
    """Extract individual post links from a tag/index page."""
    # Simon's posts follow pattern: /YYYY/Mon/DD/slug/
    pattern = r'href="(/\d{4}/\w+/\d+/[^"]+/)"'
    links = re.findall(pattern, page_html)
    # Deduplicate and make absolute
    seen = set()
    result = []
    for link in links:
        if link not in seen:
            seen.add(link)
            result.append(base + link)
    return result

def fetch_and_save_post(url, output_dir, index):
    """Fetch a single post, clean it, save as txt."""
    raw = fetch_page(url)
    if not raw:
        return False

    clean = clean_html(raw)

    # Extract title from URL slug
    slug = url.rstrip('/').split('/')[-1]
    date_parts = url.split('/')
    try:
        year = date_parts[3]
        month = date_parts[4]
        day = date_parts[5]
        date_str = f"{year}-{month}-{day}"
    except:
        date_str = "unknown-date"

    filename = f"SW_{date_str}_{slug[:60]}.txt"
    filepath = os.path.join(output_dir, filename)

    # Add metadata header
    content = f"""=====================================================================
SIMON WILLISON — BLOG POST
Source: {url}
Fetched: {datetime.now().strftime('%Y-%m-%d')}
Nominated by: Seat 1004 (Max Sullivan)
Collection: ext_creator
=====================================================================

{clean}
"""

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"  [{index}] Saved: {filename} ({len(clean):,} chars)")
    return True

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print("SIMON WILLISON CORPUS FETCH")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 60)

    all_links = set()

    # Collect post links from tag pages
    print("\nCollecting post links...")
    for feed_url in FEED_URLS:
        print(f"  Scanning: {feed_url}")
        page = fetch_page(feed_url)
        if page:
            links = extract_post_links(page)
            print(f"    Found {len(links)} posts")
            all_links.update(links)

    print(f"\nTotal unique posts found: {len(all_links)}")

    # Fetch and save each post
    print("\nFetching posts...")
    saved = 0
    failed = 0

    for i, url in enumerate(sorted(all_links), 1):
        success = fetch_and_save_post(url, OUTPUT_DIR, i)
        if success:
            saved += 1
        else:
            failed += 1

    print("\n" + "=" * 60)
    print(f"COMPLETE")
    print(f"Saved:  {saved} posts")
    print(f"Failed: {failed} posts")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 60)
    print("\nNext step:")
    print('python dex-ingest.py --path "C:\\Users\\dkitc\\DDL_External\\nominations\\ext_creator\\1004_SimonWillison" --collection ext_creator --nominated-by "1004" --fast')

if __name__ == "__main__":
    main()

