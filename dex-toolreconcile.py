#!/usr/bin/env python3
"""
dex-toolreconcile.py -- make the tooling's declarations argue with reality.

THE DEFECT THIS EXISTS FOR
--------------------------
On 2026-07-24 I built `leakscan.py` and wrote in its README:

    "No real roster loaded -- pluggable; the real decoy roster plugs in later."
    "necessary, not sufficient -- the mechanical floor under human review,
     which remains the other half of the gate."

Two declared gaps. A missing plug, and a named empty slot.

On 2026-08-05 I built `ddl-leakscan.py` against a different document, and it
filled the second slot without either of us noticing -- then `ddl-gate.py`
filled the first. Two halves of one gate, built a fortnight apart, by the same
worker, neither aware of the other.

Nobody was careless. The information needed to notice was spread across a
README, a spec in Drive, and two scratch directories, and no single reader ever
held all of it at once.

`dex-reconcile.py` fixes exactly this for CORPUS facts. There was no equivalent
for TOOLING. This is it.

THE ONE RULE THAT MAKES IT WORK
-------------------------------
**This tool declares no inventory.** It contains no list of what tools should
exist, no expected versions, no required layout. It knows only WHERE to look
and WHAT a declaration looks like. Every finding is a file:line you can open.

Same discipline as dex-reconcile.py, and for the same reason: an inventory with
a hardcoded expectation becomes another stale document, and then it is part of
the problem it was written to detect.

WHAT IT MEASURES
----------------
  DIVERGENT_COPY   same filename, different content, more than one location.
                   Two writable copies is how DDL lost three days in July.
  DECLARED_GAP     a tool says, in its own words, that something is missing,
                   deferred, or someone else's job. Collected into a register.
  DANGLING_REF     a file cites a path that does not exist.
  ORPHAN           nothing anywhere references this tool by name.
  UNVERIFIED       declares EXPERIMENTAL / REVIEW REQUIRED / NOT WIRED.

THE HONEST LIMIT, WHICH MIRRORS THE TOOL THAT INSPIRED IT
----------------------------------------------------------
`leakscan.py` cannot catch an entity that is not on its roster. **This cannot
catch a gap nobody wrote down.** It harvests gaps that were stated in
recognisable form -- a section header, a known phrase. A gap phrased unusually,
or never phrased at all, is invisible to it.

So a clean DECLARED_GAP register means "no tool admitted to a gap in words I
recognise." It does not mean there are no gaps. Same shape of claim, stated
plainly rather than implied.

It also does not match gaps to the things that filled them. That is a semantic
judgement and this tool does not make semantic judgements -- it puts the gap and
the tooling in one list so a human can see them at the same time, which is the
thing that was missing.

  python dex-toolreconcile.py                 full report
  python dex-toolreconcile.py --gaps          the declared-gap register only
  python dex-toolreconcile.py --duplicates    divergent copies only
  python dex-toolreconcile.py --root PATH     add a scan root (repeatable)
  python dex-toolreconcile.py --json

Exit: 0 nothing found - 1 findings present - 2 usage

Read-only. Opens files to read them. Writes nothing, anywhere.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ---------------------------------------------------------------------------
# WHERE to look. NOT what should be there.
# ---------------------------------------------------------------------------
DEFAULT_ROOTS = [
    Path(r"C:\Users\dexjr\.ddl-worker-scratch"),
    Path(r"C:\Users\dexjr\ddl-org\reborn-cowork"),
    Path(r"C:\Users\dexjr\dex-rag"),
]

SCAN_EXT = {".py", ".md"}

# ---------------------------------------------------------------------------
# UNLANDED -- work that was written and never delivered
# ---------------------------------------------------------------------------
# Twice in two days: a D-mail written into an inbox directory and left
# untracked for four hours, so it never reached its recipient; and three
# finished artifacts that sat in scratch for two days because the person who
# commits for me was busy elsewhere.
#
# Both were invisible for the same reason. `?? path` in git status renders
# almost identically to a file that landed, and a scratch directory looks the
# same whether its contents are finished or half-written.
#
# **Write is not delivery.** This makes that checkable instead of remembered.
#
# The check is deliberately factual rather than judgemental: it reports a work
# product in a non-repo directory with no tracked counterpart anywhere. Whether
# it SHOULD land is a human call -- the tool surfaces, it does not decide.
SCRATCH_ROOTS = [
    Path(r"C:\Users\dexjr\.ddl-worker-scratch"),
]

REPO_ROOTS = [
    Path(r"C:\Users\dexjr\ddl-org"),
    Path(r"C:\Users\dexjr\ddl-wings\reborn-cowork"),
    Path(r"C:\Users\dexjr\dex-rag"),
]

# Names that are scratch BY DESIGN and are not undelivered work. Kept small and
# explicit -- a broad filter here would hide the thing the check exists to find.
SCRATCH_BY_DESIGN = re.compile(
    r"^(test[-_]|_tmp|probe_|scratch|hydration-manifest|.*\.jsonl$)", re.I)

# Directories that hold copies-by-design. A second clone of a git repo is not
# a divergent copy in the sense that matters -- git already reconciles those.
SKIP_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules", ".claude",
    ".pytest_cache", ".mypy_cache", "site-packages", ".worktrees",
}

# ---------------------------------------------------------------------------
# WHAT a declared gap looks like. This is a heuristic and is stated as one.
# ---------------------------------------------------------------------------
# Section headers whose whole purpose is to admit something is missing.
GAP_SECTIONS = re.compile(
    r"^\W*(?:#+\s*)?("
    r"deliberately not(?:\s+done)?"
    r"|not (?:proposed|done|built|implemented|yet built)"
    r"|what it does not do|what this (?:does|is) not"
    r"|known limitations?|known issues?|limitations?"
    r"|out of scope|residual [a-z-]+ risk"
    r"|open (?:items?|questions?)|future work|todo"
    r")\b.*$",
    re.I | re.M)

# Inline admissions. Each of these was written by someone being honest about a
# hole; the point is that honesty currently goes nowhere.
GAP_PHRASES = [
    (r"plugs? in later", "deferred plug"),
    (r"\bnot (?:yet )?(?:built|wired|implemented|done)\b", "not built"),
    (r"\bnot wired (?:in|into)\b", "not wired"),
    (r"\bgated on\b", "gated"),
    (r"\bthe other half\b", "names another half"),
    (r"\bremains? (?:a |the )?(?:separate|other|human)\b", "delegated elsewhere"),
    (r"\bis a separate\b.{0,40}\bproblem\b", "declared out of scope"),
    (r"\bpending\b(?!\s+operator\s+confirmation)", "pending"),
    (r"\bTODO\b", "todo"),
    (r"\bnot a re-identification\b", "declared non-goal"),
    (r"\bnecessary,? not sufficient\b", "declares itself partial"),
    (r"\bhas (?:not|never) been (?:built|wired|run|tested)\b", "never exercised"),
    (r"\bstill needs? to be\b", "outstanding"),
    (r"\bnobody (?:has |ever )?\w+", "nobody-does-this"),
]

UNVERIFIED = re.compile(
    r"\b(EXPERIMENTAL|OPERATOR REVIEW REQUIRED|REVIEW REQUIRED|"
    r"NOT WIRED|UNRATIFIED|PROPOSED|DRAFT|UNVERIFIED)\b")

# A path-looking token inside prose or code.
PATHISH = re.compile(
    r"[`'\"]([A-Za-z0-9_\-./\\]+\.(?:py|md|json|jsonl|yaml|yml|txt))[`'\"]")


# ---------------------------------------------------------------------------
@dataclass
class Finding:
    kind: str
    subject: str
    detail: str
    where: list = field(default_factory=list)

    def line(self) -> str:
        return f"{self.kind:<15} {self.subject}"


@dataclass
class ToolFile:
    path: Path
    rel: str
    sha: str
    size: int
    summary: str = ""


def _iter_files(roots: list[Path]):
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if p.suffix.lower() not in SCAN_EXT:
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.is_file():
                yield p


# How much content two same-named files must share before they count as
# copies of one document rather than siblings that follow a naming convention.
# Tuned against the real tree: leakscan.py's two copies share ~0.95; the
# fifteen README.md files share ~0.0-0.05 with each other.
SIMILARITY_FLOOR = 0.40


def _similarity(a: str, b: str) -> float:
    """Jaccard overlap on substantial lines. Short lines are dropped because
    blank lines, `---`, and `)` are shared by every document ever written and
    would manufacture similarity out of punctuation."""
    la = {ln.strip() for ln in a.splitlines() if len(ln.strip()) > 12}
    lb = {ln.strip() for ln in b.splitlines() if len(ln.strip()) > 12}
    if not la or not lb:
        return 0.0
    return len(la & lb) / len(la | lb)


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _summary_of(text: str, path: Path) -> str:
    """First meaningful line of the docstring or markdown. Descriptive only --
    this is quoted back, never interpreted."""
    if path.suffix == ".py":
        m = re.search(r'"""(.*?)"""', text, re.S)
        if m:
            for line in m.group(1).strip().splitlines():
                s = line.strip()
                if s and not s.startswith(("---", "===")):
                    return s[:110]
    for line in text.splitlines():
        s = line.strip().lstrip("#").strip()
        if s and not s.startswith(("---", "===", "!", "[")):
            return s[:110]
    return ""


# ---------------------------------------------------------------------------
def collect(roots: list[Path], want_dangling: bool = False
            ) -> tuple[list[ToolFile], list[Finding]]:
    files: list[ToolFile] = []
    findings: list[Finding] = []
    by_name: dict[str, list[ToolFile]] = defaultdict(list)
    all_text: dict[str, str] = {}

    for p in _iter_files(roots):
        text = _read(p)
        if not text:
            continue
        sha = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:12]
        try:
            rel = str(p.relative_to(Path(r"C:\Users\dexjr")))
        except ValueError:
            rel = str(p)
        tf = ToolFile(path=p, rel=rel, sha=sha, size=len(text),
                      summary=_summary_of(text, p))
        files.append(tf)
        by_name[p.name].append(tf)
        all_text[rel] = text

    # ---- DIVERGENT_COPY --------------------------------------------------
    # Same name and DIFFERENT content is not sufficient. `README.md` exists in
    # fifteen project folders and all fifteen are correctly different
    # documents; flagging those buries the one finding that matters.
    #
    # The first cut did exactly that, and leakscan.py's own README had already
    # warned why it is fatal: "a scanner that cries wolf gets ignored, and an
    # ignored scanner is worse than none."
    #
    # A real divergent copy is the same DOCUMENT in two places, drifted. So the
    # test is content overlap: substantially-shared lines (a copy that moved
    # apart) but not identical (git already reconciles those).
    for name, group in sorted(by_name.items()):
        if len(group) < 2:
            continue
        pairs = []
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a.sha == b.sha:
                    continue          # identical: a clone, not a divergence
                sim = _similarity(all_text[a.rel], all_text[b.rel])
                if sim >= SIMILARITY_FLOOR:
                    pairs.append((a, b, sim))
        if not pairs:
            continue
        involved = {t.rel: t for p in pairs for t in (p[0], p[1])}
        worst = max(p[2] for p in pairs)
        findings.append(Finding(
            "DIVERGENT_COPY", name,
            f"{len(involved)} copies share {worst:.0%} of their content but are "
            f"NOT identical. One is stale and a reader cannot tell which.",
            [f"{t.rel}  [{t.sha}] {t.size:,}b"
             for t in sorted(involved.values(), key=lambda t: -t.size)]))

    # ---- DECLARED_GAP ----------------------------------------------------
    for tf in files:
        text = all_text[tf.rel]
        hits: list[str] = []

        for m in GAP_SECTIONS.finditer(text):
            ln = text[:m.start()].count("\n") + 1
            hits.append(f"L{ln}  section: {m.group(1).strip()}")

        for pat, label in GAP_PHRASES:
            for m in re.finditer(pat, text, re.I):
                ln = text[:m.start()].count("\n") + 1
                start = text.rfind("\n", 0, m.start()) + 1
                end = text.find("\n", m.end())
                sentence = text[start:end if end > 0 else len(text)].strip()
                sentence = re.sub(r"^[#\-*>\s]+", "", sentence)[:130]
                if sentence:
                    hits.append(f"L{ln}  [{label}] {sentence}")

        if hits:
            # Dedupe by line so one sentence matching two patterns lands once.
            seen, uniq = set(), []
            for h in hits:
                k = h.split("  ", 1)[0]
                if k not in seen:
                    seen.add(k)
                    uniq.append(h)
            findings.append(Finding(
                "DECLARED_GAP", tf.rel,
                f"{len(uniq)} declared gap(s) — the tool admits these itself",
                uniq[:12]))

    # ---- UNVERIFIED ------------------------------------------------------
    for tf in files:
        text = all_text[tf.rel]
        marks = sorted({m.group(1).upper() for m in UNVERIFIED.finditer(text)})
        if marks and tf.path.suffix == ".py":
            findings.append(Finding(
                "UNVERIFIED", tf.rel,
                f"declares its own standing as: {', '.join(marks)}",
                [tf.summary] if tf.summary else []))

    # ---- DANGLING_REF ---------------------------------------------- OPT-IN
    # DEMOTED, and the reason is worth reading before anyone promotes it back.
    #
    # It produced 471 hits across 128 files on the real tree, and spot-checking
    # showed the overwhelming majority are not defects:
    #   - docstring examples: x.py, fileA.txt, alpha.md, test.txt
    #   - runtime artifacts that do not exist until something runs:
    #     manifest.json, beacon.json, _backup_log.jsonl
    #   - CORRECT historical references: session logs citing dex-query.py,
    #     a file that was deliberately deleted in Step 50.3. The log is right.
    #
    # Telling those apart from a genuinely stale pointer needs to know whether
    # a document describes the present or the past, and I have no reliable
    # signal for that. Rather than ship a check that buries the register it
    # sits next to -- leakscan.py's README: "a scanner that cries wolf gets
    # ignored, and an ignored scanner is worse than none" -- it is off by
    # default and excluded from the exit code.
    #
    # Deleting it would hide that the check was tried and found wanting.
    known = {t.path.name for t in files}
    for tf in files if want_dangling else []:
        text = all_text[tf.rel]
        missing = []
        for m in PATHISH.finditer(text):
            ref = m.group(1)
            base = Path(ref).name
            if base in known:
                continue
            cand = (tf.path.parent / ref)
            if cand.exists() or Path(ref).exists():
                continue
            if any(x in ref for x in ("http", "://", "*")):
                continue
            ln = text[:m.start()].count("\n") + 1
            missing.append(f"L{ln}  {ref}")
        if missing:
            findings.append(Finding(
                "DANGLING_REF", tf.rel,
                f"{len(missing)} referenced path(s) not found on disk",
                missing[:8]))

    # ---- UNLANDED --------------------------------------------------------
    # A work product sitting in scratch with no tracked counterpart in any
    # repo. See SCRATCH_ROOTS for why this exists.
    tracked_names: set[str] = set()
    for repo in REPO_ROOTS:
        if not (repo / ".git").exists():
            continue
        try:
            out = subprocess.run(["git", "-C", str(repo), "ls-files"],
                                 capture_output=True, text=True, timeout=60)
            for line in out.stdout.splitlines():
                tracked_names.add(Path(line).name)
        except (OSError, subprocess.SubprocessError):
            # A repo we cannot query is a hole in the check, not a clean pass.
            findings.append(Finding(
                "UNLANDED", str(repo),
                "could not list tracked files — UNLANDED results below are "
                "incomplete and may report landed work as stranded", []))

    for scratch in SCRATCH_ROOTS:
        if not scratch.exists():
            continue
        stranded = []
        for p in scratch.rglob("*"):
            if p.suffix.lower() not in SCAN_EXT or not p.is_file():
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if SCRATCH_BY_DESIGN.match(p.name):
                continue
            if p.name in tracked_names:
                continue
            age = (time.time() - p.stat().st_mtime) / 86400
            stranded.append((age, p))
        if stranded:
            stranded.sort(reverse=True)
            findings.append(Finding(
                "UNLANDED", str(scratch),
                f"{len(stranded)} work product(s) with no tracked counterpart "
                f"anywhere. Written, not delivered.",
                [f"{age:5.1f}d  {p.stat().st_size:>8,}b  "
                 f"{p.relative_to(scratch)}" for age, p in stranded]))

    # ---- ORPHAN ----------------------------------------------------------
    # A .py that no other scanned file names. Weak signal on purpose: an
    # orphan may be perfectly good and simply new. Reported last, quietly.
    corpus = "\n".join(all_text.values())
    for tf in files:
        if tf.path.suffix != ".py":
            continue
        refs = corpus.count(tf.path.name)
        if refs <= 1:      # only its own filename inside itself, if that
            findings.append(Finding(
                "ORPHAN", tf.rel,
                "no other scanned file mentions this by name",
                [tf.summary] if tf.summary else []))

    return files, findings


# ---------------------------------------------------------------------------
ORDER = ["UNLANDED", "DIVERGENT_COPY", "DECLARED_GAP", "DANGLING_REF", "UNVERIFIED", "ORPHAN"]
MARK = {"UNLANDED": "!!", "DIVERGENT_COPY": "!!", "DECLARED_GAP": " ?", "DANGLING_REF": " ?",
        "UNVERIFIED": "  ", "ORPHAN": "  "}


def render(files: list[ToolFile], findings: list[Finding], only: str | None) -> None:
    print()
    print("DEX TOOL RECONCILE — what the tooling says about itself vs. what is there")
    print("=" * 78)
    print("This tool declares no inventory. Every line below is a file you can open.")
    print(f"Scanned {len(files)} file(s).\n")

    groups = defaultdict(list)
    for f in findings:
        groups[f.kind].append(f)

    for kind in ORDER:
        if only and kind != only:
            continue
        items = groups.get(kind, [])
        if not items:
            continue
        print("-" * 78)
        print(f"{kind}  ({len(items)})")
        print("-" * 78)
        for f in items:
            print(f"{MARK[kind]} {f.subject}")
            print(f"     {f.detail}")
            for w in f.where:
                print(f"       {w}")
            print()

    dup = len(groups.get("DIVERGENT_COPY", []))
    gap = sum(len(f.where) for f in groups.get("DECLARED_GAP", []))
    print("=" * 78)
    print(f"  {dup} divergent copy set(s) · {gap} declared gap(s) · "
          f"{len(groups.get('DANGLING_REF', []))} dangling reference(s)")
    print()
    print("  The declared-gap register is the point. Each line is a hole someone")
    print("  wrote down honestly and then nobody tracked. Read it beside the tool")
    print("  list and the overlaps become visible — which is the thing that was")
    print("  missing when two halves of one gate got built a fortnight apart.")
    print()
    print("  A clean register means no tool ADMITTED a gap in words this")
    print("  recognises. It does not mean there are none.")
    print("=" * 78)
    print()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="reconcile what tooling declares against what exists")
    ap.add_argument("--root", action="append", default=[], metavar="PATH",
                    help="scan root (repeatable). Defaults are used if omitted.")
    ap.add_argument("--gaps", action="store_true", help="declared-gap register only")
    ap.add_argument("--duplicates", action="store_true", help="divergent copies only")
    ap.add_argument("--dangling", action="store_true",
                    help="also report referenced paths not on disk. OFF by "
                         "default: ~90%% are docstring examples, runtime "
                         "artifacts, or correct historical citations. See the "
                         "note at the check.")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 — documented cp1252 hazard
            pass

    roots = [Path(r) for r in a.root] or DEFAULT_ROOTS
    files, findings = collect(roots, want_dangling=a.dangling)

    only = "DECLARED_GAP" if a.gaps else "DIVERGENT_COPY" if a.duplicates else None

    if a.json:
        print(json.dumps({
            "scanned": len(files),
            "findings": [asdict(f) for f in findings
                         if not only or f.kind == only],
        }, indent=2, default=str))
    else:
        render(files, findings, only)

    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())

