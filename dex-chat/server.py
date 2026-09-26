#!/usr/bin/env python3
r"""
server.py — the Dex chat backend. A thin FastAPI face over the engine spine.

  GET  /             the chat UI (index.html)
  GET  /api/health   liveness + a VERIFIED brain check (UP/DEGRADED/DOWN/UNKNOWN)
  POST /api/chat     {message} -> {answer, citations, sources}

Read-only. This serves a FACE on Dex; it never writes the corpus, changes config,
or touches a collection. All grounding happens in Dex's own governed query path.

Run (from dex-chat/, with the dex-rag venv active or on PATH):
    python server.py
  or
    ..\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8791

Standing: EXPERIMENTAL / OPERATOR REVIEW REQUIRED (2026-07-23).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import engine
import routines

HERE = Path(__file__).resolve().parent
app = FastAPI(title="Dex Chat", docs_url=None, redoc_url=None)


class ChatIn(BaseModel):
    message: str
    mode: str = "grounded"   # "grounded" (default report voice) | "conversational"
    model: str = "dexjr"     # conversational-mode voice; any local chat model


@app.get("/")
def index():
    return FileResponse(HERE / "index.html")


@app.get("/api/health")
def health():
    """Liveness AND a real brain check.

    This used to return a hardcoded {"ok": True, "brain": "dex-jr"} — it would
    have claimed health with the corpus deleted and Ollama stopped, and the UI's
    brain pill reads straight off it. The one endpoint whose whole job is to say
    "I'm healthy" verified nothing. It verifies now.

    `brain` carries the real state so the existing UI binding inherits the truth:
    UP -> "dex-jr", DEGRADED -> "dex-jr · degraded", DOWN -> "brain down". If the
    check itself cannot run we say UNKNOWN — never healthy on unverified ground,
    and never DOWN on a check we failed to perform.
    """
    try:
        v = engine.vitals()
    except Exception as exc:  # noqa: BLE001 — can't verify != verified bad
        return {"ok": False, "verdict": "UNKNOWN", "brain": "dex-jr · unverified",
                "surface": "dex-chat", "detail": f"health check failed: {exc}"}
    verdict = v.get("verdict", "UNKNOWN")
    label = {"UP": "dex-jr", "DEGRADED": "dex-jr · degraded",
             "DOWN": "brain down"}.get(verdict, "dex-jr · unverified")
    return {"ok": verdict == "UP", "verdict": verdict, "brain": label,
            "surface": "dex-chat",
            # everything not verified-good, so a bad pill can be diagnosed
            "failing": [c for c in v.get("checks", []) if c.get("ok") is not True]}


TRANSCRIPTS = HERE / "transcripts"


def _log_transcript(question: str, rec: dict, mode: str) -> None:
    """Append every exchange to a weekly-rotating running log — 'document
    everything.' New file each ISO week. Never breaks the chat if it fails."""
    import datetime, json as _json
    try:
        TRANSCRIPTS.mkdir(exist_ok=True)
        now = datetime.datetime.now()
        y, w, _ = now.isocalendar()
        entry = {"ts": now.isoformat(timespec="seconds"), "mode": mode,
                 "model": rec.get("model", ""), "question": question,
                 "answer": rec.get("answer", ""),
                 "sources": [s.get("file") for s in rec.get("sources", [])]}
        with open(TRANSCRIPTS / f"{y}-W{w:02d}.jsonl", "a", encoding="utf-8") as f:
            f.write(_json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — the log is an audit trail, never a failure point
        pass


@app.post("/api/chat")
def chat(body: ChatIn):
    try:
        if body.mode == "conversational":
            rec = engine.ask_conversational(body.message, model=body.model)
        else:
            rec = engine.ask(body.message)
        _log_transcript(body.message, rec, body.mode)
        return rec
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:  # noqa: BLE001 — a brain failure is a reported error, not a crash
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/search")
def search(q: str = Query(..., min_length=1), k: int = Query(6, ge=1, le=20),
           collection: str | None = Query(None)):
    """Dex's real retrieval, no generation — ranked chunks only. Read-only."""
    try:
        return engine.search(q, top_k=k, collection=collection or None)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


class FetchIn(BaseModel):
    url: str
    question: str
    model: str = "dexjr"


class VisionIn(BaseModel):
    image: str            # base64 (data-URL prefix ok)
    question: str = ""
    model: str = "llava"


@app.post("/api/vision")
def vision(body: VisionIn):
    """Dex sees an image — LLaVA. OCR is just a question. Local, read-only."""
    try:
        return engine.ask_vision(body.image, body.question, model=body.model)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.post("/api/fetch")
def fetch(body: FetchIn):
    """Web-fetch connector: Dex reads a live URL and answers grounded on it."""
    try:
        return engine.fetch_and_ground(body.url, body.question, model=body.model)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"error": str(exc)})


