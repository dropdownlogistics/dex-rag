# ADR-INGEST-EXCLUSIONS-001 — Fail-Closed Exclusion List for All Ingest

**Status:** Accepted — Operator ruling 2026-08-03, filed via Marcus Caldwell (Seat 1002)
**Date:** 2026-08-03
**Author:** Silas Reeve (DDL-3004), reborn-cowork
**Supersedes:** N/A
**Closes:** ADR-INGEST-PIPELINE-001 pending decision **#5** (sensitive content handling)
**Related:** STD-CORPUS-003 (canon), ADR-DEXJR-WAKE-001 (fail-closed precedent),
ADR-INGEST-PIPELINE-001 (the pipeline this gates)

---

## Context

Two filesystem roots became the corpus source of record on 2026-08-02. Phased
read-only audits of both surfaced ~86 files of employment-litigation exhibits,
payroll records, and mental-health material naming identifiable third parties.

That material had **already been sequestered by the Operator** into a folder
named `16_personal_legal` before either audit ran. It was still raised as an
open question, for two reasons that are the actual subject of this ADR:

1. **The ruling lived in conversation and folder naming.** A pipeline reads
   neither. A builder who had not been in the room could only infer it.
2. **The folder sat inside the ingest source tree.** Excluding it depended on
   every future walker remembering to skip it.

The second point is the one with teeth. The preceding week produced nine
defects, and the common shape was a control that depended on someone
remembering rather than something failing loudly. Two of them were *silent
passes* — a test that reported success without executing, and a blocked hook
that reported PASS because `cmd | tail` returns tail's exit status.

An exclusion policy enforced by memory is the same shape. It works until the
one time it doesn't, and that time is silent.

**The additional hazard specific to this corpus:** roughly 6,400 of the files
are AI chat exports. A credential pasted into a conversation is invisible to
every filename-based check. A content scan is therefore a separate, mandatory
gate — this ADR governs *what must never be walked*, not *what must be scanned*.

---

## Decision

**Every ingest path into a DDL corpus loads an exclusion list before doing
anything else, and exits non-zero if that list is missing, unreadable,
malformed, or empty.**

`sys.exit(2)`. Not a warning, not a skip, not an empty default.

An absent exclusion list is **not** permission to ingest everything. It is
indistinguishable from a list that failed to load, and the pipeline cannot tell
those apart from the inside. When the two cases cannot be distinguished, the
safe one is the only one available.

Reference implementation: `dex_exclusions.py`, schema in
`ingest-exclusions.example.json`, 38 tests in `test_dex_exclusions.py`.

---

## Rationale

### Why fail-closed rather than warn-and-continue

This is the same reasoning as ADR-DEXJR-WAKE-001's credential handling, applied
to a different resource, and it comes down to which failure is recoverable.

- **Refusing to run when the list is fine** costs a confused operator and one
  minute. Loud, immediate, obvious.
- **Running when the list is absent** ingests sequestered material into a
  searchable index that is then exposed on a phone endpoint. Silent, and by the
  time anyone notices, the embeddings are built and the retraction is a rebuild.

The asymmetry is total, so the choice is not close.

### Why the list is local and gitignored

The paths themselves disclose what was set aside. A committed exclusion list
naming `16_personal_legal` publishes the existence and location of exactly the
material it protects. This follows the roster precedent established with Ellis
Cooper (DDL-4008): **schema in the repo, values on the machine.**

### Why three overlapping rule kinds

| kind | matches | why it exists |
|---|---|---|
| `exclude_paths` | absolute path and everything beneath | the precise, current answer |
| `exclude_dir_names` | a bare directory name at **any** depth | **survives relocation** |
| `exclude_filename_patterns` | glob on basename | categories, e.g. `*.mbox`, `*.har` |

The overlap is deliberate. The sequestered directory is caught by both its
absolute path *and* its name, so a copy, a restore, or a move does not silently
re-admit it. Verified: a path under the **old** `16_personal_legal` location —
which no longer exists — is still excluded by the name rule.

Redundancy is the correct instinct where the cost of a miss is unrecoverable and
the cost of a redundant rule is nothing.

### Why the digest is over the canonical rule set, not the file bytes

Reformatting the JSON or reordering an array must **not** change the digest.
Adding, removing, or moving a rule between kinds **must**.

