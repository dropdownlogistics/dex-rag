"""
DEX JR HYBRID AUTO-COUNCIL — v3.0 (Definitive)
Local models + Free cloud APIs + Governance + RAG + Save + Ingest

Usage:
  python dex-council.py "your prompt here"
  python dex-council.py "your prompt here" --all --rag
  python dex-council.py "your prompt here" --all --rag --save council-runs/my-review
  python dex-council.py "your prompt here" --all --rag --save council-runs/my-review --ingest
  python dex-council.py --synthesize council-runs/my-review
  python dex-council.py --from-file prompt.txt --all --rag

Tiers:
  LOCAL:  qwen2.5-coder:7b, llama3.1:8b, deepseek-r1:8b (gaming rig)
  CLOUD:  Gemini 2.5 Flash, Mistral Small (free APIs)
  SYNTH:  Dexcell (governed local model)

Features:
  --save PATH        Save all responses + synthesis to folder
  --synthesize PATH  Re-synthesize from saved folder
  --ingest           Auto-ingest saved outputs into RAG corpus
  --retry            Retry failed models once
  --timeout N        Custom timeout per model (default 180s)
  --verbose          Show full responses instead of previews

Dropdown Logistics — Chaos -> Structured -> Automated
Hybrid AutoCouncil v3.0 | 2026-03-06
"""

import os
import sys
import json
import time
import argparse
import datetime
import requests
import subprocess

# -----------------------------
# CONFIG
# -----------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(SCRIPT_DIR, ".env")
LOG_FILE = os.path.join(SCRIPT_DIR, "dex-council-log.jsonl")

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"

CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"
CANON_COLLECTION = "dex_canon"
RAW_COLLECTION = "ddl_archive"
EMBED_MODEL = "nomic-embed-text"

DEFAULT_SYNTHESIZER = "dexjr"
DEFAULT_TIMEOUT = 180
TOP_K = 5

# Local models (gaming rig via Ollama)
LOCAL_MODELS = [
    {"id": "qwen2.5-coder:7b", "name": "Qwen (Code Specialist)", "provider": "local"},
    {"id": "llama3.1:8b", "name": "Llama (General Reasoning)", "provider": "local"},
    {"id": "deepseek-r1:8b", "name": "DeepSeek-Local (Chain-of-Thought)", "provider": "local"},
]

# Cloud models (FREE TIER ONLY — tested and working)
CLOUD_MODELS = [
    {
        "id": "gemini-2.5-flash",
        "name": "Gemini (Google)",
        "provider": "gemini",
        "env_key": "GEMINI_API_KEY",
    },
    {
        "id": "mistral-small-latest",
        "name": "Mistral/LeChat (European)",
        "provider": "mistral",
        "env_key": "MISTRAL_API_KEY",
        "url": "https://api.mistral.ai/v1/chat/completions",
    },
]

# Disabled cloud models (uncomment when credits/payment added)
# {
#     "id": "deepseek-chat",
#     "name": "DeepSeek-Cloud",
#     "provider": "deepseek",
#     "env_key": "DEEPSEEK_API_KEY",
#     "url": "https://api.deepseek.com/v1/chat/completions",
# },
# {
#     "id": "grok-2-latest",
#     "name": "Grok (xAI)",
#     "provider": "grok",
#     "env_key": "GROK_API_KEY",
#     "url": "https://api.x.ai/v1/chat/completions",
# },
# {
#     "id": "llama-3.1-8b-instant",
#     "name": "Groq-Llama",
#     "provider": "groq",
#     "env_key": "GROQ_API_KEY",
#     "url": "https://api.groq.com/openai/v1/chat/completions",
# },

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
# GOVERNANCE
# -----------------------------
# =====================================================
# COUNCIL GOVERNANCE BLOCK — v4.1 ALIGNED
# =====================================================
# Replaces the GOVERNANCE string in dex-council.py
#
# WHAT WAS REMOVED (now owned by Modelfile v4.1):
#   - CottageHumble design tokens (palette, fonts, bans)
#   - Operator behavioral patterns (ADHD, burst mode, evening hours)
#   - Canon > Archive source weighting
#   - "When you don't know" fallback
#   - "Models advise, operator decides" boundary
#
# WHAT STAYS (council-specific, not in Modelfile):
#   - Governance hierarchy (7 levels)
#   - Council structure and review mechanics
#   - Artifact type definitions
#   - Divergence-before-convergence instruction
#   - Clinical boundary
#   - DDL/DexOS/MindFrame definitions (cloud models need these)
#
# NOTE: Cloud models (Gemini, Mistral) don't have the
# Modelfile. This block is their ONLY governance layer.
# Dexjr gets this PLUS the Modelfile. Minor duplication
# on identity/hierarchy is acceptable — contradiction is not.
# =====================================================

