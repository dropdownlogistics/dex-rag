"""
waypoint.py -- Waypoint, phase 1: a finder over the private store, for DDL's own seats.

Architecture: ddl-org reborn-cowork/work/DDL-SEARCH/ARCHITECTURE_v0.1.md with the v0.2 and v0.3 changes.
GO to build phase 1: Reed Vane (DDL-2004), 2026-10-12, on the Operator's standing "build our own" and his
ruling the same day that seats are his extension and the default for his own material is yes.

It returns PLACES, not answers: for each hit the root, the path, which chunk of the file, a short snippet
and its score. The seat opens the file itself. No model is in the path.

What phase 1 does and does not do, stated so nobody reads more into a result than is there:
  - Ranking is meaning only (the store's shortlist-then-exact cosine). There is no word index yet.
  - Filters `root:` `ext:` `in:` and their `-` forms are applied to the ranked candidates, so a narrow
    filter can leave fewer than k hits; the envelope says how many candidates were looked at.
  - Quoted phrases, `-word` exclusions and bare DDL identifiers are PARSED AND REPORTED BUT NOT APPLIED.
    Exact matching is phase 2 and waits for the frozen baseline (Wren Keeler, DDL-3010:20261012T173136Z-a0c6):
    a benchmark filed after hybrid search cannot say what hybrid search bought.
  - Chunks in the v2 store carry no line numbers, so a hit names the chunk (3 of 12), not a line span.

What is never returned: the text of a possible live credential (masked in the snippet, counted), anything
a seat's `deny` list covers (a clean rater's exclusions), and a whole file. Telemetry is numbers only: no
query text and no snippet text is ever written.

Everything here is pure: `ask` is handed in, so the tests use a made-up store.

Silas Reeve / DDL-3004 / 2026-10-12
"""
import fnmatch
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import dex_photo_secret_scan as secrets     # the photo scanner's prefix rules, used as one more source of spans
except Exception:                               # noqa: BLE001 -- a missing scanner withholds every snippet (below)
    secrets = None

VERSION = "waypoint/0.3"
DEFAULT_K, MAX_K = 8, 25
OVERFETCH, MAX_CANDIDATES = 8, 200          # candidates looked at = min(k * OVERFETCH, MAX_CANDIDATES) when a filter is set
SNIPPET_CHARS = 400
MASK = "[withheld: possible credential]"
CREDENTIAL_RULES = ("R1", "R2")             # the two rules that mark a credential's own text; R3 fires on any hash
RULED_DEPTH = 4                             # Wren Keeler's shortlist ruling (256 wide, 5000 kept) was measured at this depth

FILTERS = ("root", "ext", "in")
LATER = ("repo", "kind", "from", "to", "after", "before", "wt", "is")       # in the design, not in phase 1
TOKEN = re.compile(r'(-?)(?:(\w+):)?(?:"([^"]*)"|(\S+))')
IDENT = re.compile(r"^(?:[A-Z][A-Z0-9]{1,9}-(?:[A-Z0-9]+-)*\d+[A-Z]?|[0-9a-f]{7,40})$")
HEADER = re.compile(r"\Afile: .*\npath: .*\n\n")

