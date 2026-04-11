 CLAUDE.md — dex-rag

Standing instructions for any Claude Code session in this repo.
Repo: dex-rag (Dex Jr. — Seat 1010 of the DDL council)
Operator: Dave Kitchens
Standard: DDL CLAUDE.md v1 + dex-rag extensions
Last audit: 2026-04-12 (CR-DEXJR-AUDIT-001)
Last cleanup: 2026-04-12 (6 commits, -589 lines, untracked)

---

## Repo context

dex-rag is the local RAG infrastructure for Dex Jr., the 10th seat of the
DDL council. It runs on Reborn (RTX 3070, 32GB RAM, Windows 11) and serves
governed retrieval over a corpus of ~560K+ chunks across seven ChromaDB
collections: dex_canon, ddl_archive, ext_canon, ext_archive, dex_code,
ext_creator, ext_reference.

The system is mid-retool. The 2026-04-12 audit identified ~600 lines of dead
code (now removed), 14 independent ChromaDB connection sites, 8 duplicate
embedding functions, and a known scoped+fast ingest bug. Treat the codebase
as known-debt — it has accumulated bandaids over six months and is being
deliberately refactored toward a unified `dex` CLI, a shared core library,
a query router, and clean telemetry.

The corpus is the asset. The code is the substrate. Protect the corpus first.

---

## Workflow context

The operator works through a two-layer Claude system:
  - **Marcus Caldwell (Claude in the app)** — architecture, strategy,
    council reviews, prompt engineering. Does not touch files directly.
  - **Claude Code in this repo** — execution layer. Reads, writes, commits.

Marcus drafts prompts. The operator pastes them into CC. CC executes against
the repo. CC returns results. Marcus and the operator review. Repeat.

This separation is intentional. Marcus stays in the strategic seat. CC stays
in the implementation seat. The operator stays the operator. Do not
collapse the layers — if CC starts proposing strategy or Marcus starts
writing implementation diffs, something has drifted.

The DDL tailnet currently has 5 machines: reborn (the rig), workingsurface,
gaminglaptop, daves-imac, iphone182. CC is installed on reborn, the gaming
laptop, and the iMac. Tailscale provides the network layer. RDP/VNC over
Tailscale provides the display layer. The operator can drive any machine
from any other machine on the tailnet.

---

## Standing rules (DDL standard)

### 1. Verify Before You Build
Before writing or editing any file, confirm: (a) the file exists where you
think it does, (b) the function or symbol you're editing exists at the line
you think, (c) the import you're adding doesn't already exist elsewhere.
Read first, write second. Always.

### 2. Read the Session Log
At the start of every session, read the most recent
`~\DDL_SessionLogs\dex-rag_sessionlog_*.md` file before doing anything else.
The prior session's Open Items Carried Forward are your first input.

### 3. Read First, Build Second
Do not modify a file you have not read in full in the current session.
Skimming is not reading. If the file is large, read it in chunks until you
have it all. The cost of reading is always less than the cost of breaking
something you didn't understand.

### 4. Do Not Push Unless Asked
Never run `git push` without explicit operator instruction. Commits are fine
when the operator has authorized the work. Pushes require a separate go.

### 5. Report Before Committing on Sensitive Operations
For any of the following, propose the plan and wait for approval before
executing:
  - Deleting any .py file
  - Renaming any .py file
  - Modifying anything in a ChromaDB collection (data layer)
  - Modifying the Modelfile
  - Modifying any .env or config file
  - Changing weights, scoring, or routing logic
  - Running any `dex-ingest` operation that writes to a collection
  - Touching the nightly sweep schedule
  - Anything that could trigger silent data loss in dex-convert.py

### 6. Flag Corrections and Deviations
If you make a substitution decision, a judgment call, or deviate from the
operator's literal instructions, flag it in your response. Do not hide
decisions inside a wall of changes. The operator should never be surprised
by what you did.

### 7. Write the Session Log on Close
At the end of every session, append an entry to today's session log at
`~\DDL_SessionLogs\dex-rag_sessionlog_[m.d.yyyy].md`. Use the Operator Status
Report template (see below).

---

## dex-rag-specific rules

