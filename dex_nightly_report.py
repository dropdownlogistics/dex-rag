"""
dex_nightly_report.py -- one record per night of what the three nightly jobs did, read from their own logs.

Operator, 2026-10-11: "we should track telemetry to this and look for patterns and opportunities to
improve ... have it kick out a report after each run giving stats and then we could just feed the
reports right into DexHQ."

It runs last in the chain (dex-backup-task.cmd calls it after the backup, whatever the backup did) and
can be run by hand for any night. It reads; it changes nothing the jobs own.

    sweep            dex-sweep-log.jsonl                       start, end, outcome, counts
    corpus refresh   C:\\Users\\dexjr\\dex\\corpus-refresh.log     start, wait, end, the step that failed, lock errors
                     ingest-report-everything_*.json           files scanned and ingested, chunks written
    backups          <backup root>\\_backup_log.jsonl           each backup: start, end, copy, restore test, size, chunks
    backup task      <backup root>\\_dex-backup-task.log        how long it waited for the earlier jobs

Writes, under --out (default C:\\Users\\dexjr\\dex-data\\nightly):
    nightly.jsonl            one row per night, replaced if the night is reported again
    latest.json              the last night's row plus the trend over the nights before it
    nightly-<date>.md        the same in words, for a person

Rules (the briefing's, kept): no model; every number is read from a log or counted from its rows; a
log that cannot be read is said so in `unreadable` and its section is null, never left out or guessed;
counts and times only, never a file name or a line of anyone's text.

    python dex_nightly_report.py                 # last night
    python dex_nightly_report.py --night 2026-10-11
    python dex_nightly_report.py --backfill 30   # the last 30 nights, from the logs as they stand
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SWEEP_LOG = Path(os.environ.get("DEX_SWEEP_LOG", r"C:\Users\dexjr\dex-rag\dex-sweep-log.jsonl"))
BACKUP_LOG = Path(os.environ.get("DEX_BACKUP_LOG", r"D:\DDL_Backup\chromadb_backups\_backup_log.jsonl"))
BACKUP_TASK_LOG = Path(os.environ.get("DEX_BACKUP_TASK_LOG", r"D:\DDL_Backup\chromadb_backups\_dex-backup-task.log"))
REFRESH_LOG = Path(os.environ.get("DEX_REFRESH_LOG", r"C:\Users\dexjr\dex\corpus-refresh.log"))
INGEST_DIR = Path(os.environ.get("DEX_INGEST_REPORTS", r"C:\Users\dexjr\dex-rag"))
OUT = Path(os.environ.get("DEX_NIGHTLY_DIR", r"C:\Users\dexjr\dex-data\nightly"))

NIGHT_START_H, NIGHT_END_H = 0, 12        # a night is local midnight to local noon of its date
LONG_BACKUP_MIN = 90
# A sweep that found nothing of the Operator's to ingest is a quiet night, not a fault.
SWEEP_FINE = ("success", "skipped_report_only", "no_files_found")
REFRESH_START = re.compile(r"^==== \w{3} (\d\d)/(\d\d)/(\d{4})\s+(\d{1,2}):(\d\d):(\d\d)\.\d+ corpus refresh (start|done)(?: \(DRYRUN=(\d*)\))?")
WAIT = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d) wait_quiet: (quiet after ([\d.]+) min|waiting for|still busy|cannot read)")
FAILED = re.compile(r"\b([A-Z][A-Z ]*?) FAILED\b")


class Unreadable(Exception):
    pass


def _local(dt_naive):
    """A naive local time as an aware UTC time."""
    return dt_naive.astimezone().astimezone(timezone.utc)


def _utc(s):
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t.astimezone(timezone.utc) if t.tzinfo else _local(t)


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ") if t else None


def _mins(a, b):
    return round((b - a).total_seconds() / 60, 1) if a and b else None


def window(night):
    d = datetime.combine(night, datetime.min.time())
    return _local(d + timedelta(hours=NIGHT_START_H)), _local(d + timedelta(hours=NIGHT_END_H))


def _lines(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        raise Unreadable(f"{path.name}: {type(e).__name__}") from e


def _jsonl(path):
    out = []
    for line in _lines(path):
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue                      # a torn row is skipped; the rows around it still count
    return out


# ---- each job, from its own record -------------------------------------------------------------

def sweep(night, path=SWEEP_LOG):
    lo, hi = window(night)
    rows = [r for r in _jsonl(path) if r.get("start_ts") and not r.get("dry_run") and lo <= _utc(r["start_ts"]) < hi]
    if not rows:
        return None
    r = rows[-1]
    s, e = _utc(r["start_ts"]), _utc(r["end_ts"]) if r.get("end_ts") else None
    err = (r.get("error") or "").split(":")[0][:60] or None           # the error's class, not its text
    return {"start": _iso(s), "end": _iso(e), "minutes": _mins(s, e), "outcome": r.get("outcome"),
            "files_found": r.get("files_found"), "files_copied": r.get("files_copied"),
            "ingested": bool(r.get("ingestion_triggered") and r.get("ingestion_success")), "error": err, "runs": len(rows)}


def backups(night, path=BACKUP_LOG):
    lo, hi = window(night)
    started, out = {}, []
    for r in _jsonl(path):
        if r.get("stage") == "started":
            started[r.get("backup_path")] = r["timestamp"]
        elif "result" in r and r.get("timestamp"):
            e = _utc(r["timestamp"])
            s = _utc(started[r["backup_path"]]) if r.get("backup_path") in started else None
            if not (lo <= (s or e) < hi):
                continue
            gib = round(r["total_size_bytes"] / 2**30, 1) if r.get("total_size_bytes") else None
            out.append({"start": _iso(s), "end": _iso(e), "minutes": _mins(s, e), "result": r["result"],
                        "copy_minutes": round(r["duration_seconds"] / 60, 1) if r.get("duration_seconds") is not None else None,
                        "restore_minutes": round(r["restore_test_elapsed_seconds"] / 60, 1) if r.get("restore_test_elapsed_seconds") is not None else None,
                        "gib": gib, "chunks": r.get("total_chunk_count"),
                        "triggers": [re.sub(r"\d+", "N", t) for t in r.get("triggers", [])]})
    return out


def refresh(night, path=REFRESH_LOG, ingest_dir=INGEST_DIR):
    lo, hi = window(night)
    lines = _lines(path)
    blocks, cur = [], None
    for i, line in enumerate(lines):
        m = REFRESH_START.match(line)
        if m and m.group(7) == "start":
            mo, d, y, h, mi, s = (int(x) for x in m.groups()[:6])
            cur = {"start": _local(datetime(y, mo, d, h, mi, s)), "dry": bool(m.group(8)), "from": i, "to": len(lines), "end": None}
            blocks.append(cur)
        elif m and cur is not None:
            mo, d, y, h, mi, s = (int(x) for x in m.groups()[:6])
            cur["end"], cur["to"] = _local(datetime(y, mo, d, h, mi, s)), i
            cur = None
        elif cur is not None and line.startswith("==== ") and "dry run ok" in line:
            cur["to"] = i
            cur = None
    for a, b in zip(blocks, blocks[1:]):
        a["to"] = min(a["to"], b["from"])
    mine = [b for b in blocks if not b["dry"] and lo <= b["start"] < hi]
    if not mine:
        return None
    b = mine[-1]
    body = lines[b["from"]:b["to"]]
    waited, active, wait_state = None, b["start"], None
    for line in body:
        w = WAIT.match(line)
        if w:
            wait_state = w.group(2).split(" ")[0]
            if w.group(3) is not None:
                waited, active, wait_state = float(w.group(3)), _local(datetime.fromisoformat(w.group(1))), "quiet"
    failed = [m.group(1).strip() for line in body for m in [FAILED.search(line)] if m]
    locked = sum(1 for line in body if "database is locked" in line)
    ingest, end, end_from = None, b["end"], "done line" if b["end"] else None
    try:
        reports = sorted(ingest_dir.glob("ingest-report-everything_*.json"))
    except OSError:
        reports = []
    for p in reports:
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
            g = _utc(j["generated_utc"])
        except (OSError, ValueError, KeyError):
            continue
        if b["start"] <= g < (b["end"] or hi):
            st = j.get("stats", {})
            ingest = {"scanned": st.get("scanned"), "ingested": st.get("ingested"), "chunks": st.get("chunks"),
                      "skipped_unreadable": st.get("skipped_unreadable"), "skipped_unembeddable": st.get("skipped_unembeddable")}
            if end is None:                                # no done line: the report's write time is the last sign of it
                end, end_from = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc), "ingest report written"
            break
    outcome = "ok" if b["end"] and not failed else ("failed: " + ", ".join(dict.fromkeys(failed))) if failed else ("did not run: " + wait_state) if wait_state in ("still", "cannot") else "no done line"
    return {"start": _iso(b["start"]), "active_from": _iso(active), "waited_minutes": waited, "end": _iso(end), "end_from": end_from,
            "minutes": _mins(b["start"], end), "outcome": outcome, "lock_errors": locked, "ingest": ingest}


def backup_task(night, path=BACKUP_TASK_LOG):
    lo, hi = window(night)
    waited, state = None, None
    kept = (None, None)                       # the last wait that was not a dry run of the script
    for line in _lines(path):
        if "backup task: dry run" in line:    # a hand-run check of the script, not the night's job: forget its wait
            waited, state = kept
            continue
        w = WAIT.match(line)
        if not w or not (lo <= _local(datetime.fromisoformat(w.group(1))) < hi):
            continue
        if w.group(2).startswith("waiting") and state in (None, "quiet", "still", "cannot"):
            kept = (waited, state)            # a new wait begins: remember where things stood before it
        state = w.group(2).split(" ")[0]
        if w.group(3) is not None:
            waited, state = float(w.group(3)), "quiet"
    return None if state is None else {"waited_minutes": waited, "wait_outcome": {"quiet": "ran", "still": "gave up", "cannot": "could not look", "waiting": "still waiting"}[state]}


# ---- the night as a whole ----------------------------------------------------------------------

def _overlap(a0, a1, b0, b1):
    if not (a0 and a1 and b0 and b1):
        return 0.0
    return max(0.0, (min(a1, b1) - max(a0, b0)).total_seconds() / 60)


def build(night, sources=None):
    s = sources or {"sweep": sweep, "refresh": refresh, "backups": backups, "backup_task": backup_task}
    rec, unreadable = {"night": night.isoformat()}, []
    for k, fn in s.items():
        try:
            rec[k] = fn(night)
        except Unreadable as e:
            rec[k], _ = None, unreadable.append(str(e))
    rec["unreadable"] = unreadable
    t = lambda x: _utc(x) if x else None
    sw, rf, bks = rec.get("sweep"), rec.get("refresh"), rec.get("backups") or []
    points = [t(sw["start"]), t(sw["end"])] if sw else []
    points += [t(rf["start"]), t(rf["end"])] if rf else []
    points += [p for b in bks for p in (t(b["start"]), t(b["end"]))]
    points = [p for p in points if p]
    rec["chain"] = {"start": _iso(min(points)), "end": _iso(max(points)), "minutes": _mins(min(points), max(points))} if points else None
    # Overlaps: two jobs on the live store at once. A backup wholly inside the refresh is the refresh's own.
    over = []
    if sw and rf:
        m = _overlap(t(sw["start"]), t(sw["end"]), t(rf["active_from"]), t(rf["end"]))
        if m >= 1:
            over.append({"a": "sweep", "b": "corpus refresh", "minutes": round(m, 1)})
    if rf:
        for b in bks:
            b0, b1, r0, r1 = t(b["start"]), t(b["end"]), t(rf["active_from"]), t(rf["end"])
            m = _overlap(b0, b1, r0, r1)
            inside = b0 and b1 and r0 and r1 and r0 <= b0 and b1 <= r1
            if m >= 1 and not inside and not (sw and t(sw["start"]) and t(sw["end"]) and b0 and t(sw["start"]) <= b0 <= t(sw["end"])):
                over.append({"a": "backup", "b": "corpus refresh", "minutes": round(m, 1)})
    rec["overlaps"] = over
    ok = [b for b in bks if b["result"] == "success" and b["chunks"] is not None]
    rec["chunks_added"] = (ok[-1]["chunks"] - ok[0]["chunks"]) if len(ok) >= 2 else None
    flags = []
    if not sw:
        flags.append("sweep did not run")
    elif sw["outcome"] not in SWEEP_FINE and (sw["outcome"] is not None or sw["error"]):
        flags.append(f"sweep {sw['outcome']}" + (f" ({sw['error']})" if sw["error"] else ""))
    if not rf:
        flags.append("corpus refresh did not run")
    elif rf["outcome"] != "ok":
        flags.append("corpus refresh " + rf["outcome"])
    if rf and rf["lock_errors"]:
        flags.append(f"database is locked: {rf['lock_errors']}")
    if not bks:
        flags.append("no backup")
    flags += [f"backup {b['result']}" for b in bks if b["result"] != "success"]
    flags += [f"backup took {b['minutes']:.0f} min" for b in bks if b["minutes"] and b["minutes"] >= LONG_BACKUP_MIN]
    flags += [f"{o['a']} and {o['b']} overlapped {o['minutes']:.0f} min" for o in over]
    flags += [f"could not read {u}" for u in unreadable]
    rec["flags"] = flags
    return rec


def trend(rows, n=7):
    """Averages over the last n nights before the newest, and the newest beside them. Rows oldest first."""
    if not rows:
        return None
    last, prior = rows[-1], rows[-1 - n:-1]

    def backup_min(r):
        v = [b["minutes"] for b in (r.get("backups") or []) if b.get("minutes") and b["result"] == "success"]
        return max(v) if v else None

    def gib(r):
        v = [b["gib"] for b in (r.get("backups") or []) if b.get("gib")]
        return v[-1] if v else None

    def avg(f):
        v = [x for x in (f(r) for r in prior) if x is not None]
        return round(sum(v) / len(v), 1) if v else None

    chain = lambda r: (r.get("chain") or {}).get("minutes")
    clean = lambda r: not r.get("flags")
    return {"nights_before": len(prior),
            "longest_backup_minutes": {"last": backup_min(last), "average_before": avg(backup_min)},
            "store_gib": {"last": gib(last), "average_before": avg(gib)},
            "chain_minutes": {"last": chain(last), "average_before": avg(chain)},
            "chunks_added": {"last": last.get("chunks_added"), "average_before": avg(lambda r: r.get("chunks_added"))},
            "clean_nights_before": sum(1 for r in prior if clean(r)), "last_clean": clean(last)}


# ---- writing ------------------------------------------------------------------------------------

def _hm(iso):
    return _utc(iso).astimezone().strftime("%H:%M") if iso else "?"


def words(rec, tr=None):
    L = [f"# Nightly jobs, {rec['night']}", ""]
    L.append("**Clean night: nothing flagged.**" if not rec["flags"] else "**Flagged:** " + "; ".join(rec["flags"]) + ".")
    L += ["", "| Job | Started | Ended | Minutes | Result |", "|---|---|---|---:|---|"]
    sw, rf = rec.get("sweep"), rec.get("refresh")
    if sw:
        L.append(f"| Sweep | {_hm(sw['start'])} | {_hm(sw['end'])} | {sw['minutes']} | {sw['outcome']}; {sw['files_found']} found, {sw['files_copied']} copied, {'ingested' if sw['ingested'] else 'no ingest'} |")
    else:
        L.append("| Sweep | | | | no record |")
    if rf:
        ing = rf["ingest"]
        L.append(f"| Corpus refresh | {_hm(rf['start'])} | {_hm(rf['end'])} | {rf['minutes']} | {rf['outcome']}; waited {rf['waited_minutes'] if rf['waited_minutes'] is not None else 'n/a'} min"
                 + (f"; {ing['ingested']:,} files, {ing['chunks']:,} chunks" if ing and ing.get("chunks") is not None else "") + " |")
    else:
        L.append("| Corpus refresh | | | | no record |")
    for b in rec.get("backups") or []:
        L.append(f"| Backup | {_hm(b['start'])} | {_hm(b['end'])} | {b['minutes']} | {b['result']}; copy {b['copy_minutes']}, restore test {b['restore_minutes']}; {b['gib']} GiB, {b['chunks']:,} chunks |"
                 if b["chunks"] is not None else f"| Backup | {_hm(b['start'])} | {_hm(b['end'])} | {b['minutes']} | {b['result']} |")
    bt = rec.get("backup_task")
    L += ["", f"- Backup task: {bt['wait_outcome']}, waited {bt['waited_minutes']} min for the earlier jobs." if bt else "- Backup task: no wait recorded (it ran on the old schedule, or did not run)."]
    ch = rec.get("chain")
    if ch:
        L.append(f"- Whole chain: {_hm(ch['start'])} to {_hm(ch['end'])}, {ch['minutes']} minutes.")
    if rec.get("chunks_added") is not None:
        L.append(f"- Chunks added between the first and last backup: {rec['chunks_added']:,}.")
    L.append("- Overlaps on the live store: " + ("none." if not rec["overlaps"] else "; ".join(f"{o['a']} with {o['b']}, {o['minutes']} min" for o in rec["overlaps"]) + "."))
    if tr and tr["nights_before"]:
        L += ["", f"## Against the {tr['nights_before']} nights before", "", "| | Last night | Average before |", "|---|---:|---:|"]
        for label, k in (("Longest backup, minutes", "longest_backup_minutes"), ("Store size, GiB", "store_gib"), ("Whole chain, minutes", "chain_minutes"), ("Chunks added", "chunks_added")):
            L.append(f"| {label} | {tr[k]['last'] if tr[k]['last'] is not None else 'n/a'} | {tr[k]['average_before'] if tr[k]['average_before'] is not None else 'n/a'} |")
        L.append(f"\nClean nights before: {tr['clean_nights_before']} of {tr['nights_before']}.")
    L += ["", "Read from the jobs' own logs. No model. A number here is a count or a time in a log."]
    return "\n".join(L) + "\n"


def save(rec, out=OUT):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    hist = out / "nightly.jsonl"
    rows = {}
    if hist.exists():
        for line in hist.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                rows[r["night"]] = r
            except (ValueError, KeyError):
                continue
    rec = dict(rec, generated_utc=_iso(datetime.now(timezone.utc)))
    rows[rec["night"]] = rec
    ordered = [rows[k] for k in sorted(rows)]
    tmp = hist.with_suffix(".part")
    tmp.write_text("".join(json.dumps(r) + "\n" for r in ordered), encoding="utf-8", newline="\n")
    os.replace(tmp, hist)
    upto = [r for r in ordered if r["night"] <= rec["night"]]
    tr = trend(upto)
    (out / f"nightly-{rec['night']}.md").write_text(words(rec, tr), encoding="utf-8", newline="\n")
    if ordered[-1]["night"] == rec["night"]:
        tmp = out / "latest.part"
        tmp.write_text(json.dumps({"latest": rec, "trend": tr, "nights_on_record": len(ordered)}, indent=1), encoding="utf-8", newline="\n")
        os.replace(tmp, out / "latest.json")
    return rec, tr


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--night", help="YYYY-MM-DD (the local date the jobs ran on); default today")
    ap.add_argument("--backfill", type=int, help="report this many nights ending with --night")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    night = date.fromisoformat(a.night) if a.night else date.today()
    nights = [night - timedelta(days=i) for i in range((a.backfill or 1) - 1, -1, -1)]
    for n in nights:
        rec, tr = save(build(n), a.out)
        print(f"{rec['night']}: {'clean' if not rec['flags'] else '; '.join(rec['flags'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
