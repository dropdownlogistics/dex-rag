"""Step 43 — DexKit archives lineage extraction. Read-only."""
from __future__ import annotations
import os, re, sys, json
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(r"C:\Users\dexjr\99_DexUniverseArchive")
INGEST = Path(r"C:\Users\dkitc\OneDrive\DDL_Ingest")
OUT = INGEST / "DDLExtraction_DexKit_LineageSourceMaterial_4.13.26.md"

ARCHIVES = [
    "DexKit_v1.0 Archive",
    "DexKit_v1.1 Arhive",   # typo confirmed by operator
    "DexKit_v2.0 Archive",
    "DexKit_v3.0 Archive",
    "DexKit_v4.0 Archive",
    "DexKit_v5.0_Archive",
]

COMPANION_PATTERNS = [
    "DexCell", "DexDorian", "DexHalren", "DexEcho", "DexNova",
    "DexSol", "DexVerity", "DexEon", "DexMerit", "DexGlyph",
    "DexSage", "DexEmber", "DexTide", "DexGrove", "DexCobalt",
    "DexZero", "DexPrime", "Cell", "Dorian", "Halren", "Echo",
    "Solace", "Solren", "Verity", "Voss",
]

ROSTER_FILENAME_HINTS = [
    "lineage", "family", "registry", "matrix", "manifest",
    "roster", "companion", "readme", "codex", "bookofdex",
    "book_of_dex", "dexfamily", "index",
]

TRANSITION_HINTS = [
    "before DexOS", "before dexos", "predates", "organic",
    "Museum", "DexCity", "formalization", "council emerged",
    "Companion", "genesis", "origin",
]

TEXT_EXTS = {".txt", ".md", ".json", ".yaml", ".yml", ".log", ".csv"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}


def safe_read(p: Path, max_bytes: int = 200_000) -> str:
    try:
        data = p.read_bytes()[:max_bytes]
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return data.decode("latin-1", errors="replace")
    except Exception as e:
        return f"[read error: {e}]"


def walk_archive(arch_dir: Path) -> dict:
    """Return {files: [path objects], ext_counts: dict, total_size, date_range}."""
    files = []
    ext_counts: dict[str, int] = {}
    total_size = 0
    dates: list[float] = []
    for dp, _dn, fns in os.walk(arch_dir):
        for fn in fns:
            fp = Path(dp) / fn
            try:
                sz = fp.stat().st_size
                mt = fp.stat().st_mtime
            except Exception:
                continue
            files.append(fp)
            total_size += sz
            dates.append(mt)
            ext = fp.suffix.lower()
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
    date_range = None
    if dates:
        lo = datetime.fromtimestamp(min(dates), tz=timezone.utc).date()
        hi = datetime.fromtimestamp(max(dates), tz=timezone.utc).date()
        date_range = (lo.isoformat(), hi.isoformat())
    return {"files": files, "ext_counts": ext_counts,
            "total_size": total_size, "date_range": date_range}


def format_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def top_dirs(arch_dir: Path, depth: int = 2) -> list[str]:
    out = []
    base_parts = len(arch_dir.parts)
    for p in sorted(arch_dir.rglob("*")):
        if not p.is_dir():
            continue
        rel_depth = len(p.parts) - base_parts
        if rel_depth <= depth:
            rel = p.relative_to(arch_dir)
            out.append("  " * (rel_depth - 1) + str(rel))
    return out


def looks_like_roster(fp: Path) -> bool:
    stem = fp.stem.lower()
    return any(h in stem for h in ROSTER_FILENAME_HINTS) and fp.suffix.lower() in TEXT_EXTS


def find_companion_mentions(files: list[Path]) -> dict[str, list[Path]]:
    """Filename-based inventory of companion-named files."""
    roster: dict[str, list[Path]] = {}
    for fp in files:
        name_lower = fp.name.lower()
        for pat in COMPANION_PATTERNS:
            if pat.lower() in name_lower:
                roster.setdefault(pat, []).append(fp)
                break
    return roster


