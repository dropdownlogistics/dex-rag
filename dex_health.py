#!/usr/bin/env python3
"""
dex_health.py — Full-stack health check for Dex Jr.

8 subsystem checks, 3 CLI modes (default, --quick, --json).
Read-only everywhere. Zero writes, zero side effects.

Usage:
  python dex_health.py              # Full check (~15s)
  python dex_health.py --quick      # Infrastructure only (~3s)
  python dex_health.py --json       # JSON output
  python dex_health.py --verbose    # Detailed per-check info

Step 52 | Authority: CLAUDE.md Refactor Target #4
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import chromadb
import requests

from dex_core import (
    CHROMA_DIR, INGEST_CACHE_DIR as CACHE_DIR, OLLAMA_HOST, EMBED_MODEL,
    GEN_MODEL, BACKUP_DIR, SWEEP_REPORTS_DIR, SCRIPT_DIR as _CORE_SCRIPT_DIR,
    CHUNK_FLOORS, COLLECTIONS, COLLECTION_SUFFIX, suffixed,
)

BACKUP_LOG = os.path.join(BACKUP_DIR, "_backup_log.jsonl")
SWEEP_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dex-sweep-log.jsonl")

# Derive from dex_core registry
LIVE_COLLECTIONS = {suffixed(k): v for k, v in CHUNK_FLOORS.items()}
PROVISIONED_COLLECTIONS = [suffixed(k) for k, v in COLLECTIONS.items() if v["status"] == "PROVISIONED"]

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _hours_ago(iso_ts: str) -> float:
    """Parse an ISO timestamp and return hours since then."""
    try:
        # Handle both Z and +00:00 suffixes, and naive timestamps
        ts = iso_ts.replace("Z", "+00:00")
        if "+" not in ts and "T" in ts:
            dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(ts)
        delta = datetime.now(timezone.utc) - dt
        return delta.total_seconds() / 3600
    except Exception:
        return float("inf")


# ── Check implementations ────────────────────────────────────────────────────

def check_ollama(verbose: bool = False) -> dict:
    """Check 1: Ollama reachable + required models loaded."""
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=10)
        r.raise_for_status()
        models = {m["name"] for m in r.json().get("models", [])}
    except Exception as e:
        return {"status": "FAIL", "detail": f"Ollama unreachable: {e}"}

    has_embed = any(m.startswith(EMBED_MODEL) for m in models)
    has_gen = GEN_MODEL in models
    missing = []
    if not has_embed:
        missing.append(EMBED_MODEL)
    if not has_gen:
        missing.append(GEN_MODEL)

    if missing:
        return {"status": "FAIL", "detail": f"Missing models: {', '.join(missing)}",
                "models_loaded": len(models)}

    detail = f"{len(models)} models loaded"
    extra = {"models": sorted(models)} if verbose else {}
    return {"status": "PASS", "detail": detail, **extra}


def check_chromadb(verbose: bool = False) -> dict:
    """Check 2: ChromaDB readable + collection integrity."""
    try:
        client = chromadb.PersistentClient(path=CHROMA_DIR)
    except Exception as e:
        return {"status": "FAIL", "detail": f"ChromaDB open failed: {e}"}

    total = 0
    issues = []
    col_details = {}

    for name, floor in LIVE_COLLECTIONS.items():
        try:
            col = client.get_collection(name)
            count = col.count()
            total += count
            col_details[name] = count
            if count < floor:
                issues.append(f"{name}: {count:,} < floor {floor:,}")
        except Exception as e:
            issues.append(f"{name}: MISSING ({e})")

    for name in PROVISIONED_COLLECTIONS:
        try:
            col = client.get_collection(name)
            count = col.count()
            col_details[name] = count
        except Exception:
            col_details[name] = "not found"

    if issues:
        return {"status": "FAIL", "detail": " | ".join(issues),
                "total_chunks": total, "collections": col_details}

    detail = f"{total:,} chunks across {len(LIVE_COLLECTIONS)} collections"
    extra = {"collections": col_details} if verbose else {}
    return {"status": "PASS", "detail": detail, "total_chunks": total, **extra}


def check_embedding(verbose: bool = False) -> dict:
    """Check 3: Embedding smoke test."""
    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": "health check"},
            timeout=30,
        )
        r.raise_for_status()
        emb = r.json().get("embedding", [])
    except Exception as e:
        return {"status": "FAIL", "detail": f"Embedding call failed: {e}"}

    dim = len(emb)
    if dim != 1024:
        return {"status": "FAIL", "detail": f"Wrong dimension: {dim} (expected 1024)"}
    if all(v == 0.0 for v in emb):
        return {"status": "FAIL", "detail": "Embedding is all zeros"}

    return {"status": "PASS", "detail": f"{dim}-dim {EMBED_MODEL}",
            "_embedding": emb}


def check_retrieval(embedding: list, verbose: bool = False) -> dict:
    """Check 4: Retrieval smoke test against dex_canon_v2."""
    if not embedding:
        return {"status": "FAIL", "detail": "No embedding available (Check 3 failed)"}

    try:
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        col = client.get_collection("dex_canon_v2")
        res = col.query(
            query_embeddings=[embedding],
            n_results=1,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        return {"status": "FAIL", "detail": f"Query failed: {e}"}

    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]

    if not docs:
        return {"status": "FAIL", "detail": "Query returned 0 results"}

    dist = dists[0]
    if not isinstance(dist, (int, float)) or not (-1e10 < dist < 1e10):
        return {"status": "FAIL", "detail": f"Non-finite distance: {dist}"}

    detail = f"1 result, distance {dist:.4f}"
    result_info = {
        "_distance": dist,
        "_metadata": metas[0] if metas else {},
        "_document_preview": (docs[0] or "")[:100],
    }
    extra = {"source_file": (metas[0] or {}).get("source_file", "")} if verbose else {}
    return {"status": "PASS", "detail": detail, **result_info, **extra}


def check_weighting(retrieval_result: dict, verbose: bool = False) -> dict:
    """Check 5: Weighted retrieval integration."""
    try:
        from dex_weights import calculate_weight, score_result
    except Exception as e:
        return {"status": "FAIL", "detail": f"Import failed: {e}"}

    dist = retrieval_result.get("_distance")
    meta = retrieval_result.get("_metadata", {})
    if dist is None:
        return {"status": "FAIL", "detail": "No retrieval result available (Check 4 failed)"}

    try:
        weight = calculate_weight("dex_canon_v2", meta)
        wscore = score_result(dist, weight)
    except Exception as e:
        return {"status": "FAIL", "detail": f"Weight calculation failed: {e}"}

    if not (0.0 < weight < 2.0):
        return {"status": "FAIL", "detail": f"Weight out of range: {weight}"}
    if not (0.0 < wscore < 2.0):
        return {"status": "FAIL", "detail": f"Weighted score out of range: {wscore}"}

    return {"status": "PASS", "detail": f"weight {weight:.2f}, score {wscore:.4f}"}


def check_ingest_cache(verbose: bool = False) -> dict:
    """Check 6: Ingest cache health."""
    if not os.path.isdir(CACHE_DIR):
        return {"status": "WARN", "detail": "Cache directory not found (first sweep will create it)"}

    cache_files = [f for f in os.listdir(CACHE_DIR) if f.endswith(".json")]
    if not cache_files:
        return {"status": "WARN", "detail": "No cache files found (first sweep will create them)"}

    total_entries = 0
    corrupt = []
    file_details = {}

    for cf in cache_files:
        path = os.path.join(CACHE_DIR, cf)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            count = len(data)
            total_entries += count
            file_details[cf] = count

            # Spot-check: first entry has required fields
            if data:
                sample = next(iter(data.values()))
                required = {"filepath", "content_hash", "collection"}
                missing = required - set(sample.keys())
                if missing:
                    corrupt.append(f"{cf}: missing fields {missing}")
        except json.JSONDecodeError as e:
            corrupt.append(f"{cf}: invalid JSON ({e})")
        except Exception as e:
            corrupt.append(f"{cf}: read error ({e})")

    if corrupt:
        return {"status": "FAIL", "detail": " | ".join(corrupt)}

    detail = f"{total_entries:,} entries in {len(cache_files)} cache file(s)"
    extra = {"cache_files": file_details} if verbose else {}
    return {"status": "PASS", "detail": detail, **extra}


def check_backup(verbose: bool = False) -> dict:
    """Check 7: Backup currency."""
    if not os.path.isdir(BACKUP_DIR):
        return {"status": "FAIL", "detail": f"Backup directory not found: {BACKUP_DIR}"}

    # Find most recent backup dir
    backup_dirs = sorted(
        [d for d in os.listdir(BACKUP_DIR)
         if d.startswith("chromadb_") and os.path.isdir(os.path.join(BACKUP_DIR, d))],
        reverse=True,
    )
    if not backup_dirs:
        return {"status": "FAIL", "detail": "No backup directories found"}

    # Check backup log for last entry
    last_ts = None
    last_status = None
    if os.path.isfile(BACKUP_LOG):
        try:
            with open(BACKUP_LOG, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if lines:
                last_entry = json.loads(lines[-1])
                last_ts = last_entry.get("timestamp")
                last_status = last_entry.get("result", "unknown")
        except Exception:
            pass

    if last_ts:
        age_hours = _hours_ago(last_ts)
    else:
        # Fall back to directory name parsing: chromadb_2026-04-15_090105_1616
        latest = backup_dirs[0]
        try:
            parts = latest.replace("chromadb_", "").split("_")
            date_str = parts[0]
            time_str = parts[1] if len(parts) > 1 else "000000"
            ts_str = f"{date_str}T{time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}Z"
            age_hours = _hours_ago(ts_str)
            last_ts = ts_str
        except Exception:
            age_hours = float("inf")

    detail_parts = []
    if last_ts:
        detail_parts.append(f"{age_hours:.1f} hours old")
    if last_status:
        detail_parts.append(f"status {last_status}")
    detail_parts.append(f"latest: {backup_dirs[0]}")
    detail = ", ".join(detail_parts)

    extra = {"backup_count": len(backup_dirs), "latest_dir": backup_dirs[0]} if verbose else {}

    if age_hours > 96:
        return {"status": "FAIL", "detail": detail, **extra}
    if age_hours > 48:
        return {"status": "WARN", "detail": detail, **extra}
    return {"status": "PASS", "detail": detail, **extra}


def check_sweep(verbose: bool = False) -> dict:
    """Check 8: Last sweep health."""
    # Check sweep JSONL log (repo-local)
    last_sweep = None
    recent_errors = 0
    if os.path.isfile(SWEEP_LOG):
        try:
            with open(SWEEP_LOG, "r", encoding="utf-8") as f:
                lines = f.readlines()
            # Check last 3 entries for errors
            for line in lines[-3:]:
                try:
                    entry = json.loads(line)
                    if entry.get("error"):
                        recent_errors += 1
                except json.JSONDecodeError:
                    pass
            if lines:
                last_sweep = json.loads(lines[-1])
        except Exception:
            pass

    if last_sweep is None:
        return {"status": "FAIL", "detail": "No sweep log found or empty"}

    ts = last_sweep.get("timestamp") or last_sweep.get("start_ts")
    outcome = last_sweep.get("outcome", "unknown")
    files_found = last_sweep.get("files_found", 0)
    files_copied = last_sweep.get("files_copied", 0)
    age_hours = _hours_ago(ts) if ts else float("inf")

    # Check sweep reports dir for most recent report
    report_age = float("inf")
    if os.path.isdir(SWEEP_REPORTS_DIR):
        reports = sorted(
            [f for f in os.listdir(SWEEP_REPORTS_DIR)
             if f.startswith("ingest_report_") and f.endswith(".md")],
            reverse=True,
        )
        if reports:
            # Parse timestamp from filename: ingest_report_2026-04-15_111207.346316_...
            try:
                parts = reports[0].replace("ingest_report_", "").split(".")
                date_time = parts[0]  # 2026-04-15_111207
                dt_parts = date_time.split("_")
                ts_str = f"{dt_parts[0]}T{dt_parts[1][:2]}:{dt_parts[1][2:4]}:{dt_parts[1][4:6]}Z"
                report_age = _hours_ago(ts_str)
            except Exception:
                pass

    detail_parts = [f"outcome={outcome}"]
    if files_found:
        detail_parts.append(f"{files_found} found")
    if files_copied:
        detail_parts.append(f"{files_copied} copied")
    detail_parts.append(f"{age_hours:.1f} hours ago")
    detail = ", ".join(detail_parts)

    extra = {}
    if verbose:
        extra["recent_errors"] = recent_errors
        extra["last_outcome"] = outcome

    if recent_errors > 0 and last_sweep.get("error"):
        return {"status": "FAIL", "detail": f"Last sweep errored: {last_sweep.get('error')}", **extra}

    # Outcome-based assessment
    ok_outcomes = {"success", "no_files_found", "skipped_report_only", "dry_run"}
    if outcome not in ok_outcomes:
        return {"status": "FAIL", "detail": detail, **extra}

    if age_hours > 48:
        return {"status": "WARN", "detail": detail, **extra}

    return {"status": "PASS", "detail": detail, **extra}


# ── Main ─────────────────────────────────────────────────────────────────────

def run_health(quick: bool = False, verbose: bool = False) -> list[dict]:
    """Run all health checks. Returns list of result dicts."""
    results = []

    # Check 1: Ollama
    r = check_ollama(verbose)
    results.append({"name": "Ollama reachable", **r})

    # Check 2: ChromaDB
    r = check_chromadb(verbose)
    results.append({"name": "ChromaDB integrity", **r})

    if not quick:
        # Check 3: Embedding
        r = check_embedding(verbose)
        results.append({"name": "Embedding smoke test", **r})
        embedding = r.get("_embedding")

        # Check 4: Retrieval
        r = check_retrieval(embedding or [], verbose)
        results.append({"name": "Retrieval smoke test", **r})

        # Check 5: Weighting
        r = check_weighting(r, verbose)
        results.append({"name": "Weighted retrieval", **r})

    # Check 6: Ingest cache
    r = check_ingest_cache(verbose)
    results.append({"name": "Ingest cache health", **r})

    # Check 7: Backup
    r = check_backup(verbose)
    results.append({"name": "Backup currency", **r})

    # Check 8: Sweep
    r = check_sweep(verbose)
    results.append({"name": "Last sweep health", **r})

    return results


def print_results(results: list[dict], as_json: bool = False) -> int:
    """Print results and return exit code (0 = all pass, 1 = any fail)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Clean internal fields from JSON output
    clean_results = []
    for r in results:
        clean = {k: v for k, v in r.items() if not k.startswith("_")}
        clean_results.append(clean)

    if as_json:
        payload = {
            "timestamp": now,
            "checks": clean_results,
            "pass_count": sum(1 for r in results if r["status"] in ("PASS", "WARN")),
            "fail_count": sum(1 for r in results if r["status"] == "FAIL"),
            "total": len(results),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"\n{'=' * 60}")
        print(f"  DEX JR. HEALTH CHECK")
        print(f"  {now}")
        print(f"{'=' * 60}")
        print()

        for r in results:
            status = r["status"]
            tag = f"[{status}]"
            print(f"  {tag:<6} {r['name']} ({r.get('detail', '')})")

        pass_count = sum(1 for r in results if r["status"] in ("PASS", "WARN"))
        fail_count = sum(1 for r in results if r["status"] == "FAIL")
        total = len(results)

        print(f"\n{'=' * 60}")
        if fail_count == 0:
            print(f"  ALL PASS ({pass_count}/{total})")
        else:
            print(f"  FAILURES PRESENT ({pass_count}/{total} pass, {fail_count} fail)")
        print(f"{'=' * 60}\n")

    return 0 if all(r["status"] != "FAIL" for r in results) else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Dex Jr. full-stack health check")
    p.add_argument("--json", action="store_true", help="Output as JSON")
    p.add_argument("--quick", action="store_true",
                   help="Skip embedding/retrieval/weighting checks (infrastructure only)")
    p.add_argument("--verbose", action="store_true",
                   help="Show detailed info per check")
    args = p.parse_args()

    results = run_health(quick=args.quick, verbose=args.verbose)
    return print_results(results, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
