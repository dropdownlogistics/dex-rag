"""dex_nightly_report: each number comes from a log, an unreadable log is said so, overlaps are found, and no file name gets out.

Made-up logs. Times are written the way each job writes them (local for the sweep, the refresh and the waits; UTC for the backup).
Silas Reeve / DDL-3004 / 2026-10-11
"""
import json
import os
from datetime import date, datetime, timezone

import pytest

import dex_nightly_report as nr

NIGHT = date(2026, 10, 12)


def utc(h, m=0, s=0):
    """A local clock time on the night, as the UTC string the backup log would hold."""
    return datetime(2026, 10, 12, h, m, s).astimezone().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def logs(tmp_path, sweep_rows=None, backup_rows=None, refresh_text=None, task_text=None, ingest=None):
    d = tmp_path
    if sweep_rows is not None:
        (d / "sweep.jsonl").write_text("".join(json.dumps(r) + "\n" for r in sweep_rows), encoding="utf-8")
    if backup_rows is not None:
        (d / "backup.jsonl").write_text("".join(json.dumps(r) + "\n" for r in backup_rows), encoding="utf-8")
    if refresh_text is not None:
        (d / "refresh.log").write_text(refresh_text, encoding="utf-8")
    if task_text is not None:
        (d / "task.log").write_text(task_text, encoding="utf-8")
    if ingest is not None:
        f = d / "ingest-report-everything_x.json"
        f.write_text(json.dumps(ingest), encoding="utf-8")
        when = datetime(2026, 10, 12, 5, 26).timestamp()          # the report was written at 05:26 on the night, not when this test ran
        os.utime(f, (when, when))
    return {"sweep": lambda n: nr.sweep(n, d / "sweep.jsonl"), "refresh": lambda n: nr.refresh(n, d / "refresh.log", d),
            "backups": lambda n: nr.backups(n, d / "backup.jsonl"), "backup_task": lambda n: nr.backup_task(n, d / "task.log")}


SWEEP_OK = {"start_ts": "2026-10-12T04:00:02.1", "end_ts": "2026-10-12T05:08:00.0", "outcome": "success", "files_found": 3, "files_copied": 3,
            "ingestion_triggered": True, "ingestion_success": True, "error": None, "dry_run": False, "filenames": ["Private Diary.txt"]}


def backup(start, end, chunks, gib=49.0, result="success", triggers=("force",), path="B1"):
    return [{"timestamp": start, "stage": "started", "backup_path": path},
            {"timestamp": end, "result": result, "backup_path": path, "duration_seconds": 1800.0, "restore_test_elapsed_seconds": 1200.0,
             "total_size_bytes": int(gib * 2**30), "total_chunk_count": chunks, "triggers": list(triggers)}]


REFRESH_OK = ("==== Mon 10/12/2026  4:40:01.95 corpus refresh start (DRYRUN=) \n"
              "2026-10-12T04:40:02 wait_quiet: waiting for dex-sweep.py\n"
              "2026-10-12T05:08:32 wait_quiet: quiet after 28.5 min (watched: dex-sweep.py)\n"
              "  ingesting a private file called Secret Plan.md\n"
              "==== Mon 10/12/2026  5:50:10.00 corpus refresh done \n")
TASK_OK = ("2026-10-12T05:30:01 wait_quiet: waiting for corpus_refresh.cmd\n"
           "2026-10-12T05:50:31 wait_quiet: quiet after 20.5 min (watched: dex-sweep.py, corpus_refresh.cmd)\n")
INGEST = {"generated_utc": utc(5, 9), "stats": {"scanned": 68505, "ingested": 390, "chunks": 17898, "skipped_unreadable": 0, "skipped_unembeddable": 0}}


def clean_night(tmp_path):
    return logs(tmp_path, [SWEEP_OK], backup(utc(4, 2), utc(5, 2), 2_293_752) + backup(utc(5, 51), utc(6, 55), 2_311_650, 49.4, triggers=("volume_based_delta_17898_chunks",), path="B2"),
                REFRESH_OK, TASK_OK, INGEST)


