#!/usr/bin/env python3
"""
dex_ingest_ledger.py -- reconciliation ledger for the conversion stage.

THE DEFECT THIS EXISTS FOR
--------------------------
`dex-convert.py` sits between the source roots and the store. When a parse
aborted, an extension was unhandled, or a record failed to decode, the run
printed a WARN at most, returned an empty list, and exited 0. The corpus that
came out the other side looked clean: files existed, counts were plausible,
nothing failed. Nobody could say how many documents had been lost, because
nothing ever counted what went in.

That is how the first corpus was built. This is the layer that makes the
second corpus auditable.

THE ONE RULE THAT MAKES IT WORK
-------------------------------
**The ledger measures the input independently of the converter that parses it.**

If "units offered" came from the same parse that drops records, a parse that
aborts at row 90,000 reports 90,000 offered and 90,000 emitted -- a clean
ledger over a lossy run. So every input type has a *probe*: a cheap, separate,
failure-tolerant counter (physical CSV rows, `From ` lines in an mbox,
BEGIN:VCARD markers) that does not share code with the converter.

Same principle as dex-reconcile.py: declare nothing, measure everything.

THE ACCOUNTING IDENTITY
-----------------------
Per input file:

    units_offered == units_emitted + sum(units_dropped)

A run is CLEAN only if that holds for every file, every drop carries a reason
code, and every input file has a status. Loss is acceptable; *unattributed*
loss is not, and *unaccounted* loss -- the identity failing to balance -- is
the loudest thing this tool can say, because it means the converter lost
records by a path nobody has named yet.

STATUS CODES (per file)
-----------------------
  OK                every offered unit reached an output
  PARTIAL           some units dropped, all drops attributed
  TOTAL_LOSS        file produced no output at all, reason named
  SKIPPED           deliberately not converted, reason named
  UNACCOUNTED       identity does not balance  <- the bad one
  UNMEASURED        no probe exists for this type (stated, not hidden)

REASON CODES (per drop)
-----------------------
  OPEN_FAILED           input could not be opened
  PARSE_ABORT           parser raised mid-file; everything after is lost
  UNHANDLED_TYPE        no converter claimed this extension
  EMPTY_INPUT           file contained zero units
  RECORD_DECODE_FAILED  individual record raised
  RECORD_NO_CONTENT     record parsed but carried no text to emit
  RECORD_UNTERMINATED   record started and never closed (truncated source)
  LIMIT_REACHED         run-imposed cap stopped processing (deliberate loss)
  FIELD_TRUNCATED       record emitted, but content was cut (not a unit loss)
  RECORD_DEGRADED       record emitted, but part of it failed to decode
                        (not a unit loss — counted so it cannot hide inside one)

EXIT CODES
----------
  0  CLEAN             identity balances everywhere, no loss
  2  ATTRIBUTED_LOSS   loss occurred, every unit of it has a name
  3  UNACCOUNTED_LOSS  identity broken, or a file has no status
  4  LEDGER_ERROR      the ledger itself failed

`--allow-loss` downgrades 2 to 0 for runs where loss is expected and reviewed.
It can never downgrade 3.

Read-only with respect to the corpus. Writes one JSON ledger where told.

Dropdown Logistics -- Chaos -> Structured -> Automated
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# ── Vocabulary ────────────────────────────────────────────────────────────────

ST_OK          = "OK"
ST_PARTIAL     = "PARTIAL"
ST_TOTAL_LOSS  = "TOTAL_LOSS"
ST_SKIPPED     = "SKIPPED"
ST_UNACCOUNTED = "UNACCOUNTED"
ST_UNMEASURED  = "UNMEASURED"

R_OPEN_FAILED          = "OPEN_FAILED"
R_PARSE_ABORT          = "PARSE_ABORT"
R_UNHANDLED_TYPE       = "UNHANDLED_TYPE"
R_EMPTY_INPUT          = "EMPTY_INPUT"
R_RECORD_DECODE_FAILED = "RECORD_DECODE_FAILED"
R_RECORD_NO_CONTENT    = "RECORD_NO_CONTENT"
R_RECORD_UNTERMINATED  = "RECORD_UNTERMINATED"
R_LIMIT_REACHED        = "LIMIT_REACHED"
R_FIELD_TRUNCATED      = "FIELD_TRUNCATED"
R_RECORD_DEGRADED      = "RECORD_DEGRADED"

# Drops that do not remove a unit from the output -- they degrade one.
# Keeping these out of the identity is what stops a truncation from being
# mistaken for a loss, and a loss from hiding behind a truncation.
NON_UNIT_REASONS = {R_FIELD_TRUNCATED, R_RECORD_DEGRADED}

EXIT_CLEAN      = 0
EXIT_ATTRIBUTED = 2
EXIT_UNACCOUNTED = 3
EXIT_LEDGER_ERROR = 4

# ── Probes: independent input measurement ─────────────────────────────────────
#
# A probe answers "how many units does this file offer?" WITHOUT using the
# converter's parser. It must be failure-tolerant: a probe that raises on a
# damaged file is useless precisely when it matters. Return None only when no
# honest measurement is possible -- that surfaces as UNMEASURED, never as OK.


def probe_csv_rows(path: Path) -> int | None:
    """Physical CSV data rows. Tolerant: counts what the reader can reach,
    then falls back to raw newline counting for the remainder."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return None
    if not raw.strip():
        return 0
    text = raw.decode("utf-8", errors="replace")
    # csv module honours quoted embedded newlines; count through it where it
    # survives, and fall back to physical lines past the point it dies.
    rows = 0
    try:
        import io
        reader = csv.reader(io.StringIO(text, newline=""))
        for i, _row in enumerate(reader):
            if i == 0:
                continue  # header
            rows += 1
        return rows
    except (csv.Error, ValueError):
        # Damaged file: fall back to physical non-empty lines minus header.
        lines = [ln for ln in text.splitlines() if ln.strip()]
        return max(len(lines) - 1, 0)


