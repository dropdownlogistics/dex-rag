#!/usr/bin/env python3
"""
dex_query_gate.py -- decide what KIND of thing was asked, before retrieving.

THE DEFECT THIS EXISTS FOR
--------------------------
Measured against dex_canon_v2 on 2026-08-05:

    "Hello"                                          0.564   PASSES the gate
    "What is the Platinum Bounce recovery protocol?"  0.630   REFUSED

The live refusal threshold is MAX_DISTANCE = 0.62, so a greeting retrieves
BETTER than a real question about the corpus's own content. On a phone endpoint
"Hello" is the most likely first message, and today it hands the model five
arbitrary canon chunks and asks it to answer from them.

WHY THIS IS NOT A THRESHOLD PROBLEM
-----------------------------------
It was tested. Four candidate signals, over short real questions vs greetings:

    top1     real[0.333..0.985]  deg[0.564..0.818]   OVERLAPS
    spread   real[0.036..0.169]  deg[0.030..0.094]   OVERLAPS
    ratio    real[0.751..0.964]  deg[0.870..0.957]   OVERLAPS
    words    real[1..7]          deg[0..2]           OVERLAPS

None separate. The spread hypothesis -- that a degenerate query sits near the
centroid so everything is equidistant -- fails because low spread ALSO means
"every hit is a great match": `MindFrame` scores 0.417 top-1 with 0.037 spread
because the top ten are all chunks of one document.

Low-information input has no meaningful distance to measure. Measuring it
harder cannot help.

SO: ENUMERATE, DO NOT THRESHOLD
-------------------------------
Greetings and acknowledgements are a small, closed, enumerable class. That is a
lookup, not a statistics problem, and its failure mode is bounded: an
unrecognised greeting degrades to today's behaviour, which is the current
baseline, not worse. A misfit threshold silently refuses real questions
forever, and nobody finds out.

A mechanism with a known failure mode beats a heuristic with an unknown one.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It does not decide whether the corpus can ANSWER a question -- that is
retrieval's job and distance does it well (on-domain vs off-domain separates
cleanly, gap +0.083). This only separates "not a question" from "a question".

`"What is AEN"` is a REAL question that the corpus cannot answer. It must reach
retrieval and be refused for no-evidence. Refusing it here, as noise, would be
the wrong refusal for the right outcome -- and would hide a genuine coverage
gap behind a conversational reply.

  python dex_query_gate.py "Hello"        classify one query
  python dex_query_gate.py --self-test    run the built-in cases
"""

from __future__ import annotations

import re
import sys
import unicodedata

# ---------------------------------------------------------------------------
# The three outcomes. Only SUBSTANTIVE touches the corpus.
# ---------------------------------------------------------------------------
CONVERSATIONAL = "conversational"   # a greeting or acknowledgement; no retrieval
EMPTY = "empty"                     # nothing to act on at all
SUBSTANTIVE = "substantive"         # send it to retrieval

# Exact-match phrases, normalized. ENUMERATED ON PURPOSE -- see the docstring.
#
# Every entry must be a complete utterance that cannot be the whole of a real
# question. "what" is absent because "what is AEN" is real; "hey" is present
# because no corpus question is exactly "hey".
#
# The bar for adding one: could this phrase, ALONE, ever be a question someone
# wants an answer to from this corpus? If yes, it does not belong here.
GREETINGS = frozenset({
    "hello", "hi", "hey", "yo", "sup", "hiya", "howdy",
    "hello there", "hi there", "hey there", "you there", "anyone there",
    "good morning", "good afternoon", "good evening", "morning", "evening",
    "gm", "hey dex", "hi dex", "hello dex", "dex",
})

ACKNOWLEDGEMENTS = frozenset({
    "thanks", "thank you", "thanks!", "ty", "thx", "cheers", "nice", "great",
    "ok", "okay", "k", "kk", "cool", "got it", "gotcha", "understood",
    "yes", "no", "yep", "yup", "nope", "sure", "right", "correct",
    "perfect", "awesome", "excellent", "good", "fine", "sounds good",
    "np", "no problem", "you bet", "will do", "roger", "copy that",
    "bye", "goodbye", "later", "see ya", "night", "goodnight",
})

# Test/probe strings. Not greetings, but not corpus questions either.
PROBES = frozenset({"test", "testing", "ping", "hello world", "asdf", "..."})

CONVERSATIONAL_SET = GREETINGS | ACKNOWLEDGEMENTS | PROBES

