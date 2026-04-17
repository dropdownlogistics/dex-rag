"""
dex_core.py — Shared foundation for all Dex Jr. tools.

Single source of truth for config, connections, and utilities.
When the _v2 rename ceremony happens: change COLLECTION_SUFFIX to "".
One file. One line. Done everywhere.

Step 54 | Authority: CLAUDE.md Refactor Target #1
"""

import os
import requests
from typing import Optional

# ── Paths ────────────────────────────────────────────────────────────────────

CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"
INGEST_CACHE_DIR = r"C:\Users\dkitc\.dex-jr\ingest_cache"
BACKUP_DIR = r"D:\DDL_Backup\chromadb_backups"
INGEST_DIR = r"C:\Users\dkitc\OneDrive\DDL_Ingest"
SWEEP_REPORTS_DIR = os.path.join(INGEST_DIR, "_sweep_reports")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Models ───────────────────────────────────────────────────────────────────

OLLAMA_HOST = "http://localhost:11434"
EMBED_MODEL = os.environ.get("DEXJR_EMBED_MODEL", "mxbai-embed-large")
GEN_MODEL = "qwen2.5-coder:7b"

# Adaptive truncation for mxbai-embed-large (512-token context)
EMBED_TRUNC_LEVELS = (1200, 900, 600, 300)

# ── Collections ──────────────────────────────────────────────────────────────

COLLECTION_SUFFIX = os.environ.get("DEXJR_COLLECTION_SUFFIX", "_v2")

# Registry — base names. Suffix applied via suffixed().
COLLECTIONS = {
    "dex_canon":     {"weight": 0.90, "label": "Canon",        "status": "LIVE"},
    "ddl_archive":   {"weight": 0.65, "label": "Archive",      "status": "LIVE"},
    "dex_code":      {"weight": 0.85, "label": "Code",         "status": "LIVE"},
    "ext_creator":   {"weight": 0.85, "label": "ExtCreator",   "status": "LIVE"},
    "ext_reference": {"weight": 0.75, "label": "ExtReference", "status": "PROVISIONED"},
}

# Hard-gated — never ingest under any circumstance (ADR-CORPUS-001 Rule 3)
GATED_COLLECTIONS = ["dex_dave"]

# Floor values for health checks (Step 33c baseline)
CHUNK_FLOORS = {
    "dex_canon":   253_978,
    "ddl_archive": 291_520,
    "dex_code":     20_384,
    "ext_creator":     922,
}

# ── Multi-host (Tailscale MagicDNS) ─────────────────────────────────────────

HOSTS = {
    "reborn": {
        "url": "http://reborn:11434",
        "fallback_url": "http://localhost:11434",
        "gpu": "RTX 3070",
    },
    "gaminglaptop": {
        "url": "http://gaminglaptop:11434",
        "gpu": "RTX 3060",
    },
}


# ── Collection helpers ───────────────────────────────────────────────────────

def suffixed(name: str) -> str:
    """Apply collection suffix to a base name."""
    return name + COLLECTION_SUFFIX


def get_live_collections() -> list[str]:
    """Return suffixed names of all LIVE collections."""
    return [suffixed(k) for k, v in COLLECTIONS.items() if v["status"] == "LIVE"]


def is_gated(collection_name: str) -> bool:
    """Check if a collection is hard-gated (never ingest)."""
    return any(collection_name.startswith(g) for g in GATED_COLLECTIONS)


# ── ChromaDB ─────────────────────────────────────────────────────────────────

def get_chroma_client():
    """Single ChromaDB connection factory."""
    import chromadb
    return chromadb.PersistentClient(path=CHROMA_DIR)


def get_collection(name: str):
    """Get a collection by base name (suffix applied automatically)."""
    client = get_chroma_client()
    return client.get_collection(suffixed(name))


# ── Embedding ────────────────────────────────────────────────────────────────

def embed(text: str) -> list[float]:
    """Embed text with adaptive truncation for mxbai-embed-large."""
    last_err: Exception | None = None
    for lim in EMBED_TRUNC_LEVELS:
        prompt = (text or "")[:lim]
        try:
            r = requests.post(
                f"{OLLAMA_HOST}/api/embeddings",
                json={"model": EMBED_MODEL, "prompt": prompt},
                timeout=60,
            )
            if r.status_code == 200:
                return r.json()["embedding"]
            last_err = requests.HTTPError(
                f"{r.status_code} at trunc={lim}: {r.text[:200]}"
            )
        except requests.RequestException as e:
            last_err = e
    if last_err:
        raise last_err
    raise RuntimeError("embed: unreachable")


# ── Host resolution ──────────────────────────────────────────────────────────

def get_ollama_url(host_name: str) -> Optional[str]:
    """Resolve Ollama URL for a host. Try primary, then fallback."""
    host = HOSTS.get(host_name, HOSTS["reborn"])
    try:
        r = requests.get(f"{host['url']}/api/tags", timeout=5)
        if r.status_code == 200:
            return host["url"]
    except Exception:
        pass
    fallback = host.get("fallback_url")
    if fallback:
        try:
            r = requests.get(f"{fallback}/api/tags", timeout=5)
            if r.status_code == 200:
                return fallback
        except Exception:
            pass
    return None


# ── Primer ───────────────────────────────────────────────────────────────────

PRIMER_PATH = os.path.join(SCRIPT_DIR, "DDL_PRIMER.md")


def load_primer() -> str:
    """Load DDL_PRIMER.md for injection into query context.
    Returns empty string if file not found (graceful degradation)."""
    if os.path.exists(PRIMER_PATH):
        try:
            with open(PRIMER_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""
    return ""


# ── Council roster ───────────────────────────────────────────────────────────

COUNCIL_SEATS = {
    0:    {"name": "Emily",             "role": "verification authority"},
    1001: {"name": "Archer Hawthorne",  "role": "structural cartography"},
    1002: {"name": "Marcus Caldwell",   "role": "LLMPM, architecture"},
    1003: {"name": "Elias Mercer",      "role": "contradiction detection"},
    1004: {"name": "Max Sullivan",      "role": "sourced, decisive"},
    1005: {"name": "Rowan Bennett",     "role": "operational rigor"},
    1006: {"name": "Ava Sinclair",      "role": "big-picture framing"},
    1007: {"name": "Leo Prescott",      "role": "tactical crystallizer"},
    1008: {"name": "Marcus Grey",       "role": "synthesis, PM voice"},
    1009: {"name": "Kai Langford",      "role": "systems architecture"},
    1010: {"name": "Dex Jr.",           "role": "local governed model"},
    1011: {"name": "Connor",            "role": "audit architect"},
}

# Default voting seats (Seat 0 excluded — verification authority, not a voter)
DEFAULT_VOTING_SEATS = [s for s in COUNCIL_SEATS if s != 0]

REVIEW_DIR = os.path.join(SCRIPT_DIR, "council-reviews")
