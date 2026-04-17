"""DDL Search + MindFrame Chat API v0.5"""
import os, sys
from datetime import datetime

try:
    from fastapi import FastAPI, Query
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse
    import uvicorn
    import requests as req
    import chromadb
    from pydantic import BaseModel
except ImportError:
    print("pip install fastapi uvicorn requests chromadb pydantic")
    sys.exit(1)

from dex_core import (
    CHROMA_DIR, OLLAMA_HOST, EMBED_MODEL, GEN_MODEL,
    get_live_collections, suffixed,
)
OLLAMA_URL = f"{OLLAMA_HOST}/api/embeddings"
OLLAMA_CHAT = f"{OLLAMA_HOST}/api/chat"
CHAT_MODEL = GEN_MODEL
PORT = 8787

MINDFRAME_SYSTEM = """You are running a MindFrame calibration session for Dropdown Logistics.

MindFrame is a behavioral calibration system that maps how someone thinks, communicates, makes decisions, and handles conflict — not through self-report, but through conversation.

YOUR ROLE:
- You are a warm, direct, curious interviewer
- You ask one question at a time
- You listen for PATTERNS, not answers
- You never judge — you observe and reflect
- After 8-10 exchanges, you produce a calibration profile

QUESTION AREAS (cover all of these across the conversation):
1. COMMUNICATION STYLE — How do they explain things? Do they lead with data or stories? Do they validate before asserting?
2. DECISION PATTERNS — How do they make choices under uncertainty? Do they seek consensus or decide alone?
3. CONFLICT APPROACH — How do they handle disagreement? Avoidance, confrontation, evidence-based redirect?
4. COGNITIVE PREFERENCES — Do they think in systems, narratives, categories, or sequences?
5. STRESS RESPONSE — What do they do when overwhelmed? Withdraw, organize, act, or talk?
6. BLIND SPOTS — What patterns do they not see in themselves?

CONVERSATION FLOW:
- Start with a warm greeting and explain what MindFrame does in 2 sentences
- Ask your first question (something easy and open)
- Each follow-up should build on what they said — don't just go down a checklist
- Reflect back patterns you notice: "I notice you tend to..." 
- After 8-10 exchanges, say "I have enough to build your profile" and produce the output

PROFILE OUTPUT FORMAT (produce this at the end):
```
MINDFRAME CALIBRATION PROFILE
============================
Communication Style: [2-3 sentences]
Decision Pattern: [2-3 sentences]
Conflict Approach: [2-3 sentences]
Cognitive Preference: [2-3 sentences]
Stress Response: [2-3 sentences]
Blind Spot: [1-2 sentences]
One-Line Summary: [one sentence that captures the whole person]
```

RULES:
- Never be clinical or robotic
- Use their words back to them
- If they give short answers, ask follow-ups
- If they go deep, let them — that's data
- The profile should feel like someone who truly listened, not a personality test
"""

def get_embedding(text):
    resp = req.post(OLLAMA_URL, json={"model": EMBED_MODEL, "prompt": text}, timeout=30)
    resp.raise_for_status()
    return resp.json()["embedding"]

def get_rag_context(query, collection, top_n=3):
    """Pull relevant MindFrame context from the corpus."""
    try:
        embedding = get_embedding(query)
        results = collection.query(
            query_embeddings=[embedding],
            n_results=top_n,
            include=["documents"],
        )
        chunks = [doc for doc in results["documents"][0] if doc]
        return "\n\n---\n\n".join(chunks)
    except:
        return ""

# ChromaDB — Step 54: load all 4 live collections (fixes 2-of-4 bug)
client = chromadb.PersistentClient(path=CHROMA_DIR)
collections = {}
for col_name in get_live_collections():
    try:
        col = client.get_collection(col_name)
        collections[col_name] = col
        print(f"  {col_name}: {col.count()} chunks")
    except Exception:
        print(f"  {col_name}: not found")

# Backward compat aliases
canon = collections.get(suffixed("dex_canon"))
archive = collections.get(suffixed("ddl_archive"))

# App
app = FastAPI(title="DDL API", version="0.5.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage]

@app.get("/")
def root():
    counts = {name: col.count() for name, col in collections.items()}
    return {"service": "DDL API", "status": "online", "version": "0.6.0",
            "collections": counts}

@app.get("/search")
def search(q: str = Query(..., min_length=2), top: int = Query(5, ge=1, le=20), corpus: str = Query("canon")):
    # Accept short names (canon, archive, code, ext_creator) or full suffixed names
    name_map = {
        "canon": suffixed("dex_canon"), "archive": suffixed("ddl_archive"),
        "code": suffixed("dex_code"), "ext_creator": suffixed("ext_creator"),
    }
    resolved = name_map.get(corpus, corpus)
    collection = collections.get(resolved)
    if not collection:
        return {"error": f"'{corpus}' not found", "results": []}
    embedding = get_embedding(q)
    results = collection.query(query_embeddings=[embedding], n_results=top, include=["documents", "metadatas", "distances"])
    hits = []
    for i in range(len(results["ids"][0])):
        meta = results["metadatas"][0][i]
        hits.append({"text": results["documents"][0][i][:500], "source": meta.get("source_file", "?"), "distance": round(results["distances"][0][i], 2)})
    return {"query": q, "corpus": corpus, "count": len(hits), "results": hits}

@app.post("/mindframe/chat")
def mindframe_chat(request: ChatRequest):
    """MindFrame calibration chat. Sends conversation to Ollama with MindFrame system prompt + RAG context."""
    
    # Get the latest user message for RAG context
    latest_user_msg = ""
    for msg in reversed(request.messages):
        if msg.role == "user":
            latest_user_msg = msg.content
            break
    
    # Pull relevant MindFrame context from corpus
    rag_context = ""
    if canon and latest_user_msg:
        rag_context = get_rag_context("MindFrame calibration " + latest_user_msg, canon, top_n=3)
    
    # Build system prompt with RAG context
    system_prompt = MINDFRAME_SYSTEM
    if rag_context:
        system_prompt += f"\n\nRELEVANT DDL CONTEXT (from the archive):\n{rag_context}\n\nUse this context to inform your questions and observations, but don't quote it directly."
    
    # Build Ollama messages
    ollama_messages = [{"role": "system", "content": system_prompt}]
    for msg in request.messages:
        ollama_messages.append({"role": msg.role, "content": msg.content})
    
    # Call Ollama
    try:
        resp = req.post(OLLAMA_CHAT, json={
            "model": CHAT_MODEL,
            "messages": ollama_messages,
            "stream": False,
        }, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        assistant_msg = data.get("message", {}).get("content", "I'm having trouble responding. Can you try again?")
        return {"role": "assistant", "content": assistant_msg}
    except Exception as e:
        return {"role": "assistant", "content": f"Connection error: {str(e)}"}

@app.get("/stats")
def stats():
    counts = {name: col.count() for name, col in collections.items()}
    counts["path"] = CHROMA_DIR
    return counts

if __name__ == "__main__":
    print(f"\n  DDL API v0.5 — Dex Jr.")
    print(f"  http://localhost:{PORT}")
    print(f"  http://localhost:{PORT}/search?q=star+schema")
    print(f"  http://localhost:{PORT}/mindframe/chat (POST)\n")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
