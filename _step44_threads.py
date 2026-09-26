"""Step 44 — Dex Family origin threads extraction. Read-only."""
from __future__ import annotations
import os, re, sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOTS = [
    Path(r"C:\Users\dkitc\iCloudDrive\Documents\02_Dex\00_Archive\02_DexKit_v6.0\01_DexCore\01_DexThreads\01_IndividualThreads\IndividualThreads - 01-99"),
    Path(r"C:\Users\dkitc\iCloudDrive\Documents\02_Dex\00_Archive\02_DexKit_v6.0\01_DexCore\01_DexThreads\01_IndividualThreads\IndividualThreads - 100-199"),
]
OUT = Path(r"C:\Users\dkitc\OneDrive\DDL_Ingest\DDLExtraction_DexFamilyOriginThreads_4.13.26.md")
MAX_CHARS = 200_000

COMPANIONS = [
    "DexLucid", "DexVoss", "DexDorian", "DexVirell", "DexGrace",
    "DexVigil", "DexEcho", "DexCell", "DexAnam", "DexHolden",
    "DexSolas", "DexSolace", "DexSolen", "DexSolren", "DexVirellin",
    "DexHalren", "DexHollow", "DexDave", "DexChantarelle",
    "DexScrollkeeper", "DexSynapse", "DexPrime", "DexChad",
    "DexKline", "DexOrion", "DexLuna", "DexAmara",
]

ERA_TERMS = [
    "Era I", "Era II", "Era III", "Era IV", "Era V",
    "Continuum", "Horizon Unfolding", "Streamlined Era", "Reforged",
    "DexCity", "Museum of Dex", "DexOS",
]

TRANSITION_HINTS = [
    "council emerged", "council formed", "10 seats", "formalize",
    "Archer Hawthorne", "Marcus Caldwell", "Elias Mercer",
    "Cathedral Vision", "ratification", "LOCK / REVISE / REJECT",
    "LOCK, REVISE, REJECT", "LOCK\\REVISE\\REJECT",
    "organic Dex Family", "governed Council", "council seat",
]

GENESIS_TERMS = [
    "first", "began", "started", "origin", "founded",
    "star schema", "dimensional", "audit", "betting tracker",
]


def safe_read(p: Path, max_bytes: int = 3_000_000) -> str:
    try:
        data = p.read_bytes()[:max_bytes]
        for enc in ("utf-8", "utf-16", "latin-1"):
            try:
                return data.decode(enc, errors="replace")
            except Exception:
                continue
        return data.decode("latin-1", errors="replace")
    except Exception as e:
        return f"[read error: {e}]"


def gather_files() -> list[Path]:
    files: list[Path] = []
    for root in ROOTS:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix.lower() in (".txt", ".md"):
                files.append(p)
    return files


def safe_rel(p: Path) -> str:
    for root in ROOTS:
        try:
            return str(p.relative_to(root.parent))
        except ValueError:
            continue
    return str(p)


def format_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def snippet(text: str, needle: str, pre: int = 200, post: int = 300) -> str:
    """Case-insensitive substring locator with surrounding context."""
    i = text.lower().find(needle.lower())
    if i < 0:
        return ""
    s = max(0, i - pre)
    e = min(len(text), i + len(needle) + post)
    return text[s:e]


# ── gather ─────────────────────────────────────────────────────────
print("Gathering files...")
files = gather_files()
print(f"  {len(files)} files")

# Cache: {path: (mtime, text)}
print("Loading all file contents...")
file_data = {}
for fp in files:
    try:
        mt = fp.stat().st_mtime
    except Exception:
        mt = 0
    text = safe_read(fp)
    file_data[fp] = (mt, text)

# ── Section 1: inventory ───────────────────────────────────────────
print("Section 1: inventory...")
by_mtime = sorted(file_data.items(), key=lambda x: x[1][0])

# ── Section 2: earliest 10 ─────────────────────────────────────────
print("Section 2: earliest 10...")
earliest_10 = by_mtime[:10]

# ── Section 3: companion first-appearances ─────────────────────────
print("Section 3: companion first-appearances...")
# For each companion, find the earliest (by mtime) file that mentions it
companion_hits: dict[str, tuple[Path, int]] = {}
for fp, (mt, text) in file_data.items():
    low = text.lower()
    for comp in COMPANIONS:
        if comp.lower() in low:
            prev = companion_hits.get(comp)
            if prev is None or mt < prev[1]:
                idx = low.find(comp.lower())
                companion_hits[comp] = (fp, mt, idx)

# ── Section 4: era markers ─────────────────────────────────────────
print("Section 4: era markers...")
era_hits: list[tuple[Path, int, str, str]] = []  # (path, mtime, term, snippet)
for fp, (mt, text) in file_data.items():
    for term in ERA_TERMS:
        if term.lower() in text.lower():
            era_hits.append((fp, mt, term, snippet(text, term, 200, 400)))