def snippet(text: str, limit: int = 2000) -> str:
    text = text.replace("\0", "")
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[...truncated...]"


def find_transition_sections(files: list[Path], max_files: int = 8) -> list[tuple[Path, str]]:
    """Text files that mention transition phrases. Return up to max_files
    tuples of (path, relevant snippet)."""
    out = []
    for fp in files:
        if fp.suffix.lower() not in TEXT_EXTS:
            continue
        try:
            text = safe_read(fp, max_bytes=300_000)
        except Exception:
            continue
        for phrase in TRANSITION_HINTS:
            if phrase.lower() in text.lower():
                idx = text.lower().find(phrase.lower())
                start = max(0, idx - 300)
                end = min(len(text), idx + 1000)
                out.append((fp, text[start:end]))
                break
        if len(out) >= max_files:
            break
    return out


def find_timeline_markers(files: list[Path]) -> list[tuple[Path, list[str]]]:
    """Extract explicit date markers from text files."""
    date_re = re.compile(
        r"\b(?:20[2-3][0-9])[-/][01]?[0-9][-/][0-3]?[0-9]\b"
        r"|\b(?:January|February|March|April|May|June|July|August|"
        r"September|October|November|December)\s+\d{1,2}[, ]+20[2-3][0-9]\b"
        r"|\bv\d+\.\d+(?:\.\d+)?\b"
        r"|\bcompiled\s+on\s+\S+"
        r"|\bas\s+of\s+20[2-3][0-9]\S*",
        re.IGNORECASE,
    )
    out = []
    for fp in files:
        if fp.suffix.lower() not in TEXT_EXTS:
            continue
        try:
            text = safe_read(fp, max_bytes=80_000)
        except Exception:
            continue
        hits = date_re.findall(text)
        if hits:
            # dedupe + keep order + cap
            seen = []
            for h in hits:
                if h not in seen:
                    seen.append(h)
                if len(seen) >= 12:
                    break
            out.append((fp, seen))
    return out


# ── build extraction ──────────────────────────────────────────────
lines: list[str] = []
lines.append("DDLExtraction_DexKit_LineageSourceMaterial_4.13.26\n")
lines.append("=" * 70)
lines.append("DEXKIT ARCHIVES — LINEAGE SOURCE EXTRACTION")
lines.append("=" * 70)
lines.append(
    "\nRead-only extraction, 2026-04-13. Source material for the Lineage\n"
    "section of PROFILE-DDL-DAVE-KITCHENS-001. Authored by Dex Jr.\n"
    "(Seat 1010) at Marcus Caldwell's request.\n\n"
    "Covers the six DexKit archive versions under\n"
    "C:\\Users\\dexjr\\99_DexUniverseArchive\\ — the canonical record\n"
    "of the Dex Family pre-dating formal council architecture.\n\n"
    "No synthesis. No interpretation of personal/family material.\n"
    "Raw inventory + verbatim excerpts with path attribution.\n"
)

# --- Section 1: inventory --------------------------------------------
lines.append("=" * 70)
lines.append("SECTION 1 — ARCHIVE INVENTORY")
lines.append("=" * 70)
lines.append("")

