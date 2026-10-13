"""waypoint_mcp: the stdio relay speaks the protocol, relays, and fails in words a seat can act on. No server."""
import io
import json
import subprocess
import sys
from pathlib import Path

import waypoint_mcp as m


def poster(status=200, out=None, raises=None):
    calls = []

    def post(path, body=None):
        calls.append((path, body))
        if raises:
            raise raises
        return status, out if out is not None else {"hits": []}
    return post, calls


def rpc(method, params=None, mid=1):
    return {"jsonrpc": "2.0", "id": mid, "method": method, **({"params": params} if params is not None else {})}


def test_the_handshake_and_the_tool_list():
    r = m.handle(rpc("initialize", {"protocolVersion": m.PROTOCOL}))
    assert r["result"]["serverInfo"]["name"] == "waypoint" and "tools" in r["result"]["capabilities"]
    assert m.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None       # a notification gets no reply
    tools = m.handle(rpc("tools/list"))["result"]["tools"]
    assert [t["name"] for t in tools] == ["search", "explain", "sources"]
    assert "MEANING" in tools[0]["description"] and "grep" in tools[0]["description"]          # the limit is in the tool's own words
    assert m.handle(rpc("ping"))["result"] == {} and m.handle(rpc("nope"))["error"]["code"] == -32601


def test_search_relays_the_query_with_the_seat_and_returns_the_envelope(monkeypatch):
    monkeypatch.setenv("WAYPOINT_SEAT", "DDL-9001")
    post, calls = poster(out={"hits": [{"path": "a.md"}], "limits": ["meaning only"]})
    r = m.handle(rpc("tools/call", {"name": "search", "arguments": {"query": "where is it", "k": 3}}), post)
    assert calls == [("/api/v1/waypoint/search", {"query": "where is it", "k": 3, "seat": "DDL-9001"})]
    assert r["result"]["isError"] is False and json.loads(r["result"]["content"][0]["text"])["hits"] == [{"path": "a.md"}]
    monkeypatch.delenv("WAYPOINT_SEAT")
    post, calls = poster()
    m.handle(rpc("tools/call", {"name": "search", "arguments": {"query": "x"}}), post)
    assert calls[0][1] == {"query": "x", "k": 8}                                              # no seat named: none sent
    post, calls = poster()
    m.handle(rpc("tools/call", {"name": "sources"}), post)
    m.handle(rpc("tools/call", {"name": "explain", "arguments": {"query": "q"}}), post)
    assert calls == [("/api/v1/waypoint/sources", None), ("/api/v1/waypoint/explain", {"query": "q"})]


def test_every_failure_is_an_error_in_words_and_says_grep_still_works():
    for post, want in ((poster(raises=ConnectionRefusedError())[0], "did not answer: ConnectionRefusedError"),
                       (poster(503, {"error": "the store is still opening"})[0], "the store is still opening; try again"),
                       (poster(401, {"error": "x"})[0], "refused the token"),
                       (poster(500, {"error": "boom"})[0], "HTTP 500: boom")):
        text, bad = m.call_tool("search", {"query": "x"}, post)
        assert bad and want in text and "grep" in text
    text, bad = m.call_tool("search", {"query": "root:vault"}, poster(400, {"error": "nothing to search by"})[0])
    assert bad and text == "Waypoint refused the query: nothing to search by"                  # the seat's own mistake: no fallback line
    assert m.call_tool("delete_everything", {}, poster()[0]) == ("Waypoint has no tool called 'delete_everything'. It has: search, explain, sources.", True)


def test_the_token_is_sent_and_never_put_in_a_message(monkeypatch):
    monkeypatch.setenv("DEX_API_TOKEN", "t0k-not-real")
    seen = {}

    class R:
        status = 200

        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_open(req, timeout=0):
        seen["auth"] = req.get_header("Authorization")
        return R()
    monkeypatch.setattr(m.urllib.request, "urlopen", fake_open)
    text, bad = m.call_tool("sources", {})
    assert seen["auth"] == "Bearer t0k-not-real" and "t0k" not in text and not bad


def test_the_loop_answers_line_by_line_and_survives_garbage():
    lines = [json.dumps(rpc("initialize", {})), "not json", "", json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
             json.dumps(rpc("tools/list", mid=2)), "[1, 2]"]
    out = io.StringIO()
    m.serve(io.StringIO("\n".join(lines) + "\n"), out, poster()[0])
    replies = [json.loads(l) for l in out.getvalue().splitlines()]
    assert [r.get("id") for r in replies] == [1, None, 2, None]
    assert replies[1]["error"]["code"] == -32700 and replies[3]["error"]["code"] == -32600


def test_as_a_real_process_it_speaks_only_protocol_on_stdout():
    script = Path(m.__file__).resolve()
    msgs = "\n".join(json.dumps(x) for x in (rpc("initialize", {}), rpc("tools/list", mid=2))) + "\n"
    r = subprocess.run([sys.executable, str(script)], input=msgs, capture_output=True, text=True, encoding="utf-8", timeout=30,
                       env={"SystemRoot": __import__("os").environ.get("SystemRoot", ""), "WAYPOINT_URL": "http://127.0.0.1:1"})
    out = [json.loads(l) for l in r.stdout.splitlines()]
    assert r.returncode == 0 and [o["id"] for o in out] == [1, 2] and len(out[1]["result"]["tools"]) == 3
