# dex-wake persistence — operator runbook

**For:** the Operator (or anyone else). You do not need to have read anything
else. Follow the steps in order.
**Author:** Ellis Cooper (DDL-4008), 2026-08-03. Companion to ADR-DEXJR-WAKE-001.

**What this does:** makes `dex-wake` (port 8789) start automatically when Reborn
boots, with nobody logged in, so it is reachable without someone being at the
machine.

**Current state:** the task definition is written and validated, but it is
**NOT registered yet**. Registering it needs Administrator rights, which the
agent that prepared this did not have. That is Step 1.

---

## Step 1 — register the task (one time, needs Administrator)

Open **PowerShell as Administrator** (right-click → Run as administrator), then
paste this exactly:

```powershell
schtasks /Create /TN "DexWake-Persistent" /XML "C:\Users\dexjr\dex-rag\dex-wake-task.xml" /F
```

**PASS looks like:**

```
SUCCESS: The scheduled task "DexWake-Persistent" has successfully been created.
```

**FAIL looks like:** anything containing `ERROR:`. Most likely causes:
- `Access is denied.` → the window is not actually elevated. Reopen as Administrator.
- `The task XML is malformed` → the XML file was edited or corrupted. Stop and report.

---

## Step 2 — smoke-test it BEFORE rebooting (still Administrator)

This proves the account/logon configuration works. It is the single most
useful check available before a reboot, because it is the part most likely to
fail. Paste:

```powershell
schtasks /Run /TN "DexWake-Persistent"
Start-Sleep -Seconds 12
powershell -File "C:\Users\dexjr\dex-rag\verify-dex-wake-persistence.ps1"
```

**What you want to see:** the row
`listener runs in SESSION 0 (no interactive user)` showing **PASS**.

That row passing means the service can run with no user logged on. If it says
`1` instead of `0`, or the task reports a logon failure, **stop and report it** —
the S4U logon type is not working for this account and the principal in
`dex-wake-task.xml` needs changing.

> The overall VERDICT in this step may still say FAIL on the
> `started CLOSE TO boot` row. **That is expected here** — you started it by
> hand, not by booting. This step is only about the SESSION 0 row.

Then stop it again so the reboot test is clean:

```powershell
schtasks /End /TN "DexWake-Persistent"
```

---

## Step 3 — reboot

Reboot Reborn whenever convenient. **Do not log in for at least 90 seconds**
after it comes back up, so the boot trigger (which fires 30 seconds after boot)
runs with genuinely nobody logged on.

---

## Step 4 — verify (this is the real test)

After logging back in, open PowerShell **as Administrator** and paste:

```powershell
powershell -File "C:\Users\dexjr\dex-rag\verify-dex-wake-persistence.ps1"
```

> Run it elevated. Unelevated, two rows may report `UNKNOWN` instead of a result,
> and the verdict will be INCOMPLETE rather than PASS.

### Reading the result

The last lines print one of exactly three verdicts:

| Verdict | Meaning | What to do |
|---|---|---|
| `VERDICT: PASS` | dex-wake came back by itself, with no user logged in. **The requirement is met.** | Nothing. Report PASS. |
| `VERDICT: INCOMPLETE` | Nothing failed, but some checks could not be read. | Re-run as Administrator. |
| `VERDICT: FAIL` | dex-wake did not come back correctly. | See below. |

### The rows that actually matter

- **`listener runs in SESSION 0 (no interactive user)`** — this is the whole
  point. Session 0 means it started with nobody logged on. Any other number
  means something started it *after* a human logged in, which does not meet the
  requirement even if everything else looks healthy.
- **`listener started CLOSE TO boot`** — proves it started because of the boot
  trigger, not because someone ran it later.
- **`CONTROL can detect a down service`** — must be PASS. If this ever says
  FAIL, the script itself is broken and **no other row on the table can be
  trusted**.

### If it says FAIL

Look here first:

```powershell
Get-Content C:\Users\dexjr\dex-rag\dex-wake.boot.log -Tail 40
Get-ScheduledTaskInfo -TaskName DexWake-Persistent
```

The log is appended to on every start. Note that it also contains entries from
pre-reboot testing on 2026-08-03; a marker line separates those from anything
that happens after.

---

## Optional — enabling phone reachability

**As configured, dex-wake binds `127.0.0.1` only.** It is running, but it is
**not reachable from your phone.** That was left as the Operator's decision
rather than made automatically, because exposing a service that starts other
processes on all interfaces, unattended, at boot, is a security posture change.

To enable it: edit `C:\Users\dexjr\dex-rag\dex-wake-task.xml`, find the
`<Arguments>` line, and add ` --tailnet` immediately after `dex-wake.py"`.
Then re-run Step 1 to re-register, and reboot.

Read the "What it does NOT protect against" section of ADR-DEXJR-WAKE-001
before doing this.

---

## Rollback

To remove persistence entirely (elevated):

```powershell
schtasks /End /TN "DexWake-Persistent"
schtasks /Delete /TN "DexWake-Persistent" /F
```

This removes only the scheduled task. It does not touch `dex-wake.py`, the
credential hash, or any corpus data.