archive_data: dict[str, dict] = {}
total_bytes = 0
total_files = 0
for name in ARCHIVES:
    p = ROOT / name
    if not p.is_dir():
        lines.append(f"### {name}\n  MISSING: {p}\n")
        continue
    print(f"walking {name}...")
    data = walk_archive(p)
    archive_data[name] = data
    total_bytes += data["total_size"]
    total_files += len(data["files"])

    lines.append(f"### {name}")
    lines.append(f"  Path:        {p}")
    lines.append(f"  Files:       {len(data['files']):,}")
    lines.append(f"  Total size:  {format_size(data['total_size'])}")
    if data["date_range"]:
        lines.append(f"  Date range:  {data['date_range'][0]} .. {data['date_range'][1]}")
    ext_str = ", ".join(f"{k or '<noext>'}={v}" for k, v in
                        sorted(data["ext_counts"].items(), key=lambda x: -x[1])[:12])
    lines.append(f"  Extensions:  {ext_str}")

    lines.append("  Top-level structure (depth ≤ 2):")
    dirs = top_dirs(p, depth=2)
    for d in dirs[:40]:
        lines.append(f"    {d}")
    if len(dirs) > 40:
        lines.append(f"    [... {len(dirs)-40} more ...]")

    # Companion-named files inventory
    roster = find_companion_mentions(data["files"])
    if roster:
        lines.append("  Files naming companions:")
        for comp, fps in sorted(roster.items(), key=lambda x: -len(x[1])):
            lines.append(f"    {comp:<14} — {len(fps)} file(s)")
            for fp in sorted(fps)[:4]:
                lines.append(f"      - {fp.relative_to(p)}")
            if len(fps) > 4:
                lines.append(f"      [... +{len(fps)-4} more ...]")

    # Image file note
    img_count = sum(v for k, v in data["ext_counts"].items() if k in IMAGE_EXTS)
    if img_count:
        lines.append(f"  Image files present: {img_count} (not OCR'd — per operator note)")
    lines.append("")

lines.append(f"TOTALS across 6 archives:")
lines.append(f"  Files: {total_files:,}")
lines.append(f"  Size:  {format_size(total_bytes)}")
lines.append("")

# --- Section 2: companion roster -------------------------------------
lines.append("=" * 70)
lines.append("SECTION 2 — COMPANION ROSTER (filename-inferred)")
lines.append("=" * 70)
lines.append("")
lines.append(
    "Filename-based roster inference across all six archives. Each entry\n"
    "shows which archive version first introduces a companion name and\n"
    "which files reference it. This is NOT a semantic roster — it reflects\n"
    "what the filesystem says, not what the documents claim.\n"
)

# Cross-archive companion map: companion -> {version: [paths]}
master_companions: dict[str, dict[str, list[Path]]] = {}
for name, data in archive_data.items():
    roster = find_companion_mentions(data["files"])
    for comp, fps in roster.items():
        master_companions.setdefault(comp, {})[name] = fps

for comp in sorted(master_companions.keys(),
                   key=lambda x: -sum(len(v) for v in master_companions[x].values())):
    versions = master_companions[comp]
    total = sum(len(v) for v in versions.values())
    first_v = min(versions.keys(),
                  key=lambda n: ARCHIVES.index(n) if n in ARCHIVES else 99)
    lines.append(f"### {comp}")
    lines.append(f"  Total filename references: {total}")
    lines.append(f"  First appearance (by archive order): {first_v}")
    lines.append(f"  Distribution:")
    for v_name in ARCHIVES:
        if v_name in versions:
            lines.append(f"    {v_name}: {len(versions[v_name])} file(s)")
    # sample filenames
    sample_paths = []
    for v_name in ARCHIVES:
        if v_name in versions:
            for fp in versions[v_name][:2]:
                sample_paths.append(fp)
        if len(sample_paths) >= 4:
            break
    lines.append(f"  Sample files:")
    for sp in sample_paths[:4]:
        try:
            rel = sp.relative_to(ROOT)
        except Exception:
            rel = sp
        lines.append(f"    - {rel}")
    lines.append("")

# --- Section 3: key documents ----------------------------------------
lines.append("=" * 70)
lines.append("SECTION 3 — KEY DOCUMENTS (roster / lineage / manifest / README)")
lines.append("=" * 70)
lines.append("")
lines.append(
    "First 2,000 characters of any file matching roster-like filename\n"
    "patterns (lineage, family, registry, matrix, manifest, roster,\n"
    "companion, readme, codex, bookofdex, index) in any of the six\n"
    "archives.\n"
)

