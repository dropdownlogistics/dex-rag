"""Step 42 — Dave Kitchens source material extraction for PROFILE drafting.

Read-only. Pulls $contains chunks across dex_canon_v2 + ddl_archive_v2,
ranks by descriptive density, outputs a single extraction file to DDL_Ingest.
No synthesis.
"""
from __future__ import annotations
import json, os, sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import chromadb

CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"
INGEST = r"C:\Users\dkitc\OneDrive\DDL_Ingest"
OUT_FILE = os.path.join(
    INGEST, "DDLExtraction_DaveKitchens_SourceMaterial_4.13.26.md"
)

client = chromadb.PersistentClient(path=CHROMA_DIR)
canon = client.get_collection("dex_canon_v2")
archive = client.get_collection("ddl_archive_v2")


def qall(term: str, limit: int = 100) -> list[dict]:
    """Query both collections, return merged list of {corpus,sf,text}."""
    out = []
    for label, col in [("canon", canon), ("archive", archive)]:
        try:
            h = col.get(
                where_document={"$contains": term},
                limit=limit,
                include=["documents", "metadatas"],
            )
        except Exception as e:
            print(f"  [warn] {label}/{term!r}: {e}")
            continue
        for d, m in zip(h.get("documents", []) or [], h.get("metadatas", []) or []):
            out.append({
                "corpus": label,
                "sf": (m or {}).get("source_file", "?"),
                "text": d or "",
            })
    return out


def count_only(term: str) -> tuple[int, int]:
    """Fast count query — just the id length."""
    cn = canon.get(where_document={"$contains": term}, include=[]).get("ids", [])
    an = archive.get(where_document={"$contains": term}, include=[]).get("ids", [])
    return len(cn), len(an)


def dedupe_top(hits: list[dict], term: str, n: int,
               extra_descriptors: list[str] = None) -> list[dict]:
    """Score by mention count + descriptor presence, dedupe across corpora, top n."""
    extra_descriptors = extra_descriptors or []
    scored = []
    for h in hits:
        t = h["text"]
        score = t.count(term) * 2
        for d in extra_descriptors:
            if d.lower() in t.lower():
                score += 2
        scored.append((score, h))
    scored.sort(key=lambda x: -x[0])
    seen: set[tuple[str, str]] = set()
    out = []
    for score, h in scored:
        # dedupe on (filename tail, first 100 chars) so canon/archive dupes collapse
        key = (h["sf"].split("\\")[-1], h["text"][:100])
        if key in seen:
            continue
        seen.add(key)
        out.append({**h, "score": score})
        if len(out) >= n:
            break
    return out


def snippet_around(text: str, term: str, pre: int = 250, post: int = 800) -> str:
    idx = text.find(term)
    if idx < 0:
        # not found (might happen via case-insensitive match); just head
        return text[:pre + post]
    start = max(0, idx - pre)
    end = min(len(text), idx + len(term) + post)
    return text[start:end]


def emit_category(title: str, blocks: list[str]) -> str:
    sep = "=" * 70
    body = "\n\n".join(blocks)
    return f"{sep}\n{title}\n{sep}\n\n{body}\n"


# ── run ───────────────────────────────────────────────────────────

doc_lines: list[str] = []
doc_lines.append("DDLExtraction_DaveKitchens_SourceMaterial_4.13.26\n")
doc_lines.append("=" * 70)
doc_lines.append("DAVE KITCHENS SOURCE EXTRACTION — FOR PROFILE-DDL-* DRAFTING")
doc_lines.append("=" * 70)
doc_lines.append("")
doc_lines.append(
    "Read-only extraction, 2026-04-13. Source for operator-authored\n"
    "PROFILE-DDL-DAVE-KITCHENS-001, PROFILE-DDL-DAVE-OPERATOR-001,\n"
    "PROFILE-DDL-DAVE-EXTERNAL-001. Authored by Dex Jr. (Seat 1010)\n"
    "at Marcus Caldwell's request.\n\n"
    "Methodology: $contains queries against dex_canon_v2 and\n"
    "ddl_archive_v2, ranked by descriptive density (mention count +\n"
    "category-specific descriptor hits). Raw chunks with source_file\n"
    "attribution. Snippets cut to ~1000 chars around the matched term.\n\n"
    "No synthesis. No interpretation of personal context. Marcus and\n"
    "the operator handle framing.\n"
)

