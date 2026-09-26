"""
fetch_ext_creators.py
Batch fetch for all DDL council-approved ext_creator nominations.
Runs sequentially with polite delays between requests.

Nominations:
  Benn Stancil      — Seat 1002 (Marcus Caldwell)
  Simon Willison    — Seat 1004 (Max Sullivan)      [may already be fetched]
  Gwern Branwen     — Seat 1003 (Elias Mercer)
  patio11           — Seat 1002 (Marcus Caldwell)
  Maggie Appleton   — Seat 1002 (Marcus Caldwell)
  Tiago Forte       — Seat 1006 (Ava Sinclair)
  John Cutler       — Seat 1008 (Marcus Grey)
  Greg Wilson       — Seat 1009 (Kai Langford)
  Simon Wardley     — Seat 1007 (Leo Prescott)
"""

import requests
import re
import html
import os
import time
from datetime import datetime

BASE_DIR = r"C:/Users/dkitc/DDL_External/nominations/ext_creator"

CREATORS = [
    {
        "name": "BennStancil",
        "seat": "1002",
        "urls": [
            "https://benn.substack.com/",
            "https://benn.substack.com/archive",
        ],
        "link_pattern": r'href="(https://benn\.substack\.com/p/[^"]+)"',
        "base": "",
    },
    {
        "name": "SimonWillison",
        "seat": "1004",
        "urls": [
            "https://simonwillison.net/tags/ai/",
            "https://simonwillison.net/tags/llms/",
            "https://simonwillison.net/tags/datasette/",
        ],
        "link_pattern": r'href="(/\d{4}/\w+/\d+/[^"]+/)"',
        "base": "https://simonwillison.net",
    },
    {
        "name": "Gwern",
        "seat": "1003",
        "urls": [
            "https://gwern.net/index",
        ],
        "link_pattern": r'href="(https://gwern\.net/[a-z][^"#]+)"',
        "base": "",
        "max_posts": 30,
    },
    {
        "name": "patio11",
        "seat": "1002",
        "urls": [
            "https://www.kalzumeus.com/archive/",
            "https://www.kalzumeus.com/",
        ],
        "link_pattern": r'href="(https://www\.kalzumeus\.com/\d{4}/[^"]+)"',
        "base": "",
    },
    {
        "name": "MaggieAppleton",
        "seat": "1002",
        "urls": [
            "https://maggieappleton.com/essays",
        ],
        "link_pattern": r'href="(/essays/[^"]+)"',
        "base": "https://maggieappleton.com",
    },
    {
        "name": "TiagoForte",
        "seat": "1006",
        "urls": [
            "https://fortelabs.com/blog/",
        ],
        "link_pattern": r'href="(https://fortelabs\.com/blog/[^"]+)"',
        "base": "",
        "max_posts": 40,
    },
    {
        "name": "JohnCutler",
        "seat": "1008",
        "urls": [
            "https://cutlefish.substack.com/archive",
        ],
        "link_pattern": r'href="(https://cutlefish\.substack\.com/p/[^"]+)"',
        "base": "",
        "max_posts": 50,
    },
    {
        "name": "GregWilson",
        "seat": "1009",
        "urls": [
            "https://third-bit.com/",
            "https://third-bit.com/blog/",
        ],
        "link_pattern": r'href="(/\d{4}/\d{2}/\d{2}/[^"]+)"',
        "base": "https://third-bit.com",
        "max_posts": 40,
    },
    {
        "name": "SimonWardley",
        "seat": "1007",
        "urls": [
            "https://blog.gardeviance.org/",
        ],
        "link_pattern": r'href="(https://blog\.gardeviance\.org/\d{4}/\d{2}/[^"]+\.html)"',
        "base": "",
        "max_posts": 40,
    },
]


def clean_html(raw):
    raw = re.sub(r'<script[^>]*>.*?</script>', '', raw, flags=re.DOTALL)
    raw = re.sub(r'<style[^>]*>.*?</style>', '', raw, flags=re.DOTALL)
    raw = re.sub(r'<[^>]+>', '', raw)
    raw = html.unescape(raw)
    raw = re.sub(r'\n{3,}', '\n\n', raw)
    raw = re.sub(r'[ \t]{2,}', ' ', raw)
    return raw.strip()