def test_a_clean_night_in_a_row_has_no_flags_and_every_number_is_from_a_log(tmp_path):
    rec = nr.build(NIGHT, clean_night(tmp_path))
    assert rec["flags"] == [] and rec["overlaps"] == [] and rec["unreadable"] == []
    sw, rf, b = rec["sweep"], rec["refresh"], rec["backups"]
    assert (sw["minutes"], sw["outcome"], sw["files_found"], sw["files_copied"], sw["ingested"]) == (68.0, "success", 3, 3, True)
    assert (rf["waited_minutes"], rf["outcome"], rf["lock_errors"], rf["minutes"], rf["end_from"]) == (28.5, "ok", 0, 70.2, "done line")
    assert rf["ingest"] == {"scanned": 68505, "ingested": 390, "chunks": 17898, "skipped_unreadable": 0, "skipped_unembeddable": 0}
    assert [(x["minutes"], x["copy_minutes"], x["restore_minutes"], x["gib"], x["chunks"]) for x in b] == [(60.0, 30.0, 20.0, 49.0, 2_293_752), (64.0, 30.0, 20.0, 49.4, 2_311_650)]
    assert b[1]["triggers"] == ["volume_based_delta_N_chunks"]                       # a trigger's name, with its number taken out so nights compare
    assert rec["backup_task"] == {"waited_minutes": 20.5, "wait_outcome": "ran"}
    assert rec["chunks_added"] == 17898 and rec["chain"]["minutes"] == 175.0


def test_no_file_name_or_log_text_gets_into_the_record_or_the_words(tmp_path):
    rec = nr.build(NIGHT, clean_night(tmp_path))
    out = json.dumps(rec) + nr.words(rec, nr.trend([rec]))
    for leak in ("Private Diary", "Secret Plan", "filenames", "ingesting a private"):
        assert leak not in out, leak


def test_the_old_schedule_is_seen_as_an_overlap_a_failed_sweep_and_a_lock(tmp_path):
    sweep_bad = dict(SWEEP_OK, end_ts="2026-10-12T05:07:32.0", outcome="failure", files_copied=0, ingestion_triggered=False, ingestion_success=False,
                     error="TimeoutExpired: Command '['python', 'dex-backup.py']' timed out after 300 seconds")
    refresh_bad = ("==== Mon 10/12/2026  4:40:01.95 corpus refresh start (DRYRUN=) \n"
                   "chromadb.errors.InternalError: error returned from database: (code: 5) database is locked\n"
                   "PRIVATE INGEST FAILED  \n")
    rec = nr.build(NIGHT, logs(tmp_path, [sweep_bad], backup(utc(4, 2), utc(5, 2), 100) + backup(utc(5, 31), utc(6, 32), 150, path="B2"), refresh_bad, "", INGEST))
    assert rec["refresh"]["outcome"] == "failed: PRIVATE INGEST" and rec["refresh"]["end_from"] == "ingest report written"
    assert rec["overlaps"][0]["a"] == "sweep" and rec["overlaps"][0]["b"] == "corpus refresh" and rec["overlaps"][0]["minutes"] >= 27
    assert rec["flags"][:3] == ["sweep failure (TimeoutExpired)", "corpus refresh failed: PRIVATE INGEST", "database is locked: 1"]
    assert "dex-backup.py" not in json.dumps(rec)                                    # the error's class, never its text
    assert rec["backup_task"] is None


def test_quiet_sweep_outcomes_are_not_faults_and_a_missing_job_is_said(tmp_path):
    quiet = dict(SWEEP_OK, outcome="skipped_report_only", files_copied=0, ingestion_triggered=False)
    rec = nr.build(NIGHT, logs(tmp_path, [quiet], backup(utc(5, 31), utc(6, 32), 150), "", "", None))
    assert rec["flags"] == ["corpus refresh did not run"]
    rec = nr.build(NIGHT, logs(tmp_path, [], [], "", "", None))
    assert rec["flags"] == ["sweep did not run", "corpus refresh did not run", "no backup"] and rec["chain"] is None


def test_a_log_that_cannot_be_read_is_named_and_its_section_is_null_not_guessed(tmp_path):
    src = clean_night(tmp_path)
    (tmp_path / "backup.jsonl").unlink()
    rec = nr.build(NIGHT, src)
    assert rec["backups"] is None and rec["unreadable"] == ["backup.jsonl: FileNotFoundError"]
    assert "could not read backup.jsonl: FileNotFoundError" in rec["flags"] and "no backup" in rec["flags"]
    assert rec["sweep"]["outcome"] == "success"                                      # the rest is still reported