def probe_json_units(path: Path) -> int | None:
    """Units in a JSON export. Recognises the shapes dex-convert claims to
    handle; returns 1 for an opaque-but-valid document; None if unreadable."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict):
        for key in ("Browser History", "messages", "items"):
            if isinstance(data.get(key), list):
                return len(data[key])
        return 1
    if isinstance(data, list):
        return len(data)
    return 1


def probe_vcf_cards(path: Path) -> int | None:
    """BEGIN:VCARD markers -- counts started cards, including unterminated
    ones. That asymmetry against END:VCARD is the point."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return sum(1 for ln in text.splitlines() if ln.startswith("BEGIN:VCARD"))


def probe_vcf_terminated(path: Path) -> int:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    return sum(1 for ln in text.splitlines() if ln.startswith("END:VCARD"))


def probe_mbox_messages(path: Path) -> int | None:
    """`From ` at line start is the mbox record separator. Counted raw so a
    mailbox the stdlib refuses to open still reports a denominator."""
    try:
        n = 0
        with open(path, "rb") as f:
            for line in f:
                if line.startswith(b"From "):
                    n += 1
        return n
    except OSError:
        return None


def probe_single_document(path: Path) -> int | None:
    """HTML and other whole-file documents: one unit, unless empty."""
    try:
        return 0 if Path(path).stat().st_size == 0 else 1
    except OSError:
        return None


PROBES = {
    "csv":        probe_csv_rows,
    "reddit-csv": probe_csv_rows,
    "json":       probe_json_units,
    "facebook":   probe_json_units,
    "vcf":        probe_vcf_cards,
    "mbox":       probe_mbox_messages,
    "html":       probe_single_document,
}


def probe_for(kind: str):
    return PROBES.get(kind)


