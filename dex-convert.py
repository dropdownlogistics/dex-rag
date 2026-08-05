"""
dex-convert.py v1.2
Converts external data formats to ingest-ready .txt files.
v1.1: Step 62 — fix 5 bare except blocks (CLAUDE.md Critical Bug #1)
v1.2: ingest integrity layer — every input file is reconciled against its
      outputs through dex_ingest_ledger.py. v1.1 stopped the silent drops
      from being silent; v1.2 makes the run *countable*: N in, M converted,
      K units carried, every discrepancy named and attributed, non-zero
      exit on loss. See --ledger / --allow-loss.

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
  python dex-convert.py --dir "D:/Root" --ext csv --ledger runs/ledger.json

Output:
  All converted files go to --out-dir (default: converted/)
  Files are named for easy identification and dedup
  Each file gets a source header for provenance
  A reconciliation ledger is always computed and printed; --ledger writes it

Exit codes (v1.2):
  0  clean — every input unit reached an output
  2  attributed loss — units were lost, all of it named (--allow-loss → 0)
  3  unaccounted loss — the accounting identity broke; do not ingest this run
  4  ledger error

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

import dex_ingest_ledger as LED
from dex_ingest_ledger import EXIT_CLEAN, EXIT_UNACCOUNTED

# ── Reconciliation ledger (module-global so every converter can record) ──────
# Always live, even for direct importers, so no code path can convert without
# being counted. main() replaces it with one that knows the run's arguments.
LEDGER = LED.Ledger(tool="dex-convert.py v1.2", run_args=[])

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
    entry  = LEDGER.begin_file(file_path, "html")

    try:
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
    except (OSError, UnicodeError) as e:
        _log_convert_error("html-read", e, file_path.name)
        entry.drop(LED.R_OPEN_FAILED, entry.units_offered or 1, str(e)[:120])
        LEDGER.end_file(entry)
        return []

    text = clean_text(text)
    full_content = header + text

    # A document that survives the parse but yields no text is a real loss —
    # previously it wrote an output file containing only the header.
    if not text.strip():
        entry.drop(LED.R_RECORD_NO_CONTENT, entry.units_offered or 1,
                   "parsed but produced zero characters of text")
        LEDGER.end_file(entry)
        print(f"  [DROP] {file_path.name}: no text after HTML strip")
        return []

    if chunk_size > 0 and len(full_content) > chunk_size:
        paths = chunk_file(full_content, file_path.stem, out_dir, chunk_size, "html", entry)
    else:
        out_path = out_dir / f"{file_path.stem}_converted.txt"
        write_output(full_content, out_path, file_path.name)
        paths = [out_path]

    entry.emit(entry.units_offered or 1)
    for p in paths:
        entry.output(p)
    LEDGER.end_file(entry)
    return paths

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
    entry          = LEDGER.begin_file(file_path, "reddit-csv")

    lines = []
    rows_seen = 0
    try:
        with open(file_path, encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                rows_seen += 1
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

                if len(entry_lines) == 1:
                    # Row parsed but carried no field this converter emits.
                    entry.drop(LED.R_RECORD_NO_CONTENT, 1, "row had no emittable field")
                    continue

                entry_lines.append("")
                lines.append("\n".join(entry_lines))
                entry.emit()

    except Exception as e:
        # v1.1 printed a WARN and discarded every row already parsed.
        # v1.2 keeps the parsed prefix and attributes the unreachable tail.
        _log_convert_error("reddit-csv-parse", e, file_path.name)
        offered = entry.units_offered
        lost = max((offered - rows_seen), 0) if offered is not None else None
        entry.drop(LED.R_PARSE_ABORT,
                   lost if lost is not None else 1,
                   f"reader raised after {rows_seen} rows: {type(e).__name__}")
        entry.note(f"parse aborted at row {rows_seen}; prefix retained")

    content = header + "\n".join(lines)
    if not lines:
        entry.note("no rows emitted; no output file written")
        LEDGER.end_file(entry)
        return []

    out_path = out_dir / f"Reddit_{file_path.stem}_converted.txt"
    write_output(content, out_path, file_path.name)
    entry.output(out_path)
    LEDGER.end_file(entry)
    return [out_path]

def convert_csv_generic(file_path: Path, out_dir: Path) -> list[Path]:
    """Convert any CSV to readable text format."""
    converted_date = datetime.now().strftime("%Y-%m-%d")
    header = source_header(str(file_path), "csv", converted_date)
    entry  = LEDGER.begin_file(file_path, "csv")

    lines = []
    rows_seen = 0
    try:
        with open(file_path, encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                rows_seen += 1
                block = f"--- Row {i+1} ---\n"
                fields = 0
                for key, val in row.items():
                    if val and val.strip():
                        block += f"{key}: {val.strip()}\n"
                        fields += 1
                if fields == 0:
                    entry.drop(LED.R_RECORD_NO_CONTENT, 1, "row had no non-empty field")
                    continue
                lines.append(block)
                entry.emit()
    except Exception as e:
        _log_convert_error("csv-parse", e, file_path.name)
        offered = entry.units_offered
        lost = max((offered - rows_seen), 0) if offered is not None else None
        entry.drop(LED.R_PARSE_ABORT,
                   lost if lost is not None else 1,
                   f"reader raised after {rows_seen} rows: {type(e).__name__}")
        entry.note(f"parse aborted at row {rows_seen}; prefix retained")

    content = header + "\n".join(lines)
    if not lines:
        entry.note("no rows emitted; no output file written")
        LEDGER.end_file(entry)
        return []

    out_path = out_dir / f"{file_path.stem}_converted.txt"
    write_output(content, out_path, file_path.name)
    entry.output(out_path)
    LEDGER.end_file(entry)
    return [out_path]

# ── JSON converter ────────────────────────────────────────────────────────────

def convert_json(file_path: Path, out_dir: Path, chunk_size: int = 0) -> list[Path]:
    """Convert JSON to readable text. Handles Chrome history and generic JSON."""
    converted_date = datetime.now().strftime("%Y-%m-%d")
    header = source_header(str(file_path), "json", converted_date)
    entry  = LEDGER.begin_file(file_path, "json")

    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except Exception as e:
        # Whole-document loss. The probe could not measure an unparseable
        # document either, so the count is unknown — but the loss is not.
        _log_convert_error("json-parse", e, file_path.name)
        entry.drop(LED.R_PARSE_ABORT,
                   entry.units_offered if entry.units_offered is not None else 1,
                   f"document unparseable: {type(e).__name__}")
        entry.note("units_offered unmeasurable: probe cannot parse it either")
        LEDGER.end_file(entry)
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
            if not (title or url):
                entry.drop(LED.R_RECORD_NO_CONTENT, 1, "history entry had no title or url")
                continue
            lines.append(f"{ts_str}  {title}\n  {url}\n")
            entry.emit()

    # Generic JSON — pretty print
    else:
        lines.append(json.dumps(data, indent=2, ensure_ascii=False))
        entry.emit(entry.units_offered or 1)

    content = header + "\n".join(lines)

    if chunk_size > 0 and len(content) > chunk_size:
        paths = chunk_file(content, file_path.stem, out_dir, chunk_size, "json", entry)
    else:
        out_path = out_dir / f"{file_path.stem}_converted.txt"
        write_output(content, out_path, file_path.name)
        paths = [out_path]

    for p in paths:
        entry.output(p)
    LEDGER.end_file(entry)
    return paths

# ── VCF converter (Google Contacts) ──────────────────────────────────────────

def convert_vcf(file_path: Path, out_dir: Path) -> list[Path]:
    """Convert VCF contacts to readable text."""
    converted_date = datetime.now().strftime("%Y-%m-%d")
    header = source_header(str(file_path), "vcf-contacts", converted_date)
    entry  = LEDGER.begin_file(file_path, "vcf")

    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except Exception as e:
        _log_convert_error("vcf-read", e, file_path.name)
        entry.drop(LED.R_OPEN_FAILED,
                   entry.units_offered if entry.units_offered is not None else 1,
                   str(e)[:120])
        LEDGER.end_file(entry)
        return []

    contacts = []
    current = []
    started = 0
    open_card = False
    for line in raw.splitlines():
        if line.startswith("BEGIN:VCARD"):
            if open_card:
                # A card started while another was still open — the previous
                # one never terminated and its lines are about to be discarded.
                entry.drop(LED.R_RECORD_UNTERMINATED, 1, "BEGIN:VCARD without END:VCARD")
            current = []
            started += 1
            open_card = True
        elif line.startswith("END:VCARD"):
            contacts.append(current)
            current = []
            open_card = False
        else:
            current.append(line)
    if open_card:
        # Truncated source: the final card never closed. v1.1 dropped it
        # without a word.
        entry.drop(LED.R_RECORD_UNTERMINATED, 1, "final card unterminated at EOF")

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
        if len(contact_lines) == 1:
            entry.drop(LED.R_RECORD_NO_CONTENT, 1, "vcard had no recognised field")
            continue
        contact_lines.append("")
        lines.append("\n".join(contact_lines))
        entry.emit()

    content = header + "\n".join(lines)
    if entry.units_emitted == 0:
        entry.note("no contacts emitted; no output file written")
        LEDGER.end_file(entry)
        return []

    out_path = out_dir / f"{file_path.stem}_contacts_converted.txt"
    write_output(content, out_path, file_path.name)
    entry.output(out_path)
    LEDGER.end_file(entry)
    return [out_path]

# ── MBOX converter (Gmail) ────────────────────────────────────────────────────

def convert_mbox(file_path: Path, out_dir: Path, max_emails: int = 0) -> list[Path]:
    """Convert MBOX to individual email text files. Groups into chunks."""
    converted_date = datetime.now().strftime("%Y-%m-%d")
    ensure_dir(out_dir)
    entry = LEDGER.begin_file(file_path, "mbox")

    print(f"\n  Processing MBOX: {file_path.name}")
    print(f"  This may take a while for large files...")

    try:
        mbox = mailbox.mbox(str(file_path))
    except Exception as e:
        _log_convert_error("mbox-open", e, file_path.name)
        entry.drop(LED.R_OPEN_FAILED,
                   entry.units_offered if entry.units_offered is not None else 1,
                   str(e)[:120])
        LEDGER.end_file(entry)
        return []

    output_files = []
    batch        = []
    batch_num    = 1
    batch_size   = 500  # emails per output file
    count        = 0

    seen = 0
    for i, message in enumerate(mbox):
        if max_emails and i >= max_emails:
            offered = entry.units_offered
            remaining = max(offered - i, 0) if offered is not None else None
            entry.drop(LED.R_LIMIT_REACHED,
                       remaining if remaining is not None else 1,
                       f"--max-emails={max_emails}")
            break
        seen += 1

        try:
            date    = str(message.get("Date", ""))
            subject = str(message.get("Subject", "(no subject)"))
            sender  = str(message.get("From", ""))
            to      = str(message.get("To", ""))

            # Get text body
            body = ""
            degraded = False
            if message.is_multipart():
                for part in message.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                            break
                        except Exception as e:
                            _log_convert_error("mbox-multipart-decode", e, f"email-{i+1}")
                            degraded = True
            else:
                try:
                    body = message.get_payload(decode=True).decode("utf-8", errors="replace")
                except Exception as e:
                    _log_convert_error("mbox-singlepart-decode", e, f"email-{i+1}")
                    degraded = True
                    body = str(message.get_payload())

            if degraded:
                # The record still ships, with a damaged body. That is a
                # degradation, not a unit loss — it must not enter the identity.
                entry.drop(LED.R_RECORD_DEGRADED, 1, "body decode failed; headers retained")
            if len(body) > 2000:
                # The 2000-char cap is a content cut, not a record loss.
                entry.drop(LED.R_FIELD_TRUNCATED, 1,
                           f"body cut from {len(body)} to 2000 chars")

            email_entry = (
                f"--- Email {i+1} ---\n"
                f"Date: {date}\n"
                f"From: {sender}\n"
                f"To: {to}\n"
                f"Subject: {subject}\n\n"
                f"{body[:2000]}\n\n"
            )
            batch.append(email_entry)
            entry.emit()
            count += 1

        except Exception as e:
            _log_convert_error("mbox-message", e, f"email-{i+1}")
            entry.drop(LED.R_RECORD_DECODE_FAILED, 1,
                       f"message raised: {type(e).__name__}")
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

    for p in output_files:
        entry.output(p)
    if entry.units_offered is not None and seen < entry.units_offered and not max_emails:
        # The stdlib iterator stopped early relative to the raw `From ` count.
        # Nothing in v1.1 would have noticed this.
        entry.drop(LED.R_PARSE_ABORT, entry.units_offered - seen,
                   f"mailbox iterator yielded {seen} of {entry.units_offered} records")
    LEDGER.end_file(entry)

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
        entry = LEDGER.begin_file(jf, "facebook")
        try:
            with open(jf, encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        except Exception as e:
            _log_convert_error("facebook-json", e, str(jf.name))
            entry.drop(LED.R_PARSE_ABORT,
                       entry.units_offered if entry.units_offered is not None else 1,
                       f"document unparseable: {type(e).__name__}")
            LEDGER.end_file(entry)
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
            try:
                dt = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M") if ts else ""
            except (ValueError, OSError, OverflowError, TypeError) as e:
                _log_convert_error("facebook-timestamp", e, str(jf.name))
                entry.drop(LED.R_RECORD_DEGRADED, 1, "unreadable timestamp")
                dt = str(ts)
            content   = msg.get("content", "")
            if content:
                lines.append(f"[{dt}] {sender}: {content}")
                entry.emit()
            else:
                # Attachments, photos, reactions, unsends: no text to carry.
                # Real, expected, and previously invisible.
                entry.drop(LED.R_RECORD_NO_CONTENT, 1, "message had no text content")

        if entry.units_emitted == 0:
            entry.note("no text messages in thread; no output file written")
            LEDGER.end_file(entry)
            continue

        out_name = safe_filename(f"FB_{'_'.join(participant_names[:2])}_{jf.stem}.txt")
        out_path = out_dir / out_name
        write_output("\n".join(lines), out_path, jf.name)
        entry.output(out_path)
        LEDGER.end_file(entry)
        output_files.append(out_path)

    return output_files

# ── Chunker ───────────────────────────────────────────────────────────────────

def chunk_file(content: str, stem: str, out_dir: Path,
               chunk_size: int, file_type: str, entry=None) -> list[Path]:
    """Split large content into chunk files.

    A chunked document is still one unit, so unit accounting cannot see a
    slice that loses text. `entry` gets a character count instead: what the
    chunker was handed, and what it actually wrote."""
    chunks       = []
    written      = 0
    total_chunks = (len(content) // chunk_size) + 1
    print(f"  Chunking {stem} → {total_chunks} files ({chunk_size/1000:.0f}K chars each)")

    for i in range(total_chunks):
        start     = i * chunk_size
        end       = min(start + chunk_size, len(content))
        chunk     = content[start:end]
        out_path  = out_dir / f"{stem}_chunk_{i+1:03d}of{total_chunks:03d}.txt"
        write_output(chunk, out_path, f"{stem} chunk {i+1}/{total_chunks}")
        chunks.append(out_path)
        written += len(chunk)
        if end >= len(content):
            break

    if entry is not None:
        entry.chars_expected = len(content)
        entry.chars_written  = written

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
    parser.add_argument("--ledger",    help="Write the reconciliation ledger to this JSON path")
    parser.add_argument("--allow-loss", action="store_true",
                        help="Exit 0 on fully attributed loss (never on unaccounted loss)")
    parser.add_argument("--ledger-verbose", action="store_true",
                        help="Include a per-file line for every input in the printed ledger")
    args = parser.parse_args()

    # v1.2: on Windows an un-redirected console is cp1252, and the arrows and
    # em-dashes in this tool's own progress output raise UnicodeEncodeError the
    # moment stdout is captured or redirected to a file — which is exactly what
    # a scheduled run does. v1.1 died mid-directory with a traceback and a
    # partial output set. Nothing about that failure was about the data.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass

    global LEDGER
    LEDGER = LED.Ledger(tool="dex-convert.py v1.2", run_args=sys.argv[1:])

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
            print(f"  [WARN] Unknown type for {fp.name} — no converter claimed it")
            LEDGER.record_skip(fp, ext.lstrip(".") or "unknown",
                               LED.R_UNHANDLED_TYPE,
                               f"no converter for extension '{ext}'")
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
            present    = [f for f in dp.iterdir() if f.is_file()]
            files = present if not ext_filter else [
                f for f in present if f.suffix.lower() == ext_filter
            ]

            if ext_filter and len(files) != len(present):
                LEDGER.note_scope(
                    f"--ext {ext_filter} restricted the run to {len(files)} of "
                    f"{len(present)} files in {dp} "
                    f"({len(present) - len(files)} not examined)"
                )
            LEDGER.note_scope(f"non-recursive: subdirectories of {dp} were not traversed")

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
                    # v1.1: a bare `continue`. A file sitting in the input
                    # directory that no converter claimed left no trace
                    # anywhere — not in the log, not in the counts.
                    LEDGER.record_skip(fp, ext.lstrip(".") or "unknown",
                                       LED.R_UNHANDLED_TYPE,
                                       f"no converter for extension '{ext}'")
                    print(f"  [SKIP] {fp.name} — no converter for '{ext}'")
                    continue
                all_outputs.extend(outputs)

    else:
        parser.print_help()
        return EXIT_CLEAN

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

    # ── Reconciliation ledger ────────────────────────────────────────────────
    LEDGER.finish()
    LEDGER.report(verbose=args.ledger_verbose)
    if args.ledger:
        p = LEDGER.write_json(args.ledger)
        print(f"  Ledger written: {p}\n")

    code = LEDGER.exit_code(allow_loss=args.allow_loss)

    # Copy to canon — gated on the ledger. A run that lost units without
    # accounting for them must not seed the next ingest.
    if args.to_canon and all_outputs:
        if code == EXIT_UNACCOUNTED:
            print("  [BLOCKED] --to-canon refused: ledger verdict UNACCOUNTED_LOSS.\n"
                  "            Fix the accounting before this run feeds an ingest.\n")
        else:
            copy_to_canon(all_outputs)
            print(f"\n  Files copied to canon. Run dex-ingest.py to embed.\n")

    return code

if __name__ == "__main__":
    sys.exit(main())