# ---- Text credential masking (v0.2) ---------------------------------------------------------------------
# Amos Sayer's pre-install audit (surface-audit/work/WAYPOINT-AUDIT/WAYPOINT_PHASE1_AUDIT_v0.1.md, section 1):
# the photo scanner masked the KEYWORD and left the value, and knew only a short prefix list. These rules mask
# the VALUE. They over-mask on purpose: a snippet that hides a harmless "key: value" costs a seat one file open;
# a snippet that shows a live credential cannot be taken back.
# v0.3 (Amos's second pass, WAYPOINT_SECOND_PASS_v0.2.md, classes A, B, C):
#  A. a credential word counts ANYWHERE inside a name (accessToken, PGPASSWORD, AccountKey, secretkey, passphrase);
#     short words that are also ordinary prose (key, pin, sig, pass, auth) still need to stand alone as a name part,
#     so "monkey" and "author" are left alone. A capital-K "Key" ending a camelCase name counts (privateKey).
#  B. the value is whatever follows: a quoted value to its closing quote, an unquoted one to the end of the token
#     (so ; , and ' inside it do not cut it short); a scheme word (Basic, Bearer, ...) is skipped to reach the value;
#     ":" "=" "is" and a folded-YAML next line all lead into a value ("=>" works as "=" then a marker); `--password X` is its own rule.
#  C. the prefix list grew by seven families. It is a floor: a list is always behind.
_SUB = (r"token|secret|passw|pwd|passphrase|passcode|accountkey|apikey|privatekey|credential|authoriz|authent")
_WORD = r"api[_-]key|key|pin|sig|signature|pass|auth"
_NAME = (r"(?<![A-Za-z0-9_.\-])[A-Za-z0-9_.\-]*?(?:"
         r"(?:" + _SUB + r")[A-Za-z0-9_.\-]*"
         r"|(?<![A-Za-z0-9])(?:" + _WORD + r")(?![A-Za-z0-9])(?:[_.\-][A-Za-z0-9_.\-]*)?"
         r"|(?-i:(?<=[a-z0-9])Key)(?![A-Za-z])[A-Za-z0-9_.\-]*)")
_VALUE = (r"""(?:(?:basic|bearer|token|negotiate|ntlm|bot)[ \t]+(?=\S))?"""
          r"""(?:"((?:\\.|[^"\\\r\n])+)"|'((?:\\.|[^'\\\r\n])+)'|`([^`\r\n]+)`"""
          r"""|[\"'`]([^\r\n]{1,80})|([^\s"'`]\S*))""")
TEXT_RULES = (
    # a name, an optional closing quote, then ":" "=" or "is", an optional folded-YAML marker, the value
    # (which may be on the next line)
    ("assignment", re.compile(_NAME + r"""["'`]?(?:[ \t]*[:=]|[ \t]+(?:is|was)\b)[ \t]*(?:[>|][+-]?[ \t]*)?"""
                              r"""(?:\r?\n[ \t]*)?""" + _VALUE, re.I)),
    # --password X, --api-key X (a long option with its value after a space)
    ("long_option", re.compile(r"(?<![\w-])--[\w-]*?(?:" + _SUB + r"|api-key|pass|auth(?!or))[\w-]*[ \t]+(?!-)" + _VALUE, re.I)),
    # curl -u user:password
    ("basic_flag", re.compile(r"(?<!\S)-u[ \t]+[^\s:]+:(\S+)")),
    ("bearer", re.compile(r"(?i)\bbearer[ \t]+([A-Za-z0-9\-._~+/]+=*)")),
    ("url_userinfo", re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@]+:([^/\s@]+)@")),
    ("pem", re.compile(r"(-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z))", re.S)),
    ("jwt", re.compile(r"\b(eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,})")),
    ("prefix", re.compile(r"\b((?:AKIA|ASIA)[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,}|(?:sk|rk|pk)_(?:live|test)_[0-9A-Za-z]{10,}"
                          r"|xox[abposr]-[0-9A-Za-z-]{10,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_\w{20,}|glpat-[\w-]{20,}"
                          r"|sk-[A-Za-z0-9_-]{20,}"
                          r"|npm_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|SG\.[\w-]{16,}\.[\w-]{16,}|pypi-[A-Za-z0-9_-]{20,}"
                          r"|shp(?:at|ss|ca|pa)_[A-Za-z0-9]{16,}|ya29\.[\w-]{20,}|whsec_[A-Za-z0-9]{16,}"
                          r"|tskey-[\w-]{20,}|dckr_pat_[\w-]{16,}|glsa_[A-Za-z0-9_]{20,}|dop_v1_[0-9a-f]{20,}|xapp-[\w-]{20,})")),
)
# a credential word followed by a separator and a long mixed tail, inside ONE path segment (notes/accessToken_Zq81....md)
PATH_RULE = re.compile(r"(?i)(?:" + _SUB + r")[A-Za-z0-9]*[_\-.=:]((?=[A-Za-z0-9+%_\-]*\d)(?=[A-Za-z0-9+%_\-]*[A-Za-z])[A-Za-z0-9+%_\-]{16,})")


