"""memguard: a heavy job is refused when the machine has no room, and when room cannot be read.

The readings are supplied, so nothing here depends on how full this machine is today; one test
reads the real machine to prove the reader works on it.  Silas Reeve / DDL-3004 / 2026-10-09
"""
import pytest

import memguard


def reader(free, total=32.0):
    return lambda: (free, total)


def test_room_returns_the_reading():
    r = memguard.require(4.0, "job", reserve_gb=6.0, reader=reader(15.8, 31.9))
    assert r == {"what": "job", "free_gb": 15.8, "total_gb": 31.9, "need_gb": 4.0,
                 "reserve_gb": 6.0, "left_after_gb": 11.8}


def test_exactly_enough_passes_and_one_step_less_refuses():
    assert memguard.require(4.0, "job", reserve_gb=6.0, reader=reader(10.0))["left_after_gb"] == 6.0
    with pytest.raises(memguard.Refused):
        memguard.require(4.0, "job", reserve_gb=6.0, reader=reader(9.99))


def test_refusal_says_the_numbers():
    with pytest.raises(memguard.Refused) as e:
        memguard.require(13.1, "all vectors in float32", reserve_gb=6.0, reader=reader(15.8, 31.9))
    msg = str(e.value)
    for piece in ("all vectors in float32", "15.8", "31.9", "13.1", "6.0", "19.1", "Short by 3.3"):
        assert piece in msg, piece


def test_the_outage_would_have_been_refused():
    """2026-10-03: a second scoring process of about 10.8 GiB on a machine the first had filled."""
    with pytest.raises(memguard.Refused):
        memguard.require(10.8, "second scoring process", reader=reader(31.9 - 10.8 - 9.0, 31.9))


def test_unreadable_memory_refuses_and_is_a_refusal():
    def broken():
        raise memguard.Unknown("free memory could not be read")
    with pytest.raises(memguard.Unknown):
        memguard.require(1.0, "job", reader=broken)
    assert issubclass(memguard.Unknown, memguard.Refused)      # a caller catching Refused catches it too


def test_reader_failure_becomes_unknown(monkeypatch):
    class Dead:
        def __getattr__(self, name):
            raise OSError("no kernel32 here")
    monkeypatch.setattr(memguard.ctypes, "windll", Dead(), raising=False)
    with pytest.raises(memguard.Unknown) as e:
        memguard.read()
    assert "refusing, not guessing" in str(e.value)


@pytest.mark.parametrize("need", [0, -1, None, "4"])
def test_a_job_must_say_what_it_needs(need):
    with pytest.raises(ValueError):
        memguard.require(need, "job", reader=reader(30.0))


def test_negative_reserve_is_refused_as_a_mistake():
    with pytest.raises(ValueError):
        memguard.require(1.0, "job", reserve_gb=-1, reader=reader(30.0))


def test_real_machine_reading_is_plausible():
    free, total = memguard.read()
    assert 1.0 < total < 4096 and 0 <= free <= total


def test_cli_exit_codes(monkeypatch, capsys):
    monkeypatch.setattr(memguard, "read", reader(15.8, 31.9))
    monkeypatch.setattr(memguard.require, "__defaults__", (memguard.DEFAULT_RESERVE_GB, memguard.read))
    assert memguard.main(["--need", "4", "--what", "probe"]) == 0
    assert "room: 15.8 GiB free of 31.9" in capsys.readouterr().out
    assert memguard.main(["--need", "13.1"]) == 1
    assert "REFUSED:" in capsys.readouterr().err

    def broken():
        raise memguard.Unknown("cannot read")
    monkeypatch.setattr(memguard.require, "__defaults__", (memguard.DEFAULT_RESERVE_GB, broken))
    assert memguard.main(["--need", "1"]) == 2
    assert "REFUSED (unknown)" in capsys.readouterr().err
