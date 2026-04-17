"""
DEX JR AUTO-COUNCIL DELIBERATION ENGINE — v1.0
Multi-round governed discussion with automatic follow-up generation.

Usage:
  python dex-deliberate.py "your topic" --rounds 3
  python dex-deliberate.py "your topic" --rounds 3 --all --rag
  python dex-deliberate.py "your topic" --rounds 2 --save deliberations/my-topic
  python dex-deliberate.py --from-file topic.txt --rounds 3 --all

Workflow:
  Round 1: All models respond to the original prompt independently
  Dexcell reads all responses and generates follow-up questions
  Round 2: All models respond to the follow-up questions
  Dexcell reads Round 2 and generates deeper follow-ups
  Round N: Repeat until --rounds is reached
  Final: Dexcell produces a comprehensive synthesis across all rounds

Each round's responses are saved. The full deliberation arc is preserved.
Models never see each other's responses within a round (independence).
They DO see the synthesis/questions from the previous round (informed iteration).

Dropdown Logistics — Chaos -> Structured -> Automated
AutoCouncil Deliberation Engine v1.0 | 2026-03-06
"""

import os
import sys
import json
import time
import argparse
import datetime
import requests

# -----------------------------
# CONFIG
# -----------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(SCRIPT_DIR, ".env")
LOG_FILE = os.path.join(SCRIPT_DIR, "dex-deliberation-log.jsonl")

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"

CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"
CANON_COLLECTION = "dex_canon"
RAW_COLLECTION = "ddl_archive"
EMBED_MODEL = "nomic-embed-text"

DEFAULT_SYNTHESIZER = "dexjr"
TOP_K = 5

# Local models
LOCAL_MODELS = [
    {"id": "qwen2.5-coder:7b", "name": "Qwen", "provider": "local"},
    {"id": "llama3.1:8b", "name": "Llama", "provider": "local"},
    {"id": "deepseek-r1:8b", "name": "DeepSeek", "provider": "local"},
]

# Cloud models (free only)
CLOUD_MODELS = [
    {
        "id": "gemini-1.5-flash",
        "name": "Gemini",
        "provider": "gemini",
        "env_key": "GEMINI_API_KEY",
    },
    {
        "id": "llama-3.1-8b-instant",
        "name": "Groq-Llama",
        "provider": "groq",
        "env_key": "GROQ_API_KEY",
        "url": "https://api.groq.com/openai/v1/chat/completions",
    },
    {
        "id": "mistral-small-latest",
        "name": "Mistral",
        "provider": "mistral",
        "env_key": "MISTRAL_API_KEY",
        "url": "https://api.mistral.ai/v1/chat/completions",
    },
]

# Governance context (condensed)
GOVERNANCE = """DDL AutoCouncil Deliberation
You are participating in a multi-round Dropdown Logistics (DDL) council deliberation.
DDL is a one-person governance and analytics operation run by D.K. Hale (CPA, 10+ years audit).
Methodology: Chaos -> Structured -> Automated. Design: CottageHumble.

Core: DDL (methodology + star schemas), DexOS (AI governance + council), MindFrame (persona calibration).
DDL is NOT "Data Definition Language." Council: 10 seats, LOCK/REVISE/REJECT verdicts.
Hierarchy: Safety > Operator > Governance > Council > Procedures > Heuristics.
Boundaries: No clinical diagnosis. No silent fixes. Canon > Archive.

This is a DELIBERATION — multiple rounds of discussion on a single topic.
In each round, respond to the prompt independently. Do not hedge.
State your position clearly. If you disagree with the premise, say so.
If you see risks, name them. If you see opportunity, quantify it.
Be direct. Be specific. Take a stance."""

GOVERNANCE_SHORT = """DDL Council Deliberation. DDL = Dropdown Logistics (NOT SQL).
One-person governance + analytics op. Methodology: Chaos -> Structured -> Automated.
Council: 10 seats, LOCK/REVISE/REJECT. Hierarchy: Safety > Operator > Governance.
Take a clear stance. Be direct. Name risks. Quantify opportunity."""

# -----------------------------
# LOAD ENV
# -----------------------------
def load_env():
    keys = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    keys[k.strip()] = v.strip()
    return keys

# -----------------------------
# RAG
# -----------------------------
def retrieve_context(query, top_k=TOP_K, use_raw=False):
    try:
        import chromadb
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        collection = client.get_collection(RAW_COLLECTION if use_raw else CANON_COLLECTION)
        r = requests.post(OLLAMA_EMBED_URL, json={"model": EMBED_MODEL, "prompt": query}, timeout=60)
        r.raise_for_status()
        embedding = r.json().get("embedding")
        if not embedding:
            return ""
        results = collection.query(query_embeddings=[embedding], n_results=top_k, include=["documents", "metadatas"])
        chunks = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                source = meta.get("source_file", "unknown")
                chunks.append(f"[Source: {source}]\n{doc[:400]}")
        return "\n\n".join(chunks)
    except Exception as e:
        print(f"  [WARN] RAG failed: {e}")
        return ""

