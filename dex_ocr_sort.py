"""
dex_ocr_sort.py -- a first, coarse sort of the image pool by the words Tesseract found.

Operator, 2026-10-10: "do a pool of all the images and then sort them at a high level what's
obvious and then pare down from there". This is the "what's obvious" layer. It reads what
dex_ocr_batch.py wrote and writes a LIST. It never opens, moves, renames or deletes an image.

How an image gets a bin: each bin has signals (words or phrases). An image's score for a bin is
the number of DISTINCT signals found in its text. The highest score wins if it is at least
MIN_HITS; a tie goes to the bin listed first; anything else is "unsorted". Every bin's score is
kept in the row, so a wrong call can be seen and the rules changed. Rules are data (BINS below);
they were drawn from the word counts of the pool, not from reading images.

Writes, under the OCR folder:
    bins.jsonl      one row per distinct image: sha256, pile, bin, scores, phone, words, confidence
    SORT-REPORT.md  counts per pile and bin, by source folder, and a few example paths per bin

    python dex_ocr_sort.py --ocr C:\\Users\\dexjr\\dex-data\\ocr
"""
import argparse
import collections
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

MIN_HITS = 2
EXAMPLES = 8
FOLDER_DEPTH = 4
FOLDERS_SHOWN = 30
PILES = ("text", "low-confidence", "no-text", "not-opened", "set-aside")
# Set aside by the Operator's word (2026-10-10: "definitely leave out album art"). An image is set
# aside only if EVERY copy of it sits under one of these folders; a copy anywhere else keeps it in.
SET_ASIDE = [("album-art", "onedrive/Music/")]

# Order matters only for ties. A signal is matched on word boundaries, case-insensitive.
BINS = [
    ("ai-usage-meter", ["usage limits", "context window", "autocompact buffer", "plan usage", "weekly limit",
                        "limit resets", "hour limit", "memory files", "mcp tools", "custom agents", "free space"]),
    ("ai-chat", ["chatgpt", "claude", "dexhub", "mindframe", "ask anything", "reply to claude", "write a message",
                 "message dexhub", "gemini", "copilot", "grok", "perplexity", "sonnet", "opus", "gpt", "dex jr",
                 "prompt", "regenerate", "thinking"]),
    ("code-terminal", ["traceback", "powershell", "ps c:", "users dkitc", "users dexjr", "def", "import", "git",
                       "npm", "pip install", "python", "localhost", "stderr", "exit code", "commit", "json",
                       "syntaxerror", "function", "const", "return"]),
    ("spreadsheet", ["excel", "pivot", "vlookup", "xlookup", "sumifs", "formula", "worksheet", "workbook", "autosum",
                     "conditional formatting", "power query", "cell", "column", "rows", "pivottable", "sheet1"]),
    ("email", ["inbox", "subject", "unsubscribe", "gmail", "outlook", "reply all", "forwarded message", "cc",
               "sent from my iphone", "attachment", "to me"]),
    ("text-messages", ["imessage", "delivered", "text message", "read receipt", "today", "yesterday", "tapback",
                       "facetime", "voicemail", "missed call"]),
    ("social", ["linkedin", "reddit", "twitter", "facebook", "instagram", "tiktok", "followers", "following", "repost",
                "retweet", "upvote", "impressions", "connections", "invite friend", "like comment", "subscribers"]),
    ("money", ["subtotal", "total due", "receipt", "invoice", "payment", "balance", "order number", "card ending",
               "transaction", "refund", "tax", "statement", "deposit", "amount", "checkout", "visa", "mastercard"]),
    ("game", ["item power", "quest", "inventory", "xp", "loot", "damage", "armor", "respawn", "legendary", "dungeon"]),
    ("ddl-governance", ["governance", "council", "dropdown logistics", "audit", "standard", "canon", "ratified",
                        "seat", "adr", "charter", "protocol", "v1.0", "operator", "ddl"]),
    ("document", ["page", "chapter", "section", "abstract", "introduction", "references", "figure", "table of contents",
                  "copyright", "published", "appendix"]),
]
PHONE = ["t-mobile", "verizon", "at&t", "lte", "5g", "wi-fi"]


