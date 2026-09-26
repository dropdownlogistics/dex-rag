#!/usr/bin/env python3
"""
dexjr_respond.py — DexJr Exchange Responder (specimen)

Makes the DexJr corpus a *correspondent* on the DDL Exchange. Any session on any
machine sends a question envelope to station `reborn-dexjr`; this script answers
by mail, with source citations recorded in `source_artifacts`.

    ddlx send --to reborn-dexjr --scope question --subject "..." --body "..."
    python dexjr_respond.py            # answers pending questions
    -> reply envelope REBORN-DEXJR-#### lands in outbox, thread-linked

WHAT IT DOES (one pass, then exits):
  1. Scans <messages-root>/inbox for envelopes with scope==question addressed
     to `reborn-dexjr` that do not yet have a reborn-dexjr reply.
  2. For each, asks the corpus via the Reborn REST API (/ask): retrieve top-N
     chunks + generate a grounded answer.
  3. Emits a reply envelope by shelling out to ddlx.ps1 `reply`, which builds
     the doctor-clean triplicate, links thread_id / in_reply_to, and records the
     retrieved file paths in source_artifacts.

DESIGN NOTES:
  - NO DAEMON. Exchange v0 forbids always-on processes. This is manual-trigger:
    it processes what is pending and exits. The scheduled/always-on version is a
    separate, separately-authorized step.
  - DECONFLICTION. This script never restarts the API, never opens ChromaDB, and
    never touches sshd/authorized_keys. It only reads inbox, makes a read-only
    /ask HTTP call, and asks ddlx to write the outbox. If the API is down it
    reports and exits without writing — nothing to clean up, safe to re-run.
  - ENGINE REUSE. `ask_corpus()` is the shared retrieve+generate core, importable
    by the forthcoming "Ask MindFrame" CLI (`from dexjr_respond import ask_corpus`)
    so both faces run one engine.
  - IDEMPOTENT. Re-running is safe: a question that already has a reborn-dexjr
    reply is skipped.

Stdlib only — runs under any Python 3.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

STATION = "reborn-dexjr"
DEFAULT_ROOT = r"C:\Users\dexjr\ddl-operations\messages"
DEFAULT_DDLX = r"C:\Users\dexjr\ddl-operations\ddlx.ps1"
DEFAULT_API = "http://127.0.0.1:8765"

# Boxes to scan when deciding whether a question is already answered.
REPLY_BOXES = ("outbox", "sent", "archive")


# ---------------------------------------------------------------------------
# Engine — shared retrieve+generate core (also imported by the Ask MindFrame CLI)
# ---------------------------------------------------------------------------

def ask_corpus(
    query: str,
    api_base: str = DEFAULT_API,
    n_results: int = 5,
    threshold: float | None = 0.9,
    timeout: float = 120.0,
) -> tuple[str, list[str], dict[str, Any]]:
    """
    Ask the DexJr corpus one question via the Reborn REST API.

    Returns (answer, source_paths, raw_response). source_paths are the file_path
    values of the retrieved chunks, de-duplicated in rank order — these become the
    envelope's source_artifacts. Raises RuntimeError on any API failure so callers
    can report and skip rather than emit an ungrounded reply.
    """
    payload = json.dumps(
        {"query": query, "n_results": n_results, "threshold": threshold}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{api_base.rstrip('/')}/ask",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"/ask returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"/ask unreachable at {api_base}: {exc}") from exc

    answer = (data.get("answer") or "").strip()
    if not answer:
        raise RuntimeError("/ask returned an empty answer")

    seen: set[str] = set()
    sources: list[str] = []
    for chunk in data.get("sources", []):
        fp = chunk.get("file_path")
        if fp and fp not in seen:
            seen.add(fp)
            sources.append(fp)
    return answer, sources, data


# ---------------------------------------------------------------------------
# Exchange lane — envelope discovery
# ---------------------------------------------------------------------------

def _load_metadata(msg_dir: Path) -> dict[str, Any] | None:
    """Parse a MSG-* folder's message.json. Returns metadata dict or None."""
    mj = msg_dir / "message.json"
    if not mj.is_file():
        return None
    try:
        obj = json.loads(mj.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    meta = obj.get("metadata")
    return meta if isinstance(meta, dict) else None


def _station_of(meta: dict[str, Any]) -> str:
    frm = meta.get("from") or {}
    return str(frm.get("station") or "").lower()


def find_answered_ids(root: Path) -> set[str]:
    """message_ids that already have a reply from this station (idempotency)."""
    answered: set[str] = set()
    for box in REPLY_BOXES:
        box_dir = root / box
        if not box_dir.is_dir():
            continue
        for msg_dir in box_dir.glob("MSG-*"):
            meta = _load_metadata(msg_dir)
            if not meta:
                continue
            if _station_of(meta) == STATION and meta.get("in_reply_to"):
                answered.add(str(meta["in_reply_to"]))
    return answered


def find_pending_questions(root: Path) -> list[dict[str, Any]]:
    """
    Questions in inbox addressed to this station, scope==question, not from this
    station, and not already answered. Returns their metadata dicts.
    """
    inbox = root / "inbox"
    if not inbox.is_dir():
        return []
    answered = find_answered_ids(root)
    pending: list[dict[str, Any]] = []
    for msg_dir in sorted(inbox.glob("MSG-*")):
        meta = _load_metadata(msg_dir)
        if not meta:
            continue
        to = [str(t).lower() for t in (meta.get("to") or [])]
        if STATION not in to:
            continue
        if str(meta.get("scope", "")).lower() != "question":
            continue
        if _station_of(meta) == STATION:
            continue  # never answer our own mail
        if str(meta.get("message_id")) in answered:
            continue
        pending.append(meta)
    return pending


# ---------------------------------------------------------------------------
# Exchange lane — reply emission (delegated to ddlx.ps1, the schema authority)
# ---------------------------------------------------------------------------

def emit_reply(
    question_id: str,
    body: str,
    source_paths: list[str],
    root: Path,
    ddlx_path: str,
    pwsh: str,
) -> str:
    """
    Shell out to ddlx.ps1 `reply` to write a doctor-clean reply envelope.
    ddlx auto-links thread_id / in_reply_to / recipient from the question and
    stamps source_artifacts. Returns the created outbox folder path.
    """
    with tempfile.NamedTemporaryFile(
        "w", suffix=".md", encoding="utf-8", delete=False
    ) as tf:
        tf.write(body)
        body_file = tf.name

    try:
        cmd = [
            pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", ddlx_path, "reply", question_id,
            "--root", str(root),
            "--station", STATION,
            "--scope", "result",
            "--body-file", body_file,
        ]
        if source_paths:
            cmd += ["--source-artifacts", ",".join(source_paths)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"ddlx reply failed (exit {proc.returncode}): "
                f"{proc.stderr.strip() or proc.stdout.strip()}"
            )
        return proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    finally:
        try:
            Path(body_file).unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Reply formatting
# ---------------------------------------------------------------------------

def format_body(question_meta: dict[str, Any], answer: str, sources: list[str]) -> str:
    """Assemble the reply body: answer + a human-readable citation list."""
    lines = [answer.rstrip(), ""]
    lines.append("---")
    if sources:
        lines.append("**Sources** (retrieved chunks grounding this answer; "
                     "canonical list in `source_artifacts`):")
        for s in sources:
            lines.append(f"- {s}")
    else:
        lines.append("**Sources**: none returned above the retrieval threshold. "
                     "Treat this answer as low-confidence.")
    lines.append("")
    lines.append("-- DexJr (reborn-dexjr) · corpus responder · answered by mail")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DexJr Exchange Responder (single pass, no daemon)")
    ap.add_argument("--messages-root", default=DEFAULT_ROOT,
                    help=f"Exchange message lane (default: {DEFAULT_ROOT})")
    ap.add_argument("--api", default=DEFAULT_API,
                    help=f"Reborn API base URL (default: {DEFAULT_API})")
    ap.add_argument("--ddlx", default=DEFAULT_DDLX,
                    help=f"Path to ddlx.ps1 (default: {DEFAULT_DDLX})")
    ap.add_argument("--pwsh", default="pwsh",
                    help="PowerShell 7 executable used to run ddlx (default: pwsh)")
    ap.add_argument("--n-results", type=int, default=5, help="Chunks to retrieve (default: 5)")
    ap.add_argument("--threshold", type=float, default=0.9,
                    help="Max cosine distance for retrieval (default: 0.9)")
    ap.add_argument("--limit", type=int, default=0,
                    help="Max questions to answer this pass (0 = all)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show what would be answered without writing any envelope")
    args = ap.parse_args(argv)

    root = Path(args.messages_root)
    if not root.is_dir():
        print(f"ERROR: messages root not found: {root}", file=sys.stderr)
        return 2

    pending = find_pending_questions(root)
    if not pending:
        print(f"No pending questions for {STATION} in {root / 'inbox'}. Nothing to do.")
        return 0

    if args.limit > 0:
        pending = pending[: args.limit]

    print(f"{'DRY-RUN: ' if args.dry_run else ''}{len(pending)} pending "
          f"question(s) for {STATION}:")

    failures = 0
    for meta in pending:
        qid = str(meta.get("message_id"))
        sender = _station_of(meta) or "unknown"
        subject = meta.get("subject", "")
        # The question text: prefer the subject; fall back to body if present.
        body_path = root / "inbox" / f"MSG-{qid}" / "message.json"
        question_text = subject
        try:
            obj = json.loads(body_path.read_text(encoding="utf-8"))
            if obj.get("body"):
                question_text = f"{subject}\n\n{obj['body']}".strip()
        except (OSError, json.JSONDecodeError):
            pass

        print(f"\n  [{qid}] from {sender}: {subject!r}")

        try:
            answer, sources, raw = ask_corpus(
                question_text, api_base=args.api,
                n_results=args.n_results, threshold=args.threshold,
            )
        except RuntimeError as exc:
            print(f"    SKIP — corpus unavailable: {exc}")
            failures += 1
            continue

        print(f"    answer: {len(answer)} chars, {len(sources)} source(s), "
              f"{raw.get('elapsed_ms', '?')}ms")
        for s in sources:
            print(f"      - {s}")

        if args.dry_run:
            print("    (dry-run: no envelope written)")
            continue

        body = format_body(meta, answer, sources)
        try:
            folder = emit_reply(qid, body, sources, root, args.ddlx, args.pwsh)
            print(f"    REPLY WRITTEN: {folder}")
        except RuntimeError as exc:
            print(f"    ERROR emitting reply: {exc}")
            failures += 1

    print(f"\nDone. {len(pending) - failures} answered, {failures} failed/skipped.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
