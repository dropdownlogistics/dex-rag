"""
dex_photo_secret_scan.py -- flag photos that may show a password or key, hide them, and list them for review.

Rules: Lena Marsh / DDL-3005, gaminglaptop-cowork/work/WORK-GRAPH/PHOTO_SECRET_FLAGS_v0.1.md, at the
Operator's word ("you can flag any password looking thing and see if you can have Silas make a place
for you to put them that we can review", 2026-10-10). Runs on Reborn only, where the photos and their
words are.

    R1 label          password, passcode, passphrase, PIN, secret key, recovery code, backup code,
                      security question, one-time code, 2FA, MFA, seed phrase, mnemonic
    R2 key shape      sk-, pk_, ghp_, github_pat_, xox, AKIA..., -----BEGIN, Bearer ..., a JWT (eyJ...)
    R3 random string  16 or more characters mixing upper case, lower case and digits, no spaces
    R4 seed phrase    12 or more lowercase words in a numbered list
    R5 location       an album or old path containing password, credential, keeper, vault, login, 2fa, recovery
    R6 app screen     Keeper, 1Password, Bitwarden, "Sign-in & security", "copy password"
    R7 nothing read   R5 fired and no words were read (never cleared by "no text found")

Strength: strong = R2, R4, R5, R7, or R1 with R3 within NEAR characters of it. Otherwise medium.
Words read with low confidence are scanned too: a dense screen that read poorly can still hold a key.

What it writes, and what it never writes:
    <library>/review.jsonl      one row per flagged photo: sha256, photo_id, rules, strength, flagged_at.
                                Rewritten each run. It holds the FLAGS only. What the Operator decided
                                about each (not a secret / keep hidden / still live) is in app-state.jsonl
                                as `review` rows, written by the album app, so there is one writer per file.
    <library>/app-state.jsonl   with --apply, a `hidden: true` row for each newly flagged photo, so it
                                leaves every album, search, the graveyard and the graph export at once.
    NEVER, anywhere: the matched text, any part of a string, a crop. Not in a file, a log or the output.
A photo he has already decided about, whatever the decision, is not hidden again by a later run.

    python dex_photo_secret_scan.py --library D:\\DDL_Corpus\\library --ocr C:\\Users\\dexjr\\dex-data\\ocr
    python dex_photo_secret_scan.py ... --strength strong --apply
"""
import argparse
import collections
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

NEAR = 120
R1 = re.compile(r"(?i)\b(password|passcode|passphrase|pin|secret key|recovery code|backup code|security question|"
                r"one[- ]time code|2fa|mfa|seed phrase|mnemonic)\b")
R2 = re.compile(r"sk-[A-Za-z0-9_-]{8,}|pk_[A-Za-z0-9_]{8,}|ghp_[A-Za-z0-9]{8,}|github_pat_[A-Za-z0-9_]{4,}|xox[a-z]-[A-Za-z0-9-]{4,}|"
                r"AKIA[A-Z0-9]{8,}|-----BEGIN|Bearer\s+\S|eyJ[A-Za-z0-9_-]{30,}")
R3_RUN = re.compile(r"(?<![A-Za-z0-9_+=-])[A-Za-z0-9_+=-]{16,}(?![A-Za-z0-9_+=-])")
R3_SKIP = re.compile(r"^(P-|ASSET-|DDL-|FND-)")
R4_ITEM = re.compile(r"(?m)^\s*(\d{1,2})[.):]?\s+([a-z]{3,10})\s*$")
R5 = re.compile(r"(?i)password|credential|keeper|vault|login|2fa|recovery")
R6 = re.compile(r"(?i)\b(keeper|1password|bitwarden|copy password)\b|sign-in & security")
STRONG = {"R2", "R4", "R5", "R7"}


def random_runs(text):
    """Start offsets of runs that mix upper case, lower case and digits and are not a DDL id."""
    out = []
    for m in R3_RUN.finditer(text):
        s = m.group(0)
        if R3_SKIP.match(s):
            continue
        if re.search(r"[A-Z]", s) and re.search(r"[a-z]", s) and re.search(r"[0-9]", s):
            out.append(m.start())
    return out


def numbered_words(text):
    """True if a numbered list of lowercase single words runs 1, 2, 3 ... to at least 12."""
    want = 1
    for m in R4_ITEM.finditer(text):
        n = int(m.group(1))
        if n == want:
            want += 1
        elif n == 1:
            want = 2
    return want > 12


