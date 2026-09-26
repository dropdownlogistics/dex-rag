#!/usr/bin/env python3
"""Tests for the Dex chat engine — pure parse logic (the I/O wrapper is proven live).

Run:  python -m unittest test_engine -v
"""
from __future__ import annotations

import json
import unittest

import engine as E

SAMPLE = json.dumps({
    "question": "Who is Dex Jr?",
    "chunks": [
        {"source_file": "DexJr_FirstSteps.txt", "collection": "dex_canon_v2",
         "distance": 0.4842, "weight": 0.9, "score": 0.6064,
         "text": "Hello D.K.! I'm Dex Jr., the 10th council member of DDL."},
        {"source_file": "ROLE.txt", "collection": "dex_canon_v2",
         "distance": 0.52, "score": 0.59, "content": "You are Dex — co-architect."},
    ],
    "answer": "Dex Jr. is the 10th council member of Dropdown Logistics.",
    "citations": ["DexJr_FirstSteps.txt", "ROLE.txt"],
})


class TestParse(unittest.TestCase):
    def setUp(self):
        self.rec = E.parse_dex_json(SAMPLE)

    def test_answer_carried_through(self):
        self.assertEqual(self.rec["answer"],
                         "Dex Jr. is the 10th council member of Dropdown Logistics.")

    def test_citations_carried_through(self):
        self.assertEqual(self.rec["citations"], ["DexJr_FirstSteps.txt", "ROLE.txt"])

    def test_sources_have_file_and_scores(self):
        s0 = self.rec["sources"][0]
        self.assertEqual(s0["file"], "DexJr_FirstSteps.txt")
        self.assertEqual(s0["collection"], "dex_canon_v2")
        self.assertEqual(s0["distance"], 0.4842)
        self.assertEqual(s0["score"], 0.6064)

    def test_preview_reads_any_text_key(self):
        # first chunk spells it "text", second "content" — both must render
        self.assertIn("Dex Jr.", self.rec["sources"][0]["preview"])
        self.assertIn("co-architect", self.rec["sources"][1]["preview"])

    def test_missing_answer_is_empty_string_not_none(self):
        rec = E.parse_dex_json(json.dumps({"chunks": [], "citations": []}))
        self.assertEqual(rec["answer"], "")
        self.assertEqual(rec["sources"], [])

    def test_missing_text_key_yields_empty_preview_not_crash(self):
        rec = E.parse_dex_json(json.dumps(
            {"chunks": [{"source_file": "x", "distance": 0.5}], "answer": "a"}))
        self.assertEqual(rec["sources"][0]["preview"], "")
        self.assertEqual(rec["sources"][0]["file"], "x")


if __name__ == "__main__":
    unittest.main()