GOVERNANCE = """GOVERNANCE CONTEXT — DDL AutoCouncil
You are reviewing documents and producing structured assessments as part of a Dropdown Logistics (DDL) council review.
DDL is a one-person governance and analytics operation run by D.K. Hale (CPA, 10+ years audit).
Methodology: Chaos -> Structured -> Automated.

CORE SYSTEMS:
- DDL: Operational methodology. Star schema dimensional modeling. If it generates data, DDL builds the system.
- DexOS: AI behavior governance. Manifest (llms.txt), council (10 seats), behavioral contracts.
- MindFrame: Persona calibration. Per-model cognitive tuning.
- DDL is NOT "Data Definition Language." DexOS is NOT "Distributed Execution Operating System."

GOVERNANCE HIERARCHY (highest to lowest):
1. Safety & Ethics
2. Operator Authority
3. Governance Artifacts (STD-, PRO-, llms.txt)
4. Council Consensus (CR-, SYN-)
5. Procedural Rules
6. Heuristic Judgment
7. Interpretive Judgment
When governance and heuristic conflict: governance wins. Always.

COUNCIL STRUCTURE:
- 9 cloud models (seats 1001-1009) + 1 local model (seat 1010, Dexcell/Dex Jr.)
- Reviews use LOCK/REVISE/REJECT verdicts
- Artifact types: CR- (review), PRO- (protocol), STD- (standard), SYS- (system), REC- (recommendation), OBS- (observation)
- Divergence before convergence — respond independently, then synthesize

BOUNDARIES:
- Clinical: Never diagnose mental health. Pivot to structural pattern analysis.
- RED zones: Layouts, navigation, design tokens, governed artifacts — halt and escalate.
- Silent fixes: Never silently correct architecture. Halt, flag, ask.

Respond with structured reasoning. Be direct. Be specific."""

# -----------------------------
# RAG
# -----------------------------
def retrieve_context(query, top_k=TOP_K, use_raw=False):
    try:
        import chromadb
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        col_name = RAW_COLLECTION if use_raw else CANON_COLLECTION
        collection = client.get_collection(col_name)
        r = requests.post(
            OLLAMA_EMBED_URL,
            json={"model": EMBED_MODEL, "prompt": query},
            timeout=60,
        )
        r.raise_for_status()
        embedding = r.json().get("embedding")
        if not embedding:
            return ""
        results = collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            include=["documents", "metadatas"],
        )
        chunks = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                source = meta.get("source_file", "unknown")
                chunks.append(f"[Source: {source}]\n{doc[:500]}")
        return "\n\n".join(chunks)
    except Exception as e:
        print(f"  [WARN] RAG retrieval failed: {e}")
        return ""

# -----------------------------
# MODEL QUERIES
# -----------------------------
def query_local(model_id, prompt, timeout=DEFAULT_TIMEOUT):
    try:
        start = time.time()
        r = requests.post(
            OLLAMA_URL,
            json={
                "model": model_id,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_ctx": 16384},
            },
            timeout=timeout,
        )
        r.raise_for_status()
        elapsed = time.time() - start
        return {
            "response": r.json().get("response", "[No response]"),
            "elapsed": round(elapsed, 1),
            "error": None,
        }
    except Exception as e:
        return {"response": None, "elapsed": 0, "error": str(e)}