def scan(text, places):
    """(rules fired, strength) for one photo. `text` is the words read (may be empty); `places` is its
    albums and old paths. Returns ([], None) when nothing fires. Pure; returns no part of the text."""
    rules = []
    text = text or ""
    r1 = [m.start() for m in R1.finditer(text)]
    r3 = random_runs(text)
    if r1:
        rules.append("R1")
    if R2.search(text):
        rules.append("R2")
    if r3:
        rules.append("R3")
    if numbered_words(text):
        rules.append("R4")
    r5 = any(R5.search(p) for p in places)
    if r5:
        rules.append("R5")
    if R6.search(text):
        rules.append("R6")
    if r5 and not text.strip():
        rules.append("R7")
    if not rules:
        return [], None
    near = any(abs(a - b) <= NEAR for a in r1 for b in r3)
    strong = bool(STRONG & set(rules)) or near
    return rules, "strong" if strong else "medium"


def run(library, ocr, apply=False, strength="all", now=None, log=print):
    library, ocr = Path(library), Path(ocr)
    now = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    index = [json.loads(l) for l in (library / "index.jsonl").open(encoding="utf-8")]
    labels = {r["sha256"]: r for r in map(json.loads, (library / "labels.jsonl").open(encoding="utf-8"))}
    old = {}
    if (library / "review.jsonl").exists():
        for l in (library / "review.jsonl").open(encoding="utf-8"):
            r = json.loads(l)
            old[r["sha256"]] = r
    hidden, decided = set(), set()
    state_file = library / "app-state.jsonl"
    if state_file.exists():
        for l in state_file.open(encoding="utf-8"):
            r = json.loads(l)
            if r.get("hidden") is True:
                hidden.add(r["sha256"])
            elif r.get("hidden") is False:
                hidden.discard(r["sha256"])
            if r.get("review"):
                decided.add(r["sha256"])
    rows, by_rule, by_strength, combos = [], collections.Counter(), collections.Counter(), collections.Counter()
    for r in index:
        sha = r["sha256"]
        lab = labels.get(sha)
        if lab is None:
            continue
        f = ocr / "text" / sha[:2] / f"{sha}.txt"
        text = f.read_text(encoding="utf-8") if f.exists() else ""
        rules, strong = scan(text, list(lab["albums"]) + list(r.get("was_at", [])))
        if not rules:
            continue
        by_strength[strong] += 1
        combos["+".join(rules)] += 1
        for x in rules:
            by_rule[x] += 1
        if strength != "all" and strong != strength:
            continue
        prev = old.get(sha, {})
        rows.append({"sha256": sha, "photo_id": lab["photo_id"], "rules": rules, "strength": strong,
                     "flagged_at": prev.get("flagged_at", now)})
    stats = {"photos_scanned": len(index), "flagged_all_strengths": sum(by_strength.values()),
             "by_strength": dict(by_strength), "by_rule": dict(sorted(by_rule.items())),
             "top_combinations": combos.most_common(8), "in_review_list": len(rows), "newly_hidden": 0}
    if apply:
        # rows kept from an earlier run but outside this run's strength filter stay in the list
        keep = {r["sha256"]: r for r in old.values()}
        for r in rows:
            keep[r["sha256"]] = r
        tmp = library / "review.jsonl.part"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            for r in sorted(keep.values(), key=lambda r: (r["strength"] != "strong", r["photo_id"])):
                f.write(json.dumps(r) + "\n")
        os.replace(tmp, library / "review.jsonl")
        new = [r for r in rows if r["sha256"] not in decided and r["sha256"] not in hidden]
        if new:
            with open(state_file, "a", encoding="utf-8", newline="\n") as f:
                for r in new:
                    f.write(json.dumps({"sha256": r["sha256"], "photo_id": r["photo_id"], "at": now, "hidden": True,
                                        "why": "possible secret (" + ", ".join(r["rules"]) + "); awaiting review"}) + "\n")
        stats["newly_hidden"] = len(new)
        stats["in_review_list"] = len(keep)
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", required=True, type=Path)
    ap.add_argument("--ocr", required=True, type=Path)
    ap.add_argument("--strength", choices=("all", "strong", "medium"), default="all", help="which flags go in the review list")
    ap.add_argument("--apply", action="store_true", help="write review.jsonl and hide the flagged photos; without it, counts only")
    a = ap.parse_args()
    for k, v in run(a.library, a.ocr, a.apply, a.strength).items():
        print(f"  {k:<22} {v}")
    if not a.apply:
        print("  (counted only; nothing written, nothing hidden)")


if __name__ == "__main__":
    sys.exit(main())
