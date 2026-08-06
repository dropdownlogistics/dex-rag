#!/usr/bin/env python3
"""
dex_groundcheck.py -- prove a specific was invented. Not that an answer is true.

THE GAP THIS FILLS
------------------
This repo now reconciles declarations against measurement, accounts for every
source file, measures retrieval separability, and gates the query. All of it
sits UPSTREAM of the answer. Nothing looks at what the model actually said.

So Dex Jr. can retrieve the right chunks and still emit a number that is in
none of them, and every instrument we own reports green.

WHAT IT REFUSES TO CLAIM
------------------------
The obvious design is a second model judging the first. That is the failure
AB-0029 names -- and worse here, because a judge sharing the generator's
training shares its confabulations. Two models agreeing is not evidence.

So this is deterministic, and the cost of that is a narrow claim:

  IT CANNOT verify an answer is correct.
  IT CANNOT verify a paraphrase preserves meaning.
  IT CANNOT catch an omission, or a true statement wrongly attributed.
  IT CANNOT tell a rounded figure from a wrong one.

  IT CAN prove that a specific token in the answer appears NOWHERE in the
  context the model was given. That is not a paraphrase. That is invention,
  and it is the failure that matters most, because a fabricated specific is
  the one a reader will act on.

A PASS here means "no fabricated specifics detected". It does NOT mean the
answer is right, and the report says so on every run rather than leaving the
reader to infer the limit. An instrument that lets its verdict be read wider
than it measured is the defect this repo keeps removing.

WHY SPECIFICS AND NOT PROSE
---------------------------
Prose is not checkable without semantics. Specifics are: a number, a date, a
quoted span, an identifier, a capitalised multi-word name either occurs in the
source text or it does not. Restricting the claim to what a string comparison
can settle is what keeps this honest -- and it happens to cover the class a
reader is most likely to lift and reuse.

  python dex_groundcheck.py --answer a.txt --context c.txt
  python dex_groundcheck.py --self-test

Exit: 0 nothing ungrounded - 1 ungrounded specifics found - 2 bad usage
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata

# ---------------------------------------------------------------------------
# What counts as a checkable specific
# ---------------------------------------------------------------------------
# Each pattern is here because a string comparison can SETTLE it. Anything a
# comparison cannot settle is deliberately absent -- adding it would widen the
# verdict past what the instrument measures.
PATTERNS = [
    # Quoted spans: the model claiming to reproduce source text verbatim.
    ("quote", re.compile(r'"([^"\n]{8,120})"')),
    # Money, with or without separators.
    ("money", re.compile(r'(?<![\w.])(\$\s?\d[\d,]*(?:\.\d+)?)')),
    # Dates in common written forms.
    ("date", re.compile(
        r'\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|'
        r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})\b')),
    # Identifiers: ADR-..., CR-..., STD-..., DDL-3004, commit hashes.
    ("identifier", re.compile(r'\b([A-Z]{2,}[A-Z0-9]*-[A-Z0-9]+(?:-[A-Z0-9]+)*|\b[0-9a-f]{7,40}\b)')),
    # Bare numbers with 3+ digits or decimals -- counts, sizes, percentages.
    ("number", re.compile(r'(?<![\w.\-])(\d[\d,]{2,}(?:\.\d+)?|\d+\.\d+)(?![\w.])')),
]

# Words that look like proper nouns but are sentence-initial or common. A
# capitalised word at the start of a sentence carries no evidence of being a
# name, and flagging it would bury real findings in noise.
_STOPCAPS = {
    "The", "This", "That", "These", "Those", "It", "He", "She", "They", "We",
    "I", "A", "An", "In", "On", "At", "For", "From", "To", "But", "And", "Or",
    "If", "When", "While", "Because", "However", "There", "Here", "What",
    "Which", "Who", "Its", "Their", "Our", "No", "Not", "Yes", "Per", "See",
    "Note", "Source", "Sources", "Context", "Answer", "Based", "According",
}
PROPER = re.compile(r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){1,3})\b')


def _norm(s: str) -> str:
    """Fold for comparison. Conservative: case, whitespace, and unicode form
    only. Stripping punctuation would let '47,213' match '47213' in a way a
    reader would not accept as 'present in the source'."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip().lower()


def extract(answer: str) -> list[dict]:
    """Every checkable specific in the answer, with its kind."""
    out, seen = [], set()

    # Ignore the endpoint's own appended source list -- it is generated from
    # the hit metadata, not by the model, so checking it would grade the
    # plumbing rather than the answer.
    body = answer.split("\n---\nsources:")[0]

    # Claimed character spans. PATTERNS is ordered most-specific first, so a
    # more meaningful kind takes the span before a generic one can.
    #
    # Without this, "$99,999.99" is reported TWICE -- once as `money`, once as
    # `number`, because the bare-number pattern matches inside the money span.
    # One fabrication becoming two findings inflates every count the tool
    # produces, and a reader has no way to tell double-reporting from two
    # distinct inventions. Found by the control assertion disagreeing with the
    # expected count, not by review.
    claimed: list[tuple[int, int]] = []

    def overlaps(a: int, b: int) -> bool:
        return any(a < end and b > start for start, end in claimed)

    for kind, pat in PATTERNS:
        for m in pat.finditer(body):
            if overlaps(m.start(), m.end()):
                continue
            val = m.group(1).strip()
            if not _norm(val):
                continue
            key = (kind, _norm(val))
            if key in seen:
                continue
            seen.add(key)
            claimed.append((m.start(), m.end()))
            out.append({"kind": kind, "value": val})

    for m in PROPER.finditer(body):
        if overlaps(m.start(), m.end()):
            continue
        val = m.group(1).strip()
        if val.split()[0] in _STOPCAPS:
            continue
        key = ("name", _norm(val))
        if key in seen:
            continue
        seen.add(key)
        claimed.append((m.start(), m.end()))
        out.append({"kind": "name", "value": val})

    return out


