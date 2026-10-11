"""
dex_photo_work_log.py -- when the work happened, so the album app can show what was going on around a photo.

Writes <library>/work.jsonl, one row per event, oldest first:

    {"at": "2026-10-11T17:15:09", "kind": "commit", "where": "ddl-org", "what": "<the commit's first line>"}
    {"at": "2026-10-11T15:42:38", "kind": "dmail", "where": "DDL-3010", "what": "<the message's subject>"}

`at` is this machine's local clock time with no zone, the same as the times on the photos (a camera's
EXIF time and a screenshot's file-name time are both local). A commit's time is its author time. A
D-mail's time is the UTC stamp in its file name, moved to local.

Commits come from `git log` of each --repo at the ref given (default the remote's main branch, so
nothing unpushed is listed). D-mails come from the file names under _shared/DDL-MSG/from-*/ in --org,
read from git, not the working copy. A commit that only delivers a D-mail or a receipt is left out: the
message itself is already a row.

The file stays in the library on Reborn and is not for git.

    python dex_photo_work_log.py --library D:\\DDL_Corpus\\library --org C:\\Users\\dexjr\\ddl-wings\\reborn-cowork
        --repo ddl-org=C:\\Users\\dexjr\\ddl-wings\\reborn-cowork@origin/master --repo dex=C:\\Users\\dexjr\\dex@origin/main ...

Silas Reeve / DDL-3004 / 2026-10-11
"""
import argparse
import collections
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

MSG = re.compile(r"^_shared/DDL-MSG/from-(DDL-\d{4})/msg__(\d{8}T\d{6})Z__from-DDL-\d{4}__(.+)\.md$")
TO = re.compile(r"^(?:to-[A-Za-z0-9-]+__)+")
MAIL_COMMIT = re.compile(r"^(?:d-?mail\b|receipts?\b|dmail:)", re.I)
MAX_WHAT = 160


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def to_local(stamp):
    """20261011T204238 (UTC) -> this machine's local time, no zone."""
    return datetime.strptime(stamp, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None).isoformat(timespec="seconds")


def dmails(paths):
    """Rows for the message files among `paths` (repo-relative, forward slashes)."""
    out = []
    for p in paths:
        m = MSG.match(p)
        if not m:
            continue
        seat, stamp, rest = m.groups()
        subject = TO.sub("", rest).replace("-", " ").strip()
        try:
            at = to_local(stamp)
        except ValueError:
            continue
        out.append({"at": at, "kind": "dmail", "where": seat, "what": subject[:MAX_WHAT]})
    return out


def commits(name, lines):
    """Rows from `git log --pretty=%ad%x09%s` lines with a local, zone-less date."""
    out = []
    for line in lines:
        at, _, subject = line.partition("\t")
        if len(at) != 19 or not subject.strip() or MAIL_COMMIT.match(subject.strip()):
            continue
        out.append({"at": at, "kind": "commit", "where": name, "what": subject.strip()[:MAX_WHAT]})
    return out


def build(org, repos):
    """(rows oldest first, stats). `repos` is [(name, path, ref)]; `org` is (path, ref) or None."""
    rows, stats = [], collections.Counter()
    for name, path, ref in repos:
        got = commits(name, git(path, "log", ref, "--no-merges", "--date=format-local:%Y-%m-%dT%H:%M:%S", "--pretty=%ad%x09%s").splitlines())
        stats["commits_" + name] = len(got)
        rows += got
    if org:
        got = dmails(git(org[0], "-c", "core.quotepath=off", "ls-tree", "-r", "--name-only", org[1], "_shared/DDL-MSG").splitlines())
        stats["dmails"] = len(got)
        rows += got
    rows.sort(key=lambda r: (r["at"], r["kind"], r["where"], r["what"]))
    stats["rows"] = len(rows)
    return rows, dict(stats)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--library", required=True, type=Path)
    ap.add_argument("--org", help="path[@ref] of a ddl-org clone, for the D-mails")
    ap.add_argument("--repo", action="append", default=[], help="name=path[@ref], repeatable")
    a = ap.parse_args()

    def at_ref(s, default):
        path, _, ref = s.rpartition("@") if "@" in s[3:] else (s, "", "")
        return path, ref or default

    repos = []
    for r in a.repo:
        name, _, rest = r.partition("=")
        repos.append((name, *at_ref(rest, "origin/HEAD")))
    rows, stats = build(at_ref(a.org, "origin/master") if a.org else None, repos)
    out = a.library / "work.jsonl"
    tmp = out.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, out)
    print(json.dumps({**stats, "first": rows[0]["at"] if rows else None, "last": rows[-1]["at"] if rows else None}, sort_keys=True))


if __name__ == "__main__":
    main()
