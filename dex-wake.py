#!/usr/bin/env python3
"""
dex-wake.py -- start DDL services on Reborn from a phone. Port 8789.

Closes the ferry gap: services that should NOT be always-on (they contend the
GPU, or simply need not run) become startable on demand from the tailnet,
without a supervisor and without Paseo.

  GET  /healthz            liveness only. No auth, no content.
  GET  /v1/services        what is allowlisted and what is running. AUTH.
  POST /v1/services/start  start one allowlisted service by name. AUTH.

There is no stop. Status is read-only and is what you actually want from a
hotel; stop degrades security posture remotely and can be done at the machine.

Design locked 2026-08-01 by Operator + Caldwell + Ellis Cooper. See
ADR-DEXJR-WAKE-001 for the credential decision and its residual risk.
"""

import argparse
import hashlib
import hmac
import os
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

try:
    from fastapi import Depends, FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    sys.exit("pip install fastapi uvicorn pydantic")

PORT = 8789
SELF_NAME = "dex-wake"          # see ALLOWLIST comment -- deliberately absent
VENV = Path(r"C:\Users\dexjr\dex-rag\.venv\Scripts\python.exe")
DEXRAG = Path(r"C:\Users\dexjr\dex-rag")
COCKPIT = Path(r"C:\Users\dexjr\campaign-cockpit")
TOKEN_HASH_FILE = Path(r"C:\Users\dexjr\.config\ddl\wake-token.sha256")

VRAM_FLOOR_MB = 1200

# ---------------------------------------------------------------------------
# ALLOWLIST -- IN-PROCESS CONSTANTS. NEVER LOADED FROM DISK.
# ---------------------------------------------------------------------------
# Ellis Cooper's catch, and it is the load-bearing control here: if this map
# lived in a config file, write access to that file would be write access to
# what this service executes -- a privilege escalation path that routes around
# the API entirely. An attacker who cannot reach the endpoint could still edit
# the config. So it is source, not data.
#
# No client-supplied arguments. The client sends a NAME; the argv is fixed
# here. Nothing from the request ever reaches a command line.
#
# `dex-wake` IS DELIBERATELY ABSENT FROM THIS MAP. The thing that starts
# everything is the one thing it cannot start -- otherwise a compromised call
# could restart this service with different behavior, which is a full escape.
# Restarting dex-wake is a job for the persistence layer (Ellis, DDL-4008),
# not for dex-wake.
ALLOWLIST: dict[str, dict] = {
    "dex-openai-api": {
        "argv": [str(VENV), str(DEXRAG / "dex-openai-api.py")],
        "cwd": DEXRAG,
        "port": 8788,
        "gpu": True,          # calls Ollama for generation
        "desc": "Dex Jr. mobile endpoint (OpenAI-compatible, corpus-bounded)",
        "env_required": ["DEXJR_API_TOKEN"],
    },
    "dex-search-api": {
        "argv": [str(VENV), str(DEXRAG / "dex-search-api.py")],
        "cwd": DEXRAG,
        "port": 8787,
        "gpu": True,
        "desc": "retrieval + MindFrame chat",
        "env_required": [],
    },
    "campaign-cockpit": {
        "argv": [str(VENV), str(COCKPIT / "server.py")],
        "cwd": COCKPIT,
        "port": 8801,
        "gpu": True,          # DM turns call Ollama
        "desc": "Ash, Snow & Steel campaign cockpit",
        "env_required": [],
    },
}
assert SELF_NAME not in ALLOWLIST, "dex-wake must never be able to start itself"

# name -> Popen of what WE started. Authoritative for managed processes.
# Deliberately in memory: a PID file survives a restart but PIDs are reused,
# so a stale file can point at an unrelated process. Losing the map on restart
# is the safer failure -- status then honestly reports "not managed by me".
_started: dict[str, subprocess.Popen] = {}
_auth_failures: deque[float] = deque(maxlen=64)

app = FastAPI(title="dex-wake", version="1.0.0")