# -----------------------------
# MODEL QUERIES
# -----------------------------
def query_local(model_id, prompt, timeout=180):
    try:
        start = time.time()
        r = requests.post(OLLAMA_URL, json={"model": model_id, "prompt": prompt, "stream": False, "options": {"temperature": 0.4, "num_ctx": 16384}}, timeout=timeout)
        r.raise_for_status()
        return {"response": r.json().get("response", ""), "elapsed": round(time.time() - start, 1), "error": None}
    except Exception as e:
        return {"response": None, "elapsed": 0, "error": str(e)}

def query_gemini(prompt, api_key, model_id="gemini-1.5-flash"):
    try:
        start = time.time()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
        r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers={"Content-Type": "application/json"}, timeout=120)
        r.raise_for_status()
        text = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        return {"response": text, "elapsed": round(time.time() - start, 1), "error": None}
    except Exception as e:
        return {"response": None, "elapsed": 0, "error": str(e)}

def query_openai_compat(prompt, api_key, url, model_id, timeout=120):
    try:
        start = time.time()
        r = requests.post(url, json={"model": model_id, "messages": [{"role": "user", "content": prompt}], "temperature": 0.4, "max_tokens": 4096}, headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}, timeout=timeout)
        r.raise_for_status()
        text = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"response": text, "elapsed": round(time.time() - start, 1), "error": None}
    except Exception as e:
        return {"response": None, "elapsed": 0, "error": str(e)}

def query_model(model, prompt, api_keys):
    if model["provider"] == "local":
        return query_local(model["id"], prompt)
    key = api_keys.get(model.get("env_key", ""), "")
    if not key:
        return {"response": None, "elapsed": 0, "error": f"Missing key: {model.get('env_key')}"}
    if model["provider"] == "gemini":
        return query_gemini(prompt, key, model["id"])
    return query_openai_compat(prompt, key, model["url"], model["id"])

# -----------------------------
# FOLLOW-UP GENERATOR
# -----------------------------
def generate_followup(topic, round_num, all_responses, synthesizer=DEFAULT_SYNTHESIZER):
    response_block = ""
    for r in all_responses:
        if r["result"]["response"]:
            response_block += f"\n--- {r['name']} ---\n{r['result']['response'][:800]}\n"

    prompt = f"""You are the deliberation moderator for a DDL AutoCouncil session.

TOPIC: {topic}

The following responses were collected in Round {round_num}:
{response_block}

Your job:
1. Identify the 2-3 most important UNRESOLVED disagreements or open questions from this round.
2. For each, write a sharp follow-up question that forces the models to go deeper.
3. If any model made a claim without evidence, call it out and ask for specifics.
4. If the models are converging too quickly, introduce a devil's advocate angle.

Output ONLY the follow-up prompt that will be sent to all models for Round {round_num + 1}.
Do not include preamble or explanation. Just the follow-up prompt.
Keep it under 300 words."""

    result = query_local(synthesizer, prompt, timeout=180)
    return result.get("response", "")

# -----------------------------
# FINAL SYNTHESIS
# -----------------------------
def final_synthesis(topic, all_rounds, synthesizer=DEFAULT_SYNTHESIZER):
    rounds_block = ""
    for round_num, round_data in enumerate(all_rounds):
        rounds_block += f"\n{'='*60}\nROUND {round_num + 1}\n{'='*60}\n"
        rounds_block += f"PROMPT: {round_data['prompt'][:200]}\n\n"
        for r in round_data["responses"]:
            if r["result"]["response"]:
                rounds_block += f"--- {r['name']} ({r['provider']}) ---\n{r['result']['response'][:600]}\n\n"

    prompt = f"""You are producing the FINAL SYNTHESIS for a multi-round DDL AutoCouncil deliberation.

TOPIC: {topic}

DELIBERATION RECORD:
{rounds_block}

SYNTHESIS INSTRUCTIONS:
1. ARC: How did the discussion evolve across rounds? What shifted?
2. CONVERGENCE: What did the models ultimately agree on?
3. PERSISTENT DIVERGENCE: What remained unresolved even after multiple rounds?
4. KEY INSIGHT: What was the single most valuable insight across all rounds? Name the model and round.
5. RISKS IDENTIFIED: What risks were surfaced? Rank by severity.
6. RECOMMENDED ACTIONS: What should the operator do? Prioritize by impact.
7. VERDICT: Based on the full deliberation, what is the council's recommendation? Use LOCK / REVISE / REJECT.
8. ESCALATION: Does this need cloud council review, or is this sufficient?

Be direct. Cite which model said what in which round. This is the definitive record of the deliberation."""

    return query_local(synthesizer, prompt, timeout=300)