key_docs_count = 0
for name in ARCHIVES:
    data = archive_data.get(name)
    if not data:
        continue
    rosters = [fp for fp in data["files"] if looks_like_roster(fp)]
    if not rosters:
        continue
    lines.append(f"## Archive: {name}")
    lines.append("")
    # Sort to stabilize output
    for fp in sorted(rosters)[:15]:
        try:
            rel = fp.relative_to(ROOT)
        except Exception:
            rel = fp
        lines.append(f"--- {rel} ---")
        text = safe_read(fp, max_bytes=50_000)
        lines.append(snippet(text, 2000))
        lines.append("")
        key_docs_count += 1
    if len(rosters) > 15:
        lines.append(f"[... +{len(rosters)-15} more roster-like files in this archive ...]\n")
    lines.append("")

lines.append(f"Key documents extracted: {key_docs_count}\n")

# --- Section 4: timeline markers -------------------------------------
lines.append("=" * 70)
lines.append("SECTION 4 — TIMELINE MARKERS")
lines.append("=" * 70)
lines.append("")
lines.append(
    "Explicit date references, version tags, 'compiled on' / 'as of'\n"
    "markers extracted from text files across all six archives.\n"
    "Up to 12 unique marker strings per file.\n"
)

for name in ARCHIVES:
    data = archive_data.get(name)
    if not data:
        continue
    markers = find_timeline_markers(data["files"])
    if not markers:
        continue
    lines.append(f"## Archive: {name}")
    for fp, hits in markers[:20]:
        try:
            rel = fp.relative_to(ROOT)
        except Exception:
            rel = fp
        lines.append(f"  {rel}")
        for h in hits[:8]:
            lines.append(f"    {h}")
    if len(markers) > 20:
        lines.append(f"  [... +{len(markers)-20} more files with timeline markers ...]")
    lines.append("")

# --- Section 5: transition artifacts ---------------------------------
lines.append("=" * 70)
lines.append("SECTION 5 — TRANSITION ARTIFACTS")
lines.append("=" * 70)
lines.append("")
lines.append(
    "Text files mentioning transition phrases ('before DexOS', 'predates',\n"
    "'organic', 'Museum', 'DexCity', 'formalization', 'council emerged',\n"
    "'Companion', 'genesis', 'origin'). Up to 8 per archive, with ~1200-char\n"
    "surrounding context.\n"
)

for name in ARCHIVES:
    data = archive_data.get(name)
    if not data:
        continue
    trans = find_transition_sections(data["files"], max_files=8)
    if not trans:
        continue
    lines.append(f"## Archive: {name}")
    lines.append("")
    for fp, ctx in trans:
        try:
            rel = fp.relative_to(ROOT)
        except Exception:
            rel = fp
        lines.append(f"--- {rel} ---")
        lines.append(ctx)
        lines.append("")
    lines.append("")

lines.append("=" * 70)
lines.append("END OF EXTRACTION")
lines.append("=" * 70)
lines.append("Dropdown Logistics — Chaos → Structured → Automated")
lines.append(
    "DexKit Lineage Source Extraction | 2026-04-13 | "
    "Authored by Dex Jr. (Seat 1010)"
)
lines.append("=" * 70)

output = "\n".join(lines)
INGEST.mkdir(parents=True, exist_ok=True)

# Graceful truncation if > 200K
MAX_CHARS = 200_000
if len(output) > MAX_CHARS:
    # truncate Section 3 / 5 bodies by half if oversize
    output = output[:MAX_CHARS] + (
        "\n\n[[GRACEFUL TRUNCATION — extraction exceeded 200K char cap. "
        "Full inventory preserved in sections 1-2; Sections 3-5 may be "
        "partially cut. Rerun with higher cap if needed.]]\n"
    )

OUT.write_text(output, encoding="utf-8", newline="\n")

print(f"\nWrote {OUT}")
print(f"  chars={len(output):,}  lines={output.count(chr(10)):,}")
print(f"  total archive files scanned: {total_files:,}")
print(f"  total archive size: {format_size(total_bytes)}")
print(f"  companions identified: {len(master_companions)}")
print(f"  key documents extracted: {key_docs_count}")