def fetch_page(url, delay=2.0):
    try:
        time.sleep(delay)
        r = requests.get(url, timeout=30, headers={
            'User-Agent': 'DDL-Corpus-Builder/1.0 (educational research)'
        })
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"    WARN: Failed {url}: {e}")
        return None


def extract_links(page_html, pattern, base=""):
    links = re.findall(pattern, page_html)
    seen = set()
    result = []
    for link in links:
        full = base + link if base and not link.startswith('http') else link
        # Strip query strings and fragments
        full = full.split('?')[0].split('#')[0]
        if full not in seen and len(full) > 20:
            seen.add(full)
            result.append(full)
    return result


def save_post(url, content, output_dir, creator_name, seat, index):
    clean = clean_html(content)
    if len(clean) < 200:
        return False  # Skip near-empty pages

    # Build filename from URL
    slug = url.rstrip('/').split('/')[-1][:60]
    slug = re.sub(r'[^\w\-]', '_', slug)
    filename = f"{creator_name}_{index:03d}_{slug}.txt"
    filepath = os.path.join(output_dir, filename)

    doc = f"""=====================================================================
{creator_name.upper()} — ARTICLE
Source: {url}
Fetched: {datetime.now().strftime('%Y-%m-%d')}
Nominated by: Seat {seat}
Collection: ext_creator
=====================================================================

{clean}
"""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(doc)

    print(f"    [{index}] {filename[:70]} ({len(clean):,} chars)")
    return True


def fetch_creator(creator, base_dir):
    name = creator['name']
    seat = creator['seat']
    max_posts = creator.get('max_posts', 60)
    output_dir = os.path.join(base_dir, f"{seat}_{name}")
    os.makedirs(output_dir, exist_ok=True)

    # Skip if already has content
    existing = len([f for f in os.listdir(output_dir) if f.endswith('.txt')])
    if existing > 5:
        print(f"  [{name}] Already has {existing} files — skipping")
        return existing, 0

    print(f"\n{'='*60}")
    print(f"  FETCHING: {name} (Seat {seat})")
    print(f"  Output: {output_dir}")

    # Collect post links
    all_links = []
    for url in creator['urls']:
        print(f"  Scanning: {url}")
        page = fetch_page(url)
        if page:
            links = extract_links(page, creator['link_pattern'], creator.get('base', ''))
            print(f"    Found {len(links)} links")
            all_links.extend(links)

    # Deduplicate
    seen = set()
    unique_links = []
    for l in all_links:
        if l not in seen:
            seen.add(l)
            unique_links.append(l)

    unique_links = unique_links[:max_posts]
    print(f"  Fetching {len(unique_links)} posts (max {max_posts})...")

    saved = 0
    failed = 0
    for i, url in enumerate(unique_links, 1):
        content = fetch_page(url)
        if content:
            ok = save_post(url, content, output_dir, name, seat, i)
            if ok:
                saved += 1
            else:
                failed += 1
        else:
            failed += 1

    print(f"  DONE: {saved} saved, {failed} failed")
    return saved, failed


def main():
    print("=" * 60)
    print("DDL EXT_CREATOR BATCH FETCH")
    print(f"Output base: {BASE_DIR}")
    print(f"Creators: {len(CREATORS)}")
    print("=" * 60)

    total_saved = 0
    total_failed = 0
    results = []

    for creator in CREATORS:
        saved, failed = fetch_creator(creator, BASE_DIR)
        total_saved += saved
        total_failed += failed
        results.append((creator['name'], saved, failed))

    print("\n" + "=" * 60)
    print("BATCH COMPLETE")
    print("=" * 60)
    for name, saved, failed in results:
        print(f"  {name:<20} {saved:>4} saved  {failed:>3} failed")
    print(f"  {'TOTAL':<20} {total_saved:>4} saved  {total_failed:>3} failed")
    print("\nNext step — ingest all nominations:")
    print('  python dex-ingest.py --path "C:/Users/dkitc/DDL_External/nominations/ext_creator" --collection ext_creator --nominated-by "1002,1003,1004,1006,1007,1008,1009" --fast')


if __name__ == "__main__":
    main()