@app.get("/api/doc")
def doc(file: str = Query(..., min_length=1), collection: str | None = Query(None)):
    """The corpus's copy of a cited source — every chunk, reconstructed. Read-only."""
    try:
        return engine.fetch_doc(file, collection or None)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/vitals")
def vitals():
    """Is the brain up? store / collections / models. Read-only."""
    try:
        return engine.vitals()
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


FABRIC_PY = Path(r"C:\Users\dexjr\ddl-org\_toolkit\incubating\fabric\fabric.py")


@app.get("/api/fabric")
def fabric():
    """Multi-node compute-fabric truth, via the `fabric` tool (tailnet + services).
    Read-only — fabric only probes; it never changes anything."""
    import subprocess, sys, json as _json
    if not FABRIC_PY.exists():
        return JSONResponse(status_code=404, content={"error": "fabric tool not found"})
    try:
        r = subprocess.run([sys.executable, str(FABRIC_PY), "--json"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=45)
        return _json.loads(r.stdout)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


class ProgramIn(BaseModel):
    program: str
    message: str
    model: str = "dexjr"


@app.get("/api/programs")
def programs():
    """The plugin/program registry (cards, not directives). Read-only."""
    import programs as reg
    return {"programs": reg.list_programs()}


class PluginIn(BaseModel):
    name: str
    directive: str
    icon: str = ""
    blurb: str = ""
    category: str = "Plugin"
    grounded: bool = True
    input_label: str = "input"


@app.post("/api/plugins")
def create_plugin(body: PluginIn):
    """Author a plugin from the UI — writes plugins/<id>.json and registers it live."""
    import programs as reg
    try:
        return reg.add_plugin(body.model_dump())
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.post("/api/program")
def run_program(body: ProgramIn):
    """Run a registered program/plugin over Dex. Read-only."""
    try:
        return engine.run_program(body.program, body.message, model=body.model)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/models")
def models():
    """Local chat models available as a conversational voice. Read-only."""
    try:
        return {"models": engine.chat_models()}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/collections")
def collections():
    """Live collections + chunk counts, for the knowledge graph. Read-only."""
    try:
        return {"collections": engine.collections()}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


VOICE_URL = "http://127.0.0.1:8792"          # ddl-voice server (isolated venv)
IMAGE_URL = "http://gaminglaptop:8793"       # image server — OFFLOADED to the gaminglaptop RTX 3060 over the tailnet, freeing reborn's 8GB for brain + voice
SIGNAL_LOG = HERE / "signal_log.jsonl"       # Dave's voice-flagged signal capture


@app.get("/api/image-status")
def image_status():
    """Is the image server up? Lets the UI show the Images tab as live or offline."""
    import urllib.request, json as _json
    try:
        with urllib.request.urlopen(f"{IMAGE_URL}/health", timeout=3) as r:
            return {"available": True, **_json.loads(r.read())}
    except Exception:  # noqa: BLE001
        return {"available": False}


class ImageIn(BaseModel):
    prompt: str
    steps: int = 3


@app.post("/api/image")
def image(body: ImageIn):
    """Proxy to the local image server (SDXL-Turbo). Returns PNG. Read-only."""
    import urllib.request, json as _json
    prompt = (body.prompt or "").strip()
    if not prompt:
        return JSONResponse(status_code=400, content={"error": "empty prompt"})
    try:
        req = urllib.request.Request(
            f"{IMAGE_URL}/image",
            data=_json.dumps({"prompt": prompt, "steps": body.steps}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            from fastapi.responses import Response
            return Response(content=r.read(), media_type="image/png")
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"error": f"image server: {exc}"})


@app.get("/api/voice")
def voice_status():
    """Is Dex's cloned-voice server up? Lets the UI offer 'your voice' only when real."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"{VOICE_URL}/health", timeout=3) as r:
            import json as _json
            return {"available": True, **_json.loads(r.read())}
    except Exception:  # noqa: BLE001 — voice server down is a state, not an error
        return {"available": False}


class TTSIn(BaseModel):
    text: str


@app.post("/api/tts")
def tts(body: TTSIn):
    """Proxy to the cloned-voice server so the browser stays single-origin. Returns WAV."""
    import urllib.request
    import json as _json
    text = (body.text or "").strip()
    if not text:
        return JSONResponse(status_code=400, content={"error": "empty text"})
    try:
        req = urllib.request.Request(
            f"{VOICE_URL}/tts", data=_json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            from fastapi.responses import Response
            return Response(content=r.read(), media_type="audio/wav")
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"error": f"voice server: {exc}"})


@app.post("/api/stt")
async def stt(request: Request):
    """Proxy raw audio to the voice-server's STT, return {text}. Read-only.
    Voice input is itself a signal — the transcript is captured as kind 'spoke'."""
    import urllib.request, json as _json, datetime
    data = await request.body()
    if not data:
        return JSONResponse(status_code=400, content={"error": "empty audio"})
    try:
        req = urllib.request.Request(f"{VOICE_URL}/stt", data=data,
                                     headers={"Content-Type": "application/octet-stream"})
        with urllib.request.urlopen(req, timeout=120) as r:
            out = _json.loads(r.read())
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=502, content={"error": f"voice server: {exc}"})
    text = (out.get("text") or "").strip()
    if text:   # voice-typing = too-complex-to-type = a flagged signal
        rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
               "kind": "spoke", "text": text}
        with open(SIGNAL_LOG, "a", encoding="utf-8") as f:
            f.write(_json.dumps(rec, ensure_ascii=False) + "\n")
    return out


@app.get("/api/signals")
def signals():
    """The signal capture, newest first — what Dave flagged by how he interacted:
    'spoke' (voice-typed = too-complex-to-type) + 'read' (had Dex read it aloud).
    Read-only over the append-only log."""
    import json as _json
    entries = []
    if SIGNAL_LOG.exists():
        for line in SIGNAL_LOG.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(_json.loads(line))
            except Exception:  # noqa: BLE001 — skip a corrupt line, don't fail the view
                continue
    entries.reverse()
    by_kind: dict[str, int] = {}
    for e in entries:
        by_kind[e.get("kind", "?")] = by_kind.get(e.get("kind", "?"), 0) + 1
    return {"count": len(entries), "by_kind": by_kind, "entries": entries[:200]}


class CaptureIn(BaseModel):
    kind: str          # "spoke" (STT input) | "read" (had Dex read it aloud)
    text: str


DISPATCH_DIR = Path(r"C:\Users\dexjr\dispatch-queue")


class DispatchIn(BaseModel):
    target: str = "Reeve_Worker"
    task: str


@app.post("/api/dispatch")
def dispatch(body: DispatchIn):
    """Queue a task for a worker session. Dex is the dispatcher: Dave (even away
    from home) sends a task, it lands in a durable file queue, a worker drains it.
    Write-only to the queue; the relay to the worker is done by a session with
    cross-session messaging (the PM), not the web app."""
    import datetime, json as _json
    task = (body.task or "").strip()
    if not task:
        return JSONResponse(status_code=400, content={"error": "empty task"})
    DISPATCH_DIR.mkdir(exist_ok=True)
    now = datetime.datetime.now()
    rec = {"id": now.strftime("%Y%m%d_%H%M%S"), "ts": now.isoformat(timespec="seconds"),
           "target": (body.target or "Reeve_Worker").strip(), "task": task,
           "status": "pending"}
    (DISPATCH_DIR / f"{rec['id']}.json").write_text(
        _json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "queued": rec["id"], "target": rec["target"]}


@app.get("/api/dispatch")
def dispatch_list():
    """The dispatch queue — pending + relayed tasks, newest first. Read-only."""
    import json as _json
    if not DISPATCH_DIR.exists():
        return {"queue": []}
    items = []
    for fp in sorted(DISPATCH_DIR.glob("*.json"), reverse=True):
        try:
            items.append(_json.loads(fp.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            continue
    return {"queue": items}


@app.post("/api/capture")
def capture(body: CaptureIn):
    """Signal capture: things Dave flags as important by *how* he interacted with them.
    Voice-typing = too-complex-to-type = important; having Dex read = worth hearing.
    Append-only JSONL — a running record of what mattered. Never overwrites."""
    import json as _json, datetime
    text = (body.text or "").strip()
    if not text:
        return JSONResponse(status_code=400, content={"error": "empty text"})
    rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
           "kind": body.kind, "text": text}
    with open(SIGNAL_LOG, "a", encoding="utf-8") as f:
        f.write(_json.dumps(rec, ensure_ascii=False) + "\n")
    return {"ok": True, "saved": rec["ts"]}


class RoutineRun(BaseModel):
    id: str


class RoutineToggle(BaseModel):
    id: str
    enabled: bool


@app.get("/api/routines")
def routines_list():
    """The routine registry + live state + recent run log. Read-only."""
    return {"routines": routines.list_routines(), "runs": routines.recent_runs(20)}


@app.post("/api/routines/run")
def routines_run(body: RoutineRun):
    """Run a routine now (the Run-Now button). Produces an artifact in the sandbox."""
    try:
        return routines.run_routine(body.id)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.post("/api/routines/toggle")
def routines_toggle(body: RoutineToggle):
    """Enable/disable a routine's schedule."""
    routines.set_enabled(body.id, body.enabled)
    return {"ok": True, "id": body.id, "enabled": body.enabled}


@app.get("/api/routines/artifact")
def routines_artifact(name: str = Query(..., min_length=1)):
    """A sandbox artifact's content, for review. Read-only, artifacts dir only."""
    p = routines.ARTIFACTS / name
    try:
        ok = p.resolve().is_relative_to(routines.ARTIFACTS.resolve()) and p.exists()
    except Exception:  # noqa: BLE001
        ok = False
    if not ok:
        return JSONResponse(status_code=404, content={"error": "not found"})
    return {"name": name, "text": p.read_text(encoding="utf-8")}


def _scheduler_loop():
    """Fire due routines on a timer. Runs in a daemon thread beside the server;
    routines only fire while the server is up (reboot-persistence comes with the
    launcher). A job failure is logged by run_routine, never crashes the loop."""
    import time
    while True:
        try:
            for rid in routines.due_routines():
                routines.run_routine(rid)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(300)  # check every 5 minutes


if __name__ == "__main__":
    import threading
    import uvicorn
    threading.Thread(target=_scheduler_loop, daemon=True).start()
    # 0.0.0.0 so the Tailscale tailnet can reach Dex from the operator's phone
    # (reborn = 100.117.38.55). Local 127.0.0.1 access still works. Exposure is
    # scoped to the tailnet by a Windows firewall rule allowing 8791 ONLY from
    # the Tailscale range (100.64.0.0/10) — never a public interface. Phase 1 of
    # the phone-access plan; see docs/PHONE_ACCESS_SCOPE.md.
    uvicorn.run(app, host="0.0.0.0", port=8791)
