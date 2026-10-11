"""dex_photo_work_log: file names and log lines in, time-ordered rows out. Made-up names only."""
from datetime import datetime, timezone

import dex_photo_work_log as w


def test_a_message_file_name_becomes_a_row_in_local_time():
    rows = w.dmails(["_shared/DDL-MSG/from-DDL-9001/msg__20260302T180000Z__from-DDL-9001__to-DDL-9002__to-DDL-9003__beacon-lens-fitted.md",
                     "_shared/DDL-MSG/from-DDL-9001/msg__20260302T190000Z__from-DDL-9001__no-recipient-in-name.md",
                     "_shared/DDL-MSG/inbox-DDL-9002/msg__20260302T180000Z__from-DDL-9001__a copy in an inbox.md",     # a copy, not the message
                     "_shared/DDL-MSG/from-DDL-9001/msg__20261341T990000Z__from-DDL-9001__not-a-time.md",
                     "_shared/DDL-MSG/_ORGWIDE-20260805-something.md"])
    local = datetime(2026, 3, 2, 18, tzinfo=timezone.utc).astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
    assert rows[0] == {"at": local, "kind": "dmail", "where": "DDL-9001", "what": "beacon lens fitted"}
    assert [r["what"] for r in rows] == ["beacon lens fitted", "no recipient in name"]


def test_commit_lines_become_rows_and_mail_deliveries_are_left_out():
    rows = w.commits("demo", ["2026-03-02T12:00:00\tFit the beacon lens", "2026-03-02T12:01:00\tD-mail to DDL-9002: something (#3)",
                              "2026-03-02T12:02:00\treceipts: DDL-9001 seen two", "2026-03-02T12:03:00\t", "garbage", "2026-03-02T12:04:00\t" + "x" * 400])
    assert [r["at"] for r in rows] == ["2026-03-02T12:00:00", "2026-03-02T12:04:00"]
    assert rows[0] == {"at": "2026-03-02T12:00:00", "kind": "commit", "where": "demo", "what": "Fit the beacon lens"}
    assert len(rows[1]["what"]) == w.MAX_WHAT


def test_build_orders_rows_by_time(monkeypatch):
    def fake(repo, *args):
        return "2026-03-02T12:00:00\tsecond\n2026-03-01T09:00:00\tfirst\n" if "log" in args else ""
    monkeypatch.setattr(w, "git", fake)
    rows, stats = w.build(("org", "origin/master"), [("demo", "p", "origin/main")])
    assert [r["what"] for r in rows] == ["first", "second"] and stats == {"commits_demo": 2, "dmails": 0, "rows": 2}