def credential_spans(text):
    """Every (start, end) to mask in `text`, from the text rules and the photo scanner's two credential rules.
    Raises if the photo scanner is missing, so callers fail closed."""
    if secrets is None:
        raise RuntimeError("the credential scanner is missing")
    spans = []
    for _, rx in TEXT_RULES:
        for m in rx.finditer(text):
            g = next((i for i in range(1, rx.groups + 1) if m.group(i) is not None), None)
            if g:
                spans.append((m.start(g), m.end(g)))
    spans += [(a, b) for rule, a, b in secrets.spots(text) if rule in CREDENTIAL_RULES]
    return sorted(spans)


def path_spans(text):
    """The extra spans that only make sense in a single path segment."""
    return [(m.start(1), m.end(1)) for m in PATH_RULE.finditer(text)]


def mask(text, path=False):
    """(text with every credential span replaced by MASK, how many spans were masked). Overlaps merge.
    `path=True` adds the file-name rule; the caller masks one path segment at a time."""
    out, at, masked = [], 0, 0
    spans = credential_spans(text)
    if path:
        spans = sorted(spans + path_spans(text))
    for a, b in spans:
        if b <= at:
            continue                            # inside a span already masked
        if a < at:
            at = b                              # overlaps the last mask: widen it, no second marker
            continue
        out.append(text[at:a])
        out.append(MASK)
        masked += 1
        at = b
    out.append(text[at:])
    return "".join(out), masked


# ---- Left out for every seat, at query time (audit section 2) --------------------------------------------
# Hidden photos are kept out by the build; this is the second lock, so a store rebuilt with photos in it still
# serves none of them. Nothing here is per seat and nothing here can be undone by a filter.
LEFT_OUT_ROOTS = ("photos", "photo-album", "album", "icloud-photos", "dcim", "camera roll", "camera-roll", "cameraroll",
                  "pictures", "my pictures")
LEFT_OUT_EXTS = ("jpg", "jpeg", "jpe", "jfif", "png", "heic", "heif", "heics", "hif", "avif", "gif", "webp", "tif", "tiff",
                 "bmp", "dng", "raw", "cr2", "cr3", "nef", "arw", "orf", "rw2", "raf", "mov", "mp4", "m4v", "avi", "mkv",
                 "wmv", "webm", "3gp")
LEFT_OUT_DIRS = ("dcim",)                       # a camera folder anywhere in a path (a phone's DCIM/100APPLE/...)


def left_out(chunk):
    root = str(chunk.get("source_root", "")).lower()
    path = str(chunk.get("rel_path", "")).replace("\\", "/").lower()
    name = path.rsplit("/", 1)[-1]
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    return root in LEFT_OUT_ROOTS or ext in LEFT_OUT_EXTS or any(d in LEFT_OUT_DIRS for d in path.split("/")[:-1])


def parse(query):
    """A query split into the parts the design names. Nothing is searched here."""
    out = {"text": [], "filters": {f: [] for f in FILTERS}, "exclude_filters": {f: [] for f in FILTERS},
           "exact": [], "exclude": [], "not_in_phase_1": [], "unknown_operators": []}
    for neg, key, quoted, bare in TOKEN.findall(query or ""):
        value = quoted if quoted or not bare else bare
        if not value:
            continue
        key = key.lower()
        if key in FILTERS:
            v = value.lower().lstrip(".") if key == "ext" else value.replace("\\", "/").lower() if key == "in" else value.lower()
            out["exclude_filters" if neg else "filters"][key].append(v)
        elif key in LATER:
            out["not_in_phase_1"].append(f"{'-' if neg else ''}{key}:{value}")
        elif key:
            out["unknown_operators"].append(f"{key}:{value}")
            out["text"].append(f"{key}:{value}")
        elif neg:
            out["exclude"].append(value)
        elif quoted:
            out["exact"].append(value)
            out["text"].append(value)
        else:
            if IDENT.match(value):
                out["exact"].append(value)
            out["text"].append(value)
    out["meaning"] = " ".join(out["text"])
    del out["text"]
    return out