# Punctuation-only or symbol-only input.
_MEANINGFUL = re.compile(r"[a-z0-9]", re.I)


def normalize(q: str) -> str:
    """Fold to a comparable form. Deliberately conservative: it strips
    surrounding whitespace, trailing punctuation and case, and nothing else.
    Aggressive normalization would start collapsing real questions together."""
    s = unicodedata.normalize("NFKC", q or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = s.rstrip("!?.,;: ")
    return s


def classify(q: str) -> tuple[str, str]:
    """Return (outcome, why). `why` is always populated -- a classification
    nobody can explain is the thing this whole repo keeps removing."""
    raw = q or ""
    s = normalize(raw)

    if not s or not _MEANINGFUL.search(s):
        return EMPTY, "no alphanumeric content"

    if s in CONVERSATIONAL_SET:
        return CONVERSATIONAL, f"exact match on the enumerated set: {s!r}"

    # A greeting with a real question attached is a real question.
    # "hey what is the Platinum Bounce" must reach retrieval.
    for g in sorted(GREETINGS, key=len, reverse=True):
        for sep in (" ", ", ", " - ", " — "):
            prefix = g + sep
            if s.startswith(prefix):
                rest = s[len(prefix):].strip()
                if rest and _MEANINGFUL.search(rest) and rest not in CONVERSATIONAL_SET:
                    return SUBSTANTIVE, f"greeting prefix {g!r} stripped; remainder is a query"
                return CONVERSATIONAL, f"greeting {g!r} with no query attached"

    return SUBSTANTIVE, "not in the enumerated conversational set"


# ---------------------------------------------------------------------------
def _self_test() -> int:
    """Both directions. The second list is the one that matters: these are
    SHORT REAL questions, and a length- or threshold-based gate refuses them.
    """
    must_be_conversational = [
        "Hello", "hi", "hey", "  Hey!  ", "thanks", "Thank you", "ok", "OK.",
        "yes", "no", "good morning", "you there", "sup", "hello?", "test",
        "cool", "got it", "perfect", "night", "?", "!!!", "", "   ",
        "Hey there,", "hi dex",
    ]
    must_be_substantive = [
        # Short real questions -- the false-refusal risk.
        "What is AEN", "What is the council", "council review topics",
        "MindFrame", "CanonPress", "Platinum Bounce", "AsBuiltGovernance",
        "leverage points", "what is the DDL methodology", "AEN?",
        # Greeting + real question must survive.
        "hey what is the Platinum Bounce", "Hi, what is AsBuiltGovernance?",
        "good morning - what did the council decide about calibration",
        # Ordinary questions.
        "What is the Platinum Bounce recovery protocol?",
        "Trace the evolution of MindFrame from v1.0 to v4.0",
        # Contains a greeting word but is not one.
        "who said hello in the council review",
        "what does the DexOS boot ritual say about greetings",
    ]

    fails = []
    for q in must_be_conversational:
        got, why = classify(q)
        if got == SUBSTANTIVE:
            fails.append(f"  should NOT reach retrieval: {q!r} -> {got} ({why})")
    for q in must_be_substantive:
        got, why = classify(q)
        if got != SUBSTANTIVE:
            fails.append(f"  MUST reach retrieval: {q!r} -> {got} ({why})")

    # Control: the harness must be able to detect a failure at all.
    planted_ok = classify("Hello")[0] != SUBSTANTIVE and classify("What is AEN")[0] == SUBSTANTIVE

    n = len(must_be_conversational) + len(must_be_substantive)
    print(f"\nquery gate self-test — {n} cases, both directions")
    print("=" * 62)
    if fails:
        print(f"  {len(fails)} FAILED")
        for f in fails:
            print(f)
    else:
        print(f"  all {n} passed")
    print(f"  control (harness can tell the two apart): "
          f"{'ok' if planted_ok else 'BROKEN — this suite proves nothing'}")
    print("=" * 62 + "\n")
    return 1 if (fails or not planted_ok) else 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        return _self_test()
    if len(sys.argv) < 2:
        print(__doc__.strip().split("\n")[0])
        print('\nusage: python dex_query_gate.py "your query"   |   --self-test')
        return 2
    q = " ".join(sys.argv[1:])
    outcome, why = classify(q)
    print(f"\n  query    {q!r}")
    print(f"  outcome  {outcome.upper()}")
    print(f"  because  {why}")
    print(f"  {'retrieval is SKIPPED' if outcome != SUBSTANTIVE else 'goes to retrieval'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
