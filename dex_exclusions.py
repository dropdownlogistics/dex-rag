#!/usr/bin/env python3
"""
dex_exclusions.py -- the exclusion list, and the refusal to run without it.

Operator ruling 2026-08-03 (via Caldwell, Seat 1002):

    Personal material, third-party personal material, and anything naming an
    identifiable individual who is not the Operator is out of scope for every
    DDL corpus, permanently and without case-by-case review.

    Anything uncertain is siloed for review, not ingested pending
    clarification. The default for ambiguous material is OUT.

THE LOAD-BEARING PART IS THE REFUSAL.

A pipeline that cannot find its exclusion list must not proceed on the
assumption that there is nothing to exclude. Missing, unreadable, malformed,
or empty -- all four exit non-zero. Not a warning, not a skip.

This is the same shape as 8788's token check, for the same reason: the failure
mode of "quietly continue" is silent and permanent, and the failure mode of
"stop" is loud and cheap.

The list itself is LOCAL and GITIGNORED and is never committed -- it contains
absolute paths into personal storage. `ingest-exclusions.example.json` in this
repo carries the schema with placeholder values only, per the roster precedent
established with Ellis Cooper (DDL-4008).

Usage:

    from dex_exclusions import load_exclusions
    ex = load_exclusions()          # exits the process if unusable
    if ex.excludes(path):
        continue
    stamp["exclusion_digest"] = ex.digest

CLI:

    python dex_exclusions.py             # show what is in force, and its digest
    python dex_exclusions.py --check PATH  # would this path be excluded?
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Explicit path, not discovered. Nothing walks a directory looking for this --
# a list that can be shadowed by a file dropped somewhere earlier on a search
# order is not a control.
DEFAULT_EXCLUSIONS_PATH = Path(r"C:\Users\dkitc\.config\ddl\ingest-exclusions.json")

# Override exists so the failure modes below are testable. It cannot weaken the
# control: any override still has to satisfy every check, and the digest of
# whatever was actually loaded is printed at load and recorded in the stamp --
# so a swapped list is visible in the artifact rather than only in someone's
# shell history.
ENV_OVERRIDE = "DDL_INGEST_EXCLUSIONS"

SCHEMA_VERSION = 1


class ExclusionsUnusable(Exception):
    """Raised by parse/validate. main() and load_exclusions() turn this into an
    exit -- callers that want to handle it themselves can catch it."""


@dataclass(frozen=True)
class Exclusions:
    """A loaded, validated exclusion set.

    Three rule kinds, deliberately overlapping. Overlap is the point: the
    sequestered directory is caught by its absolute path AND by its directory
    name, so relocating or copying it does not silently re-admit it.
    """

    source: Path
    paths: tuple[str, ...]            # absolute; the path itself and everything under it
    dir_names: tuple[str, ...]        # directory name matched at ANY depth
    filename_patterns: tuple[str, ...]  # glob against the basename
    digest: str                       # sha256 over the canonical rule set

    def excludes(self, path: str | os.PathLike) -> bool:
        return self.reason(path) is not None

    def reason(self, path: str | os.PathLike) -> str | None:
        """Why this path is excluded, or None. Returns a reason rather than a
        bool so an exclusion can be logged as an explanation instead of a
        silent absence -- a file that vanishes from a corpus with no recorded
        cause is indistinguishable from a file the walker simply missed."""
        p = _norm(path)

        for rule in self.paths:
            if p == rule or p.startswith(rule.rstrip("\\/") + os.sep):
                return f"under excluded path: {rule}"

        parts = Path(p).parts
        for rule in self.dir_names:
            if rule in parts:
                return f"under excluded directory name: {rule}"

        base = Path(p).name
        for rule in self.filename_patterns:
            if fnmatch.fnmatch(base, rule):
                return f"matches excluded filename pattern: {rule}"

        return None

    @property
    def rule_count(self) -> int:
        return len(self.paths) + len(self.dir_names) + len(self.filename_patterns)


def _norm(path: str | os.PathLike) -> str:
    """Case-folded, separator-normalized. Windows is case-insensitive, so a
    rule that only matches the casing someone happened to type is not a rule."""
    return os.path.normcase(os.path.normpath(str(path)))


def _canonical(paths, dir_names, patterns) -> str:
    """Digest input: sorted, normalized, structurally tagged.

    Deliberately NOT a hash of the file bytes. Reformatting the JSON or
    reordering the arrays should not change the digest; adding or removing a
    rule must. The digest identifies the POLICY IN FORCE, which is the thing a
    collection needs to record -- not the formatting of the file it came from.

    Kinds are tagged so a value moving between rule kinds registers as a change.
    """
    payload = {
        "v": SCHEMA_VERSION,
        "paths": sorted(paths),
        "dir_names": sorted(dir_names),
        "filename_patterns": sorted(patterns),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _read_list(raw: dict, key: str) -> list[str]:
    val = raw.get(key, [])
    if not isinstance(val, list):
        raise ExclusionsUnusable(f"'{key}' must be a list, got {type(val).__name__}")
    out = []
    for i, item in enumerate(val):
        if not isinstance(item, str):
            raise ExclusionsUnusable(f"{key}[{i}] must be a string, got {type(item).__name__}")
        if not item.strip():
            # An empty rule is not a harmless no-op. Depending on the matcher it
            # either matches everything or nothing, and both are catastrophic in
            # opposite directions. Refuse rather than guess which.
            raise ExclusionsUnusable(f"{key}[{i}] is empty -- refusing to guess its intent")
        out.append(item.strip())
    return out


def parse_exclusions(text: str, source: Path) -> Exclusions:
    """Parse and validate. Raises ExclusionsUnusable on anything suspect."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExclusionsUnusable(f"not valid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise ExclusionsUnusable(f"top level must be an object, got {type(raw).__name__}")

    version = raw.get("version")
    if version != SCHEMA_VERSION:
        raise ExclusionsUnusable(
            f"version is {version!r}, this code understands {SCHEMA_VERSION}. "
            "Refusing to interpret a schema it was not written for."
        )

    paths = _read_list(raw, "exclude_paths")
    dir_names = _read_list(raw, "exclude_dir_names")
    patterns = _read_list(raw, "exclude_filename_patterns")

    if any("REPLACE_ME" in v for v in (*paths, *dir_names, *patterns)):
        raise ExclusionsUnusable(
            "contains REPLACE_ME placeholders -- this is the example file, "
            "not a real exclusion list"
        )

    if not (paths or dir_names or patterns):
        # The core refusal. An empty list is not "nothing to exclude" -- it is
        # indistinguishable from a list that failed to populate, and we cannot
        # tell those apart from in here.
        raise ExclusionsUnusable("contains no rules -- an empty exclusion list is not a policy")

    for p in paths:
        if not os.path.isabs(p):
            raise ExclusionsUnusable(f"exclude_paths entry is not absolute: {p!r}")

    for d in dir_names:
        if os.sep in d or "/" in d:
            raise ExclusionsUnusable(
                f"exclude_dir_names entry looks like a path, not a name: {d!r} "
                "-- use exclude_paths for paths"
            )

    return Exclusions(
        source=source,
        paths=tuple(_norm(p) for p in paths),
        dir_names=tuple(os.path.normcase(d) for d in dir_names),
        filename_patterns=tuple(os.path.normcase(p) for p in patterns),
        digest=_canonical(
            [_norm(p) for p in paths],
            [os.path.normcase(d) for d in dir_names],
            [os.path.normcase(p) for p in patterns],
        ),
    )