def sha256_of(path: Path, cap: int = 64 * 1024 * 1024) -> str | None:
    """Content hash so a ledger can be matched to the exact bytes it describes.
    Capped so a 4GB mbox does not stall a run; truncation is disclosed."""
    try:
        h = hashlib.sha256()
        read = 0
        with open(path, "rb") as f:
            while True:
                b = f.read(1024 * 1024)
                if not b:
                    break
                read += len(b)
                h.update(b)
                if read >= cap:
                    return f"sha256-first{cap}:{h.hexdigest()}"
        return h.hexdigest()
    except OSError:
        return None


# ── Ledger entries ────────────────────────────────────────────────────────────

@dataclass
class Drop:
    reason: str
    count: int
    detail: str = ""

    def as_dict(self) -> dict:
        return {"reason": self.reason, "count": self.count, "detail": self.detail}


@dataclass
class FileEntry:
    source: str
    kind: str
    size_bytes: int | None = None
    sha256: str | None = None
    units_offered: int | None = None
    units_emitted: int = 0
    drops: list[Drop] = field(default_factory=list)
    outputs: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    status: str = ""
    # Character conservation across the chunker. Unit counts cannot see a
    # slice that loses text, because a chunked document is still one unit.
    chars_expected: int | None = None
    chars_written: int | None = None

    # -- recording ------------------------------------------------------------

    def emit(self, n: int = 1) -> None:
        self.units_emitted += n

    def drop(self, reason: str, n: int = 1, detail: str = "") -> None:
        for d in self.drops:
            if d.reason == reason and d.detail == detail:
                d.count += n
                return
        self.drops.append(Drop(reason, n, detail))

    def output(self, path: Path) -> None:
        p = Path(path)
        try:
            size = p.stat().st_size
        except OSError:
            size = None
        self.outputs.append({"path": str(p), "size_bytes": size})

    def note(self, text: str) -> None:
        self.notes.append(text)

    # -- derived --------------------------------------------------------------

    @property
    def units_dropped(self) -> int:
        return sum(d.count for d in self.drops if d.reason not in NON_UNIT_REASONS)

    @property
    def degradations(self) -> int:
        return sum(d.count for d in self.drops if d.reason in NON_UNIT_REASONS)

    def balance(self) -> int | None:
        """offered - (emitted + dropped). 0 means the identity holds."""
        if self.units_offered is None:
            return None
        return self.units_offered - (self.units_emitted + self.units_dropped)

    def settle(self) -> str:
        """Assign the status. Called once, by the ledger, at end_file."""
        if self.units_offered is None:
            # No denominator. If the file nonetheless produced nothing and a
            # reason was recorded, that is a total loss of unknown size --
            # report it as loss, not as "unmeasured", which reads like OK.
            if self.units_emitted == 0 and self.drops:
                self.status = ST_TOTAL_LOSS
            else:
                self.status = ST_UNMEASURED
        elif self.balance() != 0:
            self.status = ST_UNACCOUNTED
        elif self.units_offered == 0:
            self.status = ST_SKIPPED if self.drops else ST_OK
        elif self.units_emitted == 0:
            self.status = ST_TOTAL_LOSS
        elif self.units_dropped > 0:
            self.status = ST_PARTIAL
        else:
            self.status = ST_OK
        return self.status

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "kind": self.kind,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "units_offered": self.units_offered,
            "units_emitted": self.units_emitted,
            "units_dropped": self.units_dropped,
            "degradations": self.degradations,
            "balance": self.balance(),
            "chars_expected": self.chars_expected,
            "chars_written": self.chars_written,
            "status": self.status,
            "drops": [d.as_dict() for d in self.drops],
            "outputs": self.outputs,
            "notes": self.notes,
        }


# ── The ledger ────────────────────────────────────────────────────────────────

