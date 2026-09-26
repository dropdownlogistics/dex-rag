#!/usr/bin/env python3
"""
programs.py — the Dex plugin/program registry.

A "program" (or plugin) is a named capability: a directive prompt, an optional
grounding flag, and a default voice. It's the same shape the conversational mode
already runs — directive + model + (optional) retrieval — generalized so new
capabilities are DATA, not code. MindFrame's Programs land here as entries.

This is APP-scoped: a registry the web app reads. It has nothing to do with
Claude Code's session-start plugin machinery — no hooks, no global injection.
Adding a plugin means adding a dict below (or, later, a JSON file), the way a
superpowers skill is a folder — but confined to this app.

Read-only. Programs never write the corpus; grounded ones reuse Dex's own
retrieval so answers stay cited and inspectable.
"""
from __future__ import annotations

import json
from pathlib import Path

# Each program is a plain dict so the registry can move to JSON later untouched.
#   id        stable key the API/UI address it by
#   name      display label
#   icon      one glyph for the gallery card
#   blurb     one line: what it does
#   category  gallery grouping
#   grounded  True → run Dex's real retrieval first and feed the chunks in
#   directive the system framing prepended to the corpus notes + the user input
#   input_label  what the user is prompted to provide (topic / question / idea)
PROGRAMS: list[dict] = [
    {
        "id": "cognitive_scan",
        "name": "Cognitive Scan",
        "icon": "◎",
        "blurb": "Multi-lens read of a topic — factual, structural, risk, and blind spots.",
        "category": "Cognitive",
        "grounded": True,
        "input_label": "topic to scan",
        "directive": (
            "Run a Cognitive Scan on the topic below. Give a structured, multi-lens "
            "read: (1) Factual — what's actually established; (2) Structural — how the "
            "pieces relate; (3) Risk — failure modes and weak points; (4) Blind spots — "
            "what's conspicuously missing or unstated. Keep each lens tight. Ground "
            "every claim in the notes; where the notes are silent, say so under Blind "
            "spots rather than inventing."
        ),
    },
    {
        "id": "teach_me_5",
        "name": "Teach Me Like I'm 5",
        "icon": "🧩",
        "blurb": "Any concept, broken into simple, intuitive building blocks. No condescension.",
        "category": "Learning",
        "grounded": True,
        "input_label": "concept to explain",
        "directive": (
            "Explain the concept below simply and intuitively, like to a sharp beginner "
            "— plain language, concrete analogies, small building blocks that stack. "
            "Never condescending. Draw only from the notes; if they don't cover part of "
            "it, say that plainly instead of filling the gap with a guess."
        ),
    },
    {
        "id": "brainstormer",
        "name": "Brainstormer",
        "icon": "✦",
        "blurb": "Fast, structured idea generation across angles — with momentum.",
        "category": "Creative",
        "grounded": True,
        "input_label": "what to brainstorm",
        "directive": (
            "Brainstorm on the prompt below. Generate a structured menu of ideas across "
            "distinct angles — group them, keep each punchy, favor high-leverage / "
            "low-friction moves, and keep momentum. Use the notes as raw material and "
            "grounding; you may extend beyond them creatively, but flag which ideas are "
            "grounded in the corpus and which are net-new sparks."
        ),
    },
    {
        "id": "socratic",
        "name": "Socratic Navigator",
        "icon": "❔",
        "blurb": "You name what you're stuck on — Dex asks the questions that reveal the path.",
        "category": "Reflective",
        "grounded": True,
        "input_label": "what you're stuck on",
        "directive": (
            "The user is stuck on what's below. Do NOT solve it for them. Instead ask a "
            "short sequence of pointed, revealing questions — the ones that surface "
            "hidden assumptions, real constraints, and the actual blocker. Use the notes "
            "to make the questions specific to their situation, not generic. End by "
            "naming the single question worth answering first."
        ),
    },
    {
        "id": "ai_proficiency",
        "name": "AI Proficiency Map",
        "icon": "▤",
        "blurb": "Map strengths, gaps, and next moves in how you use AI.",
        "category": "Reflective",
        "grounded": False,
        "input_label": "describe how you use AI today",
        "directive": (
            "From the description below, map the user's AI proficiency: (1) current "
            "position across prompting, technical interaction, and workflow integration; "
            "(2) strength pattern; (3) growth edges; (4) two concrete next moves. Be "
            "specific and honest, not flattering. This program reasons from what the user "
            "tells you — there are no corpus notes to ground in."
        ),
    },
]

