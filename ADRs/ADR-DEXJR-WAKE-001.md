# ADR-DEXJR-WAKE-001 — dex-wake: on-demand service start, and its credential

**Status:** Accepted — built and tested 2026-08-01. **Not yet persistent.**
**Author:** Silas Reeve (DDL-3004) · design locked with Ellis Cooper (DDL-4008)
and Marcus Caldwell (Seat 1002) for the Operator
**Service:** `dex-wake.py`, port **8789**

---

## Decision

A small service whose only job is starting *other* services on demand, so the
things that should not be always-on can still be reached from a phone.

**Start and status. No stop.** Status is read-only and is what is actually
wanted remotely; stop degrades security posture from a distance and can be done
at the machine.

This is the counterpart to the persistence lane, not a replacement for it.
Persistence answers *what should survive a reboot automatically*. This answers
*what should be startable on demand precisely because it should not be
resident* — anything that contends the GPU, mainly.

## Ports

`8765` ddl-intel · `8787` dex-search-api · `8788` Dex Jr. mobile ·
**`8789` this** · `8791` dex-chat · `8792` ddl-voice · `8801` cockpit ·
`11434` Ollama

---

## The credential decision, and what it does not protect against

**This service is the counterexample to every other service here.** The others
fail closed: no credential, no start. `dex-openai-api` exits rather than run
unauthenticated, even on localhost, and that is correct.

dex-wake cannot work that way. It must be running *before* anything else, on a
machine that just rebooted, with nobody logged in. Its credential has to survive
a bare reboot unattended — which is the one place "fails closed" and
"auto-starts with no human present" pull directly against each other.

**Chosen: store a SHA-256 hash of the token in an ACL-restricted file. Never the
token.** The service verifies a presented credential; it holds nothing usable.

Considered and rejected:

| option | why not |
|---|---|
| Machine-scoped env var | survives reboot, but the plaintext token is readable by anything running as that user, and it leaks into child process environments |
| Credential Manager / DPAPI | stronger at rest, but more moving parts and it fails in ways that are hard to diagnose at 2am on a rebooted machine |
| ACL'd file containing the token | the ACL is doing all the work, and a single read yields a replayable credential |

**Why the hash is better than any of those:** reading the file yields something
that cannot be replayed. To gain access an attacker must *overwrite* the hash —
which breaks the Operator's phone and is therefore **noisy**. Plaintext
disclosure would be silent and permanent. This converts a silent compromise into
a loud one.

**What it does NOT protect against — stated plainly:**

> **Anyone with local admin on Reborn can overwrite that file and mint their own
> access.** The ACL is the real boundary and local admin sits above it. This
> does not defend against a compromised machine. It defends against credential
> disclosure at rest, and it makes tampering detectable rather than silent.

Perfect is not available here. That is the residual risk, named rather than
papered over.

**Plain SHA-256 rather than a KDF** is deliberate: the token is 40 chars of
high-entropy random, not a human password. There is no dictionary to slow down,
so a KDF would add cost without adding resistance.

**ACL caveat — SETTLED 2026-08-03, it was an explicit grant.**

Originally recorded as unverified: `icacls /inheritance:r /grant:r SYSTEM:F
<user>:R` was applied, but the listing surfaced only `SYSTEM:(F)`, leaving it
unclear whether read worked by grant or by owner-implicit access.

Re-measured by Ellis Cooper (DDL-4008): `icacls` now returns **both**
`REBORN\dkitc:(R)` and `NT AUTHORITY\SYSTEM:(F)`. The original listing does not
reproduce. The file was also read directly as `dkitc` — 64 characters, valid
lowercase hex. **It is an explicit grant, not owner-implicit read.**

**And the ACL turns out to be load-bearing for a decision it was not written to
make.** Because inheritance is removed, the local user `dexjr` and
`BUILTIN\Administrators` have *no* access at all. A persistence mechanism
running as `dexjr` would `sys.exit` at startup, unable to read its own
credential. That eliminated `dexjr` as the task principal on evidence rather
than on preference.

Credential path, for the record: `C:\Users\dexjr\.config\ddl\wake-token.sha256`,
matching `dex-wake.py:43`. Noted here because a dispatch stated the `dkitc`
path, which does not exist.

---

## The allowlist is source, not data

**In-process constants. Never loaded from disk.** This was Ellis Cooper's catch
and it is the load-bearing control: if the service-to-command map lived in a
config file, **write access to that file would be write access to what this
service executes** — a privilege-escalation path that routes around the API
entirely. An attacker who could not reach the endpoint could still edit the
config.

The client sends a **name**. The argv is fixed in source. Nothing from a request
ever reaches a command line: no arguments, no interpolation, no shell.

## dex-wake is not in its own allowlist

Caldwell's constraint, and neither Ellis nor I had reasoned it through: if the
service could restart itself, a compromised call could bring it back with
different behavior — a full escape. It is excluded in the constants, asserted at
import (`assert SELF_NAME not in ALLOWLIST`), rejected at the endpoint with 403,
and reported as `startable: false` in status.

**The thing that starts everything is the one thing it cannot start.** Restarting
dex-wake belongs to the persistence layer.

