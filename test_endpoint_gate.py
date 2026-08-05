#!/usr/bin/env python3
"""
test_endpoint_gate.py -- prove the query gate is actually IN the endpoint.

dex_query_gate.py's own suites prove the classifier works. This proves
dex-openai-api.py calls it, which is a different claim: a correct gate nobody
invokes protects nothing.

No server, no token, no credential. The handler is called directly, and
`retrieve` is stubbed so the substantive path can be verified without a GPU or
a model call -- the question is which BRANCH was taken, not what the model said.

    python test_endpoint_gate.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"\n          {detail}" if detail and not cond else ""))


spec = importlib.util.spec_from_file_location("dex_api", HERE / "dex-openai-api.py")
api = importlib.util.module_from_spec(spec)
sys.modules["dex_api"] = api
spec.loader.exec_module(api)


def ask(text: str) -> str:
    body = api.ChatReq(model="dex-all", messages=[api.Msg(role="user", content=text)])
    return api.chat_completions(body)["choices"][0]["message"]["content"]


def main() -> int:
    print("\nCONVERSATIONAL INPUT MUST NOT REACH RETRIEVAL\n")

    # If retrieval is reached, this raises and the test fails loudly rather
    # than quietly passing on a coincidence.
    def boom(*a, **k):
        raise AssertionError("retrieve() was called for a conversational query")

    real_retrieve = api.retrieve
    api.retrieve = boom
    try:
        for q in ("Hello", "hi", "hey there", "good morning"):
            try:
                out = ask(q)
                check(f"{q!r} answered without retrieval",
                      out == api.GREETING_REPLY, f"got {out[:60]!r}")
            except AssertionError as e:
                check(f"{q!r} answered without retrieval", False, str(e))

        for q in ("thanks", "ok", "got it", "perfect"):
            try:
                out = ask(q)
                check(f"{q!r} gets the acknowledgement reply",
                      out == api.ACK_REPLY, f"got {out[:60]!r}")
            except AssertionError as e:
                check(f"{q!r} gets the acknowledgement reply", False, str(e))

        try:
            out = ask("?")
            check("'?' gets the empty reply", out == api.EMPTY_REPLY, f"got {out[:60]!r}")
        except AssertionError as e:
            check("'?' gets the empty reply", False, str(e))

        # No conversational reply may make a claim about the corpus.
        for name, txt in (("greeting", api.GREETING_REPLY), ("ack", api.ACK_REPLY),
                          ("empty", api.EMPTY_REPLY)):
            check(f"{name} reply cites nothing", "sources:" not in txt.lower())
    finally:
        api.retrieve = real_retrieve

    print("\nSUBSTANTIVE INPUT MUST REACH RETRIEVAL\n")

    called = {"n": 0, "queries": []}

    def spy(query, names, top_n=6):
        called["n"] += 1
        called["queries"].append(query)
        return []          # no hits -> NO_EVIDENCE, no model call needed

    api.retrieve = spy
    try:
        for q in ("What is AEN", "What is the Platinum Bounce recovery protocol?",
                  "MindFrame", "hey what is the Platinum Bounce"):
            before = called["n"]
            out = ask(q)
            check(f"{q[:38]!r} reached retrieval", called["n"] == before + 1)
            check(f"{q[:38]!r} refused for NO EVIDENCE, not as chatter",
                  out == api.NO_EVIDENCE, f"got {out[:60]!r}")

        check("greeting prefix stripped before retrieval",
              called["queries"][-1] == "hey what is the Platinum Bounce",
              f"query passed through: {called['queries'][-1]!r}")
    finally:
        api.retrieve = real_retrieve

    print("\nCONTROL — the harness must be able to detect a missing gate\n")
    # Bypass the gate the way a regression would: make everything substantive.
    real_classify = api.classify
    api.classify = lambda q: (api.SUBSTANTIVE, "gate disabled by test")
    api.retrieve = spy
    try:
        before = called["n"]
        ask("Hello")
        check("CONTROL: with the gate bypassed, 'Hello' DOES reach retrieval",
              called["n"] == before + 1,
              "the suite cannot tell a wired gate from an unwired one")
    finally:
        api.classify = real_classify
        api.retrieve = real_retrieve

    print("\n" + "=" * 62)
    print(f"  {len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"    FAILED: {f}")
    print("=" * 62 + "\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