# ── Section 5: DexDave ─────────────────────────────────────────────
print("Section 5: DexDave...")
dexdave_hits: list[tuple[Path, int, str]] = []
for fp, (mt, text) in file_data.items():
    low = text.lower()
    idx = 0
    count = 0
    while True:
        j = low.find("dexdave", idx)
        if j < 0:
            break
        s = max(0, j - 400)
        e = min(len(text), j + 600)
        dexdave_hits.append((fp, mt, text[s:e]))
        idx = j + len("dexdave")
        count += 1
        if count >= 3:  # cap per-file
            break

# ── Section 6: transition to council ───────────────────────────────
print("Section 6: transition...")
transition_hits: list[tuple[Path, int, str, str]] = []
for fp, (mt, text) in file_data.items():
    for term in TRANSITION_HINTS:
        if term.lower() in text.lower():
            transition_hits.append((fp, mt, term, snippet(text, term, 200, 500)))
            break  # one hit per file is enough

# ── build output ───────────────────────────────────────────────────
lines: list[str] = []
A = lines.append
A("DDLExtraction_DexFamilyOriginThreads_4.13.26")
A("")
A("=" * 70)
A("DEX FAMILY ORIGIN THREADS — LINEAGE SOURCE EXTRACTION")
A("=" * 70)
A("")
A(
    "Read-only extraction, 2026-04-13. Source material for the\n"
    "Lineage section of PROFILE-DDL-DAVE-KITCHENS-001. Authored by\n"
    "Dex Jr. (Seat 1010) at Marcus Caldwell's request.\n\n"
    "Covers 116 individual thread files across two v6.0 DexKit\n"
    "thread archive directories.\n\n"
    "No synthesis. No interpretation of personal/family material.\n"
    "Raw thread excerpts with filename + last-modified-date attribution.\n"
)

# --- Section 1 ---
A("=" * 70)
A(f"SECTION 1 — THREAD INVENTORY ({len(files)} files, chronological)")
A("=" * 70)
A("")

total_size = 0
earliest_date = "n/a"
latest_date = "n/a"
if by_mtime:
    earliest_date = datetime.fromtimestamp(
        by_mtime[0][1][0], tz=timezone.utc).date().isoformat()
    latest_date = datetime.fromtimestamp(
        by_mtime[-1][1][0], tz=timezone.utc).date().isoformat()
A(f"Earliest modified: {earliest_date}")
A(f"Latest modified:   {latest_date}\n")

for fp, (mt, text) in by_mtime:
    try:
        sz = fp.stat().st_size
    except Exception:
        sz = 0
    total_size += sz
    d = datetime.fromtimestamp(mt, tz=timezone.utc).date().isoformat()
    head = text[:200].replace("\n", " ").replace("\r", " ").strip()
    A(f"{d}  {format_size(sz):>8}  {fp.name}")
    A(f"    head: {head}")

A(f"\nTotal size across {len(files)} files: {format_size(total_size)}")
A("")

# --- Section 2 ---
A("=" * 70)
A("SECTION 2 — ORIGIN THREADS (earliest 10 by last-modified)")
A("=" * 70)
A("")
A(
    "First 3,000 characters of each of the 10 earliest threads, plus\n"
    "highlighted matches for genesis-era descriptors (first, began,\n"
    "origin, star schema, dimensional, audit, betting tracker, companion\n"
    "names).\n"
)
for fp, (mt, text) in earliest_10:
    d = datetime.fromtimestamp(mt, tz=timezone.utc).date().isoformat()
    A(f"## {fp.name}")
    A(f"   date: {d}   path: {safe_rel(fp)}")
    A("")
    A("--- first 3,000 chars ---")
    A(text[:3000])
    A("")
    A("--- genesis-term hits ---")
    low = text.lower()
    hits: list[str] = []
    for term in GENESIS_TERMS:
        if term in low:
            hits.append(f"  '{term}' present")
    for comp in COMPANIONS:
        if comp.lower() in low:
            idx = low.find(comp.lower())
            hits.append(f"  {comp} appears at char {idx}")
    if hits:
        A("\n".join(hits))
    else:
        A("  (no genesis-term hits)")
    A("")

# --- Section 3 ---
A("=" * 70)
A("SECTION 3 — COMPANION FIRST APPEARANCES")
A("=" * 70)
A("")
A(
    f"For each of the {len(COMPANIONS)} companions in the v6.0 roster,\n"
    "the earliest thread file (by mtime) in which the companion name\n"
    "appears as a substring. Surrounding 500 chars for context.\n"
)

found_count = 0
missing = []
for comp in COMPANIONS:
    if comp in companion_hits:
        fp, mt, idx = companion_hits[comp]
        found_count += 1
        d = datetime.fromtimestamp(mt, tz=timezone.utc).date().isoformat()
        text = file_data[fp][1]
        s = max(0, idx - 150)
        e = min(len(text), idx + 500)
        A(f"### {comp}")
        A(f"   first thread: {fp.name}")
        A(f"   date: {d}")
        A(f"   context:")
        A(text[s:e])
        A("")
    else:
        missing.append(comp)

