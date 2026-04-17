#!/usr/bin/env python3
"""
dex_review.py — Council review management CLI + vote registry.

Two modes:
  MANAGEMENT — create, add votes, track status, synthesize, close
  PARSER     — parse legacy DDLCouncilReview_*.txt files into registry

Usage:
  dex r create CR-WB-M6-001 --title "Module 6"
  dex r add CR-WB-M6-001 1001 LOCK --file response.txt
  dex r status CR-WB-M6-001
  dex r list
  dex r synthesize CR-WB-M6-001
  dex r dex CR-WB-M6-001
  dex r close CR-WB-M6-001
  dex r scan
  dex r stats

Step 59 | Dropdown Logistics
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from typing import Optional

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dex_core import (
    COUNCIL_SEATS, DEFAULT_VOTING_SEATS, REVIEW_DIR, OLLAMA_HOST,
    GEN_MODEL, load_primer, embed as core_embed,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_FILE = os.path.join(REVIEW_DIR, "registry.json")

# Where legacy review files live (for scan command)
CANON_DIR = r"C:\Users\dexjr\99_DexUniverseArchive\00_Archive\DDL-Standards-Canon"
INGEST_PROCESSED = r"C:\Users\dkitc\OneDrive\DDL_Ingest\_processed"
INGEST_DIR = r"C:\Users\dkitc\OneDrive\DDL_Ingest"
SCAN_DIRS = [CANON_DIR, INGEST_PROCESSED, INGEST_DIR]

VERDICTS = {"LOCK", "REVISE", "REJECT"}

# Seat patterns for legacy file parsing
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


def seat_name(seat_id) -> str:
    s = COUNCIL_SEATS.get(int(seat_id), {})
    return s.get("name", f"Seat {seat_id}")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    os.makedirs(REVIEW_DIR, exist_ok=True)
    tmp = REGISTRY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
    os.replace(tmp, REGISTRY_FILE)


# ══════════════════════════════════════════════════════════════════════════════
# MANAGEMENT COMMANDS — create, add, status, list, synthesize, close, dex
# ══════════════════════════════════════════════════════════════════════════════

def _review_dir(cr_id: str) -> str:
    return os.path.join(REVIEW_DIR, cr_id)


def _load_manifest(cr_id: str) -> Optional[dict]:
    path = os.path.join(_review_dir(cr_id), "manifest.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_manifest(cr_id: str, manifest: dict) -> None:
    path = os.path.join(_review_dir(cr_id), "manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def cmd_create(cr_id: str, title: str = "", prompt_file: str = None) -> int:
    """Create a new review directory with manifest."""
    if not cr_id:
        cr_id = f"CR-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    rdir = _review_dir(cr_id)
    if os.path.exists(rdir):
        print(f"  ERROR: Review {cr_id} already exists at {rdir}")
        return 1

    os.makedirs(os.path.join(rdir, "responses"), exist_ok=True)

    # Copy or create prompt
    prompt_path = os.path.join(rdir, "prompt.txt")
    if prompt_file and os.path.exists(prompt_file):
        shutil.copy2(prompt_file, prompt_path)
        print(f"  Prompt copied from: {prompt_file}")
    else:
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(f"# {cr_id}: {title}\n\n[Paste prompt here]\n")
        if prompt_file:
            print(f"  WARN: prompt file not found: {prompt_file}")

    manifest = {
        "cr_id": cr_id,
        "title": title or cr_id,
        "created": now_iso(),
        "status": "OPEN",
        "author_seat": "1002",
        "prompt_file": "prompt.txt",
        "seats_expected": DEFAULT_VOTING_SEATS,
        "votes": {},
        "synthesis_file": None,
        "closed_at": None,
    }
    _save_manifest(cr_id, manifest)

    print(f"\n  Created: {cr_id}")
    print(f"  Title:   {title or cr_id}")
    print(f"  Dir:     {rdir}")
    print(f"  Prompt:  {prompt_path}")
    print(f"  Seats:   {len(DEFAULT_VOTING_SEATS)} expected")
    print(f"  Status:  OPEN\n")
    return 0


def cmd_add(cr_id: str, seat: str, verdict: str, file_path: str = None) -> int:
    """Log a seat's vote and response."""
    manifest = _load_manifest(cr_id)
    if not manifest:
        print(f"  ERROR: Review {cr_id} not found. Run 'dex r create {cr_id}' first.")
        return 1

    verdict = verdict.upper()
    if verdict not in VERDICTS:
        print(f"  ERROR: Verdict must be LOCK, REVISE, or REJECT (got '{verdict}')")
        return 1

    seat_str = str(seat)
    name = seat_name(seat_str)

    # Check for existing vote
    if seat_str in manifest["votes"]:
        old = manifest["votes"][seat_str]["verdict"]
        print(f"  WARN: Seat {seat_str} ({name}) already voted {old}. Overwriting.")

    # Read response content
    rdir = _review_dir(cr_id)
    resp_filename = f"{seat_str}_{verdict}.txt"
    resp_path = os.path.join(rdir, "responses", resp_filename)

    if file_path and os.path.exists(file_path):
        shutil.copy2(file_path, resp_path)
    elif file_path:
        print(f"  ERROR: File not found: {file_path}")
        return 1
    else:
        # Read from stdin
        print(f"  Paste {name}'s response (Ctrl+Z then Enter to finish):")
        try:
            content = sys.stdin.read()
            with open(resp_path, "w", encoding="utf-8") as f:
                f.write(content)
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            return 1

    # Update manifest
    manifest["votes"][seat_str] = {
        "verdict": verdict,
        "timestamp": now_iso(),
        "response_file": f"responses/{resp_filename}",
    }
    _save_manifest(cr_id, manifest)

    total = len(manifest["votes"])
    expected = len(manifest.get("seats_expected", []))
    print(f"  Logged: {seat_str} {name} -> {verdict} ({total}/{expected})")
    return 0