# -----------------------------
# SAVE
# -----------------------------
def save_deliberation(folder, topic, all_rounds, final_synth, rag_context=""):
    os.makedirs(folder, exist_ok=True)

    # Topic
    with open(os.path.join(folder, "00_topic.txt"), "w", encoding="utf-8") as f:
        f.write(topic)

    if rag_context:
        with open(os.path.join(folder, "00_rag_context.txt"), "w", encoding="utf-8") as f:
            f.write(rag_context)

    # Each round
    for round_num, round_data in enumerate(all_rounds):
        round_dir = os.path.join(folder, f"round_{round_num + 1:02d}")
        os.makedirs(round_dir, exist_ok=True)

        with open(os.path.join(round_dir, "prompt.txt"), "w", encoding="utf-8") as f:
            f.write(round_data["prompt"])

        if round_data.get("followup"):
            with open(os.path.join(round_dir, "followup.txt"), "w", encoding="utf-8") as f:
                f.write(round_data["followup"])

        for i, r in enumerate(round_data["responses"]):
            tier = "LOCAL" if r["provider"] == "local" else "CLOUD"
            filename = f"{i+1:02d}_{tier}_{r['name']}.txt"
            with open(os.path.join(round_dir, filename), "w", encoding="utf-8") as f:
                f.write(f"MODEL: {r['name']}\n")
                f.write(f"PROVIDER: {r['provider']}\n")
                f.write(f"ELAPSED: {r['result']['elapsed']}s\n\n")
                if r["result"]["error"]:
                    f.write(f"ERROR: {r['result']['error']}\n")
                else:
                    f.write(r["result"]["response"])

    # Final synthesis
    if final_synth and final_synth.get("response"):
        with open(os.path.join(folder, "99_final_synthesis.txt"), "w", encoding="utf-8") as f:
            f.write(f"FINAL SYNTHESIS\n")
            f.write(f"ROUNDS: {len(all_rounds)}\n")
            f.write(f"TIMESTAMP: {datetime.datetime.now().isoformat()}\n\n")
            f.write(final_synth["response"])

    # Metadata
    meta = {
        "timestamp": datetime.datetime.now().isoformat(),
        "topic": topic,
        "rounds": len(all_rounds),
        "models_per_round": len(all_rounds[0]["responses"]) if all_rounds else 0,
        "total_responses": sum(len(rd["responses"]) for rd in all_rounds),
    }
    with open(os.path.join(folder, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"\n  Deliberation saved to: {folder}")

# -----------------------------
# MAIN
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="DDL AutoCouncil Deliberation Engine v1.0")
    parser.add_argument("topic", nargs="?", default=None, help="Deliberation topic")
    parser.add_argument("--rounds", type=int, default=3, help="Number of deliberation rounds")
    parser.add_argument("--local-only", action="store_true", help="Local models only")
    parser.add_argument("--cloud-only", action="store_true", help="Cloud models only")
    parser.add_argument("--all", action="store_true", help="Both local + cloud")
    parser.add_argument("--rag", action="store_true", help="Enable RAG")
    parser.add_argument("--raw", action="store_true", help="Use archive for RAG")
    parser.add_argument("--from-file", default=None, help="Read topic from file")
    parser.add_argument("--top", type=int, default=TOP_K, help="RAG chunks")
    parser.add_argument("--save", default=None, help="Save deliberation to folder")
    parser.add_argument("--synthesizer", default=DEFAULT_SYNTHESIZER, help="Synthesis model")

    args = parser.parse_args()

    if args.from_file:
        with open(args.from_file, "r", encoding="utf-8") as f:
            topic = f.read().strip()
    elif args.topic:
        topic = args.topic
    else:
        parser.print_help()
        return

    api_keys = load_env()

    use_models = []
    if args.cloud_only:
        use_models = CLOUD_MODELS
    elif args.all:
        use_models = LOCAL_MODELS + CLOUD_MODELS
    else:
        use_models = LOCAL_MODELS

    synthesizer = args.synthesizer

    # Header
    print()
    print("=" * 70)
    print("  DDL AUTO-COUNCIL DELIBERATION ENGINE v1.0")
    print("=" * 70)
    print(f"  Topic: {topic[:80]}{'...' if len(topic) > 80 else ''}")
    print(f"  Rounds: {args.rounds}")
    print(f"  Models: {len(use_models)} ({', '.join(m['name'] for m in use_models)})")
    print(f"  Synthesizer: {synthesizer}")
    print(f"  RAG: {'Active' if args.rag else 'Disabled'}")
    if args.save:
        print(f"  Save to: {args.save}")
    print("=" * 70)

    # RAG
    rag_context = ""
    if args.rag:
        print("\n  Retrieving RAG context...")
        rag_context = retrieve_context(topic, top_k=args.top, use_raw=args.raw)
        if rag_context:
            print(f"  Retrieved {len(rag_context)} chars of context.")

    # Build initial prompt
    base_prompt = GOVERNANCE
    if rag_context:
        base_prompt += f"\n\nRETRIEVED CONTEXT:\n{rag_context}"
    base_prompt += f"\n\nDELIBERATION TOPIC:\n{topic}"
    base_prompt += "\n\nTake a clear position. Support it with reasoning. Identify risks. Be specific."

    all_rounds = []
    current_prompt = base_prompt

    for round_num in range(1, args.rounds + 1):
        print(f"\n{'='*70}")
        print(f"  ROUND {round_num} of {args.rounds}")
        print(f"{'='*70}\n")

        responses = []
        for i, model in enumerate(use_models):
            tier = "LOCAL" if model["provider"] == "local" else "CLOUD"
            print(f"  [{i+1}/{len(use_models)}] [{tier}] {model['name']}...", end=" ", flush=True)

            # Use short governance for Groq
            if model.get("provider") == "groq":
                groq_prompt = GOVERNANCE_SHORT + f"\n\nTOPIC: {topic}\n\nTake a clear position. Be specific."
                if round_num > 1:
                    groq_prompt += f"\n\nPREVIOUS ROUND FOLLOW-UP:\n{all_rounds[-1].get('followup', '')[:500]}"
                result = query_model(model, groq_prompt, api_keys)
            else:
                result = query_model(model, current_prompt, api_keys)

            responses.append({
                "name": model["name"],
                "provider": model.get("provider", "local"),
                "model_id": model["id"],
                "result": result,
            })

            if result["error"]:
                print(f"ERROR ({result['error'][:50]})")
            else:
                preview = result["response"][:100].replace("\n", " ")
                print(f"({result['elapsed']}s) {preview}...")

        round_data = {
            "round": round_num,
            "prompt": current_prompt[:500],
            "responses": responses,
            "followup": None,
        }

        # Generate follow-up if not the last round
        if round_num < args.rounds:
            print(f"\n  Generating follow-up questions for Round {round_num + 1}...")
            followup = generate_followup(topic, round_num, responses, synthesizer)
            round_data["followup"] = followup

            if followup:
                print(f"\n  {'─'*60}")
                print(f"  FOLLOW-UP FOR ROUND {round_num + 1}:")
                print(f"  {'─'*60}")
                print(f"  {followup[:500]}")
                print(f"  {'─'*60}")

                # Build next round prompt with follow-up
                current_prompt = GOVERNANCE
                if rag_context:
                    current_prompt += f"\n\nRETRIEVED CONTEXT:\n{rag_context}"
                current_prompt += f"\n\nDELIBERATION TOPIC: {topic}"
                current_prompt += f"\n\nThis is Round {round_num + 1} of a multi-round deliberation."
                current_prompt += f"\n\nFOLLOW-UP FROM PREVIOUS ROUND:\n{followup}"
                current_prompt += "\n\nRespond to the follow-up questions. Deepen your analysis. If your position has changed, explain why."
            else:
                print("  [No follow-up generated — continuing to synthesis]")

        all_rounds.append(round_data)

    # Final synthesis
    print(f"\n{'='*70}")
    print(f"  FINAL SYNTHESIS (across {len(all_rounds)} rounds)")
    print(f"{'='*70}\n")
    print("  Generating final synthesis...")

    final_synth = final_synthesis(topic, all_rounds, synthesizer)

    if final_synth and final_synth.get("response"):
        print(f"\n{final_synth['response']}")
    else:
        print(f"  ERROR: {final_synth.get('error', 'Unknown error')}")

    print(f"\n{'='*70}")

    # Save
    if args.save:
        save_deliberation(args.save, topic, all_rounds, final_synth, rag_context)

    # Log
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "topic": topic[:500],
        "rounds": len(all_rounds),
        "models": len(use_models),
        "total_responses": sum(len(rd["responses"]) for rd in all_rounds),
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except:
        pass

    print(f"  Log: {LOG_FILE}")
    print()

if __name__ == "__main__":
    main()
