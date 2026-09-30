"""The exclusion module works (test_index_exclusions.py); this proves the everything-run calls it.
A perfect rule nobody invokes protects nothing. Source-level on purpose: running the ingest writes
to a live collection.

Silas Reeve / DDL-3004 / 2026-09-29
"""
from pathlib import Path

SRC = (Path(__file__).parent / "dex-ingest-everything.py").read_text(encoding="utf-8")


def test_ingest_imports_the_shared_rule_rather_than_restating_it():
    assert "from index_exclusions import is_index_excluded" in SRC
    assert "INDEX_EXCLUDE = [" not in SRC, "patterns restated in the ingest; import them"


def test_the_check_runs_before_the_file_is_read():
    check = SRC.index("if is_index_excluded(p):")
    assert check < SRC.index("raw = p.read_bytes()")


def test_skips_are_counted_and_reported_not_silent():
    assert '"skipped_excluded": 0' in SRC
    assert 'stats["skipped_excluded"] += 1' in SRC
    report = SRC[SRC.index('for k in ("scanned"'):]
    assert '"skipped_excluded"' in report[:400]
