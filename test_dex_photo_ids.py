"""dex_photo_ids: her patterns as whole tokens, the best reading kept, real dates only, and nothing else from the words.

Silas Reeve / DDL-3004 / 2026-10-10
"""
import dex_photo_ids as pi


def w(text, conf=90.0, y=10, h=12):
    return [text, conf, 0, y, 50, h]


def ids(*words):
    return [(r["id"], r["conf"]) for r in pi.ids_in(list(words))]


def test_seat_and_graph_ids_are_found_inside_punctuation():
    assert ids(w("(DDL-3012),", 93.0), w("SEAT-1002:"), w("ASSET-0011."), w("PROP-0033"), w("CONV-0010"),
               w("STD-DDL-OPERATOR-DECISIONS-001"), w("PA1-7"), w("ADR-12B")) == [
        ("ADR-12B", 90.0), ("ASSET-0011", 90.0), ("CONV-0010", 90.0), ("DDL-3012", 93.0), ("PA1-7", 90.0), ("PROP-0033", 90.0),
        ("SEAT-1002", 90.0), ("STD-DDL-OPERATOR-DECISIONS-001", 90.0)]


def test_an_id_is_a_whole_token():
    assert ids(w("XDDL-3012"), w("DDL-30123"), w("DDL-301"), w("ddl-3012"), w("MYASSET-0011"), w("ASSET-0011x9")) == []
    assert ids(w("DDL-3004:20261010T170650Z-ccc1")) == [("DDL-3004", 90.0)]          # a D-mail id names its seat
    assert ids(w("DDL-3004/DDL-3005")) == [("DDL-3004", 90.0), ("DDL-3005", 90.0)]


def test_ids_the_graph_has_no_node_for_are_left_out():
    assert ids(w("FND-0034"), w("R-005"), w("P-00409386b7"), w("0123456789abcdef0123456789abcdef01234567"), w("FOO-12")) == []


def test_the_same_id_read_twice_keeps_its_best_reading_and_low_readings_are_kept_as_read():
    assert ids(w("DDL-3004", 41.0), w("DDL-3004", 88.5), w("DDL-3004", 60.0)) == [("DDL-3004", 88.5)]
    assert ids(w("ASSET-0001", 12.0)) == [("ASSET-0001", 12.0)]                       # the graph applies the 80 line, not this


def dates(*words):
    return [(r["date"], r["conf"]) for r in pi.dates_in(list(words))]


def test_iso_dates_in_one_word():
    assert dates(w("2026-03-02", 91.0), w("(2025-12-31)"), w("log-2024-02-29.txt")) == [("2024-02-29", 90.0), ("2025-12-31", 90.0), ("2026-03-02", 91.0)]
    assert dates(w("2026-02-30"), w("2026-13-01"), w("12026-03-02"), w("2026-03-021"), w("1989-01-01"), w("2036-01-01")) == []


def test_written_dates_across_three_words_take_the_weakest_confidence():
    assert dates(w("Mar", 95), w("2,", 70), w("2026", 88)) == [("2026-03-02", 70.0)]
    assert dates(w("September", 90), w("28th,", 90), w("2026.", 90)) == [("2026-09-28", 90.0)]
    assert dates(w("Sept.", 90), w("3", 90), w("2025", 90)) == [("2025-09-03", 90.0)]
    assert dates(w("Feb", 90), w("30,", 90), w("2026", 90)) == []                     # not a real day
    assert dates(w("Marvel", 90), w("2,", 90), w("2026", 90)) == []                   # not a month
    assert dates(w("Mar", 90, y=10), w("2,", 90, y=10), w("2026", 90, y=60)) == []    # the year is on another line


def test_nothing_but_ids_and_dates_comes_out():
    words = [w("password"), w("hunter2"), w("DDL-3004"), w("on"), w("2026-03-02"), w("secret")]
    assert pi.ids_in(words) == [{"id": "DDL-3004", "conf": 90.0}]
    assert pi.dates_in(words) == [{"date": "2026-03-02", "conf": 90.0}]