def _passes(chunk, parsed):
    root = str(chunk.get("source_root", "")).lower()
    path = str(chunk.get("rel_path", "")).replace("\\", "/").lower()
    ext = path.rsplit(".", 1)[-1] if "." in path.rsplit("/", 1)[-1] else ""
    f, x = parsed["filters"], parsed["exclude_filters"]
    if f["root"] and root not in f["root"]:
        return False
    if f["ext"] and ext not in f["ext"]:
        return False
    if f["in"] and not any(p in path for p in f["in"]):
        return False
    return not (root in x["root"] or ext in x["ext"] or any(p in path for p in x["in"]))


def denied(chunk, deny):
    """True when a seat's deny list covers this chunk. A rule is "root" or "root:glob" over the path."""
    root = str(chunk.get("source_root", "")).lower()
    path = str(chunk.get("rel_path", "")).replace("\\", "/").lower()
    for rule in deny or ():
        r, _, glob = str(rule).lower().partition(":")
        if r in (root, "*") and (not glob or fnmatch.fnmatchcase(path, glob)):
            return True
    return False


def snippet_of(text):
    """(snippet, how many possible credentials were masked). The embed header is dropped first.
    Masking runs on the whole chunk before it is cut, so a secret cannot straddle the cut. If masking
    fails for any reason the snippet is None: no text is better than unchecked text."""
    body = HEADER.sub("", text or "", count=1)
    try:
        masked_body, masked = mask(body)
    except Exception:                           # noqa: BLE001 -- fail closed, counted by the caller
        return None, 0
    s = " ".join(masked_body.split())
    return (s[:SNIPPET_CHARS] + (" ..." if len(s) > SNIPPET_CHARS else "")), masked


def path_of(path):
    """(the path with any credential-shaped part masked, how many). None if masking fails."""
    try:
        out, total = [], 0
        for seg in re.split(r"([\\/])", str(path or "")):     # one segment at a time, so a value cannot run across a "/"
            if seg in ("/", "\\"):
                out.append(seg)
                continue
            text, n = mask(seg, path=True)
            out.append(text)
            total += n
        return "".join(out), total
    except Exception:                           # noqa: BLE001
        return None, 0