# ── Category 1: identity markers (counts only) ─────────────────────
print("Category 1: identity counts...")
ident_terms = [
    "Dave Kitchens", "Dave's", "Dave is", "D.K. Hale",
    "AUD-011", "Seat 0",
]
rows = []
for term in ident_terms:
    cn, an = count_only(term)
    rows.append(f"  {term:<25} canon={cn:>5}  archive={an:>5}  total={cn+an:>5}")
    print(f"  {term}: {cn} / {an}")

doc_lines.append(emit_category(
    "CATEGORY 1 — IDENTITY MARKERS (counts only)",
    [
        "Surface-area inventory. Raw counts across both corpora. Not extracted;\n"
        "scope is too broad for per-chunk inclusion. Marcus uses this table\n"
        "to calibrate where dense material lives.",
        "\n".join(rows),
    ]
))

# Note: "operator" and "Dave" alone are too broad — they'd hit the limit
# instantly and dominate irrelevant material. Skipping counts for those;
# noting as a gap.
doc_lines.append(
    "NOTE: counts for bare 'operator' and 'Dave' skipped — both terms are\n"
    "too broad to be useful as an identity signal (every sweep report and\n"
    "CLAUDE.md reference registers). True operator-about-Dave volume is\n"
    "captured in Categories 2-8 via more specific descriptors.\n"
)


# Helper: emit a labeled multi-block chunk section
def build_block_section(title: str, pairs: list[tuple[str, str, int, list[str]]]) -> str:
    """pairs: list of (label, term, n_chunks, descriptors)"""
    blocks = []
    for label, term, n, descriptors in pairs:
        hits = qall(term, limit=100)
        top = dedupe_top(hits, term, n=n, extra_descriptors=descriptors)
        if not top:
            blocks.append(f"\n### {label}  ({term!r})\n(no hits)\n")
            continue
        chunk_blocks = [f"\n### {label}  ({term!r}) — top {len(top)}\n"]
        for i, h in enumerate(top, 1):
            snip = snippet_around(h["text"], term)
            chunk_blocks.append(
                f"--- #{i}  corpus={h['corpus']}  sf={h['sf']} ---\n{snip}\n"
            )
        blocks.append("\n".join(chunk_blocks))
    return emit_category(title, blocks)


# ── Category 2: Role + professional context ────────────────────────
print("Category 2: role...")
doc_lines.append(build_block_section(
    "CATEGORY 2 — ROLE AND PROFESSIONAL CONTEXT",
    [
        ("UMB role",          "UMB Bank",              5, ["Commission Analyst", "Cara", "Jennifer Parker", "Salesforce"]),
        ("Commission Analyst","Commission Analyst",    5, ["UMB", "Cara", "template"]),
        ("Cara Borkowski",    "Cara Borkowski",        4, ["manager", "commission", "UMB"]),
        ("Jennifer Parker",   "Jennifer Parker",       4, ["EVP", "UMB"]),
        ("Alteryx",           "Alteryx",               3, ["UMB", "pre-approval"]),
        ("CPA",               "CPA",                   5, ["credentials", "audit", "10+ years"]),
        ("internal audit",    "internal audit",        5, ["SOX", "public accounting", "senior"]),
        ("r/excel",           "r/excel",               4, ["karma", "Reddit", "Excelligence"]),
        ("Excel expertise",   "r/Excel",               3, ["karma", "Reddit"]),
        ("Dropdown Logistics","Dropdown Logistics",    5, ["founder", "operator", "studio"]),
    ]
))

