#!/usr/bin/env python3
"""
routines.py — Dex's autonomous routine engine.

A routine is a scheduled job: it runs on a timer (or on demand), does work against
Dex's brain, writes an artifact into his SANDBOX, and logs the run. This is the
reusable spine — jobs are pluggable entries, exactly like the programs registry.

Governance: a routine's output is NOT trusted. It lands in the sandbox for review
(and later promotion to canon). Autonomy is only safe because of that review gate.

Substrate (created on import):
  <sandbox>/artifacts/   — routine outputs (dated .md files)
  <sandbox>/runs.jsonl   — append-only run log (audit trail)
  <sandbox>/state.json   — per-routine {last_run, enabled} (survives restart)
"""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

import engine

SANDBOX = Path(r"C:\Users\dexjr\dex-sandbox")
ARTIFACTS = SANDBOX / "artifacts"
RUN_LOG = SANDBOX / "runs.jsonl"
STATE = SANDBOX / "state.json"
LAST_FABRIC = SANDBOX / "last_fabric.json"      # for heartbeat drift detection

HERE = Path(__file__).resolve().parent
SIGNAL_LOG = HERE / "signal_log.jsonl"
FABRIC_PY = Path(r"C:\Users\dexjr\ddl-org\_toolkit\incubating\fabric\fabric.py")

for _d in (SANDBOX, ARTIFACTS):
    _d.mkdir(parents=True, exist_ok=True)


def _now() -> datetime.datetime:
    return datetime.datetime.now()


def _stamp(dt: datetime.datetime | None = None) -> str:
    return (dt or _now()).isoformat(timespec="seconds")


# ── jobs ─────────────────────────────────────────────────────────────────────
# A job takes nothing, does its work against Dex's brain, writes an artifact, and
# returns (artifact_filename, one_line_summary). Add a job, register it below.

_MINE_QUERY = ("recurring themes, decisions, commitments, and open questions "
               "across Dex threads, conversations, and council reviews")


def job_thread_miner() -> tuple[str, str]:
    """Read a batch from the corpus and digest it into a dated review artifact."""
    sources = engine.search(_MINE_QUERY, top_k=8)["sources"]
    directive = (
        "You are Dex, mining your own archive for your operator to review. From the "
        "corpus excerpts below, produce a SHORT digest:\n"
        "1) 3–5 notable patterns or recurring themes\n"
        "2) any decisions or commitments you find\n"
        "3) open questions worth revisiting\n"
        "Ground every point in the excerpts — do not invent. Be concise."
    )
    prompt = engine._grounded_prompt(directive, "Produce the digest.", sources)
    digest = engine._ollama_generate(prompt, "dexjr", timeout=300.0)
    day = _now().strftime("%Y-%m-%d_%H%M")
    fname = f"thread-digest_{day}.md"
    body = (f"# Thread Digest — {_stamp()}\n\n"
            f"_Autonomous run by Dex (thread-miner). Grounded in {len(sources)} "
            f"corpus excerpts. FOR REVIEW — not canon._\n\n{digest}\n\n"
            f"---\nSources: " + ", ".join(sorted({s['file'] for s in sources})) + "\n")
    (ARTIFACTS / fname).write_text(body, encoding="utf-8")
    return fname, f"digested {len(sources)} excerpts → {fname}"