def cmd_status(cr_id: str) -> int:
    """Show current state of a review."""
    manifest = _load_manifest(cr_id)
    if not manifest:
        print(f"  ERROR: Review {cr_id} not found.")
        return 1

    votes = manifest.get("votes", {})
    expected = manifest.get("seats_expected", DEFAULT_VOTING_SEATS)
    voted_seats = set(votes.keys())
    pending = [s for s in expected if str(s) not in voted_seats]

    tally = {"LOCK": 0, "REVISE": 0, "REJECT": 0}
    for v in votes.values():
        tally[v["verdict"]] += 1

    print(f"\n  {manifest['cr_id']}: {manifest.get('title', '')}")
    print(f"  Status:  {manifest['status']}")
    print(f"  Created: {manifest['created'][:16]}")
    if manifest.get("closed_at"):
        print(f"  Closed:  {manifest['closed_at'][:16]}")
    if manifest.get("synthesis_file"):
        print(f"  Synthesis: {manifest['synthesis_file']}")

    print(f"\n  Votes ({len(votes)}/{len(expected)}):")
    for s in sorted(votes.keys(), key=int):
        v = votes[s]
        print(f"    [{v['verdict']:6s}] {s} {seat_name(s):22s} {v['timestamp'][:16]}")

    if pending:
        print(f"\n  Pending ({len(pending)}):")
        for s in pending:
            print(f"    {s} {seat_name(str(s))}")

    print(f"\n  Tally: {tally['LOCK']} LOCK / {tally['REVISE']} REVISE / {tally['REJECT']} REJECT\n")
    return 0