def test_other_nights_dry_runs_and_torn_rows_are_left_out(tmp_path):
    other = dict(SWEEP_OK, start_ts="2026-10-11T04:00:02.0", end_ts="2026-10-11T05:00:00.0", outcome="failure")
    dry = dict(SWEEP_OK, start_ts="2026-10-12T08:00:00.0", end_ts="2026-10-12T08:01:00.0", dry_run=True, outcome="dry_run")
    src = logs(tmp_path, [other, SWEEP_OK, dry], backup("2026-10-11T09:01:58Z", "2026-10-11T10:02:32Z", 5, path="OLD") + backup(utc(4, 2), utc(5, 2), 7),
               "==== Mon 10/12/2026  8:22:27.26 corpus refresh start (DRYRUN=1) \n2026-10-12T08:22:28 wait_quiet: quiet after 0.0 min (watched: dex-sweep.py)\n==== Mon 10/12/2026  8:32:53.51 dry run ok \n" + REFRESH_OK,
               TASK_OK + "2026-10-12T08:11:49 wait_quiet: waiting for corpus_refresh.cmd\n2026-10-12T08:31:53 wait_quiet: quiet after 9.3 min (watched: x)\nMon 10/12/2026  8:31:53.89 backup task: dry run, no copy made \n", INGEST)
    with open(tmp_path / "sweep.jsonl", "a", encoding="utf-8") as f:
        f.write('{"start_ts": "2026-10-12T04:0')                                      # a torn last row
    rec = nr.build(NIGHT, src)
    assert rec["sweep"]["outcome"] == "success" and rec["sweep"]["runs"] == 1
    assert [b["chunks"] for b in rec["backups"]] == [7]
    assert rec["refresh"]["waited_minutes"] == 28.5                                  # the night's run, not the 08:22 dry run
    assert rec["backup_task"] == {"waited_minutes": 20.5, "wait_outcome": "ran"}     # not the 9.3 minutes of the hand-run check


def test_a_backup_inside_the_refresh_is_its_own_and_one_that_straddles_it_is_an_overlap(tmp_path):
    inside = logs(tmp_path, [SWEEP_OK], backup(utc(5, 10), utc(5, 40), 9), REFRESH_OK, TASK_OK, None)
    assert nr.build(NIGHT, inside)["overlaps"] == []
    straddle = logs(tmp_path, [SWEEP_OK], backup(utc(5, 30), utc(6, 30), 9), REFRESH_OK, TASK_OK, None)
    assert nr.build(NIGHT, straddle)["overlaps"] == [{"a": "backup", "b": "corpus refresh", "minutes": 20.2}]


def test_a_backup_task_that_gave_up_is_said(tmp_path):
    src = logs(tmp_path, [SWEEP_OK], [], REFRESH_OK, "2026-10-12T05:30:01 wait_quiet: waiting for corpus_refresh.cmd\n2026-10-12T09:30:01 wait_quiet: still busy after 240 min (corpus_refresh.cmd); not running\n", None)
    assert nr.build(NIGHT, src)["backup_task"] == {"waited_minutes": None, "wait_outcome": "gave up"}


def test_save_replaces_a_night_keeps_the_others_in_order_and_writes_the_three_files(tmp_path):
    out = tmp_path / "out"
    a = nr.build(NIGHT, clean_night(tmp_path))
    nr.save(dict(a, night="2026-10-10"), out)
    nr.save(a, out)
    rec, tr = nr.save(dict(a, flags=["again"]), out)                                 # the same night, reported again
    rows = [json.loads(l) for l in (out / "nightly.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(r["night"], r["flags"]) for r in rows] == [("2026-10-10", []), ("2026-10-12", ["again"])]
    latest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    assert latest["latest"]["night"] == "2026-10-12" and latest["nights_on_record"] == 2 and latest["trend"]["nights_before"] == 1
    assert latest["trend"]["longest_backup_minutes"] == {"last": 64.0, "average_before": 64.0}
    assert (latest["trend"]["clean_nights_before"], latest["trend"]["last_clean"]) == (1, False)
    md = (out / "nightly-2026-10-12.md").read_text(encoding="utf-8")
    assert md.startswith("# Nightly jobs, 2026-10-12") and "**Flagged:** again." in md and "| Sweep | 04:00 | 05:08 | 68.0 |" in md
    nr.save(dict(a, night="2026-10-09"), out)                                        # an older night reported late does not take over "latest"
    assert json.loads((out / "latest.json").read_text(encoding="utf-8"))["latest"]["night"] == "2026-10-12"
