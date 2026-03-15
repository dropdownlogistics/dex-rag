#!/usr/bin/env python3
"""
DDL RAG Pipeline — Phase 1 Setup
Dropdown Logistics — Chaos → Structured → Automated

Run this first to verify all dependencies are ready.
"""

import subprocess
import sys

def run(cmd, label):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  ✓ {label} — OK")
    else:
        print(f"  ✗ {label} — FAILED")
        print(f"    {result.stderr.strip()}")
    return result.returncode == 0

def main():
    print("\n" + "="*60)
    print("  DDL RAG PIPELINE — PHASE 1 SETUP")
    print("  Dex Jr. × Archive Integration")
    print("="*60)

    checks = []

    # 1. Check Ollama is running
    checks.append(run("ollama list", "Ollama is installed and running"))

    # 2. Pull embedding model
    checks.append(run("ollama pull nomic-embed-text", "Pull nomic-embed-text embedding model"))

    # 3. Install Python dependencies
    checks.append(run(
        f"{sys.executable} -m pip install chromadb requests --quiet",
        "Install ChromaDB and requests"
    ))

    # 4. Verify imports
    try:
        import chromadb
        print(f"\n  ✓ ChromaDB version: {chromadb.__version__}")
        checks.append(True)
    except ImportError:
        print("\n  ✗ ChromaDB import failed")
        checks.append(False)

    try:
        import requests
        print(f"  ✓ Requests available")
        checks.append(True)
    except ImportError:
        print(f"  ✗ Requests import failed")
        checks.append(False)

    # 5. Verify nomic-embed-text responds
    try:
        import requests as req
        resp = req.post("http://localhost:11434/api/embeddings", json={
            "model": "nomic-embed-text",
            "prompt": "test"
        })
        if resp.status_code == 200 and "embedding" in resp.json():
            dim = len(resp.json()["embedding"])
            print(f"  ✓ nomic-embed-text responding — {dim} dimensions")
            checks.append(True)
        else:
            print(f"  ✗ nomic-embed-text not responding correctly")
            checks.append(False)
    except Exception as e:
        print(f"  ✗ Ollama API not reachable: {e}")
        checks.append(False)

    # Summary
    passed = sum(checks)
    total = len(checks)
    print(f"\n{'='*60}")
    print(f"  SETUP COMPLETE: {passed}/{total} checks passed")
    print(f"{'='*60}")

    if all(checks):
        print("\n  Ready for ingestion. Run:")
        print("  python dex-ingest.py")
    else:
        print("\n  Fix the failed checks above before proceeding.")

if __name__ == "__main__":
    main()