# ── Category 3: Methodology + architecture ─────────────────────────
print("Category 3: methodology...")
doc_lines.append(build_block_section(
    "CATEGORY 3 — METHODOLOGY AND ARCHITECTURE",
    [
        ("Chaos Structured Automated", "Chaos → Structured → Automated", 5, []),
        ("Dimensional",                 "dimensional",                   5, ["star schema", "fact table", "governed"]),
        ("star schema",                 "star schema",                   5, ["dimensional", "fact table"]),
        ("architecture does not change","The architecture does not change", 5, []),
        ("CottageHumble",               "CottageHumble",                 4, ["humble", "feature", "Graph Holds"]),
        ("Graph Holds",                 "Graph Holds",                   4, ["operating principle", "spine", "humble"]),
        ("AcceptableArrogance",         "AcceptableArrogance",           4, ["humble", "posture"]),
        ("F-code (F4 primary example)", "F4 violation",                  4, ["Platinum Bounce", "F-code"]),
    ]
))

# ── Category 4: Relationships ──────────────────────────────────────
print("Category 4: relationships...")
doc_lines.append(build_block_section(
    "CATEGORY 4 — RELATIONSHIPS AND COLLABORATORS",
    [
        ("Emily — Seat 0",    "Emily",            4, ["Seat 0", "wife", "Sprinkles", "Nomadic Notary"]),
        ("Sprinkles & Co",    "Sprinkles",        3, ["Emily", "business"]),
        ("Nomadic Notary",    "Nomadic Notary",   3, ["Emily"]),
        ("David (father-in-law)", "David",        3, ["father-in-law", "technical"]),
        ("Alex (cousin)",     "Alex",             3, ["cousin", "BlindSpot", "PositionBook", "trader"]),
        ("Bryce",             "Bryce",            3, ["sobriety", "support"]),
        ("Beth Epperson",     "Beth Epperson",    4, ["commercial", "AuditForge", "prospect", "filter"]),
        ("Clayton Hotze",     "Clayton Hotze",    3, ["engineering", "Nueterra", "demo"]),
        ("Connor",            "Connor",           3, ["technical"]),
        ("GK",                "GK",               2, ["adjunct"]),
        ("Meg ADJ-E",         "Meg",              2, ["ADJ-E", "adjunct"]),
        ("Todd Kitchens",     "Todd Kitchens",    2, ["brother", "family"]),
        ("Jim Kitchens",      "Jim Kitchens",     2, ["family", "father"]),
        ("Lynn Kitchens",     "Lynn Kitchens",    2, ["family", "mother"]),
    ]
))

# ── Category 5: Products ────────────────────────────────────────────
print("Category 5: products...")
doc_lines.append(build_block_section(
    "CATEGORY 5 — PRODUCTS AND SCOPE",
    [
        ("DDL the studio",    "Dropdown Logistics",  5, ["studio", "44 systems", "65 standards", "methodology"]),
        ("AuditForge",        "AuditForge",          5, ["governed", "demo", "Beth", "prospect"]),
        ("WorkBench",         "WorkBench",           5, ["modular", "17 modules", "HR & People", "Module 1"]),
        ("Ledger",            "Ledger",              4, ["identity", "verified"]),
        ("BlindSpot",         "BlindSpot",           4, ["sports betting", "Alex", "analytics"]),
        ("PositionBook",      "PositionBook",        4, ["trading", "Alex"]),
        ("Excelligence",      "Excelligence",        4, ["Excel", "knowledge graph"]),
        ("Dex Jr.",           "Dex Jr",              4, ["RAG", "retrieval", "local"]),
        ("CanonPress",        "CanonPress",          3, ["publication", "Substack"]),
        ("Little to Know Experience", "Little to Know",      3, ["memoir", "LTKE", "Substack"]),
    ]
))