def cmd_list(show_open=True, show_closed=False) -> int:
    """List all managed reviews."""
    if not os.path.isdir(REVIEW_DIR):
        print("  No reviews found.")
        return 0

    reviews = []
    for d in sorted(os.listdir(REVIEW_DIR)):
        manifest_path = os.path.join(REVIEW_DIR, d, "manifest.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    m = json.load(f)
                reviews.append(m)
            except Exception:
                pass

    open_reviews = [r for r in reviews if r.get("status") == "OPEN"]
    closed_reviews = [r for r in reviews if r.get("status") == "CLOSED"]

    if show_open and open_reviews:
        print(f"\n  OPEN REVIEWS:")
        for r in open_reviews:
            votes = r.get("votes", {})
            expected = len(r.get("seats_expected", []))
            tally = {"LOCK": 0, "REVISE": 0, "REJECT": 0}
            for v in votes.values():
                tally[v["verdict"]] += 1
            tstr = f"{tally['LOCK']}L/{tally['REVISE']}R/{tally['REJECT']}X"
            print(f"    {r['cr_id']:30s} {r.get('title','')[:30]:30s} {len(votes)}/{expected} votes  {tstr}")

    if show_closed and closed_reviews:
        print(f"\n  CLOSED REVIEWS:")
        for r in closed_reviews[-10:]:
            votes = r.get("votes", {})
            tally = {"LOCK": 0, "REVISE": 0, "REJECT": 0}
            for v in votes.values():
                tally[v["verdict"]] += 1
            closed = r.get("closed_at", "")[:10]
            tstr = f"{tally['LOCK']}L/{tally['REVISE']}R/{tally['REJECT']}X"
            print(f"    {r['cr_id']:30s} {r.get('title','')[:30]:30s} {tstr:10s} closed {closed}")

    if not open_reviews and show_open and not show_closed:
        print("  No open reviews.")

    total = len(reviews)
    print(f"\n  Total: {len(open_reviews)} open, {len(closed_reviews)} closed, {total} managed")

    # Also show registry count
    reg = load_registry()
    parsed = len(reg.get("reviews", []))
    if parsed:
        print(f"  Legacy registry: {parsed} parsed from DDLCouncilReview_*.txt files")
    print()
    return 0


def cmd_synthesize(cr_id: str, force: bool = False) -> int:
    """Synthesize all collected responses via local model."""
    manifest = _load_manifest(cr_id)
    if not manifest:
        print(f"  ERROR: Review {cr_id} not found.")
        return 1

    votes = manifest.get("votes", {})
    if len(votes) < 6 and not force:
        print(f"  Only {len(votes)} votes collected (quorum = 6). Use --force to override.")
        return 1

    # Read prompt
    rdir = _review_dir(cr_id)
    prompt_path = os.path.join(rdir, "prompt.txt")
    prompt_text = ""
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_text = f.read()

    # Read all responses
    response_block = ""
    for seat_str in sorted(votes.keys(), key=int):
        v = votes[seat_str]
        resp_file = os.path.join(rdir, v.get("response_file", ""))
        resp_text = ""
        if os.path.exists(resp_file):
            with open(resp_file, "r", encoding="utf-8") as f:
                resp_text = f.read()
        name = seat_name(seat_str)
        response_block += f"\n{'='*60}\nSEAT {seat_str}: {name} [{v['verdict']}]\n{'='*60}\n{resp_text}\n"

    primer = load_primer()

    synthesis_prompt = f"""You are synthesizing a DDL council review.

DDL SYSTEM KNOWLEDGE:
{primer}

ORIGINAL PROMPT:
{prompt_text}

SEAT RESPONSES ({len(votes)} votes):
{response_block}

SYNTHESIS INSTRUCTIONS:
1. CONVERGENCE — what do the seats agree on?
2. DIVERGENCE — where do they disagree? Cite seat numbers.
3. KEY ARGUMENTS — strongest points from each side.
4. TALLY — vote count by verdict.
5. RECOMMENDATION — based on the convergence pattern.
6. OPEN QUESTIONS — unresolved issues for the operator.

Be specific. Cite seat numbers. Do not invent consensus that doesn't exist."""

    print(f"  Synthesizing {len(votes)} responses for {cr_id}...")
    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": GEN_MODEL,
                "prompt": synthesis_prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_ctx": 16384},
            },
            timeout=300,
        )
        r.raise_for_status()
        synthesis = r.json().get("response", "[No response]")
    except Exception as e:
        print(f"  ERROR: Synthesis failed: {e}")
        return 1

    # Save
    synth_path = os.path.join(rdir, "synthesis.txt")
    with open(synth_path, "w", encoding="utf-8") as f:
        f.write(f"SYNTHESIS — {cr_id}\n")
        f.write(f"Generated: {now_iso()}\n")
        f.write(f"Synthesizer: {GEN_MODEL}\n")
        f.write(f"Votes: {len(votes)}\n\n")
        f.write(synthesis)

    manifest["synthesis_file"] = "synthesis.txt"
    _save_manifest(cr_id, manifest)

    print(f"\n{'='*60}")
    print(f"  SYNTHESIS — {cr_id}")
    print(f"{'='*60}\n")
    print(synthesis)
    print(f"\n{'='*60}")
    print(f"  Saved: {synth_path}\n")
    return 0