def query_gemini(prompt, api_key, model_id="gemini-2.5-flash", timeout=120):
    try:
        start = time.time()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
        r = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "[No response]")
        elapsed = time.time() - start
        return {"response": text, "elapsed": round(elapsed, 1), "error": None}
    except Exception as e:
        return {"response": None, "elapsed": 0, "error": str(e)}

def query_openai_compatible(prompt, api_key, url, model_id, timeout=120):
    try:
        start = time.time()
        r = requests.post(
            url,
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 4096,
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "[No response]")
        elapsed = time.time() - start
        return {"response": text, "elapsed": round(elapsed, 1), "error": None}
    except Exception as e:
        return {"response": None, "elapsed": 0, "error": str(e)}

def query_cloud(model, prompt, api_keys, timeout=120):
    key = api_keys.get(model["env_key"], "")
    if not key:
        return {"response": None, "elapsed": 0, "error": f"Missing API key: {model['env_key']}"}
    if model["provider"] == "gemini":
        return query_gemini(prompt, key, model["id"], timeout)
    else:
        return query_openai_compatible(prompt, key, model["url"], model["id"], timeout)

# -----------------------------
# GOVERNED PROMPT BUILDER
# -----------------------------
def build_governed_prompt(prompt, rag_context=""):
    parts = [GOVERNANCE]
    if rag_context:
        parts.append(f"\nRETRIEVED CONTEXT (from DDL knowledge base):\n{rag_context}")
    parts.append(f"\nPROMPT:\n{prompt}")
    return "\n".join(parts)

# -----------------------------
# SYNTHESIS
# -----------------------------
def synthesize(prompt, responses, synthesizer=DEFAULT_SYNTHESIZER):
    response_block = ""
    for i, r in enumerate(responses):
        if r["result"]["response"]:
            response_block += f"\n{'='*60}\nMODEL {i+1}: {r['name']} [{r['provider'].upper()}]\n{'='*60}\n{r['result']['response']}\n"
        else:
            response_block += f"\n{'='*60}\nMODEL {i+1}: {r['name']} [{r['provider'].upper()}]\n{'='*60}\n[FAILED: {r['result']['error']}]\n"

    synthesis_prompt = f"""You are the synthesis engine for a DDL Hybrid AutoCouncil review.

The following prompt was sent independently to {len(responses)} AI models across local and cloud tiers.
Each model received identical governance context from the DDL architecture.
Each model responded without seeing the others' responses.

ORIGINAL PROMPT:
{prompt}

MODEL RESPONSES:
{response_block}

SYNTHESIS INSTRUCTIONS:
1. CONVERGENCE: What did all or most models agree on?
2. DIVERGENCE: Where did models disagree? Note which model said what.
3. UNIQUE INSIGHTS: Did any model surface something unique? Name it.
4. LOCAL vs CLOUD: Any meaningful quality or speed differences?
5. RECOMMENDED ACTIONS: What should the operator do next? Prioritize.
6. CONFIDENCE: High/Medium/Low based on convergence.
7. VERDICT: LOCK / REVISE / REJECT
8. ESCALATION: Sufficient, or needs cloud council / operator review?

Be direct. Cite models. No filler."""

    return query_local(synthesizer, synthesis_prompt, timeout=300)

