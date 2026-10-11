"""
dex_wait_quiet.py -- wait until none of the named jobs is running, so the nightly jobs run one after another.

FND-0034, 2026-10-11. The 04:00 sweep, the 04:40 corpus refresh and the 05:30 backup were set by the
clock when a backup took 14 minutes. It takes an hour now, so the refresh wrote to the live store while
the sweep's backup was copying it, the sweep's re-check counted the store while the refresh was writing
it, and the backup task then locked the store under the refresh's last step. Operator, 2026-10-11:
"three jobs in a row is fine with me. The machine isn't doing anything else especially at that hour."

Each later job now starts with this: it waits while a Python or cmd process's command line contains one
of the given words (the earlier jobs' script names), then exits 0 and the job runs. Only python*.exe
and cmd.exe count, because those are what run the jobs. An editor with the script open, or a shell
whose command merely mentions the name, is not the job: my own first dry run waited on the shell that
launched it, which named the script in its command. The clock times stay as they
are; they are now "not before" times.

    python dex_wait_quiet.py --not dex-sweep.py                       (the corpus refresh)
    python dex_wait_quiet.py --not dex-sweep.py corpus_refresh.cmd    (the backup task)

Exit 0: quiet (says how long it waited). Exit 7: still busy after --max-minutes (the job should NOT
run: a job that has run for hours needs a person, not a second job on top of it). Exit 8: the process
list could not be read (also do not run; an unknown is not a pass).
It never stops, signals or touches another process. It only looks.
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime

# No quotes in the command on purpose: it is passed as one argument and quoting does not survive that intact.
PS = "Get-CimInstance Win32_Process | ForEach-Object { [string]$_.ProcessId + [char]9 + $_.Name + [char]9 + $_.CommandLine }"
RUNNERS = ("python.exe", "pythonw.exe", "py.exe", "cmd.exe")


def processes():
    """[(pid, image name, command line)] for every process whose command line this account can read. Raises on failure."""
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", PS],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"process list failed: exit {r.returncode}")
    out = []
    for line in r.stdout.splitlines():
        pid, _, rest = line.partition("\t")
        name, _, cmd = rest.partition("\t")
        if pid.strip().isdigit() and cmd.strip():
            out.append((int(pid), name.strip(), cmd))
    if not out:
        raise RuntimeError("process list was empty")
    return out


def busy(procs, words, me):
    """The (pid, word) pairs that are running, leaving out this process and anything launched to look."""
    hits = []
    for pid, name, cmd in procs:
        if pid in me or name.lower() not in RUNNERS or "dex_wait_quiet.py" in cmd:
            continue
        low = cmd.lower()
        for w in words:
            if w.lower() in low:
                hits.append((pid, w))
                break
    return hits


def wait(words, max_minutes=240, every=30, list_processes=processes, sleep=time.sleep, clock=time.time, log=print, me=None):
    me = me if me is not None else {os.getpid(), os.getppid()}
    start = clock()
    said = None
    while True:
        try:
            hits = busy(list_processes(), words, me)
        except Exception as e:                                   # an unknown is not a pass
            log(f"{datetime.now().isoformat(timespec='seconds')} wait_quiet: cannot read the process list ({type(e).__name__}); not running")
            return 8
        waited = clock() - start
        if not hits:
            log(f"{datetime.now().isoformat(timespec='seconds')} wait_quiet: quiet after {waited / 60:.1f} min (watched: {', '.join(words)})")
            return 0
        names = sorted({w for _, w in hits})
        if names != said:
            log(f"{datetime.now().isoformat(timespec='seconds')} wait_quiet: waiting for {', '.join(names)}")
            said = names
        if waited >= max_minutes * 60:
            log(f"{datetime.now().isoformat(timespec='seconds')} wait_quiet: still busy after {waited / 60:.0f} min ({', '.join(names)}); not running")
            return 7
        sleep(every)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--not", dest="words", nargs="+", required=True, help="words to look for in other processes' command lines")
    ap.add_argument("--max-minutes", type=float, default=240)
    ap.add_argument("--every", type=float, default=30, help="seconds between looks")
    a = ap.parse_args()
    return wait(a.words, a.max_minutes, a.every, log=lambda s: print(s, flush=True))


if __name__ == "__main__":
    sys.exit(main())
