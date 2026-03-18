"""
fetch_leila_gharani.py
Fetches Leila Gharani YouTube video transcripts for DDL ext_creator corpus.
Nominated by: Operator (Dave Kitchens) — Excel/data domain
Target: C:\Users\dkitc\DDL_External\nominations\ext_creator\operator_LeilaGharani\

Uses youtube-transcript-api for fast caption extraction.
No audio download required.
"""

import os
import re
import time
from datetime import datetime

from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import requests
from bs4 import BeautifulSoup

OUTPUT_DIR = r"C:/Users/dkitc/DDL_External/nominations/ext_creator/operator_LeilaGharani"

# Leila Gharani's YouTube channel ID
CHANNEL_ID = "UCJtUqG78MOs4eWTCKKDkYnw"

# Her most valuable playlists / video categories for DDL corpus
# High signal: Excel formulas, Power Query, data analysis, dashboards
PLAYLIST_IDS = [
    "PLmHVyfmcRKyx4o7CoLMFuzJEXJjhOLLs5",  # Excel Tips
    "PLmHVyfmcRKyxanRtBkSmgbMWLwRqT2Pq3",  # Power Query
    "PLmHVyfmcRKyw5gfN7mKcV9LHZMS7HZ4sR",  # Excel Dashboards
    "PLmHVyfmcRKywSFDBVBYIivpNQM6WZHZPV",  # Excel Functions
]

# Also seed with known high-value video IDs directly
SEED_VIDEO_IDS = [
    "0uqAVWOk_Vg",  # XLOOKUP
    "oCkj4k3mNak",  # LAMBDA
    "4-_YN0Z-TcE",  # LET function
    "eBnkGzIkLV0",  # Dynamic arrays
    "8cFoZbVDctQ",  # Power Query intro
    "2U4nNZKOy6E",  # Dashboard tips
    "bE8Tz1RYaOo",  # Advanced Excel tips
    "6oHVl99lkuQ",  # Excel tables
    "m3P3WRJRNCE",  # MAKEARRAY
]


def get_video_ids_from_playlist(playlist_id, max_videos=30):
    """Extract video IDs from a YouTube playlist page."""
    url = f"https://www.youtube.com/playlist?list={playlist_id}"
    try:
        time.sleep(2)
        r = requests.get(url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        # Extract video IDs from page source
        video_ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', r.text)
        # Deduplicate
        seen = set()
        unique = []
        for vid in video_ids:
            if vid not in seen:
                seen.add(vid)
                unique.append(vid)
        return unique[:max_videos]
    except Exception as e:
        print(f"  WARN: Could not fetch playlist {playlist_id}: {e}")
        return []


def get_transcript(video_id):
    """Fetch transcript for a YouTube video."""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
        # Combine all segments into clean text
        full_text = ' '.join([seg['text'] for seg in transcript_list])
        # Clean up
        full_text = re.sub(r'\[.*?\]', '', full_text)  # Remove [Music], [Applause] etc
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        return full_text
    except (TranscriptsDisabled, NoTranscriptFound):
        return None
    except Exception as e:
        print(f"    WARN: Transcript error for {video_id}: {e}")
        return None


def get_video_title(video_id):
    """Get video title from YouTube."""
    try:
        time.sleep(1)
        r = requests.get(
            f"https://www.youtube.com/watch?v={video_id}",
            timeout=20,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        match = re.search(r'"title":"([^"]+)"', r.text)
        if match:
            return match.group(1)
        return f"video_{video_id}"
    except:
        return f"video_{video_id}"


def save_transcript(video_id, title, transcript, output_dir, index):
    """Save transcript as a governed text file."""
    # Clean title for filename
    safe_title = re.sub(r'[^\w\s-]', '', title)[:60].strip()
    safe_title = re.sub(r'\s+', '_', safe_title)
    filename = f"LeilaGharani_{index:03d}_{safe_title}.txt"
    filepath = os.path.join(output_dir, filename)

    content = f"""=====================================================================
LEILA GHARANI — YOUTUBE TRANSCRIPT
Video: https://www.youtube.com/watch?v={video_id}
Title: {title}
Fetched: {datetime.now().strftime('%Y-%m-%d')}
Nominated by: Operator (Dave Kitchens)
Collection: ext_creator
Domain: Excel · Power Query · Data Analysis · Dashboards
=====================================================================

{transcript}
"""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"  [{index:03d}] {safe_title[:50]} ({len(transcript):,} chars)")
    return True


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print("LEILA GHARANI YOUTUBE CORPUS FETCH")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 60)

    # Collect all video IDs
    all_video_ids = set(SEED_VIDEO_IDS)

    print("\nCollecting playlist video IDs...")
    for playlist_id in PLAYLIST_IDS:
        print(f"  Scanning playlist: {playlist_id[:20]}...")
        ids = get_video_ids_from_playlist(playlist_id, max_videos=25)
        print(f"    Found {len(ids)} videos")
        all_video_ids.update(ids)

    print(f"\nTotal unique videos: {len(all_video_ids)}")
    print("\nFetching transcripts...")

    saved = 0
    skipped = 0
    failed = 0

    for i, video_id in enumerate(sorted(all_video_ids), 1):
        # Get title
        title = get_video_title(video_id)

        # Get transcript
        transcript = get_transcript(video_id)

        if not transcript:
            print(f"  [{i:03d}] SKIP (no transcript): {video_id}")
            skipped += 1
            continue

        if len(transcript) < 500:
            print(f"  [{i:03d}] SKIP (too short): {title[:40]}")
            skipped += 1
            continue

        save_transcript(video_id, title, transcript, OUTPUT_DIR, saved + 1)
        saved += 1
        time.sleep(1.5)  # Polite delay

    print("\n" + "=" * 60)
    print("COMPLETE")
    print(f"  Saved:   {saved} transcripts")
    print(f"  Skipped: {skipped} (no captions)")
    print(f"  Failed:  {failed}")
    print(f"  Output:  {OUTPUT_DIR}")
    print("=" * 60)
    print("\nNext step — ingest:")
    print('  python dex-ingest.py --path "C:/Users/dkitc/DDL_External/nominations/ext_creator/operator_LeilaGharani" --collection ext_creator --nominated-by "operator" --fast')


if __name__ == "__main__":
    main()
