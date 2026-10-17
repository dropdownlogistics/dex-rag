"""Can the Waypoint tests fail? Each mutation breaks one promise in waypoint.py; the tests must then fail.

    python mutations_waypoint.py        # exits 1 if any mutation survives

The file is restored after every mutation, and at the end whatever happens.  Silas Reeve / DDL-3004 / 2026-10-12
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = HERE / "waypoint.py"
MUTATIONS = [
    ("a credential is not masked", "        out.append(MASK)\n", "        out.append(body[a:b])\n"),
    ("a seat's deny list is ignored", "        if denied(c, deny):\n", "        if False and denied(c, deny):\n"),
    ("filters are ignored", "        if not _passes(c, parsed):\n", "        if False:\n"),
    ("the query text is logged", '"tool": "search", "seat": seat,', '"tool": "search", "seat": seat, "q": query,'),
    ("the snippet is not capped", "(s[:SNIPPET_CHARS] + ", "(s + "),
    ("k is not clamped", "    k = max(1, min(k, MAX_K))\n", "    k = max(1, k)\n"),
    ("an empty query is searched", '    if not parsed["meaning"].strip():\n', "    if False:\n"),
    ("exact terms are claimed as applied", "    not_applied = ([f'\"{e}\" (exact)' for e in parsed[\"exact\"]] + ", "    not_applied = ([] + "),
    ("the depth caveat is dropped", "    if k > RULED_DEPTH:\n", "    if False:\n"),
    ("the embed header is shown", '    body = HEADER.sub("", text or "", count=1)\n', '    body = text or ""\n'),
    # v0.3 (Amos's second pass): one mutation per new promise, so each new test is shown able to fail
    ("camelCase Key names are not recognised", r"(?-i:(?<=[a-z0-9])Key)", r"(?-i:(?<=[a-z0-9])Kxy)"),
    ("a credential word inside a name is not recognised", r'_SUB = (r"token|secret|passw|pwd|', r'_SUB = (r"token|secret|zzzz|zzz|'),
    ("a scheme word is not skipped to reach the value", r"(?:(?:basic|bearer|token|negotiate|ntlm|bot)[ \t]+(?=\S))?", ""),
    ("a quoted value is cut at its first space", r'''"((?:\\.|[^"\\\r\n])+)"|''', r'''"([^\s"]+)"|'''),
    ("an unterminated quote is not masked", r"""|[\"'`]([^\r\n]{1,80})""", ""),
    ("--password X is not a rule", r"|api-key|pass|auth(?!or))[\w-]*[ \t]+(?!-)", r"|api-key|pass|auth(?!or))[\w-]*[ \t]+(?!-)ZZ"),
    ("curl -u user:pass is not a rule", r'("basic_flag", re.compile(r"(?<!\S)-u[ \t]+', r'("basic_flag", re.compile(r"(?<!\S)-Z[ \t]+'),
    ('"the password is X" is not a rule', r"|[ \t]+(?:is|was)\b)", r"|[ \t]+(?:zzz|zzzz)\b)"),
    ("a folded YAML value is not reached", r"(?:[>|][+-]?[ \t]*)?", ""),
    ("the hf_ prefix is dropped", r"|hf_[A-Za-z0-9]{20,}", ""),
    ("the SG. prefix is dropped", r"|SG\.[\w-]{16,}\.[\w-]{16,}", ""),
    ("the credential file-name rule is dropped", "[(m.start(1), m.end(1)) for m in PATH_RULE.finditer(text)]", "[]"),
    ("a path is masked as one string, not by segment", 'for seg in re.split(r"([\\\\/])", str(path or "")):', 'for seg in [str(path or "")]:'),
    ("the pw name is dropped", "|auth|pw|pat|sid|", "|auth|zzpw|pat|sid|"),
    ("the pat name is dropped", "|auth|pw|pat|sid|", "|auth|pw|zzpat|sid|"),
    ("the cookie name is dropped", "|sess(?:ion)?[_-]?id|cookie\"", "|sess(?:ion)?[_-]?id|zzcookie\""),
    ("a glued mysql -p value is not masked", '("mysql_glued_p", re.compile(r"(?i)\\b(?:mysql', '("mysql_glued_p", re.compile(r"(?i)\\b(?:zzmysql'),
    ("avif is not a photo", '"avif", ', ""),
    ("a DCIM folder in a path is not left out", 'LEFT_OUT_DIRS = ("dcim",)', "LEFT_OUT_DIRS = ()"),
    ("a Camera Roll root is not left out", '"dcim", "camera roll", ', ""),
]


def main():
    original = TARGET.read_bytes()
    text = original.decode("utf-8").replace("\r\n", "\n")        # a Windows checkout has CRLF; the patterns are written with LF
    survived = []
    try:
        for name, old, new in MUTATIONS:
            if text.count(old) != 1:
                print(f"NOT APPLIED  {name}: the line to change was found {text.count(old)} times")
                survived.append(name)
                continue
            TARGET.write_bytes(text.replace(old, new).encode("utf-8"))
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "test_waypoint.py", "test_waypoint_credentials.py"], cwd=HERE, capture_output=True, text=True)
            caught = r.returncode != 0
            print(f"{'caught  ' if caught else 'SURVIVED'}  {name}")
            if not caught:
                survived.append(name)
    finally:
        TARGET.write_bytes(original)
    print(f"{len(MUTATIONS) - len(survived)} of {len(MUTATIONS)} caught")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