def resolve_path() -> Path:
    override = os.environ.get(ENV_OVERRIDE)
    return Path(override) if override else DEFAULT_EXCLUSIONS_PATH


def try_load(path: Path | None = None) -> tuple[Exclusions | None, str | None]:
    """Attempt to load. Returns (exclusions, None) or (None, problem).

    Does NOT exit. Exists so an unattended caller -- the nightly sweep -- can
    learn WHY the list is unusable and say so in an alert a human will actually
    see, before the process dies. `load_exclusions()` is the exiting wrapper and
    is what normal callers should use.
    """
    src = path or resolve_path()

    if not src.exists():
        return None, "file does not exist"
    if not src.is_file():
        return None, "path exists but is not a file"

    try:
        text = src.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"unreadable: {exc}"

    if not text.strip():
        return None, "file is empty"

    try:
        return parse_exclusions(text, src), None
    except ExclusionsUnusable as exc:
        return None, str(exc)


def load_exclusions(path: Path | None = None, *, quiet: bool = False) -> Exclusions:
    """Load the exclusion list, or EXIT THE PROCESS.

    This does not return None and does not return an empty set. Every path out
    of here is either a validated Exclusions or a dead process.
    """
    src = path or resolve_path()

    def die(problem: str) -> None:
        print(
            "\n".join(
                [
                    "",
                    "=" * 70,
                    "INGEST REFUSED -- exclusion list unusable",
                    "=" * 70,
                    f"  path:    {src}",
                    f"  problem: {problem}",
                    "",
                    "  This pipeline does not run without a readable, non-empty",
                    "  exclusion list. An absent list is not permission to ingest",
                    "  everything -- it is indistinguishable from a list that",
                    "  failed to load, and continuing would be a guess.",
                    "",
                    "  Schema: ingest-exclusions.example.json in this repo.",
                    "  The real list is local and gitignored. Never commit it.",
                    "=" * 70,
                    "",
                ]
            ),
            file=sys.stderr,
        )
        sys.exit(2)

    ex, problem = try_load(src)
    if ex is None:
        die(problem or "unusable for an unstated reason")

    if not quiet:
        # Always announced. The digest is how a swapped list becomes visible.
        print(f"[exclusions] {ex.rule_count} rules from {src}")
        print(f"[exclusions] digest {ex.digest[:16]}...")
        missing = [p for p in ex.paths if not os.path.exists(p)]
        if missing:
            # Warn, not fail: a list shared across machines will legitimately
            # name paths that do not exist here. But a sequester directory that
            # has moved is worth seeing.
            print(f"[exclusions] NOTE: {len(missing)} excluded path(s) not present on this machine")
            for m in missing:
                print(f"[exclusions]   {m}")

    return ex


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="show or test the ingest exclusion list")
    ap.add_argument("--check", metavar="PATH", help="report whether PATH would be excluded")
    a = ap.parse_args()

    ex = load_exclusions()

    if a.check:
        why = ex.reason(a.check)
        print()
        if why:
            print(f"  EXCLUDED  {a.check}")
            print(f"            {why}")
        else:
            print(f"  eligible  {a.check}")
        print()
        return 0

    print()
    print(f"  source  {ex.source}")
    print(f"  digest  {ex.digest}")
    print()
    for label, rules in (
        ("absolute paths", ex.paths),
        ("directory names", ex.dir_names),
        ("filename patterns", ex.filename_patterns),
    ):
        print(f"  {label} ({len(rules)}):")
        for r in rules:
            print(f"    {r}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
