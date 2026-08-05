# FINDING — Hydration run, 2026-08-05

**Outcome: the corpus source is materialized. Hydration is durable. No data was lost.**

Recorded by Silas Reeve (DDL-3004). Every number below was measured, and two
of my own claims are corrected in it.

---

## What happened

| | |
|---|---:|
| files read | **7,619** |
| failures | **0** |
| wall time | **52 min** |
| still local afterwards | **5,272** |
| re-evicted by the provider | **0** |
| gone (accounted, below) | 2,407 |

Verification is performed by `dex-ledger.py`, a different tool with its own
constants and its own tests, per AB-0029 — the executor is not permitted to
certify itself. Final state: **7,680 files, zero classifier disagreement.**

## The deletion was correct and is not a defect

`DirectIngestCopy_6.29.26` (3,215 files, ~7 GB) was removed by the Operator on
Reed's recommendation, mid-run, during an ongoing reorganization of the real
DirectIngest folder.

**That was the right call.** The folder was 76.9% duplicate of `05_DirectIngest`
by (name, size) and held the 6.39 GB mailbox already excluded by ruling.
Deleting it made the corpus smaller and cleaner. It accounts for 2,403 of the
2,407 missing files exactly.

Recording it as an operator error would put a wrong fact in the record. The
sequencing is the finding, and sequencing is nobody's fault:

> **A build cannot read a source while that source is being reorganized.**
> Not because either activity is wrong — because a manifest is a snapshot, and
> a snapshot of a moving tree is stale the moment it is taken.

Ellis's third option — *consolidate off cloud-sync first, the only one that
makes the source stable* — was filed as the slowest. It is now the only one
that composes with an org that is actively curating its own material.

**And the ledger is the only reason any of this was visible.** Without it the
rebuild would have ingested whatever happened to be present at that moment and
passed every count check it had.

## TWO CLAIMS OF MINE, CORRECTED

### 1. "Files I hydrated are being re-evicted." — WRONG

I reported 1,984 placeholders reappearing in DexUniverse and 463 in
DirectIngest, and read it as the provider clawing back what I had pulled.

Measured against the run journal: **0 re-evicted, both roots.** Every file
journalled as read is either still local or was in the deleted folder.

The placeholders I counted were **whole-root** counts — PNG, PDF, XLSX, MP4 —
the 3,151 files deliberately never hydrated because no converter can read them.
I compared a whole-root population against a manifest-scoped operation and
read the difference as a regression.

### 2. "The missing files were renamed." — WRONG

Diagnosing the first 31 vanished files, I used `difflib` to find near-matches
and it paired `AssetArt.txt` with `llms.txt.txt`. Every filename in that
directory shares a long `DDLCouncilReview_` prefix, so a fuzzy matcher returns
high-confidence nonsense. The files were simply gone.

## THE METHODOLOGICAL FINDING — three instances, one shape

Both corrections above, plus a third from earlier the same day, are the same
error:

| # | claim | actual | the mismatch |
|---|---|---|---|
| 1 | `ddl_archive_v2` has an empty index | index fine; **wrong collection sampled** | took the first collection that answered — a legacy unsuffixed store |
| 2 | 31 files were renamed | they were deleted | fuzzy-matched names sharing a long common prefix |
| 3 | hydrated files are being re-evicted | zero re-eviction | whole-root counts vs a manifest-scoped run |

**Every one was a measurement taken over the wrong population.** Not a bad
instrument, not a bad reading — the right instrument answering a question about
a different set than the one the claim was about.

This is adjacent to AB-0029 but distinct from it. AB-0029 says the environment
that built a thing is a poor judge of it. This says something narrower and, on
tonight's evidence, more frequent:

> **A measurement is only as good as the population it was taken over.**
> "I measured it" is not a defence. The question is always *measured over what,
> and is that the same set the claim is about?*

All three were caught, and all three by the same move: checking which set the
number actually described before believing it. None were caught by review.

**Not proposed as an AB.** Three instances in one operator-day, all mine, in one
domain, is one author's blind spot rather than an organisational pattern. If it
recurs in another seat's work it earns the entry, with this table attached.

## Also fixed here

The first verified run reported 40 classifier disagreements. All 40 were
**zero-byte files**, which `dex-ledger.py` classifies as `empty` — a distinct
and correct disposition. `dex-hydrate.py` counted only `materialized` as local,
so a correct classification registered as a conflict.

Neither classifier was wrong. **The comparator was.** The disagreement
mechanism did exactly its job: it refused to certify, sent someone looking, and
what turned up was a defect in the checker rather than in either thing checked.

## State now

- Corpus source materialized: **5,272 manifest files local, 0 pending transfer**
- Manifest is **stale by 2,407 files** and must be regenerated from a fresh
  `dex-ledger.py` walk before it is used as a build input
- Remaining root placeholders are non-ingestible by design (PNG/PDF/XLSX/MP4)
  and were correctly never fetched
- The reorganization is ongoing; the source is not stable, and that is a
  sequencing question for the Operator, not a defect to fix

---

*Silas Reeve / DDL-3004 / reborn-cowork / 2026-08-05*
