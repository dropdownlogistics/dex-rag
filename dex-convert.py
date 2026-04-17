"""
dex-convert.py v1.1
Converts external data formats to ingest-ready .txt files.
v1.1: Step 62 — fix 5 bare except blocks (CLAUDE.md Critical Bug #1)

Handles:
  - HTML → clean text (strip tags, preserve structure)
  - CSV → formatted text (Reddit exports, data exports)
  - JSON → readable text (Chrome history, ChatGPT exports)
  - MBOX → per-message text files (Gmail exports)
  - Large file chunking (splits files over size threshold)
  - VCF → contact text (Google Contacts)

Usage:
  python dex-convert.py --file "path/to/file.html"
  python dex-convert.py --dir "D:/GoogleTakeout" --ext html
  python dex-convert.py --file "Reddit_comments.csv" --type reddit-csv
  python dex-convert.py --dir "D:/DDL_Backup/reddit_xlsx" --type reddit-csv --all-csv
  python dex-convert.py --file "Google_SearchHistory.html" --chunk 500000
  python dex-convert.py --dir "D:/FacebookExport/messages" --type facebook
  python dex-convert.py --mbox "Takeout/Mail/All mail.mbox" --out-dir canon/gmail

Output:
  All converted files go to --out-dir (default: converted/)
  Files are named for easy identification and dedup
  Each file gets a source header for provenance

Dropdown Logistics — Chaos -> Structured -> Automated
"""

import argparse
import csv
import json
import mailbox
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Optional imports
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

# ── Error tracking (Step 62: replace silent drops with counted errors) ───────

_convert_errors: list[str] = []  # accumulated per run, reported in summary


def _log_convert_error(context: str, error: Exception, record_id: str = ""):
    """Log a conversion error instead of silently dropping the record."""
    msg = f"[{context}] {type(error).__name__}: {error}"
    if record_id:
        msg = f"[{context}] record={record_id}: {type(error).__name__}: {error}"
    _convert_errors.append(msg)
    print(f"  [ERROR] {msg}", file=sys.stderr)


# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_OUT_DIR    = "converted"
DEFAULT_CHUNK_SIZE = 800_000   # chars — safe for ingest (~200K tokens)
MAX_SAFE_SIZE      = 50_000_000  # 50MB — warn above this
CANON_FOLDER       = r"C:\Users\dexjr\99_DexUniverseArchive\00_Archive\DDL-Standards-Canon"