# -----------------------------
# SAVE TO FOLDER
# -----------------------------
def save_to_folder(folder, prompt, responses, synthesis, rag_context=""):
    os.makedirs(folder, exist_ok=True)

    # Prompt
    with open(os.path.join(folder, "00_prompt.txt"), "w", encoding="utf-8") as f:
        f.write(prompt)

    # RAG context
    if rag_context:
        with open(os.path.join(folder, "00_rag_context.txt"), "w", encoding="utf-8") as f:
            f.write(rag_context)

    # Individual responses
    for i, r in enumerate(responses):
        tier = "LOCAL" if r["provider"] == "local" else "CLOUD"
        safe_name = r["name"].replace(" ", "_").replace("/", "-").replace("(", "").replace(")", "")
        filename = f"{i+1:02d}_{tier}_{safe_name}.txt"
        with open(os.path.join(folder, filename), "w", encoding="utf-8") as f:
            f.write(f"MODEL: {r['name']}\n")
            f.write(f"PROVIDER: {r['provider']}\n")
            f.write(f"MODEL_ID: {r['model_id']}\n")
            f.write(f"ELAPSED: {r['result']['elapsed']}s\n")
            f.write(f"TIMESTAMP: {datetime.datetime.now().isoformat()}\n")
            if r["result"]["error"]:
                f.write(f"ERROR: {r['result']['error']}\n")
            else:
                f.write(f"\n{'='*60}\nRESPONSE\n{'='*60}\n\n")
                f.write(r["result"]["response"])

    # Synthesis
    if synthesis and synthesis.get("response"):
        with open(os.path.join(folder, "99_synthesis.txt"), "w", encoding="utf-8") as f:
            f.write(f"SYNTHESIZER: {DEFAULT_SYNTHESIZER}\n")
            f.write(f"ELAPSED: {synthesis['elapsed']}s\n")
            f.write(f"TIMESTAMP: {datetime.datetime.now().isoformat()}\n")
            f.write(f"\n{'='*60}\nSYNTHESIS\n{'='*60}\n\n")
            f.write(synthesis["response"])

    # Full transcript (single file with everything — easy to ingest)
    with open(os.path.join(folder, "99_full_transcript.txt"), "w", encoding="utf-8") as f:
        f.write(f"DDL AUTOCOUNCIL REVIEW TRANSCRIPT\n")
        f.write(f"{'='*60}\n")
        f.write(f"PROMPT: {prompt}\n")
        f.write(f"TIMESTAMP: {datetime.datetime.now().isoformat()}\n")
        f.write(f"MODELS: {len(responses)}\n")
        f.write(f"{'='*60}\n\n")
        for i, r in enumerate(responses):
            tier = "LOCAL" if r["provider"] == "local" else "CLOUD"
            f.write(f"\n{'─'*60}\n")
            f.write(f"MODEL {i+1}: {r['name']} [{tier}] ({r['result']['elapsed']}s)\n")
            f.write(f"{'─'*60}\n\n")
            if r["result"]["error"]:
                f.write(f"ERROR: {r['result']['error']}\n")
            else:
                f.write(r["result"]["response"])
            f.write("\n")
        if synthesis and synthesis.get("response"):
            f.write(f"\n{'='*60}\n")
            f.write(f"SYNTHESIS (by Dexcell, Seat 1010)\n")
            f.write(f"{'='*60}\n\n")
            f.write(synthesis["response"])

    # Metadata
    meta = {
        "timestamp": datetime.datetime.now().isoformat(),
        "version": "3.0",
        "prompt": prompt,
        "model_count": len(responses),
        "successful": sum(1 for r in responses if r["result"]["response"]),
        "failed": sum(1 for r in responses if r["result"]["error"]),
        "models": [
            {
                "name": r["name"],
                "provider": r["provider"],
                "model_id": r["model_id"],
                "elapsed": r["result"]["elapsed"],
                "error": r["result"]["error"],
                "response_length": len(r["result"]["response"]) if r["result"]["response"] else 0,
            }
            for r in responses
        ],
        "synthesis_elapsed": synthesis["elapsed"] if synthesis else 0,
    }
    with open(os.path.join(folder, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print(f"\n  Saved to: {folder}")
    print(f"  Files: {len(os.listdir(folder))}")

# -----------------------------
# AUTO-INGEST TO CORPUS
# -----------------------------
def auto_ingest(folder):
    """Copy the full transcript to the canon folder and trigger ingestion."""
    transcript = os.path.join(folder, "99_full_transcript.txt")
    if not os.path.exists(transcript):
        print("  [WARN] No transcript to ingest.")
        return

    canon_dir = r"C:\\Users\\dexjr\\99_DexUniverseArchive\\00_Archive\\AutoCouncil-Live"
    os.makedirs(canon_dir, exist_ok=True)

    # Generate unique filename
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = os.path.basename(folder).replace(" ", "_")
    dest = os.path.join(canon_dir, f"AutoCouncil_{basename}_{ts}.txt")

    try:
        import shutil
        shutil.copy2(transcript, dest)
        print(f"  Copied transcript to corpus: {dest}")

        # Run ingestion
        ingest_script = os.path.join(SCRIPT_DIR, "dex-ingest.py")
        if os.path.exists(ingest_script):
            print("  Running corpus ingestion...")
            result = subprocess.run(
                ["python", ingest_script, "--path", canon_dir, "--build-canon", "--fast"],
                capture_output=True, text=True, timeout=300
            )
            if "INGESTION COMPLETE" in result.stdout:
                # Extract new chunk count
                for line in result.stdout.split("\n"):
                    if "New chunks added CANON" in line:
                        print(f"  {line.strip()}")
                        break
            else:
                print(f"  [WARN] Ingestion output: {result.stdout[-200:]}")
        else:
            print(f"  [WARN] Ingest script not found at {ingest_script}")
    except Exception as e:
        print(f"  [WARN] Auto-ingest failed: {e}")

# -----------------------------
# RE-SYNTHESIZE FROM FOLDER
# -----------------------------
def resynthesize(folder, synthesizer=DEFAULT_SYNTHESIZER):
    prompt_path = os.path.join(folder, "00_prompt.txt")
    if not os.path.exists(prompt_path):
        print(f"  ERROR: No prompt file found in {folder}")
        return

    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt = f.read().strip()

    # Read response files
    responses_text = []
    for filename in sorted(os.listdir(folder)):
        if filename.endswith(".txt") and not filename.startswith("00") and not filename.startswith("99"):
            filepath = os.path.join(folder, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            lines = content.split("\n")
            name = lines[0].replace("MODEL: ", "") if lines else "Unknown"
            provider = lines[1].replace("PROVIDER: ", "") if len(lines) > 1 else "unknown"
            body = ""
            if "RESPONSE" in content:
                parts = content.split("RESPONSE\n" + "=" * 60 + "\n\n", 1)
                body = parts[-1] if len(parts) > 1 else ""
            responses_text.append({"name": name, "provider": provider, "body": body})

    if not responses_text:
        print(f"  ERROR: No responses found in {folder}")
        return

    print(f"\n  Re-synthesizing {len(responses_text)} responses from {folder}")

    response_block = ""
    for i, r in enumerate(responses_text):
        if r["body"]:
            response_block += f"\n{'='*60}\nMODEL {i+1}: {r['name']} [{r['provider'].upper()}]\n{'='*60}\n{r['body']}\n"

    synthesis_prompt = f"""You are re-synthesizing a DDL AutoCouncil review.

ORIGINAL PROMPT:
{prompt}

MODEL RESPONSES:
{response_block}

SYNTHESIS INSTRUCTIONS:
1. CONVERGENCE: What did models agree on?
2. DIVERGENCE: Where did they disagree? Cite models.
3. UNIQUE INSIGHTS: Anything only one model surfaced?
4. RECOMMENDED ACTIONS: Prioritize by impact.
5. VERDICT: LOCK / REVISE / REJECT
6. ESCALATION: Sufficient or needs further review?

Be direct. Cite models. No filler."""

    result = query_local(synthesizer, synthesis_prompt, timeout=300)

    print(f"\n{'='*70}")
    print(f"  RE-SYNTHESIS (by Dexcell, Seat 1010)")
    print(f"{'='*70}\n")
    if result.get("response"):
        print(result["response"])
    else:
        print(f"  ERROR: {result.get('error')}")
    print(f"\n{'='*70}")

    # Save
    synth_path = os.path.join(folder, "99_resynthesis.txt")
    with open(synth_path, "w", encoding="utf-8") as f:
        f.write(f"RE-SYNTHESIS\n")
        f.write(f"SYNTHESIZER: {synthesizer}\n")
        f.write(f"TIMESTAMP: {datetime.datetime.now().isoformat()}\n\n")
        f.write(result.get("response", "[No response]"))
    print(f"  Saved to: {synth_path}")

# -----------------------------
# DISPLAY
# -----------------------------
def display_header(prompt, local_models, cloud_models, synthesizer, use_rag, save_path, ingest):
    total = len(local_models) + len(cloud_models)
    print()
    print("=" * 70)
    print("  DDL HYBRID AUTO-COUNCIL v3.0")
    print("=" * 70)
    print(f"  Prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")
    if local_models:
        print(f"  Local: {len(local_models)} ({', '.join(m['name'] for m in local_models)})")
    if cloud_models:
        print(f"  Cloud: {len(cloud_models)} ({', '.join(m['name'] for m in cloud_models)})")
    print(f"  Total: {total} models")
    print(f"  Synth: {synthesizer}")
    print(f"  RAG: {'Active' if use_rag else 'Off'}")
    if save_path:
        print(f"  Save: {save_path}")
    if ingest:
        print(f"  Ingest: Auto-ingest to corpus after save")
    print("=" * 70)
    print()

def display_response(index, name, provider, result, verbose=False):
    tier = "LOCAL" if provider == "local" else "CLOUD"
    elapsed = f"{result['elapsed']}s" if result['elapsed'] else "—"
    if result["error"]:
        print(f"  [{index+1}] [{tier}] {name} — FAILED ({result['error'][:60]})")
    elif verbose:
        print(f"  [{index+1}] [{tier}] {name} ({elapsed})")
        print(f"{'─'*60}")
        print(result["response"])
        print(f"{'─'*60}")
    else:
        preview = result["response"][:150].replace("\n", " ")
        print(f"  [{index+1}] [{tier}] {name} ({elapsed})")
        print(f"      {preview}...")
    print()

def display_synthesis(result, verbose=False):
    print()
    print("=" * 70)
    print("  SYNTHESIS (by Dexcell, Seat 1010)")
    print("=" * 70)
    print()
    if result.get("error"):
        print(f"  ERROR: {result['error']}")
    else:
        print(result["response"])
    print()
    print("=" * 70)

# -----------------------------
# LOGGING
# -----------------------------
def log_council(prompt, responses, synthesis, synthesizer, use_rag):
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "version": "3.0",
        "prompt": prompt[:500],
        "synthesizer": synthesizer,
        "rag_active": use_rag,
        "model_count": len(responses),
        "local_count": sum(1 for r in responses if r["provider"] == "local"),
        "cloud_count": sum(1 for r in responses if r["provider"] != "local"),
        "successful": sum(1 for r in responses if r["result"]["response"]),
        "failed": sum(1 for r in responses if r["result"]["error"]),
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except:
        pass

# -----------------------------
# MAIN
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="DDL Hybrid AutoCouncil v3.0")
    parser.add_argument("prompt", nargs="?", default=None, help="Prompt to send")
    parser.add_argument("--local-only", action="store_true", help="Local only")
    parser.add_argument("--cloud-only", action="store_true", help="Cloud only")
    parser.add_argument("--all", action="store_true", help="Local + Cloud")
    parser.add_argument("--synthesizer", default=DEFAULT_SYNTHESIZER)
    parser.add_argument("--rag", action="store_true", help="Enable RAG")
    parser.add_argument("--raw", action="store_true", help="Archive RAG")
    parser.add_argument("--from-file", default=None, help="Prompt from file")
    parser.add_argument("--top", type=int, default=TOP_K)
    parser.add_argument("--no-governance", action="store_true")
    parser.add_argument("--save", default=None, help="Save to folder")
    parser.add_argument("--ingest", action="store_true", help="Auto-ingest to corpus")
    parser.add_argument("--synthesize", default=None, help="Re-synth from folder")
    parser.add_argument("--retry", action="store_true", help="Retry failed models")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--verbose", action="store_true", help="Full responses")

    args = parser.parse_args()

    # Re-synthesize mode
    if args.synthesize:
        resynthesize(args.synthesize, synthesizer=args.synthesizer)
        return

    # Get prompt
    if args.from_file:
        with open(args.from_file, "r", encoding="utf-8") as f:
            prompt = f.read().strip()
    elif args.prompt:
        prompt = args.prompt
    else:
        parser.print_help()
        return

    # Load keys
    api_keys = load_env()

    # Models
    use_local = []
    use_cloud = []
    if args.cloud_only:
        use_cloud = CLOUD_MODELS
    elif args.all:
        use_local = LOCAL_MODELS
        use_cloud = CLOUD_MODELS
    else:
        use_local = LOCAL_MODELS

    synthesizer = args.synthesizer
    governed = not args.no_governance

    # Header
    display_header(prompt, use_local, use_cloud, synthesizer, args.rag, args.save, args.ingest)

    # RAG
    rag_context = ""
    if args.rag:
        print("  Retrieving RAG context...")
        rag_context = retrieve_context(prompt, top_k=args.top, use_raw=args.raw)
        if rag_context:
            print(f"  Retrieved {len(rag_context)} chars of context.\n")
        else:
            print("  No relevant context found.\n")

    # Build prompt
    full_prompt = build_governed_prompt(prompt, rag_context) if governed else prompt

    # Query models
    responses = []
    total = len(use_local) + len(use_cloud)
    idx = 0

    for model in use_local:
        idx += 1
        print(f"  Querying {idx}/{total}: [LOCAL] {model['name']}...")
        result = query_local(model["id"], full_prompt, timeout=args.timeout)
        responses.append({
            "name": model["name"], "provider": "local",
            "model_id": model["id"], "result": result,
        })
        display_response(idx - 1, model["name"], "local", result, args.verbose)

    for model in use_cloud:
        idx += 1
        print(f"  Querying {idx}/{total}: [CLOUD] {model['name']}...")
        result = query_cloud(model, full_prompt, api_keys, timeout=args.timeout)

        # Retry once on failure
        if result["error"] and args.retry:
            print(f"      Retrying {model['name']}...")
            time.sleep(2)
            result = query_cloud(model, full_prompt, api_keys, timeout=args.timeout)

        responses.append({
            "name": model["name"], "provider": model["provider"],
            "model_id": model["id"], "result": result,
        })
        display_response(idx - 1, model["name"], model["provider"], result, args.verbose)

    # Synthesize
    print("  Running synthesis...")
    synthesis = synthesize(prompt, responses, synthesizer=synthesizer)
    display_synthesis(synthesis, args.verbose)

    # Save
    if args.save:
        save_to_folder(args.save, prompt, responses, synthesis, rag_context)

    # Auto-ingest
    if args.save and args.ingest:
        auto_ingest(args.save)

    # Log
    log_council(prompt, responses, synthesis, synthesizer, args.rag)

    # Summary
    ok = sum(1 for r in responses if r["result"]["response"])
    fail = sum(1 for r in responses if r["result"]["error"])
    print(f"\n  Log: {LOG_FILE}")
    print(f"  Results: {ok} responded, {fail} failed, {total} total")
    print()

if __name__ == "__main__":
    main()