def job_fabric_heartbeat() -> tuple[str, str]:
    """Scan the compute fabric, and — the Silas part — DIFF against the last
    heartbeat so *changes* surface, not just a snapshot. Drift is the signal:
    a service that flipped, a node that dropped. This is the doctrine set to watch."""
    r = subprocess.run([sys.executable, str(FABRIC_PY), "--json"], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=60)
    report = json.loads(r.stdout)
    prev = {}
    if LAST_FABRIC.exists():
        try:
            prev = json.loads(LAST_FABRIC.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            prev = {}
    prev_states = {(c["host"], c["service"]): c["state"] for c in prev.get("checks", [])}
    changes = []
    for c in report.get("checks", []):
        old = prev_states.get((c["host"], c["service"]))
        if old is not None and old != c["state"]:
            changes.append(f"{c['host']}/{c['service']}: {old} → {c['state']}")
    prev_nodes = prev.get("nodes", {})
    for n, on in report.get("nodes", {}).items():
        if n in prev_nodes and prev_nodes[n] != on:
            changes.append(f"node {n}: {'up' if prev_nodes[n] else 'offline'} → "
                           f"{'up' if on else 'offline'}")
    LAST_FABRIC.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [f"# Fabric Heartbeat — {_stamp()}", "",
             f"**Verdict: {report.get('verdict')}**", ""]
    if changes:
        lines.append("## ⚠ Changes since last heartbeat")
        lines += [f"- {c}" for c in changes]
    else:
        lines.append("_No changes since last heartbeat._")
    lines += ["", "## Current state"]
    for c in report.get("checks", []):
        lines.append(f"- `{c['state']:8s}` {c['host']}/{c['service']} — {c.get('detail', '')}")
    day = _now().strftime("%Y-%m-%d_%H%M")
    fname = f"fabric-heartbeat_{day}.md"
    (ARTIFACTS / fname).write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = report.get("verdict", "?") + (f" · {len(changes)} change(s)" if changes else " · no change")
    return fname, summary


def _read_signals() -> list[dict]:
    out = []
    if SIGNAL_LOG.exists():
        for line in SIGNAL_LOG.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    pass
    return out


def job_signal_digest() -> tuple[str, str]:
    """Synthesize what the operator flagged (signal_log) into themes — what's been
    on his mind. The modality was the signal; this reads the pattern in it."""
    entries = _read_signals()
    day = _now().strftime("%Y-%m-%d_%H%M")
    fname = f"signal-digest_{day}.md"
    if not entries:
        (ARTIFACTS / fname).write_text(
            f"# Signal Digest — {_stamp()}\n\n_No signals captured yet._\n", encoding="utf-8")
        return fname, "no signals yet"
    recent = entries[-60:]
    texts = "\n".join(f"[{e.get('kind')}] {e.get('text', '')}" for e in recent)
    directive = ("You are Dex. Below are things your operator flagged as important — "
                 "by voice-typing them (too complex to type) or having you read them "
                 "aloud (worth hearing). Synthesize them into 2–4 themes: what's been on "
                 "his mind. Be concise and ground each theme in the items.")
    digest = engine._ollama_generate(f"{directive}\n\nFLAGGED ITEMS:\n{texts}\n\nThemes:",
                                     "dexjr", timeout=200.0)
    body = (f"# Signal Digest — {_stamp()}\n\n_From {len(recent)} flagged signals. "
            f"FOR REVIEW._\n\n{digest}\n")
    (ARTIFACTS / fname).write_text(body, encoding="utf-8")
    return fname, f"digested {len(recent)} signals → themes"


def job_morning_briefing() -> tuple[str, str]:
    """A factual start-your-day read: fabric verdict, recent signals, latest routine
    outputs, recent runs. Assembled from real state — no guessing."""
    fabric_verdict = "unknown"
    if LAST_FABRIC.exists():
        try:
            fabric_verdict = json.loads(LAST_FABRIC.read_text(encoding="utf-8")).get("verdict", "unknown")
        except Exception:  # noqa: BLE001
            pass
    sigs = _read_signals()
    since = _now() - datetime.timedelta(days=1)
    recent_sigs = [s for s in sigs if s.get("ts", "") >= since.isoformat(timespec="seconds")]
    runs = recent_runs(8)
    arts = sorted(ARTIFACTS.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]

    lines = [f"# Morning Briefing — {_now().strftime('%A, %Y-%m-%d')}", ""]
    lines.append(f"**Fabric:** {fabric_verdict}")
    lines.append(f"**Signals (last 24h):** {len(recent_sigs)} flagged"
                 + (f" — {sum(1 for s in recent_sigs if s.get('kind') == 'spoke')} spoken, "
                    f"{sum(1 for s in recent_sigs if s.get('kind') == 'read')} read" if recent_sigs else ""))
    lines += ["", "**Latest sandbox artifacts:**"]
    lines += [f"- {p.name}" for p in arts] or ["- (none yet)"]
    lines += ["", "**Recent routine runs:**"]
    lines += [f"- {r.get('ts', '')} · {r.get('routine')} · {r.get('status')} · {r.get('summary', '')}"
              for r in runs] or ["- (none yet)"]
    lines += ["", "_Assembled from real state — nothing inferred._"]
    day = _now().strftime("%Y-%m-%d_%H%M")
    fname = f"morning-briefing_{day}.md"
    (ARTIFACTS / fname).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return fname, f"fabric {fabric_verdict} · {len(recent_sigs)} signals/24h"


# ── registry ─────────────────────────────────────────────────────────────────
# schedule_hours = how often it should run (None = manual only).
ROUTINES: list[dict] = [
    {
        "id": "thread_miner",
        "name": "Thread Miner",
        "schedule_hours": 24,
        "description": "Mines old threads for patterns, decisions, and open questions "
                       "— writes a dated digest to the sandbox for review.",
        "enabled_default": False,   # off until the operator turns it on
        "job": job_thread_miner,
    },
    {
        "id": "fabric_heartbeat",
        "name": "Fabric Heartbeat",
        "schedule_hours": 6,
        "description": "Scans the compute fabric and flags what CHANGED since last time "
                       "— a service that flipped, a node that dropped. Drift, not just a "
                       "snapshot. The Drift Sentinel seed.",
        "enabled_default": False,
        "job": job_fabric_heartbeat,
    },
    {
        "id": "signal_digest",
        "name": "Signal Digest",
        "schedule_hours": 168,      # weekly
        "description": "Synthesizes what you flagged (voice-typed / had Dex read) into "
                       "themes — what's been on your mind.",
        "enabled_default": False,
        "job": job_signal_digest,
    },
    {
        "id": "morning_briefing",
        "name": "Morning Briefing",
        "schedule_hours": 24,
        "description": "A factual start-your-day read: fabric verdict, recent signals, "
                       "latest artifacts, recent runs. Assembled from real state.",
        "enabled_default": False,
        "job": job_morning_briefing,
    },
]

_BY_ID = {r["id"]: r for r in ROUTINES}


# ── state (persisted) ────────────────────────────────────────────────────────

def _load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — corrupt state resets, never crashes the engine
            return {}
    return {}


def _save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _routine_state(rid: str) -> dict:
    st = _load_state().get(rid, {})
    prog = _BY_ID.get(rid, {})
    return {"last_run": st.get("last_run"),
            "enabled": st.get("enabled", prog.get("enabled_default", False))}


def set_enabled(rid: str, enabled: bool) -> None:
    state = _load_state()
    state.setdefault(rid, {})["enabled"] = bool(enabled)
    _save_state(state)


def _mark_run(rid: str, ts: str) -> None:
    state = _load_state()
    state.setdefault(rid, {})["last_run"] = ts
    _save_state(state)


# ── run + list ───────────────────────────────────────────────────────────────

def _append_run_log(rec: dict) -> None:
    with open(RUN_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run_routine(rid: str) -> dict:
    """Execute one routine now: run its job, write the artifact, log the run,
    stamp last_run. Used by both the scheduler and the Run-Now button."""
    prog = _BY_ID.get(rid)
    if prog is None:
        raise ValueError(f"unknown routine: {rid}")
    started = _stamp()
    try:
        artifact, summary = prog["job"]()
        rec = {"ts": started, "routine": rid, "status": "ok",
               "artifact": artifact, "summary": summary}
    except Exception as exc:  # noqa: BLE001 — a job failure is logged, never crashes the loop
        rec = {"ts": started, "routine": rid, "status": "error",
               "artifact": None, "summary": str(exc)[:300]}
    _mark_run(rid, started)
    _append_run_log(rec)
    return rec


def due_routines(now: datetime.datetime | None = None) -> list[str]:
    """Which enabled routines are due to run (past their schedule interval)."""
    now = now or _now()
    due = []
    for r in ROUTINES:
        hrs = r.get("schedule_hours")
        if not hrs:
            continue
        st = _routine_state(r["id"])
        if not st["enabled"]:
            continue
        last = st["last_run"]
        if last is None:
            due.append(r["id"]); continue
        try:
            last_dt = datetime.datetime.fromisoformat(last)
        except Exception:  # noqa: BLE001
            due.append(r["id"]); continue
        if (now - last_dt).total_seconds() >= hrs * 3600:
            due.append(r["id"])
    return due


def list_routines() -> list[dict]:
    """Registry + live state for the UI (no job function)."""
    out = []
    for r in ROUTINES:
        st = _routine_state(r["id"])
        next_due = None
        if r.get("schedule_hours") and st["last_run"]:
            try:
                next_due = _stamp(datetime.datetime.fromisoformat(st["last_run"])
                                  + datetime.timedelta(hours=r["schedule_hours"]))
            except Exception:  # noqa: BLE001
                pass
        out.append({
            "id": r["id"], "name": r["name"], "description": r["description"],
            "schedule_hours": r.get("schedule_hours"),
            "enabled": st["enabled"], "last_run": st["last_run"], "next_due": next_due,
        })
    return out


def recent_runs(limit: int = 20) -> list[dict]:
    if not RUN_LOG.exists():
        return []
    lines = RUN_LOG.read_text(encoding="utf-8").splitlines()
    out = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
        if len(out) >= limit:
            break
    return out