def cmd_close(cr_id: str) -> int:
    """Close a review and generate ingest-ready transcript."""
    manifest = _load_manifest(cr_id)
    if not manifest:
        print(f"  ERROR: Review {cr_id} not found.")
        return 1

    if manifest["status"] == "CLOSED":
        print(f"  Review {cr_id} is already CLOSED.")
        return 0

    manifest["status"] = "CLOSED"
    manifest["closed_at"] = now_iso()
    _save_manifest(cr_id, manifest)

    # Build full transcript for corpus ingestion
    rdir = _review_dir(cr_id)
    transcript_path = os.path.join(rdir, f"DDLCouncilReview_{cr_id.replace('-','_')}.txt")

    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(f"DDLCouncilReview_{cr_id}\n\n")
        f.write(f"{'='*60}\n")
        f.write(f"CR: {cr_id}\n")
        f.write(f"Title: {manifest.get('title', '')}\n")
        f.write(f"Created: {manifest['created']}\n")
        f.write(f"Closed: {manifest['closed_at']}\n")
        f.write(f"{'='*60}\n\n")

        # Prompt
        prompt_path = os.path.join(rdir, "prompt.txt")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as pf:
                f.write(f"PROMPT:\n{pf.read()}\n\n")

        # Responses
        votes = manifest.get("votes", {})
        for seat_str in sorted(votes.keys(), key=int):
            v = votes[seat_str]
            name = seat_name(seat_str)
            f.write(f"{'─'*60}\n")
            f.write(f"SEAT {seat_str}: {name} — {v['verdict']}\n")
            f.write(f"{'─'*60}\n\n")
            resp_file = os.path.join(rdir, v.get("response_file", ""))
            if os.path.exists(resp_file):
                with open(resp_file, "r", encoding="utf-8") as rf:
                    f.write(rf.read())
            f.write("\n\n")

        # Synthesis
        synth_path = os.path.join(rdir, "synthesis.txt")
        if os.path.exists(synth_path):
            with open(synth_path, "r", encoding="utf-8") as sf:
                f.write(f"{'='*60}\nSYNTHESIS\n{'='*60}\n\n")
                f.write(sf.read())

    # Copy to DDL_Ingest for next sweep
    ingest_dest = os.path.join(INGEST_DIR, os.path.basename(transcript_path))
    try:
        shutil.copy2(transcript_path, ingest_dest)
        print(f"  Copied to DDL_Ingest: {ingest_dest}")
    except Exception as e:
        print(f"  WARN: Could not copy to DDL_Ingest: {e}")

    tally = {"LOCK": 0, "REVISE": 0, "REJECT": 0}
    for v in votes.values():
        tally[v["verdict"]] += 1

    print(f"\n  CLOSED: {cr_id}")
    print(f"  Votes: {len(votes)} | {tally['LOCK']}L/{tally['REVISE']}R/{tally['REJECT']}X")
    print(f"  Transcript: {transcript_path}")
    print(f"  Will be ingested on next sweep.\n")
    return 0