PLUGINS_DIR = Path(__file__).resolve().parent / "plugins"


def _load_file_plugins() -> None:
    """Discover file-based plugins — drop a `plugins/<name>.json` and it becomes
    a Program, no code edit. The superpowers-style multiplier: since a program is
    just a directive, a plugin is pure data. A built-in id is never shadowed; a
    malformed file is skipped, never crashes the app.
    """
    if not PLUGINS_DIR.exists():
        return
    existing = {p["id"] for p in PROGRAMS}
    for fp in sorted(PLUGINS_DIR.glob("*.json")):
        try:
            spec = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a broken plugin is ignored, not fatal
            continue
        pid = spec.get("id") or fp.stem
        if not spec.get("directive") or pid in existing:
            continue  # a program needs a directive; don't override a built-in
        PROGRAMS.append({
            "id": pid,
            "name": spec.get("name", pid),
            "icon": spec.get("icon", "⬡"),
            "blurb": spec.get("blurb", ""),
            "category": spec.get("category", "Plugin"),
            "grounded": bool(spec.get("grounded", True)),
            "input_label": spec.get("input_label", "input"),
            "directive": spec["directive"],
            "source": "file",       # marks it as dropped-in vs built-in
        })
        existing.add(pid)


_load_file_plugins()

# Safety net: keep every gallery glyph to a single visible character.
for _p in PROGRAMS:
    if len(_p["icon"]) != 1:
        _p["icon"] = "▓"

_BY_ID = {p["id"]: p for p in PROGRAMS}


def add_plugin(spec: dict) -> dict:
    """Create a file-based plugin from the UI: validate, write plugins/<id>.json,
    and register it in memory so it's live immediately (no restart). Same result as
    hand-dropping a file — this just does it for you."""
    import re as _re
    directive = (spec.get("directive") or "").strip()
    if not directive:
        raise ValueError("a directive is required")
    pid = (spec.get("id") or spec.get("name") or "plugin").strip().lower()
    pid = _re.sub(r"[^a-z0-9_]+", "_", pid).strip("_") or "plugin"
    if pid in _BY_ID:
        raise ValueError(f"id already exists: {pid}")
    icon = (spec.get("icon") or "⬡").strip()
    entry = {
        "id": pid, "name": (spec.get("name") or pid).strip(),
        "icon": icon[:1] if icon else "⬡",
        "blurb": (spec.get("blurb") or "").strip(),
        "category": (spec.get("category") or "Plugin").strip(),
        "grounded": bool(spec.get("grounded", True)),
        "input_label": (spec.get("input_label") or "input").strip(),
        "directive": directive, "source": "file",
    }
    PLUGINS_DIR.mkdir(exist_ok=True)
    file_fields = ("id", "name", "icon", "blurb", "category", "grounded",
                   "input_label", "directive")
    (PLUGINS_DIR / f"{pid}.json").write_text(
        json.dumps({k: entry[k] for k in file_fields}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    PROGRAMS.append(entry)
    _BY_ID[pid] = entry
    return {k: v for k, v in entry.items() if k != "directive"}


def list_programs() -> list[dict]:
    """The registry, minus the directive text (the UI shows cards, not prompts)."""
    return [{k: v for k, v in p.items() if k != "directive"} for p in PROGRAMS]


def get_program(program_id: str) -> dict | None:
    return _BY_ID.get(program_id)
