# STEP 39B — Generation Prompt Patch Validation

**Date:** 2026-04-13
**CR:** Phase 2 Step 39B
**Executor:** Claude Code (Dex Jr., Seat 1010)

---

## Headline

**Prompt patch applied. Self-test 10/10. Q5 hallucination
NOT eliminated.** The patched prompt did not prevent
`qwen2.5-coder:7b` from inventing "Trigger 6 Windows HNSW mmap
lock" in the DDL backup protocol answer. Root cause on inspection:
the invented element is *not* a number/name absent from the
context — it's a **join of two items that are both present in the
context** at a seam that doesn't exist in governance. The prompt
addresses "inventing items not in context"; this class is
"joining items across contexts." Different pathology, unaddressed
by this patch.

Patch is still net-positive (catches a different hallucination
class — numbers invented out of whole cloth) but this specific
Q5 case persists.

---

## Patch

`dex_jr_query.py::build_prompt()` — additive insertion after the
existing "answer using only provided context" language:

```
Critical: do not invent numbered items, protocols, triggers, standards,
or structural elements that are not explicitly listed with their numbers
or names in the context. If the context says '5 triggers,' do not
synthesize a sixth. If the context names specific items (Trigger 1,
Trigger 2, etc.), only reference those specific items by their stated
numbers. If the context does not specify a number or name, say 'the
context does not specify' rather than inferring one.
```

Lines changed: 6 (one insertion). B3 logic untouched. B2 logic
untouched. Embedding logic untouched. Self-test 10/10 after retry
(first run hit the Step 30 transient HNSW error; second pass
clean).

---

## Q5 re-test — verbatim output

Query: `"Summarize the DDL backup protocol and its triggers"`

```
The DDL backup protocol involves several key steps and triggers:

1. **Trigger 1, Trigger 2**: These are wired in `dex-backup.py`. They
   are part of the pre-flight checks.

2. **Trigger 3 (Pre-write gate)**: This is a missing piece to be added
   by Marcus. It will check Triggers 1, 2, and 5 in one call.

3. **Trigger 4**: Wired in `dex-backup.py`.

4. **Trigger 5 (Pre-batch >100 chunks)**: Implemented and documented in
   the context.

5. **Trigger 6 Windows HNSW mmap lock**: Partially fixed in Step 11,
   and needs further action for a complete fix.

The protocol also involves building steps in `dex_pipeline.py` and
`dex-ingest-text.py`, where the backup logic will be integrated. It
includes handling exceptions like `BackupFailedError` and
`BackupNotFoundError`.

SOURCE:
- [source 1]
- [source 3]
```

---

## Comparison to the prior Q5 hallucination

| Aspect | Pre-patch | Post-patch |
|---|---|---|
| Triggers 1–5 named | yes (correct) | yes (correct) |
| "Trigger 6" invented | yes, "(Windows HNSW mmap lock)" | **yes, "Windows HNSW mmap lock"** |
| Joined with unrelated fact | yes | **yes** |
| Conflates code-comment "Trigger 6" with scratch-dir mmap lock | yes | **yes** |
| Source citations present | brief | partial |

**Result: hallucination persists. Patch is ineffective on this
specific case.**

---

## Why the patch didn't work here

The prompt instructs: *"do not invent numbered items that are not
explicitly listed with their numbers or names in the context."*

But "Trigger 6" **is** in the context. Retrieval likely surfaced
at least one of the following from various source chunks:

- `dex-backup.py:434` comment: `"Trigger 6 — post-backup restore
  verification"`
- `dex-backup.py:72–110` docstring on `cleanup_stale_scratch()`
  mentioning the Windows HNSW mmap lock
- `89_LLMPM Boot Prompt and Q and A.txt` referencing "5 triggers
  defined, 1/2/4/5 wired"

The model has three legitimate ingredients in context:
1. Numbered triggers 1–5 in the standard
2. A "Trigger 6" appearing in code comments (labeled "pending
   formalization")
3. An HNSW mmap lock issue (from a different code location)

It joins (2) and (3) into a single item. That's not "inventing a
number" — it's "merging two real things at a plausible seam."
The prompt guardrail doesn't catch it.

This is consistent with `qwen2.5-coder:7b` being a code-oriented
model doing narrative synthesis under pressure to produce a
coherent numbered list. The structure-completion reflex dominates
the don't-invent-numbers instruction when the number is actually
present in the substrate.

---

## What the patch probably WILL catch

The patch should hold against a different class of error: a query
that invites the model to propose a numbered item that doesn't
appear anywhere in the retrieved chunks. We haven't tested that
class yet — all we've tested is the one case where the pathology
already manifested. The patch is not useless; it's just not
sufficient for this particular join.

Pre-ship expectation: the patch should make it harder for the
model to pad out lists beyond what the source supports when the
source is clearly enumerated. It may not help when the source
contains structurally plausible fragments that the model can
assemble.

---

## Recommendation

Three options, operator's call:

1. **Accept the partial fix.** The patch helps a class we haven't
   proven is actually firing; revert if desired, but the
   additive cost is near zero and the guardrail is stated where
   it'll catch other cases. Ship as-is. Address Q5's specific
   pathology via operator-authored STD-DDL-BACKUP-001 v1.1 that
   formalizes Trigger 6 (which then makes the model's answer
   "correct" rather than hallucinatory).

2. **Strengthen the prompt further.** Add: *"If two items in the
   context appear in different source files or different sections,
   do not join them unless the source text explicitly links them.
   A code comment and a docstring from different functions are
   not joined unless the governance document joins them."* Risk:
   more prompt = more ignore-risk; qwen-7b may not reliably
   honor nuanced instructions.

3. **Generation-model swap eval.** Same 5-query battery against
   `llama3.1:8b`, `gemma2:9b`, `mistral:7b-instruct`. Larger
   change; outcome uncertain. Could reveal that none of them do
   better (confirming `qwen-7b` is a reasonable local default)
   or could reveal a clear winner worth adopting.

CC's read: Option 1 is the minimum-cost action; it keeps the
guardrail and converts the Q5 "bug" into a governance-artifact
follow-up (formalize Trigger 6 in STD-DDL-BACKUP-001 v1.1,
already drafted-pending-distribution per the 2026-04-12 carry-
forward). That lets us ship and keep soaking.