def cmd_dex(cr_id: str) -> int:
    """Have Dex Jr. (Seat 1010) produce its own response."""
    manifest = _load_manifest(cr_id)
    if not manifest:
        print(f"  ERROR: Review {cr_id} not found.")
        return 1

    # Read prompt
    rdir = _review_dir(cr_id)
    prompt_path = os.path.join(rdir, "prompt.txt")
    if not os.path.exists(prompt_path):
        print(f"  ERROR: No prompt.txt in {rdir}")
        return 1

    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_text = f.read()

    # Build governed prompt with primer + RAG
    primer = load_primer()
    try:
        from dex_weights import weighted_query
        rag_results = weighted_query(prompt_text[:500], n_results=3)
        rag_context = "\n\n".join(
            f"[Source: {r.get('source', '?')} | Score: {r.get('weighted_score', 0):.3f}]\n{r['document'][:400]}"
            for r in rag_results
        )
    except Exception:
        rag_context = ""

    dex_prompt = f"""You are Dex Jr. (Seat 1010), the local governed model for DDL council reviews.
Produce your verdict (LOCK / REVISE / REJECT) and structured reasoning.

DDL SYSTEM KNOWLEDGE:
{primer}

RETRIEVED CONTEXT:
{rag_context}

COUNCIL REVIEW PROMPT:
{prompt_text}

Respond with:
1. Your VERDICT (LOCK / REVISE / REJECT) on the first line
2. Your reasoning — be specific, cite primer knowledge and retrieved context
3. Any conditions or concerns"""

    print(f"  Dex Jr. reviewing {cr_id}...")
    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": "dexjr",
                "prompt": dex_prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_ctx": 16384},
            },
            timeout=300,
        )
        r.raise_for_status()
        response = r.json().get("response", "[No response]")
    except Exception as e:
        print(f"  ERROR: Dex Jr. query failed: {e}")
        return 1

    # Detect verdict from response
    first_line = response.strip().split("\n")[0].upper()
    verdict = "LOCK"  # default
    for v in VERDICTS:
        if v in first_line:
            verdict = v
            break

    # Save as 1010's vote
    resp_filename = f"1010_{verdict}.txt"
    resp_path = os.path.join(rdir, "responses", resp_filename)
    with open(resp_path, "w", encoding="utf-8") as f:
        f.write(response)

    manifest["votes"]["1010"] = {
        "verdict": verdict,
        "timestamp": now_iso(),
        "response_file": f"responses/{resp_filename}",
    }
    _save_manifest(cr_id, manifest)

    print(f"\n{'='*60}")
    print(f"  DEX JR. (Seat 1010) — {verdict}")
    print(f"{'='*60}\n")
    print(response)
    print(f"\n{'='*60}")
    print(f"  Logged: 1010 Dex Jr. -> {verdict}\n")
    return 0


# ══════════════════════════════════════════════════════════════════════════════
# PARSER COMMANDS — parse, scan, stats (legacy DDLCouncilReview_*.txt files)
# ══════════════════════════════════════════════════════════════════════════════

CR_PATTERN = re.compile(r"\bCR-[A-Z0-9]+-[A-Z0-9-]+-\d{3}\b")
CR_SIMPLE = re.compile(r"\bCR-[A-Z]+-\d{3}\b")


def extract_cr_id(text: str) -> Optional[str]:
    header = "\n".join(text.split("\n")[:30])
    m = CR_PATTERN.search(header)
    if m:
        return m.group(0)
    m = CR_SIMPLE.search(header)
    if m:
        return m.group(0)
    for line in header.split("\n"):
        if "Document:" in line or "CR-" in line:
            m = re.search(r"CR-[A-Z0-9-]+(?:-\d{3})?", line)
            if m:
                return m.group(0)
    return None


def extract_title(text: str, filename: str) -> str:
    for line in text.split("\n")[:20]:
        if "Title:" in line:
            return line.split("Title:", 1)[1].strip()
    base = os.path.splitext(filename)[0]
    base = base.replace("DDLCouncilReview_", "").replace("DDLCouncilReview", "")
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', base).replace("_", " ").strip()


