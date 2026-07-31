#!/usr/bin/env python3
"""
dex-state.py -- make Reborn report its own port/process state.

Every answer carries a type, and that is the whole thesis:

  MEASURED    queried from the machine at call time
  CITED       read from a single declared source, never restated here
  UNVERIFIED  not establishable by this tool -- printed as a value, not omitted

The third type is the point. Status tools normally drop what they cannot
establish, which is how "Tailscale is supported" became load-bearing while
unverified. Here an unverifiable fact is something the tool SAYS.

This stores nothing it could measure. There is no state file. Run it again and
you get the truth again. If a value in here could have been measured and was
written down instead, that is the bug.

  python dex-state.py            # full report
  python dex-state.py --json     # machine-readable
  python dex-state.py --quiet    # only problems

Exit: 0 nothing wrong · 1 an expected service is down or a bind is unexpected

Scope is deliberately ports and processes only (Operator ruling 2026-07-31):
prove the taxonomy on a narrow surface before it carries GPU, scheduled tasks
and reachability.
"""

import argparse
import json
import re
import subprocess
import sys

# ---------------------------------------------------------------------------
# The ONE declaration in this file.
# ---------------------------------------------------------------------------
# These are not measurements -- they are expectations, and expectations must be
# declared somewhere. Everything else in this tool is measured or cited.
# `bind` is what the service SHOULD bind, so an unexpected bind is a finding
# rather than a fact we quietly record.
EXPECTED = {
    11434: {"name": "Ollama",            "bind": "any",       "auth": "none (local model host)"},
     8765: {"name": "ddl-intel API",     "bind": "localhost", "auth": "UNVERIFIED"},
     8787: {"name": "dex-search-api",    "bind": "localhost", "auth": "UNVERIFIED"},
     8788: {"name": "Dex Jr. mobile",    "bind": "localhost", "auth": "bearer, fails closed"},
     8791: {"name": "dex-chat",          "bind": "localhost", "auth": "UNVERIFIED"},
     8792: {"name": "ddl-voice",         "bind": "localhost", "auth": "UNVERIFIED"},
     8801: {"name": "campaign-cockpit",  "bind": "localhost", "auth": "UNVERIFIED"},
}

# Facts this tool deliberately cannot establish. Printed, never guessed.
UNVERIFIED = [
    ("Tailscale reachability",
     "the --tailscale flag exists on 8788; no client has ever connected"),
    ("auth on 8765 / 8787 / 8791 / 8792 / 8801",
     "not inspected by this tool -- only 8788 is known to fail closed"),
    ("reboot survival",
     "nothing here observes a reboot; see the persistence lane (Ellis, DDL-4008)"),
]