def search(query, k, ask, deny=(), seat=None, log_path=None, now=None):
    """The search tool. `ask(text, n)` -> (chunks best first, each with "score"; the store's telemetry row).
    Returns the envelope. Raises ValueError for a query with nothing to search by."""
    t0 = time.perf_counter()
    parsed = parse(query)
    if not parsed["meaning"].strip():
        raise ValueError("nothing to search by: give some words (filters alone do not rank anything in phase 1)")
    try:
        k = int(k)
    except (TypeError, ValueError):
        k = DEFAULT_K
    k = max(1, min(k, MAX_K))
    narrowing = any(parsed["filters"].values()) or any(parsed["exclude_filters"].values()) or bool(deny)
    looked = min(k * OVERFETCH, MAX_CANDIDATES) if narrowing else k
    chunks, rec = ask(parsed["meaning"], looked)
    hits, removed, masked, withheld = [], {"filters": 0, "denied_for_seat": 0, "left_out_for_everyone": 0}, 0, 0
    for rank, c in enumerate(chunks, 1):
        if left_out(c):
            removed["left_out_for_everyone"] += 1
            continue
        if denied(c, deny):
            removed["denied_for_seat"] += 1
            continue
        if not _passes(c, parsed):
            removed["filters"] += 1
            continue
        if len(hits) == k:
            continue
        snip, m = snippet_of(c.get("text", ""))
        path, pm = path_of(c.get("rel_path"))
        if snip is None or path is None:
            withheld += 1
            continue
        masked += m + pm
        hits.append({"id": c.get("id"), "root": c.get("source_root"), "path": path,
                     "chunk": [int(c.get("chunk_index", 0)) + 1, c.get("total_chunks")], "lines": None,
                     "snippet": snip, "score": {"meaning": round(float(c["score"]), 4), "words": None},
                     "rank_before_filters": rank})
    not_applied = ([f'"{e}" (exact)' for e in parsed["exact"]] + [f"-{e}" for e in parsed["exclude"]] + parsed["not_in_phase_1"])
    limits = ["ranked by meaning only; there is no word index in phase 1",
              "a hit names its chunk of the file, not a line span",
              "the snippet is the start of the chunk, not the part that matched"]
    if k > RULED_DEPTH:
        limits.append(f"the shortlist setting was measured for the top {RULED_DEPTH}; results below rank {RULED_DEPTH} can be missing a closer match")
    if narrowing and len(hits) < k:
        limits.append(f"filters were applied to the best {looked} candidates and left {len(hits)}; a narrower match may exist further down")
    if withheld:
        limits.append(f"{withheld} hit(s) withheld because the credential check could not run on them")
    env = {"version": VERSION, "query": parsed, "not_applied": not_applied, "hits": hits,
           "settings": {"k": k, "candidates_looked_at": looked, "rows": rec.get("rows"), "prefix": rec.get("prefix"),
                        "shortlist": rec.get("shortlist"), "ranking": "meaning"},
           "removed": removed, "credentials_masked": masked, "withheld_unchecked": withheld, "limits": limits,
           "ms": round((time.perf_counter() - t0) * 1000, 1)}
    if log_path:
        roots = {}
        for h in hits:
            roots[h["root"]] = roots.get(h["root"], 0) + 1
        row = {"at": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"), "tool": "search", "seat": seat,
               "k": k, "looked": looked, "hits": len(hits), "hits_by_root": roots, "removed": removed,
               "masked": masked, "withheld": withheld, "filters_used": sorted(f for f in FILTERS if parsed["filters"][f] or parsed["exclude_filters"][f]),
               "not_applied": len(not_applied), "rows": rec.get("rows"), "prefix": rec.get("prefix"),
               "shortlist": rec.get("shortlist"), "ms": env["ms"]}
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(row) + "\n")
    return env


def explain(query):
    """How a query would be read, and what phase 1 would and would not do with each part. Runs no search."""
    p = parse(query)
    return {"version": VERSION, "query": p,
            "would_rank_by": "meaning" if p["meaning"].strip() else None,
            "would_filter_by": {k: v for k, v in p["filters"].items() if v},
            "would_exclude": {k: v for k, v in p["exclude_filters"].items() if v},
            "parsed_but_not_applied_in_phase_1": ([f'"{e}" (exact)' for e in p["exact"]] + [f"-{e}" for e in p["exclude"]] + p["not_in_phase_1"]),
            "operators": {"work now": [f"{f}:" for f in FILTERS], "in the design, not built": [f"{f}:" for f in LATER]}}


def sources(status, build):
    """What is indexed and how fresh. `status` is the resident store's status(); `build` is build.json."""
    by_root = build.get("by_root") or {}
    return {"version": VERSION, "state": status.get("state"), "rows": status.get("rows"),
            "prefix": status.get("prefix"), "shortlist": status.get("shortlist"),
            "built": {"started_utc": build.get("started_utc"), "finished_utc": build.get("finished_utc")},
            "roots": [{"root": r, "files": v.get("files"), "chunks": v.get("chunks")} for r, v in sorted(by_root.items())],
            "not_indexed_yet": ["ddl-org and the project repos (phase 3)", "uncommitted changes in a worktree (phase 4)",
                                "anything added since the build finished"],
            "left_out_on_purpose": ["the text of a possible live credential (masked in snippets)", "hidden photos"],
            "ranking": "meaning only (phase 1)"}