# ── Category 6: Personal context ───────────────────────────────────
print("Category 6: personal...")
doc_lines.append(build_block_section(
    "CATEGORY 6 — PERSONAL CONTEXT",
    [
        ("Sobriety",          "sobriety",            4, ["8 years", "AA", "memoir"]),
        ("8 years sober",     "8 years",             3, ["sober", "sobriety"]),
        ("Memoir / LTKE",     "Little to Know",      3, ["memoir", "Substack", "crisis"]),
        ("D&D / DM",          "D&D",                 3, ["DM", "Dungeons", "campaign", "Emily"]),
        ("Cole and Riley (cats)", "Cole",            2, ["Riley", "cat", "kitten"]),
        ("Riley",             "Riley",               2, ["Cole", "cat"]),
        ("Duolingo",          "Duolingo",            3, ["languages", "Spanish", "French", "German"]),
        ("Skyrim",            "Skyrim",              2, ["gaming"]),
        ("Divinity",          "Divinity",            2, ["Original Sin", "gaming"]),
        ("Kansas City",       "Kansas City",         3, ["KC", "geographic"]),
    ]
))

# ── Category 7: Voice and operator patterns ────────────────────────
print("Category 7: voice/patterns...")
doc_lines.append(build_block_section(
    "CATEGORY 7 — VOICE AND OPERATOR PATTERNS",
    [
        ("'fair?' alignment check", "fair?",           4, ["alignment", "operator"]),
        ("'let him cook'",          "let him cook",     4, ["autonomous", "stop talking", "operator"]),
        ("Compression mode",        "compression",      3, ["time", "operator", "short"]),
        ("39_DDLFormation",         "39_DDLFormation",  3, ["signature moves", "Graph Holds", "humility"]),
        ("Humility as throttle",    "humility",         4, ["throttle", "posture", "CottageHumble"]),
        ("audit trail",             "audit trail",      4, ["building", "system", "simultaneous"]),
        ("Sam Vimes",               "Sam Vimes",        3, ["Pratchett", "archetype"]),
        ("The Architect",           "The Architect",    3, ["Matrix", "archetype"]),
        ("senior internal auditor","senior internal auditor", 3, ["rogue", "product"]),
        ("calibrating the room",    "calibrating",      3, ["fair", "room", "operator"]),
    ]
))

# ── Category 8: Timeline ────────────────────────────────────────────
print("Category 8: timeline...")
doc_lines.append(build_block_section(
    "CATEGORY 8 — TIMELINE AND MILESTONES",
    [
        ("DDL methodology formalization", "methodology",     4, ["early 2026", "formalization", "DDL"]),
        ("DexCell genesis May 2025",      "DexCell",         4, ["May 2025", "genesis", "seat 1010"]),
        ("Nov 2023 first AI",             "November 2023",   3, ["AI", "first", "GPT"]),
        ("CottageHumble date",            "February 27",     3, ["CottageHumble", "r/excel", "Graph Holds"]),
        ("March 9 UMB start",             "March 9",         3, ["UMB", "start", "Commission Analyst"]),
        ("Governor lift Mar 14",          "governor lift",   2, ["March 14", "billable"]),
        ("MindFrame",                     "MindFrame",       3, ["September 2025", "MindFrame_All"]),
        ("WorkBench sprint",              "CR-WB-",          4, ["this weekend", "sprint", "2026-04-12"]),
        ("Memoir Jan 2026",               "January 2026",    3, ["memoir", "Substack"]),
    ]
))

# ── write ───────────────────────────────────────────────────────────
doc_lines.append("")
doc_lines.append("=" * 70)
doc_lines.append("END OF EXTRACTION")
doc_lines.append("=" * 70)
doc_lines.append("Dropdown Logistics — Chaos → Structured → Automated")
doc_lines.append(
    "Dave Kitchens Source Extraction | 2026-04-13 | "
    "Authored by Dex Jr. (Seat 1010)"
)
doc_lines.append("=" * 70)

output = "\n".join(doc_lines)

os.makedirs(INGEST, exist_ok=True)
with open(OUT_FILE, "w", encoding="utf-8", newline="\n") as f:
    f.write(output)

print(f"\nWrote {OUT_FILE}")
print(f"  chars={len(output):,}  lines={output.count(chr(10)):,}")