def detect_seat_sections(text: str) -> dict:
    lines = text.split("\n")
    sections = {}
    current_seat = None
    current_lines = []
    for line in lines:
        detected = None
        for seat_id, patterns in SEAT_PATTERNS.items():
            for pat in patterns:
                if re.search(rf"\b{re.escape(pat)}\b", line, re.IGNORECASE):
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
    for pat in [
        r"OVERALL\s+VERDICT[:\s]*\**\s*(LOCK|REVISE|REJECT)",
        r"FINAL\s+POSITION[:\s]*\**\s*(LOCK|REVISE|REJECT)",
        r"VERDICT[:\s]*\**\s*(LOCK|REVISE|REJECT)",
    ]:
        m = re.search(pat, section_text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    counts = {v: len(re.findall(rf"\b{v}\b", section_text)) for v in VERDICTS}
    dominant = max(counts, key=counts.get)
    return dominant if counts[dominant] > 0 else None


def extract_summary(section_text: str, max_sentences: int = 3) -> str:
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


def parse_review(filepath: str) -> Optional[dict]:
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
        cr_id = f"CR-{filename.replace('DDLCouncilReview_', '').replace('.txt', '').upper()}"

    sections = detect_seat_sections(text)
    votes = {}
    for sid, section in sections.items():
        verdict = extract_verdict(section)
        summary = extract_summary(section)
        if verdict:
            votes[sid] = {"verdict": verdict, "summary": summary, "seat_name": seat_name(sid)}

    tally = {"LOCK": 0, "REVISE": 0, "REJECT": 0}
    for v in votes.values():
        if v["verdict"] in tally:
            tally[v["verdict"]] += 1

    total_votes = sum(tally.values())
    if total_votes == 0:
        recommendation, confidence = "NO VOTES PARSED", "low"
    elif tally["LOCK"] == total_votes:
        recommendation, confidence = "LOCK - unanimous", "high"
    elif tally["LOCK"] > total_votes / 2:
        recommendation, confidence = f"LOCK - majority ({tally['LOCK']}/{total_votes})", "high"
    elif tally["REVISE"] > total_votes / 2:
        recommendation, confidence = f"REVISE - majority ({tally['REVISE']}/{total_votes})", "high"
    elif tally["REJECT"] > 0:
        recommendation, confidence = f"MIXED ({tally['LOCK']}L/{tally['REVISE']}R/{tally['REJECT']}X)", "medium"
    else:
        recommendation, confidence = f"SPLIT ({tally['LOCK']}L/{tally['REVISE']}R)", "medium"

    return {
        "cr_id": cr_id, "title": title, "source_file": filename,
        "source_path": os.path.abspath(filepath), "parsed_at": now_iso(),
        "votes": votes, "tally": tally, "total_votes": total_votes,
        "quorum": total_votes >= 5, "recommendation": recommendation,
        "parse_confidence": confidence,
    }


def cmd_parse(filepath: str) -> int:
    if not os.path.exists(filepath):
        print(f"  ERROR: File not found: {filepath}")
        return 1
    result = parse_review(filepath)
    if not result:
        return 1
    registry = load_registry()
    existing = [i for i, r in enumerate(registry["reviews"]) if r["source_file"] == result["source_file"]]
    if existing:
        registry["reviews"][existing[0]] = result
        print(f"  Updated: {result['cr_id']} ({result['source_file']})")
    else:
        registry["reviews"].append(result)
        print(f"  Added: {result['cr_id']} ({result['source_file']})")
    print(f"  Votes: {result['total_votes']} | Tally: {result['tally']}")
    print(f"  Recommendation: {result['recommendation']}")
    for s, v in sorted(result["votes"].items()):
        print(f"    {s} {v['seat_name']:20s} {v['verdict']:6s}  {v['summary'][:60]}")
    save_registry(registry)
    return 0


def cmd_scan() -> int:
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
    added = failed = 0
    for filepath in sorted(found):
        result = parse_review(filepath)
        if result:
            registry["reviews"].append(result)
            added += 1
            print(f"    {result['cr_id']:40s} {result['total_votes']} votes  {result['recommendation']}")
        else:
            failed += 1
            print(f"    FAILED: {os.path.basename(filepath)}")
    save_registry(registry)
    print(f"\n  Scan: {added} added, {failed} failed, {len(registry['reviews'])} total")
    return 0


def cmd_stats(seat=None, verdict=None, topic=None) -> int:
    registry = load_registry()
    reviews = registry.get("reviews", [])
    if not reviews:
        print("  Registry empty. Run 'dex r scan' first.")
        return 0
    if topic:
        reviews = [r for r in reviews if topic.lower() in (r.get("title", "") + r.get("cr_id", "")).lower()]
        if not reviews:
            print(f"  No reviews matching '{topic}'")
            return 0
    if verdict:
        verdict = verdict.upper()
        reviews = [r for r in reviews if any(v["verdict"] == verdict for v in r.get("votes", {}).values())]
    if seat:
        print(f"\n  VOTING HISTORY — Seat {seat} ({seat_name(seat)})")
        print(f"  {'='*60}\n")
        seat_reviews = [(r, r["votes"][seat]) for r in reviews if seat in r.get("votes", {})]
        if not seat_reviews:
            print(f"  No votes for seat {seat}")
            return 0
        counts = {"LOCK": 0, "REVISE": 0, "REJECT": 0}
        for r, v in seat_reviews:
            counts[v["verdict"]] += 1
            print(f"  {v['verdict']:6s}  {r['cr_id']:40s}  {r.get('title','')[:30]}")
        total = sum(counts.values())
        print(f"\n  Total: {total} | LOCK: {counts['LOCK']} | REVISE: {counts['REVISE']} | REJECT: {counts['REJECT']}")
        if total:
            print(f"  LOCK rate: {counts['LOCK']/total*100:.0f}%")
        return 0

    print(f"\n  COUNCIL VOTING PATTERNS ({len(reviews)} reviews)")
    print(f"  {'='*70}\n")
    seat_totals = {}
    for r in reviews:
        for s, v in r.get("votes", {}).items():
            if s not in seat_totals:
                seat_totals[s] = {"LOCK": 0, "REVISE": 0, "REJECT": 0}
            seat_totals[s][v["verdict"]] += 1
    print(f"  {'Seat':<6} {'Name':<22} {'LOCK':>5} {'REVISE':>7} {'REJECT':>7} {'Rate':>8}")
    print(f"  {'-'*60}")
    for s in sorted(seat_totals.keys()):
        c = seat_totals[s]
        total = sum(c.values())
        rate = f"{c['LOCK']/total*100:.0f}% LOCK" if total else "—"
        print(f"  {s:<6} {seat_name(s):<22} {c['LOCK']:>5} {c['REVISE']:>7} {c['REJECT']:>7} {rate:>8}")
    print(f"\n  {'='*70}\n")
    return 0


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description="DDL Council Review Management")
    sub = p.add_subparsers(dest="command")

    # Management commands
    c = sub.add_parser("create", help="Create a new review")
    c.add_argument("cr_id", nargs="?", default=None)
    c.add_argument("--title", default="")
    c.add_argument("--prompt-file", default=None)

    a = sub.add_parser("add", help="Log a seat's vote")
    a.add_argument("cr_id")
    a.add_argument("seat")
    a.add_argument("verdict")
    a.add_argument("--file", default=None)

    sub.add_parser("status", help="Show review status").add_argument("cr_id")

    ls = sub.add_parser("list", help="List reviews")
    ls.add_argument("--open", action="store_true", default=True)
    ls.add_argument("--closed", action="store_true")
    ls.add_argument("--all", action="store_true")

    sy = sub.add_parser("synthesize", help="Auto-synthesize responses")
    sy.add_argument("cr_id")
    sy.add_argument("--force", action="store_true")

    sub.add_parser("close", help="Close review + auto-ingest").add_argument("cr_id")
    sub.add_parser("dex", help="Dex Jr. votes on a review").add_argument("cr_id")

    # Parser commands
    sub.add_parser("parse", help="Parse a legacy review file").add_argument("file")
    sub.add_parser("scan", help="Scan for un-registered review files")

    st = sub.add_parser("stats", help="Voting patterns")
    st.add_argument("--seat", default=None)
    st.add_argument("--verdict", default=None)
    st.add_argument("--topic", default=None)

    args = p.parse_args()

    if args.command == "create":
        return cmd_create(args.cr_id, title=args.title, prompt_file=args.prompt_file)
    elif args.command == "add":
        return cmd_add(args.cr_id, args.seat, args.verdict, file_path=args.file)
    elif args.command == "status":
        return cmd_status(args.cr_id)
    elif args.command == "list":
        return cmd_list(show_open=True, show_closed=args.closed or args.all)
    elif args.command == "synthesize":
        return cmd_synthesize(args.cr_id, force=args.force)
    elif args.command == "close":
        return cmd_close(args.cr_id)
    elif args.command == "dex":
        return cmd_dex(args.cr_id)
    elif args.command == "parse":
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