# ---------------------------------------------------------------------------
# Credential -- see ADR-DEXJR-WAKE-001
# ---------------------------------------------------------------------------
# This service is the counterexample to every other service here. The others
# fail closed: no credential, no start. This one must be running BEFORE
# anything else, on a machine that just rebooted with nobody logged in -- so
# its credential has to survive a bare reboot unattended.
#
# Chosen: store a SHA-256 HASH of the token in an ACL-restricted file, never
# the token. The service verifies; it does not hold anything usable.
#
# What that buys: reading the file yields something that cannot be replayed.
# To gain access an attacker must OVERWRITE the hash -- which breaks the
# operator's phone and is therefore noisy. Plaintext disclosure would be
# silent and permanent; hash replacement is loud.
#
# What it does NOT protect against, stated plainly: anyone with local admin on
# Reborn can overwrite that file and mint their own access. The ACL is the
# real boundary and local admin is above it. This does not defend against a
# compromised machine. It defends against credential disclosure at rest.
#
# Plain SHA-256 rather than a KDF is deliberate: the token is high-entropy
# random, not a human password, so there is no dictionary to slow down and a
# KDF would add cost without adding resistance.
TOKEN_HASH = ""


def load_token_hash() -> str:
    if not TOKEN_HASH_FILE.exists():
        sys.exit(
            f"REFUSING TO START: no token hash at {TOKEN_HASH_FILE}\n\n"
            "This service can start processes. It does not run unauthenticated.\n\n"
            "Create it (PowerShell):\n"
            '  $t = -join ((48..57+65..90+97..122) | Get-Random -Count 40 | '
            '% {[char]$_})\n'
            '  $h = [BitConverter]::ToString([Security.Cryptography.SHA256]::'
            'Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($t))'
            ').Replace("-","").ToLower()\n'
            f'  $h | Out-File "{TOKEN_HASH_FILE}" -Encoding ascii -NoNewline\n'
            "  Write-Host $t   # <-- put THIS in the phone. It is never stored here.\n\n"
            "Then restrict it (removes inheritance, SYSTEM + you only):\n"
            f'  icacls "{TOKEN_HASH_FILE}" /inheritance:r /grant:r '
            'SYSTEM:F "$env:USERNAME:R"\n'
        )
    h = TOKEN_HASH_FILE.read_text(encoding="utf-8").strip().lower()
    if len(h) != 64:
        sys.exit(f"REFUSING TO START: {TOKEN_HASH_FILE} is not a sha256 hex digest")
    return h


def require_auth(request: Request):
    # Rate-limit failures: a 40-char token over a tailnet is not brute-forcible
    # quickly, but unlimited retries at low latency is still free attempts.
    now = time.time()
    while _auth_failures and now - _auth_failures[0] > 60:
        _auth_failures.popleft()
    if len(_auth_failures) >= 8:
        raise HTTPException(status_code=429,
                            detail="too many failed attempts; wait 60s")

    hdr = request.headers.get("authorization", "")
    supplied = hdr[7:].strip() if hdr.lower().startswith("bearer ") else ""
    digest = hashlib.sha256(supplied.encode()).hexdigest() if supplied else ""
    if not supplied or not hmac.compare_digest(digest, TOKEN_HASH):
        _auth_failures.append(now)
        raise HTTPException(status_code=401, detail="invalid or missing bearer token")


# ---------------------------------------------------------------------------
# State -- measured, with the untrustworthy part labelled
# ---------------------------------------------------------------------------
def gpu_free_mb() -> int | None:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5)
        return int(r.stdout.strip().splitlines()[0]) if r.returncode == 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def port_listening(port: int) -> bool:
    """Corroborating only. NOT proof the real service is up -- any process can
    bind a port. Authoritative liveness comes from the managed Popen."""
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True,
                             text=True, timeout=10).stdout
        return f":{port} " in out and "LISTENING" in out
    except (OSError, subprocess.SubprocessError):
        return False


def service_state(name: str) -> dict:
    spec = ALLOWLIST[name]
    proc = _started.get(name)
    managed_alive = bool(proc and proc.poll() is None)
    return {
        "name": name,
        "description": spec["desc"],
        "port": spec["port"],
        "managed_by_wake": managed_alive,          # authoritative
        "managed_pid": proc.pid if managed_alive else None,
        "port_listening": port_listening(spec["port"]),  # corroborating
        "port_note": "a listening port is NOT proof this service is up; "
                     "any process can bind it. managed_by_wake is authoritative.",
        "touches_gpu": spec["gpu"],
    }


