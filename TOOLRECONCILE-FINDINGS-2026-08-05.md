# dex-toolreconcile.py — the missing reconciler, and what it found on the first run

**Ellis Cooper / DDL-4008** · 2026-08-05 · `.ddl-worker-scratch/ellis-001/dex-toolreconcile.py`

---

## The gap it fills

`dex-reconcile.py` holds every declaration about the **corpus** at once and
makes them argue. Its docstring explains why it had to exist:

> "The information needed to notice was spread across a canon folder, a config
> module, a CLAUDE.md, and a live database, and no single reader ever held all
> four at once. **This tool holds all four at once.**"

There was no equivalent for **tooling**, and the cost showed up tonight.

On 2026-07-24 I built `leakscan.py` and wrote two admissions into its README:

> *"No real roster loaded — pluggable; the real decoy roster plugs in later."*
> *"necessary, not sufficient — the mechanical floor under human review, which
> remains the other half of the gate."*

A missing plug and a named empty slot. Both honest. Both went nowhere.

On 2026-08-05 I built `ddl-leakscan.py` against a Drive spec and it filled the
second slot; `ddl-gate.py` then filled the first. **Two halves of one gate,
built a fortnight apart, by the same worker, neither aware of the other.**

Nobody was careless. A README, a spec in Drive, and two scratch directories,
and no single reader ever held all of it at once.

## What it measures

| finding | what it means |
|---|---|
| `DIVERGENT_COPY` | same document in two places, drifted apart |
| `DECLARED_GAP` | a tool admits, in its own words, that something is missing |
| `UNVERIFIED` | declares its own standing EXPERIMENTAL / REVIEW REQUIRED |
| `ORPHAN` | nothing else references it by name |
| `DANGLING_REF` | opt-in, see below |

Same rule as `dex-reconcile.py`: **it declares no inventory.** No list of what
should exist, no expected versions. It knows where to look and what a
declaration looks like. Every finding is a `file:line` you can open.

## First run — 260 files

**One divergent copy**, and it is real:
`ddl_drive_pipeline.py` — 80% shared content between scratch and
`ddl-org/reborn-cowork/work/ELLIS-001/`, not identical. That is the file I had
already flagged to Silas by hand as stale against `fbaeec6`. **The tool found
independently what I found manually**, which is the validation that matters.

**243 declared gaps across 81 files**, median 2 per file. Readable, not a wall.

The register puts the motivating case together on one screen:

```
--- work/leak-scanner/README.md
    L102  [deferred plug]  No real roster loaded — pluggable; the real decoy
                           roster plugs in later.
    L61   [out of scope]   catch an entity not on the roster (roster
                           completeness is a separate, human problem)
    L14   [other half]     is the other half of the gate

--- ellis-001/ddl-gate.py          <- fills the first
--- ellis-001/ddl-leakscan.py      <- fills the second
```

Gap and filler, adjacent, in one list. That adjacency is the entire product.

## Two times it cried wolf, and what I did about each

**Divergent copies — fixed with a real discriminator.** The first cut matched on
filename alone and reported 6 sets, including `README.md` across 15 project
folders. Those are fifteen correctly-different documents. Flagging them buries
the one finding that matters.

`leakscan.py`'s own README had already stated the stakes: *"a scanner that cries
wolf gets ignored, and an ignored scanner is worse than none."* My own prior
warning, applying to my new tool, twelve days later.

Fixed by requiring **content similarity**, not just a shared name: same document
drifted apart (≥40% shared substantial lines, not identical) rather than
siblings following a naming convention. Measured: the two `ddl_drive_pipeline.py`
copies share 80%; the fifteen `README.md` files share ~0–5% with each other.
**15 false positives → 0. One true positive.**

**Dangling references — demoted, because I could not fix it.** 471 hits across
128 files, and spot-checking showed most are not defects:

- docstring examples — `x.py`, `fileA.txt`, `alpha.md`, `test.txt`
- runtime artifacts that do not exist until something runs — `manifest.json`,
  `beacon.json`, `_backup_log.jsonl`
- **correct historical citations** — session logs referencing `dex-query.py`,
  deliberately deleted in Step 50.3. The log is right; the file is supposed to
  be gone.

Telling those from a genuinely stale pointer requires knowing whether a document
describes the present or the past, and I have no reliable signal for that. So
it is behind `--dangling`, off by default, excluded from the exit code, with
the reasoning left in the source.

**Deleting the check would hide that it was tried and found wanting.** Leaving
it on would drown the register it sits beside. Demoting it is the honest third
option.

## The honest limit, which mirrors the tool that inspired it

`leakscan.py` cannot catch an entity that is not on its roster.

**This cannot catch a gap nobody wrote down.** It harvests gaps stated in
recognisable form — a section header, a known phrase. A gap phrased unusually,
or never phrased at all, is invisible.

So a clean register means *"no tool admitted to a gap in words I recognise."*
It does not mean there are none. Stated plainly rather than implied, because
that distinction is the one this whole day kept turning on.

It also does not match gaps to their fillers. That is a semantic judgement and
this tool makes none — it puts them in one list so a human sees them at the
same time. That was the thing that was missing.

## Known artifact

`dex-toolreconcile.py` appears in its own register with ~12 gaps, because its
docstring quotes the phrases it searches for. Some of those are genuine
self-declared limits; some are pattern definitions matching themselves. Not
special-cased — special-casing the tool's own output is how a reconciler starts
lying about itself.

## Deliberately not done

- **No gap→filler matching.** Semantic, and this tool does not do semantics.
- **No enforcement.** No hook, no CI gate. A register is for reading.
- **No cross-repo git awareness.** It reads the filesystem, not history. Two
  clones of one repo are not divergence and are correctly ignored, but only
  because their content is identical, not because it understands git.

---

*Ellis does not commit. Silas's to review and land.*