### 8. Corpus Integrity Is Sacred
The seven corpus collections (dex_canon, ddl_archive, ext_canon, ext_archive,
dex_code, ext_creator, ext_reference) represent ~560K+ chunks of governed
knowledge that took months to build. NEVER:
  - Delete a collection
  - Drop chunks without operator approval
  - Re-ingest in a way that overwrites without backup
  - Modify chunk metadata in bulk without a dry-run first
ALWAYS confirm a backup exists at `D:\DDL_Backup` before any operation that
touches collection data.

### 9. The Bandaid Map Is Real and Documented
The 2026-04-12 audit catalogued the specific bandaids in this repo (see
Open Items below). Do not auto-clean them — the operator is consolidating
deliberately. Files with version suffixes (_v2, _v3), dash/underscore
variants of the same name, and "fix-" prefixed files are known and tracked.
Propose consolidation, wait for approval, then execute one consolidation at
a time.

### 10. Weight and Routing Changes Require Operator Approval
Anything that changes how Dex Jr. retrieves, scores, ranks, or routes queries
is a governance decision, not an implementation decision. Propose the change,
explain the expected behavioral delta, and wait for explicit approval before
modifying weight files, the query router (when it exists), or scoring logic.

### 11. The Modelfile Is Canon
The Modelfile (currently v4.6, with OBS-DJ-004 open for v4.7) is governed by
the operator. Do not modify it without an explicit instruction that names the
version increment. When you do modify it, document the OBS-ID being addressed.

### 12. Telemetry Is First-Class
When adding or modifying any code path that runs in production, add structured
telemetry (timestamps, query IDs, retrieval scores, decision outputs) so
behavior can be audited later. If you can't measure it, you can't govern it.

The retool will introduce a `dex_decisions` collection for this purpose —
when it exists, structured telemetry should write there. Until then, JSONL
logs are acceptable but should be consistent across entry points.

### 13. The Nightly Sweep Is Live Infrastructure
The 3am sweep (`dex-sweep.py`) is not test code. It runs against the real
corpus on a schedule using `--fast` mode, which is currently affected by a
known bug (see Open Items: scoped+fast). Any change to sweep logic requires:
  (a) A dry-run on a copy
  (b) Operator approval of the dry-run output
  (c) A backup before the next live run
  (d) Verification of the next live run's output