def _compile(signal):
    return re.compile(r"(?<![a-z0-9])" + re.escape(signal) + r"(?![a-z0-9])")


_RULES = [(name, [(s, _compile(s)) for s in signals]) for name, signals in BINS]
_PHONE = [_compile(s) for s in PHONE]


def sort_text(text):
    """(bin, scores, phone) for one image's text. Pure."""
    t = " ".join(text.lower().split())
    scores = {}
    for name, rules in _RULES:
        n = sum(1 for _, rx in rules if rx.search(t))
        if n:
            scores[name] = n
    best, top = "unsorted", 0
    for name, _ in BINS:                      # listed order breaks ties
        if scores.get(name, 0) > top:
            best, top = name, scores[name]
    if top < MIN_HITS:
        best = "unsorted"
    return best, scores, any(rx.search(t) for rx in _PHONE)


def set_aside(paths):
    """The set-aside name if every path of the image is under one set-aside folder, else None."""
    for name, prefix in SET_ASIDE:
        if paths and all(p.startswith(prefix) for p in paths):
            return name
    return None


def text_key(text):
    """Two images with the same key show the same words in the same order (case, spacing and
    punctuation ignored): a re-saved, resized or re-exported copy of one screenshot."""
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def pile_of(cls):
    """The first-layer pile, from what the OCR pass measured."""
    return {"text": "text", "low": "low-confidence", "none": "no-text"}.get(cls, "not-opened")


def latest(results_path):
    rows = {}
    for line in Path(results_path).open(encoding="utf-8"):
        r = json.loads(line)
        rows[r["sha256"]] = r
    return rows


