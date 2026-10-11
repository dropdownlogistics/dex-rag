"""ensure_backup_current: the re-check after a successful backup can no longer fail the caller (FND-0034).

Silas Reeve / DDL-3004 / 2026-10-11
"""
import json
import subprocess

import pytest

import dex_pipeline as dp

STATUS = {"exists": True, "sqlite_readable": True, "most_recent_path": "OLD", "age_hours": 30.0,
          "triggers_to_fire": ["volume_based_delta_5000_chunks"], "should_backup": True}


class Done:
    def __init__(self, code=0, out=""):
        self.returncode, self.stdout, self.stderr = code, out, ""


def runner(third):
    """A stand-in for subprocess.run: the first check, the backup, then `third` for the re-check."""
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        if len(calls) == 1:
            return Done(0, json.dumps(STATUS))
        if len(calls) == 2:
            assert "--force" in cmd
            return Done(0, "backup done")
        if isinstance(third, Exception):
            raise third
        return third
    run.calls = calls
    return run


def test_a_recheck_that_times_out_does_not_fail_and_the_path_comes_from_the_log(monkeypatch):
    run = runner(subprocess.TimeoutExpired(cmd="x", timeout=300))
    monkeypatch.setattr(dp.subprocess, "run", run)
    monkeypatch.setattr(dp, "_last_successful_backup_path", lambda: "NEW-FROM-LOG")
    r = dp.ensure_backup_current(expected_write_chunks=10_000)
    assert len(run.calls) == 3
    assert (r["backup_ran"], r["status"], r["recheck"], r["backup_path"], r["backup_age_hours"]) == (True, "refreshed", "timed_out", "NEW-FROM-LOG", None)


def test_a_recheck_that_times_out_with_no_log_keeps_the_old_path_and_still_does_not_fail(monkeypatch):
    monkeypatch.setattr(dp.subprocess, "run", runner(subprocess.TimeoutExpired(cmd="x", timeout=300)))
    monkeypatch.setattr(dp, "_last_successful_backup_path", lambda: None)
    r = dp.ensure_backup_current(expected_write_chunks=10_000)
    assert (r["backup_ran"], r["recheck"], r["backup_path"], r["backup_age_hours"]) == (True, "timed_out", "OLD", 30.0)


def test_a_recheck_that_answers_fills_in_the_new_backup(monkeypatch):
    monkeypatch.setattr(dp.subprocess, "run", runner(Done(0, json.dumps({"most_recent_path": "NEW", "age_hours": 0.01}))))
    r = dp.ensure_backup_current(expected_write_chunks=10_000)
    assert (r["recheck"], r["backup_path"], r["backup_age_hours"]) == ("ok", "NEW", 0.01)


def test_a_recheck_that_exits_non_zero_or_prints_nonsense_is_named_not_hidden(monkeypatch):
    monkeypatch.setattr(dp.subprocess, "run", runner(Done(3, "")))
    assert dp.ensure_backup_current(expected_write_chunks=10_000)["recheck"] == "exit_3"
    monkeypatch.setattr(dp.subprocess, "run", runner(Done(0, "not json")))
    r = dp.ensure_backup_current(expected_write_chunks=10_000)
    assert (r["recheck"], r["backup_path"]) == ("unreadable", "OLD")


def test_a_failed_backup_still_fails_and_a_timed_out_first_check_still_raises(monkeypatch):
    def backup_fails(cmd, **kw):
        return Done(0, json.dumps(STATUS)) if "--check-only" in cmd else Done(1, "boom")
    monkeypatch.setattr(dp.subprocess, "run", backup_fails)
    with pytest.raises(dp.BackupFailedError):
        dp.ensure_backup_current(expected_write_chunks=10_000)

    def first_times_out(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd="x", timeout=300)
    monkeypatch.setattr(dp.subprocess, "run", first_times_out)
    with pytest.raises(subprocess.TimeoutExpired):            # the gate BEFORE a write is unchanged: no backup check, no write
        dp.ensure_backup_current(expected_write_chunks=10_000)


def test_last_successful_backup_path_reads_the_last_success_and_never_raises(tmp_path):
    log = tmp_path / "_backup_log.jsonl"
    log.write_text("\n".join([json.dumps({"result": "success", "backup_path": "A"}), "torn line {",
                              json.dumps({"stage": "started", "backup_path": "C"}), json.dumps({"result": "success", "backup_path": "B"}),
                              json.dumps({"result": "failed", "backup_path": "D"})]) + "\n", encoding="utf-8")
    assert dp._last_successful_backup_path(log) == "B"
    assert dp._last_successful_backup_path(tmp_path / "missing.jsonl") is None


def test_no_recheck_is_run_when_no_backup_is_needed_or_on_a_dry_run(monkeypatch):
    current = dict(STATUS, should_backup=False, triggers_to_fire=[])
    monkeypatch.setattr(dp.subprocess, "run", lambda cmd, **kw: Done(0, json.dumps(current)))
    assert dp.ensure_backup_current(expected_write_chunks=0)["recheck"] is None
    run = runner(Done(0, "{}"))
    monkeypatch.setattr(dp.subprocess, "run", run)
    r = dp.ensure_backup_current(expected_write_chunks=10_000, dry_run=True)
    assert (r["status"], r["recheck"], len(run.calls)) == ("dry_run", None, 2)