def sh(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


# ---------------------------------------------------------------------------
# MEASURED
# ---------------------------------------------------------------------------
LISTEN = re.compile(r"^\s*TCP\s+(\S+):(\d+)\s+\S+\s+LISTENING\s+(\d+)", re.M)


def measure_listeners() -> dict[int, dict]:
    """Listening TCP ports -> bind addresses + owning PIDs. Read-only."""
    out: dict[int, dict] = {}
    for addr, port, pid in LISTEN.findall(sh(["netstat", "-ano"])):
        p = int(port)
        e = out.setdefault(p, {"binds": set(), "pids": set()})
        e["binds"].add(addr)
        e["pids"].add(int(pid))
    return out


def measure_process_names(pids: set[int]) -> dict[int, str]:
    """PID -> image name. Best effort; a missing name is not an error."""
    names: dict[int, str] = {}
    for line in sh(["tasklist", "/fo", "csv", "/nh"]).splitlines():
        parts = [c.strip('"') for c in line.split('","')]
        if len(parts) >= 2:
            try:
                pid = int(parts[1])
            except ValueError:
                continue
            if pid in pids:
                names[pid] = parts[0].strip('"')
    return names


def classify_bind(binds: set[str]) -> str:
    """What the machine is actually exposing on this port."""
    if any(b in ("0.0.0.0", "::", "[::]") for b in binds):
        return "any"
    if all(b.startswith("127.") or b == "::1" for b in binds):
        return "localhost"
    return "specific"


# ---------------------------------------------------------------------------
# CITED -- read from one source, never restated
# ---------------------------------------------------------------------------
def cite_corpus() -> dict:
    """Corpus facts come from dex_core. This tool does not know chunk counts and
    must not learn them -- writing one down here would create the seventh
    disagreeing declaration."""
    try:
        import dex_core
        return {"ok": True, "source": "dex_core",
                "collections": dex_core.get_live_collections(),
                "chroma_dir": dex_core.CHROMA_DIR,
                "note": "counts are live in ChromaDB; cite dex_core, never restate"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "source": "dex_core", "error": str(exc)}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def build() -> dict:
    listeners = measure_listeners()
    all_pids = {p for e in listeners.values() for p in e["pids"]}
    names = measure_process_names(all_pids)

    ports, findings = [], []
    for port, exp in sorted(EXPECTED.items()):
        live = listeners.get(port)
        row = {"port": port, "name": exp["name"], "expected_bind": exp["bind"],
               "auth": exp["auth"], "type": "MEASURED"}
        if not live:
            row.update(status="DOWN", bind=None, pids=[], procs=[])
            findings.append(f"{port} ({exp['name']}) is NOT listening")
        else:
            actual = classify_bind(live["binds"])
            row.update(status="UP", bind=actual,
                       bind_raw=sorted(live["binds"]),
                       pids=sorted(live["pids"]),
                       procs=sorted({names.get(p, "?") for p in live["pids"]}))
            if exp["bind"] != "any" and actual == "any":
                findings.append(
                    f"{port} ({exp['name']}) binds ALL interfaces; expected {exp['bind']}"
                    + ("  [auth UNVERIFIED]" if exp["auth"] == "UNVERIFIED" else ""))
        ports.append(row)

    # Only the DDL service range. Reporting all 28 Windows system ports is
    # noise, and a detector that is mostly noise trains people to ignore it.
    unexpected = sorted(p for p in set(listeners) - set(EXPECTED)
                        if 8000 <= p <= 8999 or p == 11434)
    return {"ports": ports, "findings": findings,
            "unexpected_ports": unexpected, "corpus": cite_corpus(),
            "unverified": [{"fact": f, "why": w} for f, w in UNVERIFIED]}


def render(rep: dict, quiet: bool) -> None:
    print("\nREBORN — port/process state\n" + "=" * 66)
    print("MEASURED at call time. Nothing below is stored.\n")
    print(f"  {'port':>5}  {'status':<6} {'bind':<10} {'service':<20} process")
    print("  " + "-" * 62)
    for r in rep["ports"]:
        if quiet and r["status"] == "UP" and r["bind"] != "any":
            continue
        proc = ", ".join(r["procs"]) if r.get("procs") else "-"
        flag = "  <<<" if r["status"] == "DOWN" or (
            r["bind"] == "any" and r["expected_bind"] != "any") else ""
        print(f"  {r['port']:>5}  {r['status']:<6} {str(r['bind'] or '-'):<10} "
              f"{r['name']:<20} {proc}{flag}")

    if rep["unexpected_ports"]:
        print(f"\n  not in the expectation list: {rep['unexpected_ports']}")

    c = rep["corpus"]
    print("\nCITED — corpus (this tool does not know chunk counts, by design)")
    if c["ok"]:
        print(f"  source: {c['source']}   collections: {len(c['collections'])}")
        print(f"  {c['note']}")
    else:
        print(f"  could not cite {c['source']}: {c['error']}")

    print("\nUNVERIFIED — stated, not omitted")
    for u in rep["unverified"]:
        print(f"  - {u['fact']}\n      {u['why']}")

    if rep["findings"]:
        print("\nFINDINGS")
        for f in rep["findings"]:
            print(f"  !! {f}")
    else:
        print("\nno findings.")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="only problems")
    a = ap.parse_args()
    rep = build()
    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        render(rep, a.quiet)
    return 1 if rep["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
