#!/usr/bin/env python3
"""
dex-transcript.py -- YouTube / podcast transcript corpus builder.

Fetches captions with yt-dlp and writes durable, provenance-stamped text files
into a channel-partitioned corpus tree. Does NOT touch ChromaDB -- ingestion
stays with dex-ingest.py, same split as the rest of the pipeline.

  corpus/transcripts/youtube/<Channel>/<YYYY-MM-DD>_<slug>_<id>.txt
  corpus/transcripts/podcasts/<Show>/<YYYY-MM-DD>_<slug>_<id>.txt

Usage:
  python dex-transcript.py <url>                 # fetch and file one item
  python dex-transcript.py <url> --dry-run       # show target path, fetch nothing
  python dex-transcript.py <url> --force         # re-fetch and overwrite
  python dex-transcript.py --list                # inventory the corpus tree

Then ingest (unchanged tooling):
  python dex-ingest.py --collection ext_transcript --ext-filter .txt \
      --path "<CORPUS_ROOT>"

Why files rather than fetch-straight-to-vector (as dex_fetch_external.py does):
transcripts are expensive to re-acquire and captions can disappear when a video
is edited or pulled. A file corpus survives a ChromaDB rebuild and stays
greppable; the vector store becomes a derived artifact, not the only copy.

Authority: operator decision 2026-07-29 (corpus root + ext_transcript collection)
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

CORPUS_ROOT = Path(r"C:\Users\dkitc\OneDrive\DDL_Archive\corpus\transcripts")
COLLECTION = "ext_transcript"
LOG_PATH = Path(__file__).resolve().parent / "dex-transcript-log.jsonl"

# Windows-reserved characters, plus control chars
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

TS_LINE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s+-->\s+(\d{2}):(\d{2}):(\d{2})\.(\d{3})"
)
INLINE_TAG = re.compile(r"<[^>]*>")


# --------------------------------------------------------------------------
# filesystem-safe naming
# --------------------------------------------------------------------------

def safe_component(name: str, limit: int = 80) -> str:
    """Make one path component safe on Windows without mangling it beyond recognition."""
    name = unicodedata.normalize("NFC", name)
    name = _ILLEGAL.sub("-", name)
    name = re.sub(r"\s+", " ", name).strip()
    # Windows silently strips trailing dots/spaces, which breaks idempotency checks
    name = name.rstrip(". ")
    if name.upper() in _RESERVED:
        name = f"_{name}"
    if len(name) > limit:
        name = name[:limit].rstrip(". ")
    return name or "untitled"


def slugify(title: str, limit: int = 60) -> str:
    s = unicodedata.normalize("NFKD", title)
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > limit:
        s = s[:limit].rstrip("-")
    return s or "untitled"


# --------------------------------------------------------------------------
# yt-dlp
# --------------------------------------------------------------------------

def find_ytdlp() -> list[str]:
    """Locate yt-dlp: project venv first, then PATH, then module."""
    here = Path(__file__).resolve().parent
    for candidate in (
        here / ".venv" / "Scripts" / "yt-dlp.exe",
        here / ".venv" / "Scripts" / "yt-dlp",
        here / ".venv" / "bin" / "yt-dlp",
    ):
        if candidate.exists():
            return [str(candidate)]
    found = shutil.which("yt-dlp")
    if found:
        return [found]
    try:
        import yt_dlp  # noqa: F401
        return [sys.executable, "-m", "yt_dlp"]
    except ImportError:
        sys.exit(
            "error: yt-dlp not found. Install it in the project venv:\n"
            "  .venv/Scripts/pip install -U yt-dlp"
        )


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


FIELDS = ["id", "title", "channel", "uploader", "upload_date", "duration_string", "webpage_url"]


def probe(ytdlp: list[str], url: str) -> dict:
    """
    Fetch metadata and caption availability in one call.

    Caption provenance must come from yt-dlp's `subtitles` (human-authored) vs
    `automatic_captions` (ASR) maps, NOT from downloaded filenames. YouTube
    commonly serves the ASR track under both `en` and `en-orig`, so a file named
    `<id>.en.vtt` is not evidence of a manual track.
    """
    r = run(ytdlp + ["--skip-download", "--no-warnings", "--no-playlist",
                     "--dump-single-json", url])
    if r.returncode != 0:
        sys.exit(f"error: yt-dlp metadata fetch failed:\n{r.stderr.strip()[:600]}")
    try:
        info = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        sys.exit(f"error: could not parse yt-dlp JSON: {e}")

    meta = {f: (info.get(f) or "") for f in FIELDS}
    meta = {k: ("" if v == "NA" else str(v)) for k, v in meta.items()}

    def has_en(m: dict) -> bool:
        return any(k == "en" or k.startswith("en-") or k.startswith("en_")
                   for k in (m or {}))

    meta["_manual_en"] = has_en(info.get("subtitles"))
    meta["_auto_en"] = has_en(info.get("automatic_captions"))
    return meta


def fetch_captions(ytdlp: list[str], url: str, workdir: Path, meta: dict) -> tuple[Path, str]:
    """Download captions. Returns (vtt_path, 'manual'|'auto')."""
    vid = meta["id"]
    caption_type = "manual" if meta.get("_manual_en") else (
        "auto" if meta.get("_auto_en") else "")
    if not caption_type:
        sys.exit("error: no English captions (manual or automatic) available for this item")

    cmd = ytdlp + [
        "--skip-download", "--no-warnings", "--no-playlist",
        "--sub-langs", "en.*", "--sub-format", "vtt",
        "-o", str(workdir / "%(id)s.%(ext)s"),
        "--write-subs" if caption_type == "manual" else "--write-auto-subs",
        url,
    ]
    r = run(cmd)
    found = sorted(workdir.glob(f"{vid}*.vtt"))
    if not found:
        sys.exit(
            f"error: yt-dlp reported {caption_type} English captions but wrote no VTT.\n"
            + (r.stderr.strip()[:400] if r.stderr else "")
        )
    # Prefer the plain `en` variant when several land; they are often duplicates.
    for pref in (f"{vid}.en.vtt", f"{vid}.en-orig.vtt"):
        for p in found:
            if p.name == pref:
                return p, caption_type
    return found[0], caption_type


# --------------------------------------------------------------------------
# VTT -> timestamped text
# --------------------------------------------------------------------------

def _secs(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def _stamp(t: float) -> str:
    t = int(t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def vtt_to_lines(path: Path) -> list[str]:
    """
    YouTube auto-captions use a rolling window: each substantive cue repeats the
    previous line and appends a newly revealed line carrying inline word timings.
    Sub-50ms 'bridge' cues restate text with no new content. Keep the new line.
    """
    cues, cur = [], None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = TS_LINE.match(raw)
        if m:
            if cur:
                cues.append(cur)
            g = m.groups()
            cur = {"start": _secs(*g[:4]), "end": _secs(*g[4:]), "lines": []}
        elif cur is not None and raw.strip():
            cur["lines"].append(raw)
    if cur:
        cues.append(cur)

    import html as _html
    out, prev = [], None
    for c in cues:
        if c["end"] - c["start"] < 0.05:
            continue
        lines = [_html.unescape(INLINE_TAG.sub("", l)).strip() for l in c["lines"]]
        lines = [l for l in lines if l]
        if not lines:
            continue
        new = lines[-1]
        if new == prev:
            continue
        prev = new
        out.append(f"{_stamp(c['start'])}-{_stamp(c['end'])}: {new}")
    return out


# --------------------------------------------------------------------------
# corpus write
# --------------------------------------------------------------------------

def front_matter(meta: dict, kind: str, caption_type: str, nlines: int, nwords: int) -> str:
    up = meta.get("upload_date", "")
    iso = f"{up[:4]}-{up[4:6]}-{up[6:8]}" if len(up) == 8 else ""
    fields = [
        ("source", kind),
        ("url", meta.get("webpage_url", "")),
        ("item_id", meta.get("id", "")),
        ("title", meta.get("title", "")),
        ("channel", meta.get("channel") or meta.get("uploader", "")),
        ("upload_date", iso),
        ("duration", meta.get("duration_string", "")),
        ("captions", caption_type),
        ("language", "en"),
        ("cues", str(nlines)),
        ("words", str(nwords)),
        ("fetched", datetime.now(timezone.utc).isoformat(timespec="seconds")),
        ("collection", COLLECTION),
    ]
    body = "\n".join(f"{k}: {v}" for k, v in fields if v != "")
    return f"---\n{body}\n---\n"


def target_path(meta: dict, kind: str) -> Path:
    up = meta.get("upload_date", "")
    date = f"{up[:4]}-{up[4:6]}-{up[6:8]}" if len(up) == 8 else "0000-00-00"
    channel = safe_component(meta.get("channel") or meta.get("uploader") or "Unknown Channel")
    fname = f"{date}_{slugify(meta.get('title', ''))}_{meta.get('id', '')}.txt"
    return CORPUS_ROOT / kind / channel / safe_component(fname, limit=150)


def log(entry: dict) -> None:
    entry["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_list() -> None:
    if not CORPUS_ROOT.exists():
        print(f"corpus root does not exist yet: {CORPUS_ROOT}")
        return
    files = sorted(CORPUS_ROOT.rglob("*.txt"))
    if not files:
        print(f"corpus is empty: {CORPUS_ROOT}")
        return
    by_channel: dict[str, list[Path]] = {}
    for f in files:
        by_channel.setdefault(f"{f.parent.parent.name}/{f.parent.name}", []).append(f)
    total = 0
    missing = []
    for group in sorted(by_channel):
        items = by_channel[group]
        size = sum(p.stat().st_size for p in items)
        total += size
        print(f"{group}  ({len(items)} items, {size / 1024:.0f} KB)")
        for p in sorted(items):
            # Convention: a transcript's summary sits beside it as
            # <same basename>.summary.md. Surfaced here so the gap is visible
            # rather than silently accumulating.
            has = p.with_suffix(".summary.md").exists()
            print(f"    [{'S' if has else ' '}] {p.name}")
            if not has:
                missing.append(p)
    print(f"\n{len(files)} transcripts, {total / 1024:.0f} KB total")
    print(f"[S] = has a .summary.md alongside")
    if missing:
        print(f"\n{len(missing)} without a summary:")
        for p in missing:
            print(f"    {p.parent.name}/{p.name}")
    print(f"\nroot: {CORPUS_ROOT}")


def cmd_fetch(url: str, kind: str, force: bool, dry_run: bool) -> None:
    ytdlp = find_ytdlp()
    meta = probe(ytdlp, url)
    dest = target_path(meta, kind)

    print(f"title   : {meta.get('title', '')}")
    print(f"channel : {meta.get('channel') or meta.get('uploader', '')}")
    print(f"duration: {meta.get('duration_string', '')}")
    print(f"target  : {dest}")

    if dest.exists() and not force:
        print("\nalready in corpus — skipping (use --force to overwrite)")
        return
    if dry_run:
        print("\n[dry-run] nothing fetched or written")
        return

    workdir = dest.parent / ".work"
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        vtt, caption_type = fetch_captions(ytdlp, url, workdir, meta)
        lines = vtt_to_lines(vtt)
        if not lines:
            sys.exit("error: captions parsed to zero cues — refusing to write an empty transcript")
        nwords = sum(len(l.split(": ", 1)[1].split()) for l in lines if ": " in l)
        text = front_matter(meta, kind, caption_type, len(lines), nwords) + "\n".join(lines) + "\n"

        existed = dest.exists()
        dest.write_text(text, encoding="utf-8")
        print(f"\n{'overwrote' if existed else 'wrote'}: {dest}")
        print(f"captions: {caption_type} | {len(lines)} cues | {nwords} words")
        log({
            "event": "overwrite" if existed else "write",
            "url": meta.get("webpage_url", url), "item_id": meta.get("id", ""),
            "title": meta.get("title", ""), "channel": meta.get("channel") or meta.get("uploader", ""),
            "path": str(dest), "captions": caption_type, "cues": len(lines), "words": nwords,
        })
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print(f"\nto ingest:\n  python dex-ingest.py --collection {COLLECTION} "
          f'--ext-filter .txt --path "{CORPUS_ROOT}"')


def main() -> None:
    p = argparse.ArgumentParser(
        description="Fetch YouTube/podcast transcripts into the file corpus.")
    p.add_argument("url", nargs="?", help="video or episode URL")
    p.add_argument("--source", choices=["youtube", "podcasts"], default="youtube",
                   help="corpus partition (default: youtube)")
    p.add_argument("--force", action="store_true", help="re-fetch and overwrite")
    p.add_argument("--dry-run", action="store_true", help="show target path only")
    p.add_argument("--list", action="store_true", help="inventory the corpus")
    a = p.parse_args()

    if a.list:
        cmd_list()
        return
    if not a.url:
        p.error("a URL is required (or use --list)")
    cmd_fetch(a.url, a.source, a.force, a.dry_run)


if __name__ == "__main__":
    main()