# Reddit CSV column mappings
REDDIT_CSV_SCHEMAS = {
    "comments":         ["id", "permalink", "date", "ip", "subreddit", "gildings", "link", "parent", "body", "media"],
    "posts":            ["id", "permalink", "date", "ip", "subreddit", "gildings", "title", "url", "body", "media"],
    "messages":         ["id", "permalink", "date", "ip", "to", "from", "subject", "body", "media"],
    "chat_history":     ["date", "channel", "body", "media"],
    "saved_posts":      ["id", "permalink", "date", "subreddit", "title", "url"],
    "saved_comments":   ["id", "permalink", "date", "subreddit", "body"],
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def source_header(source_path: str, file_type: str, converted_date: str) -> str:
    return (
        f"SOURCE: {source_path}\n"
        f"TYPE: {file_type}\n"
        f"CONVERTED: {converted_date}\n"
        f"CONVERTED_BY: dex-convert.py v1.0\n"
        f"{'='*60}\n\n"
    )

def clean_text(text: str) -> str:
    """Collapse whitespace, remove null bytes."""
    text = text.replace("\x00", "")
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    text = re.sub(r' {3,}', '  ', text)
    return text.strip()

def safe_filename(name: str) -> str:
    """Convert to safe filename."""
    return re.sub(r'[^\w\-_.]', '_', name)[:80]

def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

def write_output(content: str, out_path: Path, label: str):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", errors="replace") as f:
        f.write(content)
    size = out_path.stat().st_size
    print(f"  [OK] {label}")
    print(f"       → {out_path.name}  ({size/1024:.1f} KB)")

# ── HTML converter ────────────────────────────────────────────────────────────

def convert_html(file_path: Path, out_dir: Path, chunk_size: int = 0) -> list[Path]:
    """Strip HTML to clean text. Optionally chunk large files."""
    converted_date = datetime.now().strftime("%Y-%m-%d")
    header = source_header(str(file_path), "html", converted_date)

    if BS4_AVAILABLE:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            soup = BeautifulSoup(f, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "head"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
    else:
        # Fallback: regex strip
        with open(file_path, encoding="utf-8", errors="replace") as f:
            raw = f.read()
        text = re.sub(r'<[^>]+>', ' ', raw)
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)

    text = clean_text(text)
    full_content = header + text

    if chunk_size > 0 and len(full_content) > chunk_size:
        return chunk_file(full_content, file_path.stem, out_dir, chunk_size, "html")

    out_path = out_dir / f"{file_path.stem}_converted.txt"
    write_output(full_content, out_path, file_path.name)
    return [out_path]

# ── CSV converter (generic + Reddit-specific) ─────────────────────────────────

def detect_reddit_type(filename: str) -> str:
    """Detect Reddit CSV type from filename."""
    name = filename.lower()
    for key in REDDIT_CSV_SCHEMAS:
        if key.replace("_", "") in name.replace("_", "").replace("-", ""):
            return key
    return "generic"

def convert_reddit_csv(file_path: Path, out_dir: Path) -> list[Path]:
    """Convert Reddit CSV export to readable text."""
    converted_date = datetime.now().strftime("%Y-%m-%d")
    reddit_type    = detect_reddit_type(file_path.stem)
    header         = source_header(str(file_path), f"reddit-csv-{reddit_type}", converted_date)

    lines = []
    try:
        with open(file_path, encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                entry_lines = [f"--- Entry {i+1} ---"]

                # Date
                date = row.get("date", row.get("Date", ""))
                if date:
                    entry_lines.append(f"Date: {date}")

                # Subreddit
                sub = row.get("subreddit", row.get("Subreddit", ""))
                if sub:
                    entry_lines.append(f"Subreddit: r/{sub}")

                # Title (posts)
                title = row.get("title", row.get("Title", ""))
                if title:
                    entry_lines.append(f"Title: {title}")

                # Permalink
                permalink = row.get("permalink", row.get("Permalink", ""))
                if permalink:
                    entry_lines.append(f"Link: {permalink}")

                # Body content
                body = row.get("body", row.get("Body", row.get("text", "")))
                if body and body.strip():
                    entry_lines.append(f"\n{body.strip()}")

                # URL (for saved posts)
                url = row.get("url", row.get("URL", ""))
                if url and url != permalink:
                    entry_lines.append(f"URL: {url}")

                # Channel (chat)
                channel = row.get("channel", "")
                if channel:
                    entry_lines.append(f"Channel: {channel}")

                entry_lines.append("")
                lines.append("\n".join(entry_lines))

    except Exception as e:
        print(f"  [WARN] CSV parse error: {e}")
        return []

    content = header + "\n".join(lines)
    out_path = out_dir / f"Reddit_{file_path.stem}_converted.txt"
    write_output(content, out_path, file_path.name)
    return [out_path]

def convert_csv_generic(file_path: Path, out_dir: Path) -> list[Path]:
    """Convert any CSV to readable text format."""
    converted_date = datetime.now().strftime("%Y-%m-%d")
    header = source_header(str(file_path), "csv", converted_date)

    lines = []
    try:
        with open(file_path, encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                entry = f"--- Row {i+1} ---\n"
                for key, val in row.items():
                    if val and val.strip():
                        entry += f"{key}: {val.strip()}\n"
                lines.append(entry)
    except Exception as e:
        print(f"  [WARN] CSV parse error: {e}")
        return []

    content = header + "\n".join(lines)
    out_path = out_dir / f"{file_path.stem}_converted.txt"
    write_output(content, out_path, file_path.name)
    return [out_path]

# ── JSON converter ────────────────────────────────────────────────────────────

def convert_json(file_path: Path, out_dir: Path, chunk_size: int = 0) -> list[Path]:
    """Convert JSON to readable text. Handles Chrome history and generic JSON."""
    converted_date = datetime.now().strftime("%Y-%m-%d")
    header = source_header(str(file_path), "json", converted_date)

    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  [WARN] JSON parse error: {e}")
        return []

    lines = []

    # Chrome history detection
    if isinstance(data, dict) and "Browser History" in data:
        items = data["Browser History"]
        lines.append(f"GOOGLE CHROME HISTORY — {len(items)} entries\n")
        for item in items:
            title = item.get("title", "")
            url   = item.get("url", "")
            ts    = item.get("time_usec", "")
            if ts:
                try:
                    dt = datetime.fromtimestamp(int(ts) / 1_000_000)
                    ts_str = dt.strftime("%Y-%m-%d %H:%M")
                except (ValueError, OSError, OverflowError) as e:
                    _log_convert_error("json-timestamp", e, f"entry-{title[:30]}")
                    ts_str = str(ts)
            else:
                ts_str = ""
            lines.append(f"{ts_str}  {title}\n  {url}\n")

    # Generic JSON — pretty print
    else:
        lines.append(json.dumps(data, indent=2, ensure_ascii=False))

    content = header + "\n".join(lines)

    if chunk_size > 0 and len(content) > chunk_size:
        return chunk_file(content, file_path.stem, out_dir, chunk_size, "json")

    out_path = out_dir / f"{file_path.stem}_converted.txt"
    write_output(content, out_path, file_path.name)
    return [out_path]

# ── VCF converter (Google Contacts) ──────────────────────────────────────────

def convert_vcf(file_path: Path, out_dir: Path) -> list[Path]:
    """Convert VCF contacts to readable text."""
    converted_date = datetime.now().strftime("%Y-%m-%d")
    header = source_header(str(file_path), "vcf-contacts", converted_date)

    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except Exception as e:
        print(f"  [WARN] VCF read error: {e}")
        return []

    contacts = []
    current = []
    for line in raw.splitlines():
        if line.startswith("BEGIN:VCARD"):
            current = []
        elif line.startswith("END:VCARD"):
            contacts.append(current)
            current = []
        else:
            current.append(line)

    lines = [f"GOOGLE CONTACTS — {len(contacts)} contacts\n"]
    for i, contact in enumerate(contacts):
        contact_lines = [f"--- Contact {i+1} ---"]
        for field in contact:
            if ":" in field:
                key, _, val = field.partition(":")
                key_clean = key.split(";")[0]
                if val.strip() and key_clean in (
                    "FN", "N", "EMAIL", "TEL", "ORG", "NOTE", "NICKNAME", "URL"
                ):
                    contact_lines.append(f"{key_clean}: {val.strip()}")
        contact_lines.append("")
        lines.append("\n".join(contact_lines))

    content = header + "\n".join(lines)
    out_path = out_dir / f"{file_path.stem}_contacts_converted.txt"
    write_output(content, out_path, file_path.name)
    return [out_path]

# ── MBOX converter (Gmail) ────────────────────────────────────────────────────

def convert_mbox(file_path: Path, out_dir: Path, max_emails: int = 0) -> list[Path]:
    """Convert MBOX to individual email text files. Groups into chunks."""
    converted_date = datetime.now().strftime("%Y-%m-%d")
    ensure_dir(out_dir)

    print(f"\n  Processing MBOX: {file_path.name}")
    print(f"  This may take a while for large files...")

    try:
        mbox = mailbox.mbox(str(file_path))
    except Exception as e:
        print(f"  [FAIL] Could not open MBOX: {e}")
        return []

    output_files = []
    batch        = []
    batch_num    = 1
    batch_size   = 500  # emails per output file
    count        = 0

    for i, message in enumerate(mbox):
        if max_emails and i >= max_emails:
            break

        try:
            date    = str(message.get("Date", ""))
            subject = str(message.get("Subject", "(no subject)"))
            sender  = str(message.get("From", ""))
            to      = str(message.get("To", ""))

            # Get text body
            body = ""
            if message.is_multipart():
                for part in message.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                            break
                        except Exception as e:
                            _log_convert_error("mbox-multipart-decode", e, f"email-{i+1}")
            else:
                try:
                    body = message.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception as e:
                    _log_convert_error("mbox-singlepart-decode", e, f"email-{i+1}")
                    body = str(message.get_payload())

            entry = (
                f"--- Email {i+1} ---\n"
                f"Date: {date}\n"
                f"From: {sender}\n"
                f"To: {to}\n"
                f"Subject: {subject}\n\n"
                f"{body[:2000]}\n\n"
            )
            batch.append(entry)
            count += 1

        except Exception as e:
            _log_convert_error("mbox-message", e, f"email-{i+1}")
            continue

        # Write batch
        if len(batch) >= batch_size:
            header = source_header(
                str(file_path), f"gmail-mbox-batch-{batch_num}", converted_date
            )
            out_path = out_dir / f"Gmail_batch_{batch_num:04d}.txt"
            write_output(header + "\n".join(batch), out_path, f"Gmail batch {batch_num}")
            output_files.append(out_path)
            batch     = []
            batch_num += 1

    # Final batch
    if batch:
        header   = source_header(str(file_path), f"gmail-mbox-batch-{batch_num}", converted_date)
        out_path = out_dir / f"Gmail_batch_{batch_num:04d}.txt"
        write_output(header + "\n".join(batch), out_path, f"Gmail batch {batch_num} (final)")
        output_files.append(out_path)

    print(f"\n  MBOX complete: {count} emails → {len(output_files)} files")
    return output_files

# ── Facebook converter ────────────────────────────────────────────────────────

def convert_facebook_messages(fb_dir: Path, out_dir: Path) -> list[Path]:
    """Convert Facebook message JSON exports to text."""
    converted_date = datetime.now().strftime("%Y-%m-%d")
    output_files   = []

    msg_dir = fb_dir / "messages"
    if not msg_dir.exists():
        msg_dir = fb_dir  # try the dir itself

    json_files = list(msg_dir.rglob("message_*.json"))
    if not json_files:
        json_files = list(msg_dir.rglob("*.json"))

    print(f"  Found {len(json_files)} Facebook message JSON files")

    for jf in json_files:
        try:
            with open(jf, encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        except Exception as e:
            _log_convert_error("facebook-json", e, str(jf.name))
            continue

        participants = data.get("participants", [])
        participant_names = [p.get("name", "?") for p in participants]
        messages = data.get("messages", [])

        lines = [
            source_header(str(jf), "facebook-messages", converted_date),
            f"CONVERSATION: {', '.join(participant_names)}",
            f"MESSAGES: {len(messages)}\n",
        ]

        for msg in reversed(messages):  # chronological
            sender    = msg.get("sender_name", "?")
            ts        = msg.get("timestamp_ms", 0)
            dt        = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M") if ts else ""
            content   = msg.get("content", "")
            if content:
                lines.append(f"[{dt}] {sender}: {content}")

        out_name = safe_filename(f"FB_{'_'.join(participant_names[:2])}_{jf.stem}.txt")
        out_path = out_dir / out_name
        write_output("\n".join(lines), out_path, jf.name)
        output_files.append(out_path)

    return output_files

# ── Chunker ───────────────────────────────────────────────────────────────────

def chunk_file(content: str, stem: str, out_dir: Path,
               chunk_size: int, file_type: str) -> list[Path]:
    """Split large content into chunk files."""
    chunks       = []
    total_chunks = (len(content) // chunk_size) + 1
    print(f"  Chunking {stem} → {total_chunks} files ({chunk_size/1000:.0f}K chars each)")

    for i in range(total_chunks):
        start     = i * chunk_size
        end       = min(start + chunk_size, len(content))
        chunk     = content[start:end]
        out_path  = out_dir / f"{stem}_chunk_{i+1:03d}of{total_chunks:03d}.txt"
        write_output(chunk, out_path, f"{stem} chunk {i+1}/{total_chunks}")
        chunks.append(out_path)
        if end >= len(content):
            break

    return chunks

# ── Copy to canon ─────────────────────────────────────────────────────────────

def copy_to_canon(files: list[Path], canon_dir: str = CANON_FOLDER):
    """Copy converted files to canon folder for next sweep/ingest."""
    canon_path = Path(canon_dir)
    if not canon_path.exists():
        print(f"  [WARN] Canon folder not found: {canon_dir}")
        return

    print(f"\n  Copying {len(files)} files to canon...")
    for f in files:
        dest = canon_path / f.name
        try:
            import shutil
            shutil.copy2(f, dest)
            print(f"  [OK] {f.name}")
        except Exception as e:
            print(f"  [WARN] Copy failed for {f.name}: {e}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="dex-convert.py — Format converter for Dex Jr. corpus")
    parser.add_argument("--file",      help="Single file to convert")
    parser.add_argument("--dir",       help="Directory to convert")
    parser.add_argument("--ext",       help="File extension filter for --dir (e.g. html, csv)")
    parser.add_argument("--type",      help="Force conversion type: html, csv, reddit-csv, json, vcf, facebook, mbox")
    parser.add_argument("--all-csv",   action="store_true", help="Convert all CSVs in dir as Reddit exports")
    parser.add_argument("--mbox",      help="MBOX file path (Gmail)")
    parser.add_argument("--chunk",     type=int, default=0,
                        help=f"Chunk size in chars (0=no chunking, default threshold={DEFAULT_CHUNK_SIZE:,})")
    parser.add_argument("--out-dir",   default=DEFAULT_OUT_DIR, help="Output directory")
    parser.add_argument("--to-canon",  action="store_true", help="Copy results to canon folder after conversion")
    parser.add_argument("--max-emails",type=int, default=0, help="Max emails to process from MBOX (0=all)")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    ensure_dir(out_dir)

    all_outputs = []

    print(f"\n{'='*60}")
    print(f"  DEX-CONVERT v1.0")
    print(f"  Output: {out_dir}")
    print(f"{'='*60}\n")

    # MBOX
    if args.mbox:
        mbox_path = Path(args.mbox)
        if not mbox_path.exists():
            print(f"  [FAIL] MBOX not found: {args.mbox}")
            sys.exit(1)
        outputs = convert_mbox(mbox_path, out_dir / "gmail", args.max_emails)
        all_outputs.extend(outputs)

    # Single file
    elif args.file:
        fp = Path(args.file)
        if not fp.exists():
            print(f"  [FAIL] File not found: {args.file}")
            sys.exit(1)

        ext        = fp.suffix.lower()
        force_type = args.type or ""
        chunk_size = args.chunk or (DEFAULT_CHUNK_SIZE if fp.stat().st_size > DEFAULT_CHUNK_SIZE else 0)

        if force_type == "reddit-csv" or (ext == ".csv" and not force_type):
            outputs = convert_reddit_csv(fp, out_dir)
        elif force_type == "html" or ext == ".html":
            outputs = convert_html(fp, out_dir, chunk_size)
        elif force_type == "json" or ext == ".json":
            outputs = convert_json(fp, out_dir, chunk_size)
        elif force_type == "vcf" or ext == ".vcf":
            outputs = convert_vcf(fp, out_dir)
        elif force_type == "facebook":
            outputs = convert_facebook_messages(fp.parent, out_dir)
        else:
            print(f"  [WARN] Unknown type for {fp.name} — trying as text")
            outputs = []
        all_outputs.extend(outputs)

    # Directory
    elif args.dir:
        dp = Path(args.dir)
        if not dp.exists():
            print(f"  [FAIL] Directory not found: {args.dir}")
            sys.exit(1)

        if args.type == "facebook":
            outputs = convert_facebook_messages(dp, out_dir)
            all_outputs.extend(outputs)

        else:
            ext_filter = f".{args.ext.lstrip('.')}" if args.ext else None
            files = list(dp.iterdir()) if not ext_filter else [
                f for f in dp.iterdir() if f.suffix.lower() == ext_filter
            ]
            files = [f for f in files if f.is_file()]

            print(f"  Files found: {len(files)}")

            for fp in sorted(files):
                ext = fp.suffix.lower()
                chunk_size = args.chunk or (DEFAULT_CHUNK_SIZE if fp.stat().st_size > DEFAULT_CHUNK_SIZE else 0)

                if args.all_csv and ext == ".csv":
                    outputs = convert_reddit_csv(fp, out_dir)
                elif ext == ".html":
                    outputs = convert_html(fp, out_dir, chunk_size)
                elif ext == ".csv":
                    outputs = convert_reddit_csv(fp, out_dir) if args.type == "reddit-csv" else convert_csv_generic(fp, out_dir)
                elif ext == ".json":
                    outputs = convert_json(fp, out_dir, chunk_size)
                elif ext == ".vcf":
                    outputs = convert_vcf(fp, out_dir)
                else:
                    continue
                all_outputs.extend(outputs)

    else:
        parser.print_help()
        return

    # Summary
    print(f"\n{'='*60}")
    print(f"  CONVERSION COMPLETE")
    print(f"  Files created: {len(all_outputs)}")
    total_size = sum(f.stat().st_size for f in all_outputs if f.exists())
    print(f"  Total size: {total_size/1024/1024:.1f} MB")
    print(f"  Output dir: {out_dir}")
    if _convert_errors:
        print(f"  ERRORS: {len(_convert_errors)} records had conversion issues")
        for err in _convert_errors[:10]:
            print(f"    {err}")
        if len(_convert_errors) > 10:
            print(f"    ... and {len(_convert_errors) - 10} more")
    else:
        print(f"  Errors: 0")
    print(f"{'='*60}\n")

    # Copy to canon
    if args.to_canon and all_outputs:
        copy_to_canon(all_outputs)
        print(f"\n  Files copied to canon. Run dex-ingest.py to embed.\n")

if __name__ == "__main__":
    main()