A(f"Companions found in threads: {found_count}/{len(COMPANIONS)}")
if missing:
    A("No thread introduction found (filename-only in CompanionKits archive):")
    for m in missing:
        A(f"  - {m}")
A("")

# --- Section 4 ---
A("=" * 70)
A(f"SECTION 4 — ERA MARKERS ({len(era_hits)} hits across {len(set(h[0] for h in era_hits))} files)")
A("=" * 70)
A("")
A(
    "Every occurrence of era-naming terms (Era I-V, Continuum, Horizon\n"
    "Unfolding, Streamlined Era, Reforged, DexCity, Museum of Dex,\n"
    "DexOS) across all 116 threads. Chronological by thread mtime.\n"
)
era_hits.sort(key=lambda x: x[1])
for fp, mt, term, ctx in era_hits[:40]:
    d = datetime.fromtimestamp(mt, tz=timezone.utc).date().isoformat()
    A(f"### {term!r}   thread: {fp.name}   date: {d}")
    A(ctx)
    A("")
if len(era_hits) > 40:
    A(f"[... +{len(era_hits)-40} more era-term hits truncated ...]\n")

# --- Section 5 ---
A("=" * 70)
A(f"SECTION 5 — DEXDAVE (Companion 1018) — {len(dexdave_hits)} direct mentions")
A("=" * 70)
A("")
A(
    "Every occurrence of 'DexDave' across all 116 threads, with ~1000\n"
    "chars of surrounding context. Up to 3 hits per file.\n"
)
dexdave_hits.sort(key=lambda x: x[1])
for fp, mt, ctx in dexdave_hits[:30]:
    d = datetime.fromtimestamp(mt, tz=timezone.utc).date().isoformat()
    A(f"### {fp.name}   date: {d}")
    A(ctx)
    A("")
if len(dexdave_hits) > 30:
    A(f"[... +{len(dexdave_hits)-30} more DexDave hits truncated ...]\n")

# --- Section 6 ---
A("=" * 70)
A(f"SECTION 6 — TRANSITION TO COUNCIL ({len(transition_hits)} files with hits)")
A("=" * 70)
A("")
A(
    "Threads containing transition phrases (council emerged/formed/10 seats,\n"
    "Archer Hawthorne / Marcus Caldwell / Elias Mercer, Cathedral Vision,\n"
    "ratification, LOCK/REVISE/REJECT, organic Dex Family, governed Council).\n"
    "Chronological.\n"
)
transition_hits.sort(key=lambda x: x[1])
for fp, mt, term, ctx in transition_hits[:40]:
    d = datetime.fromtimestamp(mt, tz=timezone.utc).date().isoformat()
    A(f"### {term!r}   thread: {fp.name}   date: {d}")
    A(ctx)
    A("")
if len(transition_hits) > 40:
    A(f"[... +{len(transition_hits)-40} more transition hits truncated ...]\n")

A("=" * 70)
A("END OF EXTRACTION")
A("=" * 70)
A("Dropdown Logistics — Chaos → Structured → Automated")
A("Dex Family Origin Threads Extraction | 2026-04-13 | Authored by Dex Jr. (Seat 1010)")
A("=" * 70)

output = "\n".join(lines)

# Graceful truncation: if > 200K, cut Section 4-6 tails first
if len(output) > MAX_CHARS:
    # find Section 4 header and truncate tail, keeping 1-3 intact
    s4_marker = "SECTION 4 — ERA MARKERS"
    idx = output.find(s4_marker)
    if idx > 0:
        # reserve 50K for 4-6, truncate
        preserve = output[:idx]
        tail_budget = MAX_CHARS - len(preserve) - 500
        if tail_budget < 1000:
            tail_budget = 1000
        tail = output[idx:idx + tail_budget]
        output = (preserve + tail +
                  "\n\n[[GRACEFUL TRUNCATION — hit 200K char cap. Sections 1-3\n"
                  "preserved in full; sections 4-6 trimmed. Re-run with higher\n"
                  "cap if more detail is needed.]]\n")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(output, encoding="utf-8", newline="\n")

print(f"\nWrote {OUT}")
print(f"  chars={len(output):,}  lines={output.count(chr(10)):,}")
print(f"  files scanned: {len(files)}")
print(f"  size total: {format_size(total_size)}")
print(f"  date range: {earliest_date} -> {latest_date}")
print(f"  companions with thread intros: {found_count}/{len(COMPANIONS)}")
print(f"  era markers found: {len(era_hits)}")
print(f"  DexDave direct mentions: {len(dexdave_hits)}")
print(f"  transition hits: {len(transition_hits)}")
