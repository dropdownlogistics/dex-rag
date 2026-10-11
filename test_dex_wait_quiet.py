"""dex_wait_quiet: it waits while an earlier job runs, never counts itself, gives up loudly, and an unknown is not a pass.

Silas Reeve / DDL-3004 / 2026-10-11
"""
import dex_wait_quiet as wq

SWEEP = (100, "python.exe", r"C:\Python312\python.exe dex-sweep.py")
REFRESH = (200, "cmd.exe", r"cmd /c C:\Users\dexjr\dex\scripts\corpus_refresh.cmd")
OTHER = (300, "explorer.exe", r"C:\Windows\explorer.exe")
SELF = (999, "python.exe", r"python.exe dex_wait_quiet.py --not dex-sweep.py corpus_refresh.cmd")        # names the words in its own arguments
LOOK = (998, "powershell.exe", "powershell.exe -NoProfile -Command Get-CimInstance Win32_Process | ... dex-sweep.py")
SHELL = (997, "bash.exe", "bash.exe -c 'cmd /c corpus_refresh.cmd; tail corpus-refresh.log'")                 # what blocked my first dry run
EDITOR = (996, "notepad.exe", r"notepad.exe C:\Users\dexjr\dex\scripts\corpus_refresh.cmd")


def run(lists, words=("dex-sweep.py", "corpus_refresh.cmd"), max_minutes=240, me=frozenset({999})):
    it = iter(lists)
    last = [None]

    def lp():
        try:
            last[0] = next(it)
        except StopIteration:
            pass
        if isinstance(last[0], Exception):
            raise last[0]
        return last[0]

    t = [0.0]
    lines = []
    code = wq.wait(list(words), max_minutes=max_minutes, every=30, list_processes=lp, sleep=lambda s: t.__setitem__(0, t[0] + s),
                   clock=lambda: t[0], log=lines.append, me=set(me))
    return code, t[0], lines


def test_quiet_at_once_when_nothing_named_is_running():
    code, waited, lines = run([[OTHER, SELF, LOOK, SHELL, EDITOR]])
    assert (code, waited) == (0, 0.0) and "quiet after 0.0 min" in lines[-1]


def test_it_never_counts_itself_its_own_look_or_its_parent():
    assert wq.busy([SELF, LOOK, (7, "cmd.exe", "cmd /c corpus_refresh.cmd")], ["dex-sweep.py", "corpus_refresh.cmd"], me={7}) == []
    assert wq.busy([(5, "Python.EXE", "python DEX-SWEEP.PY")], ["dex-sweep.py"], me=set()) == [(5, "dex-sweep.py")]      # case does not matter


def test_only_a_python_or_cmd_process_is_a_job_a_shell_or_an_editor_naming_the_script_is_not():
    words = ["dex-sweep.py", "corpus_refresh.cmd"]
    assert wq.busy([SHELL, EDITOR], words, me=set()) == []
    assert wq.busy([SHELL, EDITOR, REFRESH], words, me=set()) == [(200, "corpus_refresh.cmd")]


def test_it_waits_for_the_sweep_then_the_refresh_then_runs():
    code, waited, lines = run([[SWEEP, REFRESH], [SWEEP, REFRESH], [REFRESH], [REFRESH], [OTHER]])
    assert code == 0 and waited == 120.0
    said = [l.split("wait_quiet: ")[1] for l in lines]
    assert said == ["waiting for corpus_refresh.cmd, dex-sweep.py", "waiting for corpus_refresh.cmd", "quiet after 2.0 min (watched: dex-sweep.py, corpus_refresh.cmd)"]


def test_it_gives_up_after_the_limit_and_says_do_not_run():
    code, waited, lines = run([[SWEEP]], max_minutes=2)
    assert code == 7 and waited == 120.0 and "still busy after 2 min (dex-sweep.py); not running" in lines[-1]


def test_a_process_list_that_cannot_be_read_is_not_a_pass():
    code, _, lines = run([RuntimeError("boom")])
    assert code == 8 and "cannot read the process list" in lines[-1]
    code, _, _ = run([[SWEEP], RuntimeError("boom")])            # it had been waiting; a failed look still does not let the job run
    assert code == 8


def test_the_real_process_list_can_be_read_and_names_this_test():
    procs = wq.processes()
    assert len(procs) > 5 and all(isinstance(p, int) and n and c for p, n, c in procs)
    assert any(n.lower() == "python.exe" for _, n, _ in procs)                 # this test is one