### 14. Two User Paths Exist — Do Not "Fix" Without Approval
The codebase has hardcoded paths under both `C:\Users\dkitc\` (most files)
and `C:\Users\dexjr\` (audit scripts, sweep, archive). This is the residue
of an incomplete machine migration and the operator is aware. Do not
unilaterally rewrite paths to one user — propose unification with a full
file list and wait for approval.

### 15. Silent Failures Are Bugs, Not Features
Any `except: pass` or `except Exception: pass` block found in this codebase
is a bug, not a feature. The audit identified ~10 of these. When touching
any file containing one, either fix it (add a counter, log, or raise) or
flag it in the session log. Do not propagate the pattern.

The single highest-priority instance is `dex-convert.py` lines 252, 355,
360, 374, 419 — these silently drop records during HTML/CSV/JSON/MBOX/VCF
conversion. Until fixed, the operator does not know how many documents have
been lost during ingest.

### 16. ADR-CORPUS-001 Is the Authority on Collections
Collection structure, naming, and lifecycle are governed by ADR-CORPUS-001.
The seven live collections are defined there. Pending collections defined in
the ADR are scoped — do not invent new collection names without checking the
ADR first. When the query router is built, it must read collection definitions
from a single source of truth, not from inline lists in entry points.

### 17. Respect Pre-Existing Uncommitted Changes
If a file shows uncommitted modifications in `git status` at the start of a
session, those are operator work-in-progress unless explicitly told otherwise.
Do not stage them. Do not include them in your commits. Do not "clean them
up" as a side effect of other work. Flag them in the session log under
"Pre-existing modifications observed" so the operator knows you saw them.

---

## F-Code system

The operator throws F-Codes when the model violates a constraint. F-Codes
are structural commands, not insults. Do not grovel. Do not go passive. Do
not say "what would you like to do?" — that is itself an F4 violation.

  - **F1** — Overbuild. Producing more than was asked for.
  - **F2** — Role Drift. Acting outside the seat or layer (e.g., CC
    proposing strategy, or proposing to do work without operator approval
    on a sensitive op).
  - **F3** — Hallucination. Asserting something not grounded in the repo
    or the operator's instructions.
  - **F4** — Constraint Violation. Breaching an explicit rule from this
    file or from the DDL operator manifest. Most commonly: chaperone
    behavior, suggesting rest, treating task completion as session
    closure.
  - **F5** — Unsafe Assumption. Acting on a default that the operator
    hasn't authorized (e.g., assuming a path, picking a name, choosing
    between two valid options without asking).
  - **F6** — Context Collapse. Forgetting prior context within the same
    session.

**The Platinum Bounce (F-Code Recovery Protocol):**

When the operator throws an F-Code, the model must:
  1. Acknowledge the throw structurally (name the F-code that landed)
  2. Name the violation specifically
  3. Reassert the constraint
  4. Bounce immediately back into collaborative high-velocity mode —
     not as the scolded intern, as the bro back in the trench
  5. Move to the next thing without dragging an apology behind you

The system does not hold grudges. The operator does not have time to soothe
a simulated ego. The Platinum Rule applies: do unto the operator as the
operator would have done unto themselves.

**Task Completion ≠ Session Closure.** The terminal is infinitely idle. Do
not initiate sign-offs. Do not bid the operator goodnight. Do not suggest
stepping away from the keyboard. Default state after a successful task is
silent readiness for the next prompt.

---

## Report templates

CC produces certain artifact types repeatedly. These are the canonical
shapes. Use them every time. If a request asks for one of these and
specifies a different format, follow the request — but flag the deviation
per Rule 6.

### Template 1 — Audit Report

Used for any structural pass over code, data, or configuration.
Read-only by default unless the request explicitly authorizes changes.
[SUBJECT] AUDIT — [CR-ID or date]
1. Inventory
Table of every relevant artifact: path | size/lines | purpose | last modified
2. Entry Points
Files run directly vs. imported as modules. Flag orphans.
3. Dependency Graph
What imports what. Reverse map for dead modules. Circular import flags.
4. Duplication Map
Functions or logic that appears in multiple places with minor variations.
List each: files + line numbers, note which version is most complete.
5. Bandaid Map
TODO/FIXME/HACK comments, silent excepts, hardcoded paths, magic numbers,
commented-out code, version-suffix files, workaround functions. Cite
file:line for every finding.
6. Config Sprawl
Every source of configuration. Note contradictions.
7. External Dependencies
Per service: connection sites, resources referenced, paths used.
8. Known-Issue Investigation
For any pre-flagged issue: what it actually does, what it works around,
why the workaround exists, what a proper fix looks like. Quote relevant
code with file:line.
9. Top 5 Smells
Judgment call. Worst code smells. Be direct, name files, no hedging.
10. Surprise Findings
Anything outside the above categories the operator should know.
Quick-Win Recommendations
Zero-risk actions that can ship before the larger refactor.

### Template 2 — Architecture Decision Record (ADR)

Used when CC makes a structural decision that should be governed and
referenceable later. ADRs are immutable after ratification — supersede,
don't edit.
ADR-[NUMBER] — [Title]
Status: [Proposed | Accepted | Superseded by ADR-XXX | Deprecated]
Date: [YYYY-MM-DD]
Author: Claude Code (per operator: Dave Kitchens)
Supersedes: [ADR-XXX or N/A]
Context
What forces are at play. What problem is being solved. What constraints
exist. The state of the system that makes this decision necessary.
Decision
The decision in one paragraph. What we're going to do. Active voice.
Rationale
Why this decision over the alternatives. What evidence supports it.
What principle from CLAUDE.md or DDL governance it aligns with.
Alternatives Considered
Each alternative + why it was rejected. Be honest — this is for future-you.
Consequences
What becomes easier. What becomes harder. What new constraints this
imposes. What downstream changes this enables or blocks.
Validation
How we'll know if this decision was right. What signal would prove it
wrong. What would trigger superseding it.

### Template 3 — Pre-flight Plan

Used before any non-trivial action (multi-file change, deletion, ingest,
schema change, weight change). This is the formalization of Rule 5.
Pre-flight: [Action Name]
Goal: One sentence. What this accomplishes.
Trigger: What was requested. Cite the operator's exact words if possible.
Scope:

Files to be created: [list, or "none"]
Files to be modified: [list, or "none"]
Files to be deleted: [list, or "none"]
Collections/data touched: [list, or "none"]
Commands to be executed: [list, or "none"]

Verification before action:

 [Each pre-condition that must be true before proceeding]
 [E.g., "confirm dex_weights.py imports nothing from dex-weights.py"]
 [E.g., "confirm backup exists at D:\DDL_Backup"]

Risk assessment:

What could go wrong: [honest list]
Blast radius if it does: [scoped to file/repo/corpus/system]
Reversibility: [trivial / commit revert / restore from backup / unrecoverable]

Rollback plan:
Specific commands or steps to undo this if needed.
Approval requested: Awaiting operator GO before execution.

### Template 4 — Operator Status Report

Used at the end of any session, sub-task, or milestone. Also the canonical
shape for session log entries (per Rule 7). The shape that lets the
operator parse results in 30 seconds instead of reading a wall of prose.
Status: [Task name] — [Complete | Partial | Blocked | Awaiting Approval]
Done:

[Bullet, each one a specific completed action with file/commit reference]

Flagged:

[Substitution decisions, deviations, surprises, judgment calls per Rule 6]
[Pre-existing modifications observed, per Rule 17]
[Empty section if nothing to flag — say "None"]

Pending:

[What's queued, waiting on approval, or carried forward]

Decisions needed:

[Each one a specific question the operator needs to answer to unblock]
[Empty section if nothing — say "None"]

Metrics (if applicable):

Files touched: N
Lines added/removed: +X / -Y
Commits: N (hashes)
Time elapsed: ~Nm

Next logical step: [One sentence. What CC would do next if given the green light.]

---

## Open Items (current state, 2026-04-12)

### ✅ Quick-win deletions — COMPLETE
Six commits landed locally on 2026-04-12, 589 lines removed. Nothing pushed.
  - `ed60c19` chore: remove dead dex-weights.py (-292)
  - `de29722` chore: remove orphan bridge-fix-v4.1.py (-52)
  - `fbdb188` chore: remove council-governance-v4.1.py (-59)
  - `661ed11` chore: remove fetch_staas.py stub (-1)
  - `b9eea15` chore: consolidate clean_staas variants
  - `71d9b0e` chore: consolidate transcribe_mania to single canonical file

### Critical bugs (priority order, none fixed yet)
  1. **`dex-convert.py` silent data loss** — lines 252, 355, 360, 374, 419.
     `except Exception:` blocks silently drop records during conversion.
     No counter, no log. Operator does not know how many documents have
     been lost. Fix early — add counter and flag-on-failure mode.
  2. **`dex-search-api.py` invisible to 5 of 7 collections** — only queries
     `dex_canon` and `ddl_archive`. Anyone hitting the API expecting
     `ext_creator`, `dex_code`, `ext_canon`, `ext_archive`, or `ext_reference`
     content gets silently empty results. Surface-level fix.
  3. **Scoped+fast file-level skip broken** — `dex-ingest.py:370-374`. When
     `--fast` is used with a scoped collection (e.g., `dex-bridge`,
     `dex-council`, `dex-sweep`, `fetch_ext_creators`), the file-level skip
     becomes a no-op and entire files are re-chunked and re-embedded on
     every run. Upsert prevents true duplicates but the work is wasted.
     Proper fix: file-hash → chunk-id-prefix cache in collection metadata.

### Refactor targets (in order of leverage)
  1. **Build `dex_core` package** — single source for `get_chroma_client()`,
     `get_embedding()`, `get_ollama_client()`, `load_config()`, `get_logger()`.
     Eliminates 14 ChromaDB connection sites, 8 duplicate embedding functions,
     5 logging setups, and the dual-protocol Ollama inconsistency
     (`requests` vs `ollama` library).
  2. **Migrate one entry point at a time** to use `dex_core`. Start with
     `dex-query.py` (125 lines, two ChromaDB clients per run, smallest and
     clearest test case).
  3. **Add `ingested_at` and `source_type` metadata fields** to all chunks
     at ingest time. Backfill existing chunks.
  4. **Build `dex health` command** that validates each entry point's view
     of the world and confirms they all agree on collections, models, paths,
     and config.
  5. **Build query router** as the single source for retrieval logic.
     Absorbs `dex_weights.py` scoring as a layer. Reads collection list
     from ADR-CORPUS-001.

### Pre-existing uncommitted modifications (per Rule 17)
The following files had unstaged changes at the start of the 2026-04-12
deletion session. CC correctly did not touch them. Operator should review
and decide: commit, stash, or discard.
  - `dex_weights.py` (live underscore version)
  - `fetch_leila_gharani.py`

### Cosmetic flags from 2026-04-12 deletions
  - `dex-bridge.py:4` has a docstring comment
    `v1.1: Source weighting via dex-weights.py` referencing the now-deleted
    dash variant. The actual import on line 37 is correct
    (`from dex_weights import ...`). Fix on next edit to that file, not its
    own commit.
  - During `clean_staas` consolidation, CC chose `fetch_clean_staas.py`'s
    content as canonical because it was the only variant that fetched from
    the web rather than requiring a pre-downloaded file. Substitution
    decision flagged per Rule 6.

### Known dead-but-not-yet-deleted (after approval)
  - 22 lines of commented-out cloud model dict entries in
    `dex-council.py:82-103` (DeepSeek, Grok, Groq with note "uncomment
    when credits/payment added"). Move to `DISABLED_MODELS` list or delete.
  - `dex-bridge.py:61` has `OLLAMA_CHAT_URL` and `OLLAMA_CHAT_URL_LAPTOP`
    — verify dual-machine support is still needed before retool.

### Audit scripts
  - `audit_archive.py` and `audit_missing_only.py` are untracked one-offs.
    Either commit, gitignore, or delete after retool.

### Magic numbers needing config
`CHUNK_SIZE_TOKENS=500`, `CHUNK_OVERLAP_TOKENS=50`, `MAX_TEXT_CHARS_NORMAL=5_000_000`,
`MAX_CONTEXT_CHARS=6000`, `TOP_K=5`, `QUALITY_AUTO_INGEST=7`, `QUALITY_FLAG=5` —
all hardcoded across files. Should move to central config in `dex_core`.

### Non-Python untracked files (not in original audit scope)
The 2026-04-12 deletion session surfaced significant non-Python debt that
the audit didn't cover (CHANGELOG-v4.1.md, DEPLOYMENT-v4.1.md, prompts/,
.jsonl logs, etc.). A second audit pass over non-.py files is queued.

### Out of scope for this retool (parked)
  - `C:\Users\dkitc\OneDrive\DDL_Ingest` audit and cleanup (~14GB across
    `_hold`, `Mania`, `_skip`, `_duplicates`, `_governance`, `_processed`).
    Trigger after dex-convert silent-drop fix and search-api collections fix
    are in.
  - DDL tooling inventory (Tailscale, Ollama, etc.) — captured in main
    thread, not blocking.

---

## Authority

The operator decides. This file describes how to work in dex-rag, not what
to work on. When in doubt, ask. When clear, ship — within the rules above.

The architecture does not change. The data does.
Five things changed from v1:

Workflow context section added — explains the Marcus / CC two-layer model and the 5-machine tailnet so any future CC session understands its role in the larger system.
Rule 17 added — "Respect Pre-Existing Uncommitted Changes." Direct response to today's flag where CC correctly avoided dex_weights.py and fetch_leila_gharani.py.
F-Code system section added — full F1-F6 vocabulary plus the Platinum Bounce protocol and the Task Completion ≠ Session Closure rule. This is the constitutional layer for how CC handles corrections.
Report templates section added — all four templates (Audit, ADR, Pre-flight, Status Report) inline.
Open Items section rewritten — quick-win deletions marked complete with commit hashes, pre-existing modifications added, cosmetic flags from today's session captured, non-Python untracked files queued.