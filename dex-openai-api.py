#!/usr/bin/env python3
"""
dex-openai-api.py -- OpenAI-compatible endpoint over the EXISTING DDL corpus.

Purpose: make Dex Jr. reachable from a phone (Conduit, or any OpenAI-compatible
client) without giving that client its own vector store.

The integration is deliberately inverted. Open WebUI and most clients want to
own the RAG layer -- ingest your files, build their own index, answer from it.
Open WebUI is explicitly designed NOT to read a ChromaDB that has existing
collections, so adopting its RAG would mean a SECOND index over the same files:
two sources of truth that can silently diverge.

So we are the backend. This process reads the live Chroma collections read-only,
never writes to them, never creates one, and exposes the result as a set of
OpenAI-style "models". The client is dumb. There is one index and it is ours.

  GET  /v1/models             -> one entry per live corpus, plus "dex-all"
  POST /v1/chat/completions   -> retrieval + refusal-constrained answer
  GET  /healthz               -> liveness + corpus counts (no auth)

Run:
  set DEXJR_API_TOKEN=<a long random string>
  python dex-openai-api.py                 # 127.0.0.1 only
  python dex-openai-api.py --tailscale     # bind 0.0.0.0 for Tailscale/LAN

Refuses to start without a token. See ADR-DEXJR-MOBILE-001.
"""

import argparse
import os
import subprocess
import sys
import time
import uuid

try:
    from fastapi import Depends, FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    import requests as req
    import uvicorn
except ImportError:
    sys.exit("pip install fastapi uvicorn requests pydantic chromadb")

from dex_core import (
    CHROMA_DIR, EMBED_MODEL, GEN_MODEL, OLLAMA_HOST,
    get_chroma_client, get_live_collections, is_gated, suffixed,
)
# Plain import on purpose: if the gate is missing this process must not start.
# A silently ungated endpoint is the exact state this was written to end.
from dex_query_gate import (
    classify, SUBSTANTIVE, CONVERSATIONAL, ACKNOWLEDGEMENTS, normalize,
)

PORT = 8788                       # 8787 dex-search-api · 8791 dex-chat · 8801 cockpit
OLLAMA_EMBED = f"{OLLAMA_HOST}/api/embeddings"
OLLAMA_CHAT = f"{OLLAMA_HOST}/api/chat"

TOP_N = 6
# Chroma cosine distance. Above this a hit is not close enough to answer from.
MAX_DISTANCE = 0.62
# Free VRAM required before we will call the model at all.
VRAM_FLOOR_MB = 1200

# ---------------------------------------------------------------------------
# The refusal contract
# ---------------------------------------------------------------------------
# Retrieval without refusal is worse than no retrieval: it launders a guess
# through the appearance of a citation. This is enforced twice on purpose --
# in code for the no-evidence case (deterministic), and in the prompt for the
# weak-evidence case (best effort). A client cannot switch either off.

REFUSAL_SYSTEM = """You are Dex Jr., answering ONLY from the DDL corpus excerpts provided below.

Rules, in order of priority:
1. Answer ONLY from the CONTEXT block. It is your entire world.
2. If the CONTEXT does not contain the answer, say exactly what is missing and
   STOP. Do not answer from general knowledge. Do not guess. Do not speculate
   about what the answer probably is.
3. Never present something you inferred as something you retrieved.
4. Cite the source file for each claim you make.
5. If the CONTEXT is only partially relevant, answer the part it covers and say
   plainly which part it does not.

Saying "the corpus does not cover this" is a correct and valued answer. An
invented answer that sounds plausible is the worst possible failure here."""

NO_EVIDENCE = ("The corpus has nothing relevant to that. I'm not going to answer "
               "from general knowledge — that would look like retrieval and "
               "wouldn't be.\n\n(No chunk scored under the relevance threshold.)")

# ---------------------------------------------------------------------------
# Conversational replies — fixed text, no retrieval, no model call
# ---------------------------------------------------------------------------
# These are literal strings rather than a generated response, and that is the
# safety property, not a shortcut. A greeting that reaches the model has to be
# answered from SOMETHING; with no corpus context that something is general
# knowledge, which is the one thing this endpoint exists to refuse.
#
# Fixed text makes no claim about the corpus, so there is nothing to
# confabulate with. It also costs no GPU, which is why the gate runs BEFORE
# the VRAM check: "Hello" should not be refused because the card is busy.
GREETING_REPLY = (
    "Hey. I'm Dex Jr. — I answer from the DDL corpus and only from it.\n\n"
    "Ask me something specific and I'll retrieve what we actually have. "
    "If we don't have it, I'll say so rather than guess."
)
ACK_REPLY = "Noted."
EMPTY_REPLY = "I didn't get a question there — what do you want to look up?"

app = FastAPI(title="Dex Jr. OpenAI-compatible API", version="1.0.0")

