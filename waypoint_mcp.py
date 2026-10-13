"""
waypoint_mcp.py -- the thin stdio piece of Waypoint: an MCP server a seat's session starts, which only relays.

The store lives in ONE process, the Dex server on Reborn. A stdio MCP server is started once per session, so
if this file opened the store, six seats would be six copies in memory (Piers Frame's review,
DDL-3012:20261012T173519Z-b1c3). It opens nothing: each tool call is one HTTP request to the Dex server on
this machine and the answer is passed back as it came.

Standard library only (the `mcp` package is not installed here and is not needed for three tools): newline-
delimited JSON-RPC 2.0 on stdin and stdout, as the MCP stdio transport specifies. Nothing is written to
stdout but protocol messages.

NOT INSTALLED ON ANY SEAT. Reed Vane's GO for phase 1 (2026-10-12) says to build it and install no server
entry or hook yet. When it is installed, the entry is local to a seat on Reborn and is not committed until
other machines can reach the service (phase 6).

    WAYPOINT_URL    the Dex server (default http://127.0.0.1:8796)
    DEX_API_TOKEN   its bearer token; read from the environment, never printed, never logged
    WAYPOINT_SEAT   this seat's id (e.g. DDL-4008), sent so a clean rater's exclusions apply

    python waypoint_mcp.py --check      # one `sources` call, prints counts, exits 0 or 1

Silas Reeve / DDL-3004 / 2026-10-12
"""
import json
import os
import sys
import urllib.error
import urllib.request

PROTOCOL = "2024-11-05"
FALLBACK = "Waypoint could not answer, so nothing was searched. grep and your own Read tool still work; use them."

TOOLS = [
    {"name": "search",
     "description": ("Waypoint: find WHERE something is in DDL's private store (the vault, the document corpus, session "
                     "transcripts, the evidence locker, the archive). Returns places, not answers: root, path, which chunk "
                     "of the file, a short snippet, a score. Open the file yourself to read it. Phase 1 ranks by MEANING "
                     "ONLY: quoted phrases, -word and bare identifiers are listed under not_applied and are NOT enforced, "
                     "so for an exact string still use grep. Filters that work: root:vault ext:md in:some/folder, and "
                     "-root: -ext: -in:. Always read `limits` in the result: it says what the result does not prove."),
     "inputSchema": {"type": "object", "required": ["query"], "properties": {
         "query": {"type": "string", "description": "What you are looking for, in plain words, with optional filters."},
         "k": {"type": "integer", "minimum": 1, "maximum": 25, "description": "How many places to return (default 8)."}}}},
    {"name": "explain",
     "description": "Waypoint: show how a query would be read and which parts phase 1 would apply. Runs no search.",
     "inputSchema": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}}},
    {"name": "sources",
     "description": "Waypoint: what is indexed, how many files and chunks per root, when it was built, and what is not in it.",
     "inputSchema": {"type": "object", "properties": {}}},
]


def http(path, body=None, timeout=60):
    """One request to the Dex server. (status, parsed JSON). Raises OSError when it cannot be reached."""
    url = os.environ.get("WAYPOINT_URL", "http://127.0.0.1:8796").rstrip("/") + path
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("DEX_API_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8") if body is not None else None, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {"error": f"HTTP {e.code}"}


def call_tool(name, args, post=http):
    """(text, is_error) for one tool call."""
    args = args if isinstance(args, dict) else {}
    try:
        if name == "search":
            body = {"query": args.get("query"), "k": args.get("k", 8)}
            if os.environ.get("WAYPOINT_SEAT"):
                body["seat"] = os.environ["WAYPOINT_SEAT"]
            status, out = post("/api/v1/waypoint/search", body)
        elif name == "explain":
            status, out = post("/api/v1/waypoint/explain", {"query": args.get("query")})
        elif name == "sources":
            status, out = post("/api/v1/waypoint/sources")
        else:
            return f"Waypoint has no tool called {name!r}. It has: search, explain, sources.", True
    except (OSError, ValueError) as e:
        return f"{FALLBACK} (the Dex server on this machine did not answer: {type(e).__name__})", True
    if status == 200:
        return json.dumps(out, ensure_ascii=False, indent=1), False
    why = out.get("error") if isinstance(out, dict) else None
    if status == 400:
        return f"Waypoint refused the query: {why}", True
    if status == 401:
        return f"{FALLBACK} (the Dex server refused the token; DEX_API_TOKEN is missing or wrong in this session)", True
    if status == 503:
        return f"{FALLBACK} ({why}; try again in a minute)", True
    return f"{FALLBACK} (HTTP {status}: {why})", True


def handle(msg, post=http):
    """The reply to one JSON-RPC message, or None for a notification."""
    mid, method = msg.get("id"), msg.get("method")
    if mid is None:                                   # a notification (notifications/initialized and the like)
        return None

    def ok(result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}
    if method == "initialize":
        return ok({"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                   "serverInfo": {"name": "waypoint", "version": "0.1"},
                   "instructions": "Waypoint finds places in DDL's private store; it does not answer questions. "
                                   "Phase 1 ranks by meaning only. For an exact string, grep."})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        p = msg.get("params") or {}
        text, bad = call_tool(p.get("name"), p.get("arguments"), post)
        return ok({"content": [{"type": "text", "text": text}], "isError": bad})
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(stdin=None, stdout=None, post=http):
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            reply = handle(msg, post) if isinstance(msg, dict) else {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            stdout.flush()


def main():
    if "--check" in sys.argv[1:]:
        text, bad = call_tool("sources", {})
        if bad:
            print(text)
            return 1
        s = json.loads(text)
        print(f"waypoint: {s.get('state')}, {s.get('rows')} rows, {len(s.get('roots') or [])} roots, active index {s.get('active')}")
        return 0
    for stream in (sys.stdin, sys.stdout):
        stream.reconfigure(encoding="utf-8")
    serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
