"""Step 33a — /api/embed batching probe. Benchmarks throughput at
various batch sizes on 500 real dex_canon chunks."""
from __future__ import annotations
import json
import sys
import time

import chromadb
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHROMA_DIR = r"C:\Users\dkitc\.dex-jr\chromadb"
OLLAMA = "http://localhost:11434"
MODEL = "mxbai-embed-large"
MAX_CHARS = 1200
N_SAMPLES = 500
BATCH_SIZES = [1, 8, 16, 32, 64, 128]


def _safe_trunc(t: str, limit: int) -> str:
    return (t or "")[:limit]


def embed_batch(texts: list[str]) -> list[list[float]] | None:
    for lim in (MAX_CHARS, 900, 600, 300):
        trimmed = [_safe_trunc(t, lim) for t in texts]
        try:
            r = requests.post(f"{OLLAMA}/api/embed",
                              json={"model": MODEL, "input": trimmed},
                              timeout=300)
            if r.status_code == 200:
                return r.json()["embeddings"]
        except Exception:
            continue
    return None  # give up on this batch


def embed_single(text: str) -> list[float] | None:
    for lim in (MAX_CHARS, 900, 600, 300):
        try:
            r = requests.post(f"{OLLAMA}/api/embeddings",
                              json={"model": MODEL,
                                    "prompt": _safe_trunc(text, lim)},
                              timeout=60)
            if r.status_code == 200:
                return r.json()["embedding"]
        except Exception:
            continue
    return None


def main():
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    src = client.get_collection("dex_canon")
    got = src.get(limit=N_SAMPLES, include=["documents"])
    docs = [d for d in (got.get("documents") or []) if d]
    print(f"Loaded {len(docs)} sample chunks from dex_canon")

    results = {}
    for bs in BATCH_SIZES:
        # warm-up: drop first batch so model load time doesn't skew
        if bs == 1:
            _ = embed_single(docs[0])
            t0 = time.time()
            skipped = 0
            for d in docs:
                if embed_single(d) is None:
                    skipped += 1
            elapsed = time.time() - t0
        else:
            _ = embed_batch(docs[:bs])
            t0 = time.time()
            skipped = 0
            for i in range(0, len(docs), bs):
                b = docs[i:i + bs]
                out = embed_batch(b)
                if out is None:
                    skipped += len(b)
            elapsed = time.time() - t0

        if elapsed is None:
            results[bs] = {"ok": False, "rate": 0.0, "elapsed": None}
            print(f"  batch={bs:>4}  FAILED")
            continue
        rate = len(docs) / elapsed
        results[bs] = {"ok": True, "rate": round(rate, 2),
                       "elapsed": round(elapsed, 2), "skipped": skipped}
        print(f"  batch={bs:>4}  elapsed={elapsed:.2f}s  rate={rate:.2f} c/s  "
              f"skipped={skipped}  full_554k_est={554_000/rate/3600:.2f}h")

    ok_rates = [(bs, r["rate"]) for bs, r in results.items() if r["ok"]]
    best_bs, best_rate = max(ok_rates, key=lambda x: x[1])
    print("\n" + "=" * 60)
    print(f"BEST batch={best_bs}  rate={best_rate:.2f} c/s")
    print(f"  full 554k re-embed @ this rate: {554_000/best_rate/3600:.2f} h")
    print("=" * 60)

    with open("_step33a_batching_probe.json", "w", encoding="utf-8") as f:
        json.dump({
            "n_samples": len(docs),
            "results": results,
            "best_batch": best_bs,
            "best_rate": best_rate,
            "full_554k_hours": round(554_000 / best_rate / 3600, 2),
        }, f, indent=2)


if __name__ == "__main__":
    main()
