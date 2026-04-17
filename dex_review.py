#!/usr/bin/env python3
"""
dex_review.py — Council review parser + vote registry.

Parses DDLCouncilReview_*.txt files, extracts structured vote data,
maintains a registry in council-reviews/registry.json.

Usage:
  python dex_review.py parse <file>          Parse a single review file
  python dex_review.py scan                  Find and parse all un-registered reviews
  python dex_review.py stats                 Overall voting patterns
  python dex_review.py stats --seat 1001     Voting history for a seat
  python dex_review.py stats --verdict REVISE  Reviews with REVISE votes
  python dex_review.py stats --topic WorkBench Reviews matching a topic

Step 59 | Dropdown Logistics
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_DIR = os.path.join(SCRIPT_DIR, "council-reviews")
REGISTRY_FILE = os.path.join(REGISTRY_DIR, "registry.json")

# Where council review files live
CANON_DIR = r"C:\Users\dexjr\99_DexUniverseArchive\00_Archive\DDL-Standards-Canon"
INGEST_PROCESSED = r"C:\Users\dkitc\OneDrive\DDL_Ingest\_processed"
INGEST_DIR = r"C:\Users\dkitc\OneDrive\DDL_Ingest"

SCAN_DIRS = [CANON_DIR, INGEST_PROCESSED, INGEST_DIR]

# Seat identifiers — multiple patterns per seat for flexible matching
SEAT_PATTERNS = {
    "1001": ["1001", "LeChat", "Archer", "Hawthorne"],
    "1002": ["1002", "Claude", "Marcus Caldwell", "Caldwell"],
    "1003": ["1003", "Grok", "Elias", "Mercer"],
    "1004": ["1004", "Perplexity", "Max Sullivan", "MaxSullivan", "Sullivan"],
    "1005": ["1005", "Copilot", "Rowan", "Bennett"],
    "1006": ["1006", "Meta AI", "Meta", "Ava", "Sinclair"],
    "1007": ["1007", "Gemini", "Leo", "Prescott"],
    "1008": ["1008", "ChatGPT", "Marcus Grey", "Grey"],
    "1009": ["1009", "DeepSeek", "Kai", "Langford"],
    "1010": ["1010", "DexJr", "Dex Jr", "Dexcell", "Dex Hale"],
    "1011": ["1011", "Connor"],
}

SEAT_NAMES = {
    "1001": "Archer Hawthorne",
    "1002": "Marcus Caldwell",
    "1003": "Elias Mercer",
    "1004": "Max Sullivan",
    "1005": "Rowan Bennett",
    "1006": "Ava Sinclair",
    "1007": "Leo Prescott",
    "1008": "Marcus Grey",
    "1009": "Kai Langford",
    "1010": "Dex Jr.",
    "1011": "Connor",
}

VERDICTS = {"LOCK", "REVISE", "REJECT"}


# ── Registry I/O ─────────────────────────────────────────────────────────────

def load_registry() -> dict:
    if os.path.exists(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"reviews": []}


def save_registry(registry: dict) -> None:
    os.makedirs(REGISTRY_DIR, exist_ok=True)
    tmp = REGISTRY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
    os.replace(tmp, REGISTRY_FILE)


# ── CR ID extraction ─────────────────────────────────────────────────────────

CR_PATTERN = re.compile(r"\bCR-[A-Z0-9]+-[A-Z0-9-]+-\d{3}\b")
CR_SIMPLE = re.compile(r"\bCR-[A-Z]+-\d{3}\b")


def extract_cr_id(text: str) -> Optional[str]:
    """Extract CR ID from text. Checks first 30 lines."""
    header = "\n".join(text.split("\n")[:30])
    # Try full pattern first (CR-WB-PAYROLL-001)
    m = CR_PATTERN.search(header)
    if m:
        return m.group(0)
    # Try simpler pattern (CR-CANON-001)
    m = CR_SIMPLE.search(header)
    if m:
        return m.group(0)
    # Try broader: anything after "CR-" or "Document:" in header
    for line in header.split("\n"):
        if "Document:" in line or "CR-" in line:
            m = re.search(r"CR-[A-Z0-9-]+(?:-\d{3})?", line)
            if m:
                return m.group(0)
    return None


def extract_title(text: str, filename: str) -> str:
    """Extract title from header or derive from filename."""
    for line in text.split("\n")[:20]:
        if "Title:" in line:
            return line.split("Title:", 1)[1].strip()
    # Derive from filename: DDLCouncilReview_PayrollModuleVision.txt -> Payroll Module Vision
    base = os.path.splitext(filename)[0]
    base = base.replace("DDLCouncilReview_", "").replace("DDLCouncilReview", "")
    # CamelCase to spaces
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', base).replace("_", " ").strip()


# ── Seat + verdict extraction ───────────────────────────────────────────────

def detect_seat_sections(text: str) -> dict:
    """
    Split text into per-seat sections by detecting seat headers.
    Returns {seat_id: section_text}.
    """
    lines = text.split("\n")
    sections = {}
    current_seat = None
    current_lines = []

    for line in lines:
        detected = None
        # Check for seat section headers like "1001_LeChat — Archer" or "Seat 1002"
        for seat_id, patterns in SEAT_PATTERNS.items():
            for pat in patterns:
                # Header patterns: "1001_LeChat", "Seat 1001", "— Seat 1001"
                if re.search(rf"\b{re.escape(pat)}\b", line, re.IGNORECASE):
                    # Only trigger on lines that look like headers (short, or contain seat markers)
                    is_header = (
                        line.strip().startswith(f"{seat_id}_")
                        or line.strip().startswith(f"Seat {seat_id}")
                        or f"— {pat}" in line
                        or f"({pat})" in line
                        or f"SEAT {seat_id}" in line.upper()
                        or re.match(rf"^\**{seat_id}[_\s]", line.strip())
                    )
                    if is_header:
                        detected = seat_id
                        break
            if detected:
                break

        if detected and detected != current_seat:
            if current_seat and current_lines:
                sections[current_seat] = "\n".join(current_lines)
            current_seat = detected
            current_lines = [line]
        elif current_seat:
            current_lines.append(line)

    if current_seat and current_lines:
        sections[current_seat] = "\n".join(current_lines)

    return sections


def extract_verdict(section_text: str) -> Optional[str]:
    """Extract the dominant verdict from a seat's section."""
    # Look for explicit overall verdict patterns first
    overall_patterns = [
        r"OVERALL\s+VERDICT[:\s]*\**\s*(LOCK|REVISE|REJECT)",
        r"OVERALL[:\s]*\**\s*(LOCK|REVISE|REJECT)",
        r"FINAL\s+POSITION[:\s]*\**\s*(LOCK|REVISE|REJECT)",
        r"VERDICT[:\s]*\**\s*(LOCK|REVISE|REJECT)",
    ]
    for pat in overall_patterns:
        m = re.search(pat, section_text, re.IGNORECASE)
        if m:
            return m.group(1).upper()

    # Count verdict mentions — majority wins
    counts = {v: 0 for v in VERDICTS}
    for v in VERDICTS:
        counts[v] = len(re.findall(rf"\b{v}\b", section_text))

    total = sum(counts.values())
    if total == 0:
        return None

    # Return the most frequent verdict
    dominant = max(counts, key=counts.get)
    return dominant if counts[dominant] > 0 else None