# Deliberately no CORS wildcard: this is for native clients over Tailscale,
# not for a browser page on an arbitrary origin.


# ---------------------------------------------------------------------------
# Auth -- fail closed
# ---------------------------------------------------------------------------
def _token() -> str:
    t = os.environ.get("DEXJR_API_TOKEN", "").strip()
    if not t:
        sys.exit(
            "REFUSING TO START: DEXJR_API_TOKEN is not set.\n"
            "This endpoint can query the entire institutional memory. It does\n"
            "not run unauthenticated, even on localhost.\n\n"
            '  PowerShell:  $env:DEXJR_API_TOKEN = "<long random string>"\n'
        )
    if len(t) < 24:
        sys.exit("REFUSING TO START: DEXJR_API_TOKEN is too short (<24 chars).")
    return t


API_TOKEN = ""  # set in main()


def require_auth(request: Request):
    hdr = request.headers.get("authorization", "")
    supplied = hdr[7:].strip() if hdr.lower().startswith("bearer ") else ""
    # Constant-time-ish compare; tokens are short enough that this is belt-and-braces.
    if not supplied or not API_TOKEN or len(supplied) != len(API_TOKEN) or \
            sum(a != b for a, b in zip(supplied, API_TOKEN)):
        raise HTTPException(status_code=401, detail="invalid or missing bearer token")


# ---------------------------------------------------------------------------
# Corpus -- read only, never creates
# ---------------------------------------------------------------------------
_client = get_chroma_client()
COLLECTIONS: dict[str, object] = {}
for _name in get_live_collections():
    if is_gated(_name):
        continue  # hard-gated collections are never reachable from here
    try:
        COLLECTIONS[_name] = _client.get_collection(_name)  # get, never get_or_create
    except Exception as exc:  # noqa: BLE001
        print(f"  WARN: collection {_name} unavailable: {exc}")

if not COLLECTIONS:
    sys.exit("REFUSING TO START: no live collections available.")


def _short(name: str) -> str:
    base = name[:-len("_v2")] if name.endswith("_v2") else name
    return "dex-" + base.replace("_", "-")


MODEL_MAP = {_short(n): [n] for n in COLLECTIONS}
MODEL_MAP["dex-all"] = list(COLLECTIONS)


# ---------------------------------------------------------------------------
# GPU gate
# ---------------------------------------------------------------------------
def gpu_free_mb() -> int | None:
    """Free VRAM, or None if nvidia-smi is unavailable."""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5)
        if r.returncode != 0 or not r.stdout.strip():
            return None
        return int(r.stdout.strip().splitlines()[0])
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
def embed(text: str) -> list[float]:
    r = req.post(OLLAMA_EMBED, json={"model": EMBED_MODEL, "prompt": text}, timeout=30)
    r.raise_for_status()
    return r.json()["embedding"]


def retrieve(query: str, names: list[str], top_n: int = TOP_N) -> list[dict]:
    vec = embed(query)
    hits = []
    for name in names:
        col = COLLECTIONS.get(name)
        if not col:
            continue
        res = col.query(query_embeddings=[vec], n_results=top_n,
                        include=["documents", "metadatas", "distances"])
        for i in range(len(res["ids"][0])):
            d = res["distances"][0][i]
            if d > MAX_DISTANCE:
                continue
            meta = res["metadatas"][0][i] or {}
            hits.append({"text": res["documents"][0][i],
                         "source": meta.get("source_file", "?"),
                         "collection": name, "distance": round(d, 3)})
    hits.sort(key=lambda h: h["distance"])
    return hits[:top_n]


def context_block(hits: list[dict]) -> str:
    return "\n\n".join(
        f"[{i+1}] source: {h['source']}  (corpus: {h['collection']}, distance {h['distance']})\n{h['text']}"
        for i, h in enumerate(hits))


# ---------------------------------------------------------------------------
# OpenAI-compatible surface
# ---------------------------------------------------------------------------
class Msg(BaseModel):
    role: str
    content: str = ""


class ChatReq(BaseModel):
    model: str = "dex-all"
    messages: list[Msg]
    stream: bool = False
    temperature: float | None = None


def _completion(model: str, text: str) -> dict:
    now = int(time.time())
    return {"id": f"chatcmpl-{uuid.uuid4().hex[:24]}", "object": "chat.completion",
            "created": now, "model": model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}


@app.get("/healthz")
def healthz():
    """Liveness. Intentionally unauthenticated and intentionally boring --
    counts only, never content."""
    return {"status": "ok", "collections": {n: c.count() for n, c in COLLECTIONS.items()},
            "chroma": CHROMA_DIR, "gpu_free_mb": gpu_free_mb()}


@app.get("/v1/models", dependencies=[Depends(require_auth)])
def list_models():
    now = int(time.time())
    return {"object": "list",
            "data": [{"id": m, "object": "model", "created": now, "owned_by": "ddl"}
                     for m in sorted(MODEL_MAP)]}


