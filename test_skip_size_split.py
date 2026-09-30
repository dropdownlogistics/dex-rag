"""skipped_big used to count two different things: a file over the cap and an empty file. A count
of "big" files that is partly empty files hides the empty ones, and an empty texty file can be a
failed conversion. This proves the two are counted apart. Behaviour is tested on the pure helper;
the loop's use of it is checked at source level, because running the ingest writes to a live
collection (same reason as test_index_exclusions_wiring.py).

Silas Reeve / DDL-3004 / 2026-09-30
"""
import importlib.util
from pathlib import Path

HERE = Path(__file__).parent
SRC = (HERE / "dex-ingest-everything.py").read_text(encoding="utf-8")
_spec = importlib.util.spec_from_file_location("ingest_everything", HERE / "dex-ingest-everything.py")
ing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ing)


def test_empty_file_is_empty_not_big():
    assert ing.size_skip(0) == "skipped_empty"


def test_over_the_cap_is_big():
    assert ing.size_skip(ing.MAX_FILE_BYTES + 1) == "skipped_big"


def test_at_the_cap_and_ordinary_sizes_are_not_skipped():
    assert ing.size_skip(ing.MAX_FILE_BYTES) is None
    assert ing.size_skip(1) is None


def test_both_counters_start_at_zero_and_are_reported():
    assert '"skipped_empty": 0' in SRC and '"skipped_big": 0' in SRC
    report = SRC[SRC.index('for k in ("scanned"'):]
    assert '"skipped_empty"' in report[:500] and '"skipped_big"' in report[:500]


def test_the_loop_uses_the_helper_and_no_longer_merges_the_two():
    assert "size_skip(st.st_size)" in SRC
    assert "st.st_size > MAX_FILE_BYTES or st.st_size == 0" not in SRC