def run(ocr):
    ocr = Path(ocr)
    res = latest(ocr / "results.jsonl")
    first_path, all_paths = {}, collections.defaultdict(list)
    for line in (ocr / "paths.jsonl").open(encoding="utf-8"):
        p = json.loads(line)
        if p["sha256"] is None:
            continue
        all_paths[p["sha256"]].append(p["rel_path"])
        first_path.setdefault(p["sha256"], p["rel_path"])
    rows, missing_text, twins = [], 0, {}
    for sha in sorted(res):                     # sorted, so the same image is the "first" twin on every run
        r = res[sha]
        row = {"sha256": sha, "pile": pile_of(r["class"]), "bin": None, "scores": {}, "phone": False,
               "words": r.get("words", 0), "confidence": r.get("confidence", 0.0),
               "copies": len(all_paths.get(sha, [])), "twin_of": None}
        aside = set_aside(all_paths.get(sha, []))
        if aside:
            row["pile"], row["bin"] = "set-aside", aside
        elif r["class"] == "text":
            f = ocr / "text" / sha[:2] / f"{sha}.txt"
            if f.exists():
                text = f.read_text(encoding="utf-8")
                row["bin"], row["scores"], row["phone"] = sort_text(text)
                first = twins.setdefault(text_key(text), sha)
                row["twin_of"] = None if first == sha else first
            else:
                missing_text += 1               # counted and reported, never silently binned
                row["bin"] = "text-file-missing"
        rows.append(row)
    with open(ocr / "bins.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    report(ocr, rows, first_path, missing_text)
    return rows


def report(ocr, rows, first_path, missing_text):
    piles = collections.Counter(r["pile"] for r in rows)
    text = [r for r in rows if r["pile"] == "text"]
    bins = collections.Counter(r["bin"] for r in text)
    L = ["# Image pool: first sort", "",
         f"Made {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')} by dex_ocr_sort.py from the OCR pass. "
         "A list only: no image was opened, moved or changed.", "",
         f"Distinct images: {len(rows):,}", "", "## Piles (from the OCR pass)", "", "| pile | images |", "|---|---:|"]
    for k, v in piles.most_common():
        L.append(f"| {k} | {v:,} |")
    files = sum(r["copies"] for r in rows)
    tw = sum(1 for r in text if r["twin_of"])
    L += ["", "## Duplicates", "",
          f"- Files seen: {files:,}. Distinct images (identical bytes counted once): {len(rows):,}. "
          f"Exact copies: {files - len(rows):,}.",
          f"- Text twins: {tw:,} of the {len(text):,} text images show the same words in the same order as another "
          "image (a re-saved or resized copy). Each is marked `twin_of`; none is removed.",
          "- Not yet looked for: copies that look the same but differ in bytes and carry no text (photos)."]
    L += ["", f"## Bins inside the text pile ({len(text):,})", "",
          "| bin | images | from a phone | median words |", "|---|---:|---:|---:|"]
    for k, v in bins.most_common():
        mine = sorted(r["words"] for r in text if r["bin"] == k)
        L.append(f"| {k} | {v:,} | {sum(1 for r in text if r['bin'] == k and r['phone']):,} | {mine[len(mine) // 2]} |")
    second = collections.Counter()
    for r in text:
        ranked = sorted(r["scores"].items(), key=lambda kv: -kv[1])
        if len(ranked) > 1 and ranked[1][1] >= MIN_HITS:
            second[(r["bin"], ranked[1][0] if ranked[0][0] == r["bin"] else ranked[0][0])] += 1
    L += ["", "## Images that also fit a second bin (the sort is coarse here)", "", "| bin | also fits | images |", "|---|---|---:|"]
    for (a, b), v in second.most_common(15):
        L.append(f"| {a} | {b} | {v:,} |")
    where = collections.defaultdict(collections.Counter)
    for r in rows:
        folder = "/".join(first_path.get(r["sha256"], "?").split("/")[:-1][:FOLDER_DEPTH]) or "(top)"
        where[folder][r["pile"]] += 1
        if r["pile"] == "text":
            where[folder]["unsorted" if r["bin"] == "unsorted" else "binned"] += 1
    L += ["", f"## Where the images came from (first {FOLDER_DEPTH} folder levels, largest {FOLDERS_SHOWN})", "",
          "| folder | images | text | of which unsorted | low-confidence | no-text | not-opened | set-aside |",
          "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for folder, c in sorted(where.items(), key=lambda kv: -sum(kv[1][p] for p in PILES))[:FOLDERS_SHOWN]:
        L.append(f"| `{folder}` | {sum(c[p] for p in PILES):,} | {c['text']:,} | {c['unsorted']:,} | "
                 f"{c['low-confidence']:,} | {c['no-text']:,} | {c['not-opened']:,} | {c['set-aside']:,} |")
    if missing_text:
        L += ["", f"**{missing_text:,} images are classed text but their text file is missing.**"]
    L += ["", "## Example paths per bin (first seen path of each, under D:\\DDL_Corpus\\raw)"]
    for k, _ in bins.most_common():
        L += ["", f"### {k}", ""]
        best = sorted((r for r in text if r["bin"] == k), key=lambda r: (-max(r["scores"].values(), default=0), r["sha256"]))
        for r in best[:EXAMPLES]:
            L.append(f"- `{first_path.get(r['sha256'], '?')}`  ({r['words']} words, scores {r['scores']})")
    (ocr / "SORT-REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ocr", required=True, type=Path)
    a = ap.parse_args()
    rows = run(a.ocr)
    piles = collections.Counter(r["pile"] for r in rows)
    bins = collections.Counter(r["bin"] for r in rows if r["pile"] == "text")
    print(f"distinct images {len(rows):,}")
    for k, v in piles.most_common():
        print(f"  pile {k:<16} {v:>8,}")
    for k, v in bins.most_common():
        print(f"  bin  {k:<16} {v:>8,}")


if __name__ == "__main__":
    sys.exit(main())