class Ledger:
    def __init__(self, tool: str = "unknown", run_args: list[str] | None = None):
        self.tool = tool
        self.run_args = run_args if run_args is not None else list(sys.argv[1:])
        self.started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.finished: str | None = None
        self.files: list[FileEntry] = []
        self.errors: list[str] = []
        self.scope_notes: list[str] = []

    def note_scope(self, text: str) -> None:
        """Record what the run deliberately did not look at. Scope is not
        loss, but a ledger that omits it invites the reader to assume the
        denominator was the whole root."""
        self.scope_notes.append(text)

    # -- recording ------------------------------------------------------------

    def begin_file(self, path, kind: str, units_offered: int | None = "auto") -> FileEntry:
        p = Path(path)
        try:
            size = p.stat().st_size
        except OSError:
            size = None
        if units_offered == "auto":
            probe = probe_for(kind)
            units_offered = probe(p) if probe else None
        e = FileEntry(
            source=str(p),
            kind=kind,
            size_bytes=size,
            sha256=sha256_of(p),
            units_offered=units_offered,
        )
        return e

    def end_file(self, entry: FileEntry) -> FileEntry:
        entry.settle()
        self.files.append(entry)
        return entry

    def record_skip(self, path, kind: str, reason: str, detail: str = "",
                    count: int = 1) -> FileEntry:
        """An input the converter chose not to process. Unhandled extensions
        were previously a bare `continue`; this is what makes them visible.

        The default count of 1 is deliberate: a skipped file is a file whose
        contents did not reach the store, and it should move the run off
        CLEAN. Reviewers who accept the skip pass --allow-loss."""
        e = self.begin_file(path, kind, units_offered=None)
        e.drop(reason, count, detail)
        e.status = ST_SKIPPED
        self.files.append(e)
        return e

    def ledger_error(self, msg: str) -> None:
        self.errors.append(msg)

    def finish(self) -> None:
        self.finished = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # -- invariants -----------------------------------------------------------

    def invariants(self) -> list[dict]:
        """Each invariant is checked over the recorded entries and reported
        pass/fail with the entries that broke it. Nothing here is declared in
        advance -- these are identities, not expectations."""
        inv = []

        broken = [f for f in self.files if f.status == ST_UNACCOUNTED]
        inv.append({
            "id": "INV-1-IDENTITY",
            "statement": "units_offered == units_emitted + units_dropped, per file",
            "pass": not broken,
            "violations": [
                {"source": f.source, "offered": f.units_offered,
                 "emitted": f.units_emitted, "dropped": f.units_dropped,
                 "balance": f.balance()}
                for f in broken
            ],
        })

        unattributed = [
            {"source": f.source, "count": d.count}
            for f in self.files for d in f.drops if not d.reason
        ]
        inv.append({
            "id": "INV-2-ATTRIBUTION",
            "statement": "every dropped unit carries a reason code",
            "pass": not unattributed,
            "violations": unattributed,
        })

        statusless = [f.source for f in self.files if not f.status]
        inv.append({
            "id": "INV-3-COVERAGE",
            "statement": "every input touched by the run has a status",
            "pass": not statusless,
            "violations": statusless,
        })

        no_output = [
            f.source for f in self.files
            if f.units_emitted > 0 and not f.outputs
        ]
        inv.append({
            "id": "INV-4-MATERIALISED",
            "statement": "units emitted implies at least one output file exists",
            "pass": not no_output,
            "violations": no_output,
        })

        missing = [
            o["path"] for f in self.files for o in f.outputs
            if o["size_bytes"] in (None, 0)
        ]
        inv.append({
            "id": "INV-5-NONEMPTY-OUTPUT",
            "statement": "every declared output file exists and is non-empty",
            "pass": not missing,
            "violations": missing,
        })

        lossy_chunks = [
            {"source": f.source, "expected": f.chars_expected, "written": f.chars_written}
            for f in self.files
            if f.chars_expected is not None and f.chars_written != f.chars_expected
        ]
        inv.append({
            "id": "INV-7-CHARS-CONSERVED",
            "statement": "chunking wrote exactly the characters it was given",
            "pass": not lossy_chunks,
            "violations": lossy_chunks,
        })

        silent = [
            f.source for f in self.files
            if (f.size_bytes or 0) > 0 and not f.outputs and not f.drops
            and f.status != ST_SKIPPED
        ]
        inv.append({
            "id": "INV-6-NO-SILENT-VOID",
            "statement": "an input with bytes produced either an output or an attributed drop",
            "pass": not silent,
            "violations": silent,
        })

        return inv

    # -- rollup ---------------------------------------------------------------

    def totals(self) -> dict:
        offered = sum(f.units_offered or 0 for f in self.files)
        emitted = sum(f.units_emitted for f in self.files)
        dropped = sum(f.units_dropped for f in self.files)
        by_reason: dict[str, int] = {}
        for f in self.files:
            for d in f.drops:
                by_reason[d.reason] = by_reason.get(d.reason, 0) + d.count
        by_status: dict[str, int] = {}
        for f in self.files:
            by_status[f.status] = by_status.get(f.status, 0) + 1
        return {
            "files_in": len(self.files),
            "files_out": sum(len(f.outputs) for f in self.files),
            "units_offered": offered,
            "units_emitted": emitted,
            "units_dropped": dropped,
            "unmeasured_files": sum(1 for f in self.files if f.units_offered is None),
            "by_status": by_status,
            "by_reason": by_reason,
        }

    def verdict(self) -> str:
        if self.errors:
            return "LEDGER_ERROR"
        if any(not i["pass"] for i in self.invariants()):
            return "UNACCOUNTED_LOSS"
        t = self.totals()
        if t["units_dropped"] > 0:
            return "ATTRIBUTED_LOSS"
        return "CLEAN"

    def exit_code(self, allow_loss: bool = False) -> int:
        v = self.verdict()
        if v == "LEDGER_ERROR":
            return EXIT_LEDGER_ERROR
        if v == "UNACCOUNTED_LOSS":
            return EXIT_UNACCOUNTED
        if v == "ATTRIBUTED_LOSS":
            return EXIT_CLEAN if allow_loss else EXIT_ATTRIBUTED
        return EXIT_CLEAN

    # -- output ---------------------------------------------------------------

    def as_dict(self) -> dict:
        return {
            "ledger_version": 1,
            "tool": self.tool,
            "args": self.run_args,
            "started_utc": self.started,
            "finished_utc": self.finished,
            "scope_notes": self.scope_notes,
            "totals": self.totals(),
            "invariants": self.invariants(),
            "verdict": self.verdict(),
            "ledger_errors": self.errors,
            "files": [f.as_dict() for f in self.files],
        }

    def write_json(self, path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.as_dict(), indent=2), encoding="utf-8")
        return p

    def report(self, stream=None, verbose: bool = False) -> None:
        out = stream or sys.stdout
        t = self.totals()
        w = out.write
        w("\n" + "=" * 68 + "\n")
        w("  RECONCILIATION LEDGER — %s\n" % self.tool)
        w("=" * 68 + "\n")
        w("  files in ......... %d\n" % t["files_in"])
        w("  files out ........ %d\n" % t["files_out"])
        w("  units offered .... %d\n" % t["units_offered"])
        w("  units emitted .... %d\n" % t["units_emitted"])
        w("  units dropped .... %d\n" % t["units_dropped"])
        if t["unmeasured_files"]:
            w("  unmeasured files . %d  (no probe for type — stated, not hidden)\n"
              % t["unmeasured_files"])

        if self.scope_notes:
            w("\n  SCOPE (what this run did not look at)\n")
            for n in self.scope_notes:
                w("    %s\n" % n)

        if t["by_status"]:
            w("\n  STATUS\n")
            for k in sorted(t["by_status"]):
                w("    %-14s %d\n" % (k, t["by_status"][k]))

        if t["by_reason"]:
            w("\n  LOSS BY REASON\n")
            for k in sorted(t["by_reason"], key=lambda r: -t["by_reason"][r]):
                w("    %-22s %d\n" % (k, t["by_reason"][k]))

        problems = [f for f in self.files
                    if f.status in (ST_UNACCOUNTED, ST_TOTAL_LOSS, ST_PARTIAL, ST_SKIPPED)]
        if problems:
            w("\n  DISCREPANCIES (%d)\n" % len(problems))
            for f in problems:
                w("    [%s] %s\n" % (f.status, f.source))
                w("        offered=%s emitted=%d dropped=%d balance=%s\n"
                  % (f.units_offered, f.units_emitted, f.units_dropped, f.balance()))
                for d in f.drops:
                    w("        - %s x%d %s\n" % (d.reason, d.count,
                                                 ("(%s)" % d.detail) if d.detail else ""))
                for n in f.notes:
                    w("        note: %s\n" % n)

        w("\n  INVARIANTS\n")
        for i in self.invariants():
            w("    [%s] %s — %s\n" % ("PASS" if i["pass"] else "FAIL",
                                      i["id"], i["statement"]))
            if not i["pass"]:
                for v in i["violations"][:10]:
                    w("        %s\n" % (v,))
                if len(i["violations"]) > 10:
                    w("        ... and %d more\n" % (len(i["violations"]) - 10))

        if self.errors:
            w("\n  LEDGER ERRORS\n")
            for e in self.errors:
                w("    %s\n" % e)

        if verbose:
            w("\n  PER-FILE\n")
            for f in self.files:
                w("    [%s] %-9s offered=%s emitted=%d  %s\n"
                  % (f.status, f.kind, f.units_offered, f.units_emitted, f.source))

        w("\n  VERDICT: %s\n" % self.verdict())
        w("=" * 68 + "\n\n")