The digest identifies the **policy in force**, which is what a collection needs
to record. A byte hash would churn on whitespace and train readers to ignore it —
and a signal people ignore is not a signal.

### Why `reason()` returns an explanation, not a boolean

A file that vanishes from a corpus with no recorded cause is indistinguishable
from a file the walker simply missed. That ambiguity is how the 181
missing-on-disk files became a mystery requiring a recovery investigation. An
exclusion should be **legible as an exclusion.**

### Why an env override exists at all

The failure paths must be testable, and a control whose failure modes cannot be
exercised is a control nobody has verified. The override cannot weaken anything:
any file it points at still has to satisfy every check, and the digest of what
was *actually* loaded is printed at load and recorded in the stamp. A swapped
list is therefore visible **in the artifact**, not only in someone's shell
history.

---

## Alternatives considered

**1. Document the rule in a README.** Rejected. This is what already existed —
a correctly-named folder and a shared understanding. It is precisely what
failed, and it failed by producing a question rather than an answer.

**2. Warn and continue on a missing list.** Rejected. A warning in a pipeline
that emits thousands of lines is not observed. The one run where it matters is
the run nobody is watching.

**3. Default to an empty exclusion list.** Rejected, and this is the most
dangerous option because it looks the most reasonable. "No exclusions
configured" and "exclusions failed to load" produce identical behavior and
opposite intent.

**4. Commit the real list so it cannot go missing.** Rejected — the paths
disclose the sequestered material. The fail-closed check addresses the
"goes missing" risk without publishing anything.

**5. Deny-list by content classification instead of paths.** Rejected as the
*primary* mechanism: classification is probabilistic and this material is
categorically out. Content scanning remains a mandatory separate gate for
secrets in prose, where paths cannot help.

---

## Consequences

### Easier

- Sequestered material cannot be ingested by a walker that forgot about it.
- Every collection records which exclusion policy built it.
- Relocating or copying sequestered material does not re-admit it.
- Pending decision #5 of ADR-INGEST-PIPELINE-001 is closed rather than deferred.

### Harder

- Every ingest entry point must be wired to `load_exclusions()`. Not yet done —
  see Adoption below. Until wired, this ADR governs nothing in those paths.
- A machine without the local list cannot ingest until one is placed. Intended.
- New machines need a provisioning step for `ingest-exclusions.json`.

### Imposes

- The stamp gains two fields: `exclusion_digest` and the source-identity key.
- `dex-sweep.py`, `dex-ingest.py`, and any future ingest path inherit a
  hard dependency that fails the run rather than degrading it.

---

## Adoption status — stated plainly

| item | status |
|---|---|
| `dex_exclusions.py` + example schema + gitignore | **done** |
| 38 tests, all refusal paths in real subprocesses | **done, passing** |
| Sequestered material moved out of the source root | **done** — 86 files, verified 86/86 |
| Local exclusion list in force | **done** — 23 rules, digest `439ab23e…` |
| STD-CORPUS-003 filed in canon | **done** |
| **`dex-ingest.py` wired to `load_exclusions()`** | **NOT DONE** |
| **`dex-sweep.py` wired to `load_exclusions()`** | **NOT DONE** |
| Stamp carrying `exclusion_digest` | **NOT DONE** — build has not started |

**The last three are the ones that matter operationally.** The control exists
and is tested; it is not yet in the path of the live sweep. Wiring them touches
live ingest infrastructure and is gated on CLAUDE.md Rule 5 (sensitive
operations: anything writing to a collection, and the nightly sweep).

Claiming this ADR is in force today would be exactly the failure it was written
during. It is in force for the new build, which has not started.

---

## Validation

**Right if:** an ingest attempt on a machine without the list refuses to start;
a collection's stamp lets a reader determine which exclusion set built it; a
relocated copy of sequestered material stays excluded.

**Wrong if:** operators start setting `DDL_INGEST_EXCLUSIONS` to a stub to get
past the check — that would mean the refusal is obstructing legitimate work and
the provisioning path is too hard, not that the control is wrong. Fix
provisioning, not the gate.

**Superseded when:** exclusion policy needs per-collection scoping, which this
deliberately does not support. One list, all corpora, no exceptions.

---

**End of ADR-INGEST-EXCLUSIONS-001**
