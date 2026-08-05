#!/usr/bin/env python3
"""
dex-ledger.py -- account for every source file, or refuse to claim you did.

THE DEFECT THIS EXISTS FOR
--------------------------
The first corpus is being retired because nobody can say what is in it. Not
because it is small -- because for any given source file, there is no artifact
that answers "what happened to this one?" Counts exist. Dispositions do not.

That is how a build passes a count check and is still wrong. `dex-reconcile.py`
already holds the far end of the pipeline: it reconciles what the store
DECLARES against what the store MEASURES. Nothing holds the near end. Nothing
reconciles what went IN against what came out, and a chunk floor written down
after a lossy build certifies the loss rather than detecting it.

A floor should be DERIVED from a ledger. Not asserted alongside one.

THE SECOND DEFECT, WHICH IS WORSE BECAUSE IT IS SILENT
------------------------------------------------------
Both new corpus roots are cloud-synced (iCloud, OneDrive). Files there may be
PLACEHOLDERS: present in the namespace, absent from the disk. Opening one
triggers a silent multi-gigabyte download.

The standing mitigation is a briefing -- "check attributes, read nothing you
cannot confirm is materialized." STD-DDL-FAILFAST is explicit that this is the
wrong shape: prefer mechanisms that fail loudly over procedures that require
memory. A briefing is a procedure that requires memory, and it is executed by
whoever is tired at 2am.

So the guard here is a mechanism. `_read_guarded()` is the ONLY function in
this file that opens anything, and it refuses placeholders before it opens.
There is no call site that can forget, because forgetting is not expressible.

MEASURED, NOT ASSUMED -- and this one is a trap
-----------------------------------------------
Python 3.12.10 on this machine does NOT define these in the stat module:

    stat.FILE_ATTRIBUTE_RECALL_ON_OPEN          ABSENT
    stat.FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS   ABSENT

The natural implementation is `getattr(stat, "FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS", 0)`.
That returns 0. `attrs & 0` is 0. Every placeholder classifies as MATERIALIZED
and the tool reads all of them -- the exact accident the check was written to
prevent, produced by the most reasonable way to write the check.

The constants below are therefore literal. Do not "clean this up" by routing
them through the stat module.

Measured on real placeholders in C:\\Users\\dkitc\\OneDrive:
    attrs=0x400020  ->  RECALL_ON_DATA_ACCESS | ARCHIVE
    st_reparse_tag  ->  0  (NOT SET)

Reparse-tag detection alone would have missed every one of them. Attribute
detection is the load-bearing check; the tag check is a widener, not a
substitute.

THE ACCOUNTING INVARIANT
------------------------
Every file encountered lands in exactly one terminal disposition. At the end:

    files_seen == sum(count of every disposition)

If that fails, this tool has a bug and says so with a non-zero exit rather
than emitting a ledger that looks complete. A ledger that quietly drops a
file is worse than no ledger, because it will be trusted.

WHAT IT DOES NOT DO
-------------------
It declares no expected values -- no file count, no size, no manifest of what
SHOULD be present. Same rule as dex-reconcile.py: a tool with a baked-in
expectation becomes another disagreeing declaration. It records what is there.

NOT THE SAME TOOL AS dex_ingest_ledger.py
-----------------------------------------
Two ledgers, two stages, easy to confuse:

  dex-ledger.py         (this file)  FILESYSTEM -> what is on disk, and is it
                                     actually here or a cloud placeholder?
  dex_ingest_ledger.py               CONVERSION -> for every unit offered to a
                                     converter, was it emitted or dropped, and
                                     why?

This one runs first and answers "what have we got, and can we read it?"
That one runs during conversion and answers "did we lose any of it?"

  python dex-ledger.py --inventory ROOT --out led.jsonl     metadata only, never opens
  python dex-ledger.py --inventory ROOT --out led.jsonl --hash   + sha256 of MATERIALIZED
  python dex-ledger.py --verify led.jsonl                   re-stat, report drift
  python dex-ledger.py --summary led.jsonl                  re-read a ledger

Exit: 0 clean - 1 losses recorded (unreadable/placeholder) - 2 bad usage
      3 ACCOUNTING FAILURE (tool bug) - 4 verify found drift
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

LEDGER_FORMAT_VERSION = 1

# ---------------------------------------------------------------------------
# Windows cloud-file attributes -- LITERAL BY NECESSITY. See module docstring.
# ---------------------------------------------------------------------------
FILE_ATTRIBUTE_ARCHIVE               = 0x00000020
FILE_ATTRIBUTE_REPARSE_POINT         = 0x00000400
FILE_ATTRIBUTE_OFFLINE               = 0x00001000
FILE_ATTRIBUTE_RECALL_ON_OPEN        = 0x00040000
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000

# Any of these means "the bytes are not necessarily here."
NOT_MATERIALIZED_MASK = (
    FILE_ATTRIBUTE_OFFLINE
    | FILE_ATTRIBUTE_RECALL_ON_OPEN
    | FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
)

# Cloud reparse tags. A widener over the attribute check, never a substitute --
# measured placeholders on this machine carry NO reparse tag at all.
CLOUD_REPARSE_TAGS = frozenset(
    0x9000001A | (n << 12) for n in range(16)
) | {0x9000001A}

# ---------------------------------------------------------------------------
# Terminal dispositions. Every file lands in exactly one.
# ---------------------------------------------------------------------------
# PLACEHOLDER is the one that matters and the one every present/absent model
# gets wrong. A placeholder is NOT missing -- the file exists, is named, has a
# logical size, and will materialize if something reads it. It is also NOT
# present -- its bytes are not on this disk and cannot be hashed or converted
# without a network transfer. Modelling it as either produces a wrong build:
# as "present" you hydrate gigabytes by accident; as "missing" you under-count
# the corpus and chase files that were never gone.
D_MATERIALIZED = "materialized"   # bytes are local; safe to read
D_PLACEHOLDER  = "placeholder"    # in namespace, not on disk. NOT READ.
D_EMPTY        = "empty"          # zero bytes, materialized
D_UNREADABLE   = "unreadable"     # stat or read raised; error recorded
D_EXCLUDED     = "excluded"       # matched an exclusion rule; rule recorded
D_SYMLINK      = "symlink"        # not followed, by policy

ALL_DISPOSITIONS = (
    D_MATERIALIZED, D_PLACEHOLDER, D_EMPTY,
    D_UNREADABLE, D_EXCLUDED, D_SYMLINK,
)

# Dispositions that mean "this file did not contribute content to the build."
# Used for the exit code. A placeholder is a loss for build purposes even
# though nothing is wrong with the file.
LOSS_DISPOSITIONS = (D_PLACEHOLDER, D_UNREADABLE)


class AccountingError(RuntimeError):
    """The ledger did not account for every file it saw. This is a tool bug."""


class HydrationRefused(RuntimeError):
    """Something tried to read a non-materialized file. The guard held."""


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------
@dataclass
class Entry:
    path: str
    disposition: str
    size: int = 0
    mtime: float = 0.0
    ext: str = ""
    attrs: str = ""            # hex, so a human can audit the classification
    reparse_tag: str = ""
    sha256: str = ""           # only ever set for MATERIALIZED
    error: str = ""
    excluded_by: str = ""      # the literal rule, so exclusions are auditable

    def to_json(self) -> str:
        d = {k: v for k, v in asdict(self).items() if v not in ("", 0, 0.0)}
        d["path"] = self.path
        d["disposition"] = self.disposition
        return json.dumps(d, ensure_ascii=False)


@dataclass
class Tally:
    root: str = ""
    started_at: str = ""
    finished_at: str = ""
    hashed: bool = False
    files_seen: int = 0
    dirs_seen: int = 0
    dirs_denied: list = field(default_factory=list)
    counts: dict = field(default_factory=lambda: {d: 0 for d in ALL_DISPOSITIONS})
    bytes_materialized: int = 0
    bytes_placeholder: int = 0     # LOGICAL size; these bytes are not local
    exclusion_rules: list = field(default_factory=list)

    def record(self, e: Entry) -> None:
        if e.disposition not in self.counts:
            # An unknown disposition is an accounting hole. Refuse it here
            # rather than letting it vanish from the totals.
            raise AccountingError(
                f"unknown disposition {e.disposition!r} for {e.path!r}")
        self.counts[e.disposition] += 1
        if e.disposition == D_MATERIALIZED:
            self.bytes_materialized += e.size
        elif e.disposition == D_PLACEHOLDER:
            self.bytes_placeholder += e.size

    def check(self) -> None:
        """THE INVARIANT. Every file seen is in exactly one bucket."""
        total = sum(self.counts.values())
        if total != self.files_seen:
            raise AccountingError(
                f"files_seen={self.files_seen} but dispositions sum to {total} "
                f"(difference {self.files_seen - total}). "
                f"Some file was encountered and not classified. The ledger is "
                f"NOT a complete account and must not be trusted. "
                f"counts={self.counts}")


# ---------------------------------------------------------------------------
# Classification -- metadata only, no file is opened here
# ---------------------------------------------------------------------------
def _classify(entry: os.DirEntry) -> tuple[str, dict]:
    """Decide a disposition from scandir-cached attributes. Opens nothing.

    scandir carries the attributes from the directory enumeration itself, so
    stat(follow_symlinks=False) costs no additional I/O against the cloud
    provider and cannot trigger a recall.
    """
    try:
        st = entry.stat(follow_symlinks=False)
    except OSError as exc:
        return D_UNREADABLE, {"error": f"stat: {type(exc).__name__}: {exc}"}

    attrs = getattr(st, "st_file_attributes", 0)
    tag = getattr(st, "st_reparse_tag", 0)
    meta = {
        "size": st.st_size,
        "mtime": st.st_mtime,
        "attrs": hex(attrs),
        "reparse_tag": hex(tag) if tag else "",
    }

    if attrs & NOT_MATERIALIZED_MASK or tag in CLOUD_REPARSE_TAGS:
        return D_PLACEHOLDER, meta
    if st.st_size == 0:
        return D_EMPTY, meta
    return D_MATERIALIZED, meta


def _read_guarded(path: str, disposition: str, chunk: int = 1 << 20) -> str:
    """THE ONLY FUNCTION IN THIS FILE THAT OPENS A FILE.

    The hydration guard lives here rather than at the call site, deliberately.
    A guard at the call site is a convention -- it works until someone adds a
    second call site. A guard inside the only reader is a mechanism: to read a
    placeholder you would have to edit this function, which is a visible act.
    """
    if disposition != D_MATERIALIZED:
        raise HydrationRefused(
            f"refused to open {path!r}: disposition is {disposition!r}, not "
            f"{D_MATERIALIZED!r}. Opening it would trigger a cloud recall.")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _match_exclusion(rel_path: str, name: str, rules: list[str]) -> str:
    """Return the rule that excludes this file, or '' if none.

    Returns the RULE, not a boolean, so every exclusion in the ledger names
    the reason it happened. An exclusion nobody can attribute is the same
    silence this tool exists to remove.
    """
    for rule in rules:
        if fnmatch.fnmatch(name, rule) or fnmatch.fnmatch(rel_path, rule):
            return rule
    return ""


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------
def inventory(root: Path, out_path: Path, do_hash: bool,
              exclude: list[str], progress_every: int = 2000) -> Tally:
    tally = Tally(
        root=str(root),
        started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        hashed=do_hash,
        exclusion_rules=list(exclude),
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as out:
        # Header record, so a ledger is self-describing when read back.
        out.write(json.dumps({
            "_ledger": LEDGER_FORMAT_VERSION,
            "root": str(root),
            "started_at": tally.started_at,
            "hashed": do_hash,
            "exclusion_rules": exclude,
            "host": os.environ.get("COMPUTERNAME", ""),
        }) + "\n")

        stack = [root]
        while stack:
            cur = stack.pop()
            try:
                it = os.scandir(cur)
            except OSError as exc:
                # A directory we cannot enter is a hole in the account. Record
                # it as such -- do NOT let it pass as "nothing was there."
                tally.dirs_denied.append(f"{cur}: {type(exc).__name__}: {exc}")
                continue

            with it:
                for de in it:
                    try:
                        is_dir = de.is_dir(follow_symlinks=False)
                        is_link = de.is_symlink()
                    except OSError as exc:
                        tally.files_seen += 1
                        e = Entry(path=de.path, disposition=D_UNREADABLE,
                                  error=f"dirent: {type(exc).__name__}: {exc}")
                        tally.record(e)
                        out.write(e.to_json() + "\n")
                        continue

                    if is_link:
                        tally.files_seen += 1
                        e = Entry(path=de.path, disposition=D_SYMLINK)
                        tally.record(e)
                        out.write(e.to_json() + "\n")
                        continue

                    if is_dir:
                        tally.dirs_seen += 1
                        stack.append(Path(de.path))
                        continue

                    # ---- a file ----
                    tally.files_seen += 1
                    try:
                        rel = os.path.relpath(de.path, root)
                    except ValueError:
                        rel = de.path

                    rule = _match_exclusion(rel, de.name, exclude)
                    if rule:
                        e = Entry(path=de.path, disposition=D_EXCLUDED,
                                  ext=Path(de.name).suffix.lower(),
                                  excluded_by=rule)
                        tally.record(e)
                        out.write(e.to_json() + "\n")
                        continue

                    disp, meta = _classify(de)
                    e = Entry(
                        path=de.path,
                        disposition=disp,
                        ext=Path(de.name).suffix.lower(),
                        size=meta.get("size", 0),
                        mtime=meta.get("mtime", 0.0),
                        attrs=meta.get("attrs", ""),
                        reparse_tag=meta.get("reparse_tag", ""),
                        error=meta.get("error", ""),
                    )

                    if do_hash and disp == D_MATERIALIZED:
                        try:
                            e.sha256 = _read_guarded(de.path, disp)
                        except HydrationRefused:
                            # Cannot happen given the branch, but if the guard
                            # ever fires it is a real finding, not a warning.
                            raise
                        except OSError as exc:
                            e.disposition = D_UNREADABLE
                            e.error = f"read: {type(exc).__name__}: {exc}"

                    tally.record(e)
                    out.write(e.to_json() + "\n")

                    if progress_every and tally.files_seen % progress_every == 0:
                        print(f"  ... {tally.files_seen:,} files", file=sys.stderr)

        # FOOTER. Written last, on purpose.
        #
        # Without it, a ledger truncated after the fact is undetectable: drop
        # the last N records and the file still parses, still balances
        # internally (4 seen, 4 classified), and --summary reports it as a
        # complete account of a smaller tree. Caught by the test suite, which
        # is the only reason this exists.
        #
        # A header count cannot fix this -- the count is not known until the
        # walk finishes. So the completeness marker has to be the last thing
        # written, and its absence has to be fatal.
        tally.finished_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        tally.check()   # raises before we claim completeness
        out.write(json.dumps({
            "_ledger_end": LEDGER_FORMAT_VERSION,
            "files_seen": tally.files_seen,
            "dirs_seen": tally.dirs_seen,
            "counts": tally.counts,
            "dirs_denied": tally.dirs_denied,
            "bytes_materialized": tally.bytes_materialized,
            "bytes_placeholder": tally.bytes_placeholder,
            "finished_at": tally.finished_at,
        }) + "\n")

    return tally


# ---------------------------------------------------------------------------
# Verify -- a ledger is a claim; this is how it gets checked
# ---------------------------------------------------------------------------
def verify(ledger_path: Path, recheck_hash: bool) -> dict:
    """Re-stat everything in a ledger and report drift.

    This is what makes a ledger falsifiable rather than merely archived. A
    record that cannot be rechecked is a story about the past.
    """
    drift = {"gone": [], "appeared_materialized": [], "became_placeholder": [],
             "size_changed": [], "hash_changed": [], "checked": 0,
             "unrecheckable": []}

    # Group by parent directory first.
    #
    # The obvious implementation re-scandirs a record's parent for every
    # record, which is O(records x siblings) -- on the 24,760-file tree
    # measured here that is ~10^8 dirent comparisons, and the real corpus is
    # larger. Scanning each directory once makes it O(records).
    by_parent: dict[str, list[dict]] = {}
    order: list[str] = []
    with open(ledger_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if "_ledger" in rec or "_ledger_end" in rec:
                continue
            drift["checked"] += 1
            if rec["disposition"] in (D_EXCLUDED, D_SYMLINK):
                continue
            p = os.path.dirname(rec["path"])
            if p not in by_parent:
                by_parent[p] = []
                order.append(p)
            by_parent[p].append(rec)

    for parent in order:
        recs = by_parent[parent]
        try:
            with os.scandir(parent) as it:
                live = {de.path: de for de in it}
        except OSError as exc:
            for rec in recs:
                drift["unrecheckable"].append(
                    {"path": rec["path"], "error": f"{type(exc).__name__}: {exc}"})
            continue

        for rec in recs:
            path = rec["path"]
            was = rec["disposition"]
            found = live.get(path)
            if found is None:
                drift["gone"].append({"path": path, "was": was})
                continue

            now, meta = _classify(found)

            if was == D_PLACEHOLDER and now == D_MATERIALIZED:
                drift["appeared_materialized"].append({"path": path})
            elif was == D_MATERIALIZED and now == D_PLACEHOLDER:
                # Notable: the file was local when the ledger was written and
                # has since been evicted to the cloud. Any hash in the ledger
                # is still valid for the content, but the file is no longer
                # readable without a transfer.
                drift["became_placeholder"].append({"path": path})

            if now in (D_MATERIALIZED, D_EMPTY):
                if meta.get("size", 0) != rec.get("size", 0):
                    drift["size_changed"].append({
                        "path": path, "was": rec.get("size", 0),
                        "now": meta.get("size", 0)})
                elif recheck_hash and rec.get("sha256"):
                    try:
                        h = _read_guarded(path, now)
                    except (HydrationRefused, OSError) as exc:
                        drift["unrecheckable"].append(
                            {"path": path, "error": str(exc)})
                        continue
                    if h != rec["sha256"]:
                        drift["hash_changed"].append({"path": path})

    return drift


def read_summary(ledger_path: Path) -> Tally:
    """Rebuild a Tally by re-reading a ledger.

    Three independent checks, because internal consistency is not
    completeness. A truncated ledger balances against itself perfectly -- it
    simply describes a smaller tree than the one that was walked.

      1. the footer must be present   (was the run completed?)
      2. records must balance         (was every file classified?)
      3. re-counted totals must equal the footer's  (was anything lost since?)
    """
    t = Tally()
    footer = None
    with open(ledger_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if "_ledger" in rec:
                t.root = rec.get("root", "")
                t.started_at = rec.get("started_at", "")
                t.hashed = rec.get("hashed", False)
                t.exclusion_rules = rec.get("exclusion_rules", [])
                continue
            if "_ledger_end" in rec:
                footer = rec
                continue
            t.files_seen += 1
            e = Entry(path=rec["path"], disposition=rec["disposition"],
                      size=rec.get("size", 0))
            t.record(e)
    t.check()

    if footer is None:
        raise AccountingError(
            f"{ledger_path} has no completion footer. The run that produced it "
            f"either did not finish or the file was truncated. It parsed "
            f"cleanly and its {t.files_seen:,} records balance — which is "
            f"exactly why the footer is the check that matters. Do NOT treat "
            f"this as a complete account.")

    if footer.get("files_seen") != t.files_seen:
        raise AccountingError(
            f"{ledger_path} declares {footer.get('files_seen'):,} files in its "
            f"footer but contains {t.files_seen:,} records "
            f"({footer.get('files_seen', 0) - t.files_seen:+,}). Records were "
            f"lost or added after the walk completed.")

    t.dirs_seen = footer.get("dirs_seen", 0)
    t.dirs_denied = footer.get("dirs_denied", [])
    t.finished_at = footer.get("finished_at", "")
    return t


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
def render_tally(t: Tally) -> None:
    print()
    print("DEX LEDGER — every file accounted for, or the run fails")
    print("=" * 72)
    print(f"  root            {t.root}")
    if t.started_at:
        print(f"  started         {t.started_at}")
    if t.finished_at:
        print(f"  finished        {t.finished_at}")
    print(f"  hashed          {t.hashed}")
    if t.exclusion_rules:
        print(f"  exclusions      {t.exclusion_rules}")
    print()
    print(f"  directories     {t.dirs_seen:,}")
    print(f"  files seen      {t.files_seen:,}")
    print()
    for d in ALL_DISPOSITIONS:
        n = t.counts.get(d, 0)
        if n == 0 and d in (D_SYMLINK, D_EXCLUDED):
            continue
        mark = "!!" if (d in LOSS_DISPOSITIONS and n) else "  "
        print(f"  {mark} {d:<14} {n:>10,}")
    print()
    print(f"  bytes local     {t.bytes_materialized/1024/1024:>12,.1f} MB")
    if t.counts.get(D_PLACEHOLDER):
        print(f"  bytes in cloud  {t.bytes_placeholder/1024/1024:>12,.1f} MB  "
              f"<- NOT downloaded. Reading these would transfer them.")
    print()

    if t.dirs_denied:
        print(f"  {len(t.dirs_denied)} DIRECTORY(IES) COULD NOT BE ENTERED — these are")
        print("  holes in the account, not empty folders:")
        for d in t.dirs_denied[:10]:
            print(f"    {d}")
        if len(t.dirs_denied) > 10:
            print(f"    ... and {len(t.dirs_denied)-10} more")
        print()

    losses = sum(t.counts.get(d, 0) for d in LOSS_DISPOSITIONS)
    if losses:
        print("=" * 72)
        print(f"  {losses:,} FILE(S) DID NOT CONTRIBUTE CONTENT")
        if t.counts.get(D_PLACEHOLDER):
            print(f"    {t.counts[D_PLACEHOLDER]:,} placeholder — present in the namespace,")
            print("      bytes not on this disk. NOT missing. NOT read.")
        if t.counts.get(D_UNREADABLE):
            print(f"    {t.counts[D_UNREADABLE]:,} unreadable — see the ledger for each error")
        print("=" * 72)
    else:
        print("  every file seen was materialized, empty, or explicitly excluded.")
    print()


def render_drift(d: dict) -> None:
    print()
    print("DEX LEDGER — verify")
    print("=" * 72)
    print(f"  records checked        {d['checked']:,}")
    for key, label in (
        ("gone", "no longer present"),
        ("became_placeholder", "evicted to cloud since the ledger"),
        ("appeared_materialized", "downloaded since the ledger"),
        ("size_changed", "size changed"),
        ("hash_changed", "CONTENT CHANGED"),
        ("unrecheckable", "could not recheck"),
    ):
        items = d[key]
        if items:
            mark = "!!" if key in ("gone", "hash_changed", "size_changed") else " ?"
            print(f"  {mark} {label:<32} {len(items):,}")
            for it in items[:5]:
                print(f"       {it}")
            if len(items) > 5:
                print(f"       ... and {len(items)-5} more")
    total = sum(len(d[k]) for k in
                ("gone", "became_placeholder", "appeared_materialized",
                 "size_changed", "hash_changed", "unrecheckable"))
    print()
    print("  no drift — the ledger still describes the filesystem." if not total
          else f"  {total:,} record(s) drifted from the ledger.")
    print()


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="account for every source file, or refuse to claim you did")
    ap.add_argument("--inventory", metavar="ROOT",
                    help="walk ROOT and write a ledger")
    ap.add_argument("--out", metavar="LEDGER.jsonl",
                    help="ledger output path (required with --inventory)")
    ap.add_argument("--hash", action="store_true",
                    help="sha256 MATERIALIZED files. Placeholders are never opened.")
    ap.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                    help="exclude matching files; each exclusion is recorded "
                         "with the rule that caused it. Repeatable.")
    ap.add_argument("--verify", metavar="LEDGER.jsonl",
                    help="re-stat everything in a ledger, report drift")
    ap.add_argument("--recheck-hash", action="store_true",
                    help="with --verify, re-hash unchanged-size files too")
    ap.add_argument("--summary", metavar="LEDGER.jsonl",
                    help="re-read a ledger and print its account")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    try:
        if a.inventory:
            if not a.out:
                print("--out is required with --inventory", file=sys.stderr)
                return 2
            root = Path(a.inventory)
            if not root.is_dir():
                print(f"not a directory: {root}", file=sys.stderr)
                return 2
            t = inventory(root, Path(a.out), a.hash, a.exclude)
            if a.json:
                print(json.dumps(asdict(t), indent=2, default=str))
            else:
                render_tally(t)
                print(f"  ledger: {a.out}\n")
            return 1 if any(t.counts.get(d, 0) for d in LOSS_DISPOSITIONS) else 0

        if a.summary:
            t = read_summary(Path(a.summary))
            if a.json:
                print(json.dumps(asdict(t), indent=2, default=str))
            else:
                render_tally(t)
            return 1 if any(t.counts.get(d, 0) for d in LOSS_DISPOSITIONS) else 0

        if a.verify:
            d = verify(Path(a.verify), a.recheck_hash)
            if a.json:
                print(json.dumps(d, indent=2, default=str))
            else:
                render_drift(d)
            drifted = sum(len(d[k]) for k in
                          ("gone", "size_changed", "hash_changed"))
            return 4 if drifted else 0

        ap.print_help()
        return 2

    except AccountingError as exc:
        # The loudest failure in this tool. It means the ledger is not a
        # complete account, which is the one thing it is for.
        print("\n" + "=" * 72, file=sys.stderr)
        print("  ACCOUNTING FAILURE — this is a bug in dex-ledger.py", file=sys.stderr)
        print(f"  {exc}", file=sys.stderr)
        print("  The emitted ledger MUST NOT be used as a build input.", file=sys.stderr)
        print("=" * 72 + "\n", file=sys.stderr)
        return 3
    except HydrationRefused as exc:
        print("\n" + "=" * 72, file=sys.stderr)
        print("  HYDRATION GUARD FIRED — something tried to open a "
              "non-materialized file", file=sys.stderr)
        print(f"  {exc}", file=sys.stderr)
        print("=" * 72 + "\n", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