# ── Standalone verification of an existing ledger file ────────────────────────

def verify_ledger_file(path: Path, allow_loss: bool = False) -> int:
    """Re-derive the verdict from a written ledger, without trusting the
    verdict it recorded. A ledger that disagrees with its own contents is
    itself a finding."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print("  [FAIL] cannot read ledger: %s" % e, file=sys.stderr)
        return EXIT_LEDGER_ERROR

    problems = []
    dropped = 0
    for f in data.get("files", []):
        off, em, dr = f.get("units_offered"), f.get("units_emitted", 0), f.get("units_dropped", 0)
        dropped += dr
        if off is not None and off != em + dr:
            problems.append("identity broken: %s (%s != %s + %s)" % (f.get("source"), off, em, dr))
        if not f.get("status"):
            problems.append("no status: %s" % f.get("source"))
    for i in data.get("invariants", []):
        if not i.get("pass"):
            problems.append("invariant %s failed" % i.get("id"))

    recomputed = ("UNACCOUNTED_LOSS" if problems
                  else "ATTRIBUTED_LOSS" if dropped
                  else "CLEAN")
    recorded = data.get("verdict")
    print("  ledger:     %s" % path)
    print("  recorded:   %s" % recorded)
    print("  recomputed: %s" % recomputed)
    if recorded != recomputed:
        print("  [FAIL] recorded verdict disagrees with contents", file=sys.stderr)
        return EXIT_LEDGER_ERROR
    for p in problems:
        print("  - %s" % p)
    if recomputed == "UNACCOUNTED_LOSS":
        return EXIT_UNACCOUNTED
    if recomputed == "ATTRIBUTED_LOSS":
        return EXIT_CLEAN if allow_loss else EXIT_ATTRIBUTED
    return EXIT_CLEAN


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Verify a reconciliation ledger written by dex-convert.py")
    ap.add_argument("ledger", help="path to a ledger JSON file")
    ap.add_argument("--allow-loss", action="store_true",
                    help="treat fully attributed loss as acceptable (exit 0)")
    a = ap.parse_args()
    return verify_ledger_file(Path(a.ledger), a.allow_loss)


if __name__ == "__main__":
    sys.exit(main())