def extract_summary(section_text: str, max_sentences: int = 3) -> str:
    """Extract first 2-3 meaningful sentences after a verdict keyword."""
    lines = section_text.split("\n")
    capture = False
    sentences = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if capture and sentences:
                break
            continue
        if any(v in stripped.upper() for v in VERDICTS):
            capture = True
            # Include this line if it has content beyond just the verdict
            content = re.sub(r"\*+", "", stripped).strip()
            content = re.sub(r"^(VERDICT|OVERALL|FINAL POSITION)[:\s—-]*", "", content, flags=re.IGNORECASE).strip()
            content = re.sub(r"^(LOCK|REVISE|REJECT)[:\s—-]*", "", content).strip()
            if len(content) > 20:
                sentences.append(content)
                if len(sentences) >= max_sentences:
                    break
        elif capture:
            content = re.sub(r"\*+", "", stripped).strip()
            if len(content) > 10:
                sentences.append(content)
                if len(sentences) >= max_sentences:
                    break

    return " ".join(sentences)[:500] if sentences else ""


# ── Main parser ──────────────────────────────────────────────────────────────

def parse_review(filepath: str) -> Optional[dict]:
    """Parse a single DDLCouncilReview file into structured data."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        print(f"  [WARN] Could not read {filepath}: {e}")
        return None

    filename = os.path.basename(filepath)
    cr_id = extract_cr_id(text)
    title = extract_title(text, filename)

    if not cr_id:
        # Try deriving from filename
        cr_id = f"CR-{filename.replace('DDLCouncilReview_', '').replace('.txt', '').upper()}"

    sections = detect_seat_sections(text)

    votes = {}
    for seat_id, section in sections.items():
        verdict = extract_verdict(section)
        summary = extract_summary(section)
        if verdict:
            votes[seat_id] = {
                "verdict": verdict,
                "summary": summary,
                "seat_name": SEAT_NAMES.get(seat_id, f"Seat {seat_id}"),
            }

    tally = {"LOCK": 0, "REVISE": 0, "REJECT": 0}
    for v in votes.values():
        if v["verdict"] in tally:
            tally[v["verdict"]] += 1

    total_votes = sum(tally.values())
    quorum = total_votes >= 5

    # Determine overall recommendation
    if total_votes == 0:
        recommendation = "NO VOTES PARSED"
        confidence = "low"
    elif tally["LOCK"] == total_votes:
        recommendation = "LOCK - unanimous"
        confidence = "high"
    elif tally["LOCK"] > total_votes / 2:
        recommendation = f"LOCK - majority ({tally['LOCK']}/{total_votes})"
        confidence = "high"
    elif tally["REVISE"] > total_votes / 2:
        recommendation = f"REVISE - majority ({tally['REVISE']}/{total_votes})"
        confidence = "high"
    elif tally["REJECT"] > 0:
        recommendation = f"MIXED ({tally['LOCK']}L/{tally['REVISE']}R/{tally['REJECT']}X)"
        confidence = "medium"
    else:
        recommendation = f"SPLIT ({tally['LOCK']}L/{tally['REVISE']}R)"
        confidence = "medium"

    return {
        "cr_id": cr_id,
        "title": title,
        "source_file": filename,
        "source_path": os.path.abspath(filepath),
        "parsed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "votes": votes,
        "tally": tally,
        "total_votes": total_votes,
        "quorum": quorum,
        "recommendation": recommendation,
        "parse_confidence": confidence,
    }


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_parse(filepath: str) -> int:
    """Parse a single review file."""
    if not os.path.exists(filepath):
        print(f"  ERROR: File not found: {filepath}")
        return 1

    result = parse_review(filepath)
    if not result:
        print(f"  ERROR: Could not parse {filepath}")
        return 1

    registry = load_registry()

    # Check if already registered
    existing = [r for r in registry["reviews"] if r["source_file"] == result["source_file"]]
    if existing:
        # Update in place
        for i, r in enumerate(registry["reviews"]):
            if r["source_file"] == result["source_file"]:
                registry["reviews"][i] = result
                break
        print(f"  Updated: {result['cr_id']} ({result['source_file']})")
    else:
        registry["reviews"].append(result)
        print(f"  Added: {result['cr_id']} ({result['source_file']})")

    print(f"  Votes: {result['total_votes']} | Tally: {result['tally']}")
    print(f"  Recommendation: {result['recommendation']} (confidence: {result['parse_confidence']})")
    for seat, vote in sorted(result["votes"].items()):
        print(f"    {seat} {vote['seat_name']:20s} {vote['verdict']:6s}  {vote['summary'][:60]}")

    save_registry(registry)
    return 0


def cmd_scan() -> int:
    """Scan for un-registered council review files and parse them."""
    registry = load_registry()
    known_files = {r["source_file"] for r in registry["reviews"]}

    found = []
    for scan_dir in SCAN_DIRS:
        if not os.path.isdir(scan_dir):
            continue
        for f in os.listdir(scan_dir):
            if f.startswith("DDLCouncilReview_") and f.endswith(".txt"):
                if f not in known_files:
                    found.append(os.path.join(scan_dir, f))

    if not found:
        print(f"  No new review files found. Registry has {len(registry['reviews'])} reviews.")
        return 0

    print(f"  Found {len(found)} new review files. Parsing...")
    added = 0
    failed = 0

    for filepath in sorted(found):
        filename = os.path.basename(filepath)
        result = parse_review(filepath)
        if result:
            registry["reviews"].append(result)
            added += 1
            v = result["total_votes"]
            rec = result["recommendation"]
            print(f"    {result['cr_id']:40s} {v} votes  {rec}")
        else:
            failed += 1
            print(f"    FAILED: {filename}")

    save_registry(registry)
    print(f"\n  Scan complete: {added} added, {failed} failed, {len(registry['reviews'])} total in registry")
    return 0


def cmd_stats(seat: Optional[str] = None, verdict: Optional[str] = None,
              topic: Optional[str] = None) -> int:
    """Display voting patterns from the registry."""
    registry = load_registry()
    reviews = registry.get("reviews", [])

    if not reviews:
        print("  Registry is empty. Run 'dex review scan' first.")
        return 0

    # Filter by topic if specified
    if topic:
        reviews = [r for r in reviews if topic.lower() in (r.get("title", "") + r.get("cr_id", "")).lower()]
        if not reviews:
            print(f"  No reviews matching topic '{topic}'")
            return 0

    # Filter by verdict if specified
    if verdict:
        verdict = verdict.upper()
        reviews = [r for r in reviews if any(v["verdict"] == verdict for v in r.get("votes", {}).values())]
        if not reviews:
            print(f"  No reviews with {verdict} votes")
            return 0

    # Single seat stats
    if seat:
        print(f"\n  VOTING HISTORY — Seat {seat} ({SEAT_NAMES.get(seat, '?')})")
        print(f"  {'=' * 60}\n")
        seat_reviews = [(r, r["votes"].get(seat)) for r in reviews if seat in r.get("votes", {})]
        if not seat_reviews:
            print(f"  No votes found for seat {seat}")
            return 0
        counts = {"LOCK": 0, "REVISE": 0, "REJECT": 0}
        for r, v in seat_reviews:
            counts[v["verdict"]] += 1
            print(f"  {v['verdict']:6s}  {r['cr_id']:40s}  {r.get('title', '')[:30]}")
        total = sum(counts.values())
        print(f"\n  Total: {total} votes | LOCK: {counts['LOCK']} | REVISE: {counts['REVISE']} | REJECT: {counts['REJECT']}")
        if total > 0:
            print(f"  LOCK rate: {counts['LOCK']/total*100:.0f}%")
        return 0

    # Overall stats
    print(f"\n  COUNCIL VOTING PATTERNS ({len(reviews)} reviews)")
    print(f"  {'=' * 70}\n")

    # Per-seat summary
    seat_totals = {}
    for r in reviews:
        for s, v in r.get("votes", {}).items():
            if s not in seat_totals:
                seat_totals[s] = {"LOCK": 0, "REVISE": 0, "REJECT": 0}
            seat_totals[s][v["verdict"]] += 1

    print(f"  {'Seat':<6} {'Name':<22} {'LOCK':>5} {'REVISE':>7} {'REJECT':>7} {'Rate':>8}")
    print(f"  {'-' * 60}")

    for s in sorted(seat_totals.keys()):
        c = seat_totals[s]
        total = sum(c.values())
        rate = f"{c['LOCK']/total*100:.0f}% LOCK" if total > 0 else "—"
        print(f"  {s:<6} {SEAT_NAMES.get(s, '?'):<22} {c['LOCK']:>5} {c['REVISE']:>7} {c['REJECT']:>7} {rate:>8}")

    # Most contentious / unanimous
    print()
    by_split = sorted(reviews, key=lambda r: abs(r["tally"].get("LOCK", 0) - r["tally"].get("REVISE", 0)))
    if by_split and by_split[0]["total_votes"] > 0:
        c = by_split[0]
        print(f"  Most contentious: {c['cr_id']} ({c['tally']['LOCK']}L/{c['tally']['REVISE']}R/{c['tally']['REJECT']}X)")
    unanimous = [r for r in reviews if r["tally"]["LOCK"] == r["total_votes"] and r["total_votes"] >= 5]
    if unanimous:
        print(f"  Unanimous LOCK:   {len(unanimous)} reviews")
        for u in unanimous[:3]:
            print(f"                    {u['cr_id']}")

    # Recommendation distribution
    rec_counts = {}
    for r in reviews:
        key = r["recommendation"].split(" - ")[0].split(" (")[0]
        rec_counts[key] = rec_counts.get(key, 0) + 1
    print(f"\n  Recommendations: {rec_counts}")

    print(f"\n  {'=' * 70}\n")
    return 0


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description="DDL Council Review Parser + Vote Registry")
    sub = p.add_subparsers(dest="command")

    parse_p = sub.add_parser("parse", help="Parse a single review file")
    parse_p.add_argument("file", help="Path to DDLCouncilReview_*.txt file")

    sub.add_parser("scan", help="Find and parse all un-registered reviews")

    stats_p = sub.add_parser("stats", help="Show voting patterns")
    stats_p.add_argument("--seat", default=None, help="Filter by seat (e.g. 1001)")
    stats_p.add_argument("--verdict", default=None, help="Filter by verdict (LOCK/REVISE/REJECT)")
    stats_p.add_argument("--topic", default=None, help="Filter by topic keyword")

    args = p.parse_args()

    if args.command == "parse":
        return cmd_parse(args.file)
    elif args.command == "scan":
        return cmd_scan()
    elif args.command == "stats":
        return cmd_stats(seat=args.seat, verdict=args.verdict, topic=args.topic)
    else:
        p.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
