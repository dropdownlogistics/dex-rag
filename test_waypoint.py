"""Waypoint phase 1: the parse, the filters, the masks, the envelope and the telemetry. Made-up chunks only."""
import json

import pytest

import waypoint as wp


def chunk(i, root="vault", path=None, text=None, score=None):
    return {"id": f"c{i}", "source_root": root, "rel_path": path or f"notes/n{i}.md", "chunk_index": i, "total_chunks": 9,
            "text": text if text is not None else f"file: n{i}.md\npath: notes/n{i}.md\n\nbody of chunk {i}", "score": score if score is not None else 0.9 - i / 100}


def asker(chunks):
    calls = []

    def ask(text, n):
        calls.append((text, n))
        return chunks[:n], {"rows": 1000, "prefix": 256, "shortlist": 5000}
    return ask, calls


def test_parse_splits_a_query_into_the_parts_the_design_names():
    p = wp.parse('nightly backup "database is locked" FND-0034 -draft root:Vault ext:.MD -in:old\\stuff kind:dmail foo:bar c10e3d88d')
    assert p["meaning"] == "nightly backup database is locked FND-0034 foo:bar c10e3d88d"
    assert p["exact"] == ["database is locked", "FND-0034", "c10e3d88d"] and p["exclude"] == ["draft"]
    assert p["filters"] == {"root": ["vault"], "ext": ["md"], "in": []} and p["exclude_filters"]["in"] == ["old/stuff"]
    assert p["not_in_phase_1"] == ["kind:dmail"] and p["unknown_operators"] == ["foo:bar"]
    assert wp.parse("")["meaning"] == "" and wp.parse(None)["exact"] == []


def test_a_plain_search_returns_k_places_best_first_and_asks_for_no_more():
    ask, calls = asker([chunk(i) for i in range(30)])
    env = wp.search("where is the backup note", 3, ask)
    assert calls == [("where is the backup note", 3)]
    assert [h["id"] for h in env["hits"]] == ["c0", "c1", "c2"]
    h = env["hits"][0]
    assert h["root"] == "vault" and h["path"] == "notes/n0.md" and h["chunk"] == [1, 9] and h["lines"] is None
    assert h["snippet"] == "body of chunk 0"                               # the embed header is not shown
    assert h["score"] == {"meaning": 0.9, "words": None}
    assert env["settings"] == {"k": 3, "candidates_looked_at": 3, "rows": 1000, "prefix": 256, "shortlist": 5000, "ranking": "meaning"}
    assert not any("measured for the top" in l for l in env["limits"])       # 3 is inside the ruled depth


def test_k_is_clamped_and_a_depth_past_the_ruling_says_so():
    ask, calls = asker([chunk(i) for i in range(60)])
    env = wp.search("x", 999, ask)
    assert env["settings"]["k"] == wp.MAX_K and calls[0][1] == wp.MAX_K
    assert any("measured for the top 4" in l for l in env["limits"])
    assert wp.search("x", "lots", ask)["settings"]["k"] == wp.DEFAULT_K
    assert wp.search("x", 0, ask)["settings"]["k"] == 1


def test_filters_narrow_the_candidates_and_the_envelope_counts_what_went():
    cs = [chunk(0, "vault", "a/one.md"), chunk(1, "corpus", "a/two.py"), chunk(2, "vault", "b/three.py"), chunk(3, "sessions", "s/four.jsonl"),
          chunk(4, "vault", "a/five.py")]
    ask, calls = asker(cs)
    env = wp.search("thing root:vault ext:py", 2, ask)
    assert calls[0][1] == 2 * wp.OVERFETCH                                  # a filter means looking further down
    assert [h["path"] for h in env["hits"]] == ["b/three.py", "a/five.py"] and env["removed"]["filters"] == 3
    assert [h["rank_before_filters"] for h in env["hits"]] == [3, 5]
    env = wp.search("thing -root:vault in:a/", 5, ask)
    assert [h["path"] for h in env["hits"]] == ["a/two.py"]
    assert any("left 1" in l for l in env["limits"])                         # fewer than asked, and it says why