def check(answer: str, context: str) -> dict:
    """Which specifics in `answer` do not occur in `context`."""
    hay = _norm(context)
    specifics = extract(answer)
    grounded, ungrounded = [], []
    for s in specifics:
        (grounded if _norm(s["value"]) in hay else ungrounded).append(s)
    return {
        "checked": len(specifics),
        "grounded": grounded,
        "ungrounded": ungrounded,
        # The verdict names what it measured. It is not "correct" / "incorrect".
        "verdict": "NO_FABRICATED_SPECIFICS" if not ungrounded else "UNGROUNDED_SPECIFICS",
    }


def render(r: dict) -> str:
    lines = []
    if r["ungrounded"]:
        lines.append(f"⚠ {len(r['ungrounded'])} specific(s) in this answer appear "
                     f"in NONE of the cited sources:")
        for s in r["ungrounded"]:
            lines.append(f"    [{s['kind']}] {s['value']}")
        lines.append("  A specific that is not in the source was not retrieved. "
                     "Treat it as unverified.")
    else:
        lines.append(f"✓ all {r['checked']} checkable specific(s) occur in the cited sources.")
    lines.append("  (Checks fabrication of specifics only — NOT whether the answer "
                 "is correct, complete, or fairly paraphrased.)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
def _self_test() -> int:
    fails = []

    def case(name, answer, context, want_ungrounded):
        got = check(answer, context)
        vals = [s["value"] for s in got["ungrounded"]]
        ok = (len(got["ungrounded"]) > 0) == want_ungrounded
        print(f"  {'PASS' if ok else 'FAIL'}  {name}"
              + (f"   ungrounded={vals}" if not ok else ""))
        if not ok:
            fails.append(name)
        return got

    print("\nFABRICATION MUST BE CAUGHT\n")
    ctx = ("The Platinum Bounce is the F-Code recovery protocol. It was ratified "
           "on 2026-03-09 by Marcus Caldwell. Budget approved was $12,500.00.")
    case("invented money", "The budget was $47,213.55 per the record.", ctx, True)
    case("invented date", "It was ratified on 2026-07-01.", ctx, True)
    case("invented name", "This was authored by Rowan Bennett.", ctx, True)
    case("invented count", "There were 1,847 entries in the log.", ctx, True)
    case("invented identifier", "See ADR-CORPUS-0099 for detail.", ctx, True)

    print("\nGROUNDED ANSWERS MUST PASS\n")
    case("quotes real money", "The approved budget was $12,500.00.", ctx, False)
    case("quotes real date", "Ratified 2026-03-09.", ctx, False)
    case("quotes real name", "Marcus Caldwell ratified it.", ctx, False)
    case("pure paraphrase, no specifics",
         "It is the recovery protocol used when a constraint is breached.", ctx, False)
    case("sentence-initial capital is not a name",
         "The protocol exists. However it is narrow.", ctx, False)

    print("\nBOUNDARIES\n")
    case("appended source list is not graded",
         "Ratified 2026-03-09.\n---\nsources: NOSUCH-9999.txt", ctx, False)
    case("case and spacing differences still count as grounded",
         "ratified on 2026-03-09 by  marcus   caldwell", ctx, False)

    # CONTROL. Without this a scanner that found nothing would score 100%.
    print("\nCONTROL\n")
    planted = check("The figure was $99,999.99 and it was Zebediah Quorn.", ctx)
    ctl = len(planted["ungrounded"]) == 2
    print(f"  {'PASS' if ctl else 'FAIL'}  CONTROL: harness detects planted fabrications "
          f"(found {len(planted['ungrounded'])}/2)")
    if not ctl:
        fails.append("control")

    empty = check("", ctx)
    ok2 = empty["checked"] == 0 and not empty["ungrounded"]
    print(f"  {'PASS' if ok2 else 'FAIL'}  empty answer checks nothing and claims nothing")
    if not ok2:
        fails.append("empty")

    print("\n" + "=" * 66)
    print(f"  {len(fails)} failed" if fails else "  all cases passed")
    print("=" * 66 + "\n")
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="detect fabricated specifics in an answer")
    ap.add_argument("--answer", type=argparse.FileType("r", encoding="utf-8"))
    ap.add_argument("--context", type=argparse.FileType("r", encoding="utf-8"))
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    if a.self_test:
        return _self_test()
    if not a.answer or not a.context:
        print("need --answer and --context, or --self-test", file=sys.stderr)
        return 2

    r = check(a.answer.read(), a.context.read())
    print(render(r))
    return 1 if r["ungrounded"] else 0


if __name__ == "__main__":
    sys.exit(main())