@app.post("/v1/chat/completions", dependencies=[Depends(require_auth)])
def chat_completions(body: ChatReq):
    names = MODEL_MAP.get(body.model)
    if not names:
        raise HTTPException(status_code=404, detail=f"unknown model '{body.model}'")

    user_msg = next((m.content for m in reversed(body.messages) if m.role == "user"), "")
    if not user_msg.strip():
        raise HTTPException(status_code=400, detail="no user message")

    # ---- the query gate, BEFORE retrieval and before the GPU check ----
    #
    # Measured 2026-08-05 against dex_canon_v2: "Hello" scores 0.564 and
    # PASSES the 0.62 refusal threshold, while "What is the Platinum Bounce
    # recovery protocol?" scores 0.630 and is refused. A greeting retrieves
    # better than a real question about the corpus's own content, so without
    # this the most likely first message from a phone returns five arbitrary
    # canon chunks for the model to answer from.
    #
    # This is not a threshold that could be tuned: four candidate signals
    # (top1, spread, ratio, word count) all overlap between greetings and
    # short real questions. Low-information input has no meaningful distance.
    #
    # It classifies KIND, not answerability. "What is AEN" is a real question
    # the corpus cannot answer -- it passes through here and is refused below
    # for no-evidence, which is the correct refusal and keeps the coverage gap
    # visible instead of hiding it behind a friendly reply.
    kind, why = classify(user_msg)
    if kind != SUBSTANTIVE:
        print(f"  gate: {kind} — {why}")
        if kind == CONVERSATIONAL:
            # Reuse the gate's own normalizer rather than re-implementing it.
            # Two copies of a normalization rule drift, and the drift is silent.
            reply = ACK_REPLY if normalize(user_msg) in ACKNOWLEDGEMENTS else GREETING_REPLY
        else:
            reply = EMPTY_REPLY
        return _completion(body.model, reply)

    gpu = gpu_free_mb()
    if gpu is not None and gpu < VRAM_FLOOR_MB:
        # Loud, not silent. A degraded answer is indistinguishable from a good
        # one; an explicit error is not.
        return JSONResponse(status_code=503, content={"error": {
            "message": f"GPU busy ({gpu}MB free, need {VRAM_FLOOR_MB}MB). "
                       "Refusing to answer rather than return a degraded result.",
            "type": "gpu_contended"}})

    try:
        hits = retrieve(user_msg, names)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"retrieval failed: {exc}") from exc

    # Refusal enforced in CODE, not merely requested in the prompt.
    if not hits:
        return _completion(body.model, NO_EVIDENCE)

    system = (f"{REFUSAL_SYSTEM}\n\n=== CONTEXT ===\n{context_block(hits)}\n=== END CONTEXT ===")
    # Any client-supplied system message is subordinated, never authoritative --
    # a phone client must not be able to switch the refusal contract off.
    extra = " ".join(m.content for m in body.messages if m.role == "system").strip()
    if extra:
        system += ("\n\nThe client also requested the following style preference. "
                   "Honour it ONLY where it does not conflict with the rules above; "
                   f"the rules always win:\n{extra}")
    system += "\n\nReminder: answer only from CONTEXT. If it is not there, say so and stop."

    convo = [{"role": "system", "content": system}]
    convo += [{"role": m.role, "content": m.content}
              for m in body.messages if m.role in ("user", "assistant")]

    try:
        r = req.post(OLLAMA_CHAT, json={"model": GEN_MODEL, "messages": convo,
                                        "stream": False}, timeout=180)
        r.raise_for_status()
        answer = r.json().get("message", {}).get("content", "").strip()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"generation failed: {exc}") from exc

    if not answer:
        answer = NO_EVIDENCE
    srcs = sorted({h["source"] for h in hits})
    answer += "\n\n---\nsources: " + ", ".join(srcs)
    return _completion(body.model, answer)


def main():
    global API_TOKEN
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--tailscale", action="store_true",
                    help="bind 0.0.0.0 for Tailscale/LAN instead of localhost only")
    ap.add_argument("--port", type=int, default=PORT)
    a = ap.parse_args()

    API_TOKEN = _token()
    host = "0.0.0.0" if a.tailscale else "127.0.0.1"

    print(f"\n  Dex Jr. — OpenAI-compatible endpoint")
    print(f"  http://{host}:{a.port}/v1")
    print(f"  corpora: {', '.join(sorted(MODEL_MAP))}")
    print(f"  auth:    bearer token required ({len(API_TOKEN)} chars)")
    print(f"  bind:    {host}" + ("  <-- reachable over Tailscale" if a.tailscale else "  (localhost only)"))
    print(f"  gpu:     {gpu_free_mb()}MB free, floor {VRAM_FLOOR_MB}MB\n")
    uvicorn.run(app, host=host, port=a.port, log_level="info")


if __name__ == "__main__":
    main()