def test_exact_terms_and_exclusions_are_reported_as_not_applied():
    ask, _ = asker([chunk(0, text="nothing like it")])
    env = wp.search('"exact phrase" FND-0034 -draft kind:dmail', 4, ask)
    assert env["not_applied"] == ['"exact phrase" (exact)', '"FND-0034" (exact)', "-draft", "kind:dmail"]
    assert len(env["hits"]) == 1                                             # the chunk without the phrase still came back: meaning only


def test_a_seats_deny_list_removes_hits_and_is_counted():
    cs = [chunk(0, "vault", "council/packet.md"), chunk(1, "vault", "notes/a.md"), chunk(2, "archive", "x.md")]
    ask, _ = asker(cs)
    env = wp.search("thing", 5, ask, deny=["vault:council/*", "archive"])
    assert [h["path"] for h in env["hits"]] == ["notes/a.md"] and env["removed"]["denied_for_seat"] == 2
    assert wp.denied(cs[0], ["*:council/*"]) and not wp.denied(cs[1], ["vault:council/*"]) and not wp.denied(cs[1], [])


def test_a_possible_credential_is_masked_and_counted_never_returned():
    secret = "sk-" + "A1b2C3d4" * 5
    ask, _ = asker([chunk(0, text=f"file: k.md\npath: k.md\n\nthe key is {secret} and then more words")])
    env = wp.search("key", 1, ask)
    s = env["hits"][0]["snippet"]
    assert secret not in s and wp.MASK in s and s.endswith("and then more words") and env["credentials_masked"] == 1
    assert wp.snippet_of("a risk-register line and commit c10e3d88df7c9032c8c287ad4e700de089b6a938") == \
        ("a risk-register line and commit c10e3d88df7c9032c8c287ad4e700de089b6a938", 0)      # a hash is not a credential


def test_a_snippet_is_capped():
    s, _ = wp.snippet_of("word " * 500)
    assert len(s) == wp.SNIPPET_CHARS + 4 and s.endswith(" ...")


def test_nothing_to_search_by_is_refused():
    ask, calls = asker([chunk(0)])
    for q in ("", "   ", "root:vault ext:md", "-draft"):
        with pytest.raises(ValueError, match="nothing to search by"):
            wp.search(q, 4, ask)
    assert calls == []


def test_telemetry_is_numbers_only(tmp_path):
    log = tmp_path / "t" / "waypoint.jsonl"
    ask, _ = asker([chunk(0, "vault"), chunk(1, "corpus"), chunk(2, "vault")])
    wp.search('a very private question "secret phrase" root:vault', 5, ask, seat="DDL-9001", log_path=log)
    raw = log.read_text(encoding="utf-8")
    row = json.loads(raw)
    assert row["tool"] == "search" and row["seat"] == "DDL-9001" and row["hits"] == 2 and row["hits_by_root"] == {"vault": 2}
    assert row["filters_used"] == ["root"] and row["not_applied"] == 1 and row["shortlist"] == 5000 and row["prefix"] == 256
    for word in ("private", "question", "secret", "phrase", "body of chunk", "notes/"):
        assert word not in raw                                              # no query text, no snippet text, no path


def test_explain_runs_no_search_and_says_what_would_happen():
    e = wp.explain('backup "exact" root:vault after:2026-10-01')
    assert e["would_rank_by"] == "meaning" and e["would_filter_by"] == {"root": ["vault"]}
    assert e["parsed_but_not_applied_in_phase_1"] == ['"exact" (exact)', "after:2026-10-01"]
    assert wp.explain("root:vault")["would_rank_by"] is None


def test_sources_reports_roots_and_what_is_not_there():
    s = wp.sources({"state": "ready", "rows": 10, "prefix": 256, "shortlist": 5000},
                   {"started_utc": "a", "finished_utc": "b", "by_root": {"vault": {"files": 2, "chunks": 7}, "corpus": {"files": 1, "chunks": 3}}})
    assert s["roots"] == [{"root": "corpus", "files": 1, "chunks": 3}, {"root": "vault", "files": 2, "chunks": 7}]
    assert s["state"] == "ready" and s["built"]["finished_utc"] == "b" and s["not_indexed_yet"] and s["ranking"].startswith("meaning")