class StartReq(BaseModel):
    name: str


@app.get("/healthz")
def healthz():
    """Liveness only. No auth, and deliberately says nothing about what is
    running -- that would leak the machine's posture to an unauthenticated
    caller."""
    return {"status": "ok", "service": SELF_NAME}


@app.get("/v1/services", dependencies=[Depends(require_auth)])
def list_services():
    return {"services": [service_state(n) for n in sorted(ALLOWLIST)],
            "gpu_free_mb": gpu_free_mb(),
            "self": {"name": SELF_NAME,
                     "startable": False,
                     "why": "excluded from its own allowlist: a compromised call "
                            "could otherwise restart it with different behavior"}}


@app.post("/v1/services/start", dependencies=[Depends(require_auth)])
def start_service(body: StartReq):
    name = body.name
    if name == SELF_NAME:
        raise HTTPException(status_code=403,
                            detail="dex-wake cannot start itself, by design")
    spec = ALLOWLIST.get(name)
    if not spec:
        # Do not echo the requested name back into the error -- no reflection.
        raise HTTPException(status_code=404, detail="not an allowlisted service")

    existing = _started.get(name)
    if existing and existing.poll() is None:
        return {"ok": True, "already_running": True, "pid": existing.pid,
                "state": service_state(name)}

    missing = [v for v in spec["env_required"] if not os.environ.get(v)]
    if missing:
        raise HTTPException(status_code=503, detail={
            "message": f"cannot start {name}: required environment not set",
            "missing": missing,
            "note": "dex-wake does not hold other services' secrets; they must "
                    "be present in its environment at start."})

    # ADVISORY, NOT A LOCK. Two rapid starts can both pass this check before
    # either allocates. It reduces accidental contention; it does not prevent
    # a race, and nothing here should be read as a guarantee.
    if spec["gpu"]:
        free = gpu_free_mb()
        if free is not None and free < VRAM_FLOOR_MB:
            return JSONResponse(status_code=503, content={
                "error": {"message": f"GPU busy ({free}MB free, need "
                                     f"{VRAM_FLOOR_MB}MB). Not starting {name}.",
                          "type": "gpu_contended",
                          "note": "advisory check, not a lock"}})

    try:
        proc = subprocess.Popen(
            spec["argv"], cwd=str(spec["cwd"]),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    except OSError as exc:
        raise HTTPException(status_code=500,
                            detail=f"failed to launch: {exc}") from exc

    _started[name] = proc
    time.sleep(1.5)  # let an immediate crash surface rather than reporting success
    if proc.poll() is not None:
        _started.pop(name, None)
        raise HTTPException(status_code=500, detail={
            "message": f"{name} exited immediately (code {proc.returncode})",
            "note": "started but did not stay up -- check its own logs"})
    return {"ok": True, "started": name, "pid": proc.pid,
            "state": service_state(name)}


def main():
    global TOKEN_HASH
    ap = argparse.ArgumentParser(description="wake DDL services on demand")
    ap.add_argument("--tailnet", action="store_true",
                    help="bind 0.0.0.0 for Tailscale (default: localhost only)")
    ap.add_argument("--port", type=int, default=PORT)
    a = ap.parse_args()

    TOKEN_HASH = load_token_hash()
    host = "0.0.0.0" if a.tailnet else "127.0.0.1"

    print(f"\n  dex-wake — on-demand service start")
    print(f"  http://{host}:{a.port}")
    print(f"  allowlist: {', '.join(sorted(ALLOWLIST))}")
    print(f"  {SELF_NAME} is NOT startable by itself (by design)")
    print(f"  auth: sha256 hash from {TOKEN_HASH_FILE}")
    if a.tailnet:
        print("  bind: 0.0.0.0 — Tailscale reachability is UNVERIFIED inference,")
        print("        do not treat the tailnet as the security boundary")
    else:
        print("  bind: 127.0.0.1 (localhost only)")
    print()
    uvicorn.run(app, host=host, port=a.port, log_level="warning",
                access_log=False)  # keep bearer tokens out of access logs


if __name__ == "__main__":
    main()