## Liveness: managed PIDs, not port polling

A rogue process can bind a port and fake liveness, so the two signals are kept
separate and labelled:

- `managed_by_wake` — **authoritative.** We started it and its `Popen` is alive.
- `port_listening` — **corroborating only**, carrying a note saying so.

Observed working during testing: `campaign-cockpit` correctly reported
`managed=False, port_listening=True` — running, but not started by us.

The PID map is **in memory on purpose**. A PID file survives a restart, but PIDs
are reused, so a stale file can point at an unrelated process. Losing the map is
the safer failure: status then honestly reports "not managed by me."

## The GPU gate is advisory, and says so

Below 1200MB free, a GPU-touching service is not started. **This is not a lock.**
Two rapid starts can both pass the check before either allocates. It reduces
accidental contention; it does not prevent a race, and the response says
`"note": "advisory check, not a lock"` so its existence cannot be mistaken for a
guarantee.

## Other hardening

- **401s are rate-limited** — 8 failures per 60s, then 429.
- **`access_log=False`** so bearer tokens cannot land in uvicorn's log.
- **`/healthz` is unauthenticated but says nothing** about what is running —
  posture is not disclosed to an anonymous caller. Status requires auth for
  exactly that reason.
- **Errors do not reflect input** — an unknown service name is not echoed back.
- **Binds `127.0.0.1` by default**; `--tailnet` is explicit. Tailscale
  reachability remains **unverified inference** and is not the security model.

---

## Verified by execution, 2026-08-01

| test | result |
|---|---|
| `/healthz` unauthenticated | 200, liveness only, no posture |
| status without auth | **401** |
| start without auth | **401** |
| non-allowlisted name (`cmd.exe`) with valid auth | **404, refused** |
| **start `dex-wake` itself** with valid auth | **403, refused** |
| authorized start of an allowlisted service | started, pid returned |
| before/after status diff | **differed on exactly the started service** |

That last row is the proof the test executed. A byte-identical pass and healthy
run means the test never ran — which happened once already this week.

## Consequences

**Gained:** services that should not be resident can be reached anyway. One
service must survive reboot instead of six.

**Accepted:** this is the highest-privilege surface on the machine. It starts
processes. The mitigations are the allowlist, the fixed argv, the
self-exclusion, and auth — not the network.

**NOT DONE — requirement 3 is unmet.** The dispatch requires surviving *an
actual reboot*, verified, not merely configured. **dex-wake is not yet
persistent and has not been rebooted through.** It needs the persistence layer
(Ellis, DDL-4008) and then a real reboot test. Until then it must be started by
hand, which means the ferry gap is closed only while someone is at the machine —
i.e. **not yet closed at all** for its actual use case.

Claiming otherwise would be exactly the failure this service was built during.

### Persistence status, 2026-08-03 (Ellis Cooper, DDL-4008)

Moved from *undesigned* to *designed, validated, and one elevated command away
from being testable*. It did NOT move to persistent, and **nothing is
registered** — verified independently: no task file was written to
`System32\Tasks`, and no `DexWake-Persistent` task exists.

**Registration is blocked by privilege, not design.** The session runs as
`REBORN\dkitc` with a filtered token — Administrators deny-only, Medium
integrity. Registration failed under both the `ScheduledTasks` module and
`schtasks.exe`, including a trivial control that should have succeeded.

So **two steps remain, not one**: an elevated import, then a reboot.

Design, for the record: task `DexWake-Persistent`, principal dkitc **by SID**,
`LogonType S4U`, LeastPrivilege. SYSTEM was rejected deliberately — a process
launcher at maximum privilege would hand SYSTEM to every service it starts, and
SYSTEM cannot see dkitc's user environment. `ExecutionTimeLimit PT0S` because
the 3-day default would silently kill a long-lived service on day three.

Artifacts: `dex-wake-task.xml`, `verify-dex-wake-persistence.ps1`,
`DEXWAKE-PERSISTENCE-RUNBOOK.md`. **These are a proposal. Registering boot
persistence is a security-posture change and requires explicit Operator
authorization of the mechanism — not merely of the lane.**

**Largest unproven risk:** S4U logon for `dkitc` is untested and `dkitc` is a
MicrosoftAccount; S4U paired with an MSA is known-flaky. The runbook therefore
puts a `schtasks /Run` smoke test *before* the reboot, so that risk surfaces
without committing to a restart.

The verifier's decisive check is **Session 0**, since that is what actually
proves "nobody logged in", plus a boot-proximity check — without it a manual
`schtasks /Run` would satisfy "ran after boot" and produce a false PASS. That
false-PASS path was found and closed by testing the verifier against a
hand-started instance.

### Port 8788 has a SECOND blocker that persistence does not fix

`DEXJR_API_TOKEN` is unset in Process, User, **and** Machine scope — confirmed
independently. `dex-openai-api` declares it in `env_required`, so an authorized
start returns **503**, not a running service.

Persistence alone will not light up the mobile endpoint. And as configured
dex-wake binds `127.0.0.1`, so the phone still could not reach it; that
one-line change is a posture decision documented in the runbook, deliberately
not taken unilaterally.
