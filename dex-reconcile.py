#!/usr/bin/env python3
"""
dex-reconcile.py -- make the corpus's declarations argue with reality, out loud.

THE DEFECT THIS EXISTS FOR
--------------------------
STD-CORPUS-001 mandates `nomic-embed-text` at 768 dimensions, "No exceptions."
The live corpus is `mxbai-embed-large` at 1024. It has been for months. Every
builder who touched the code quietly did the right thing and nobody reconciled
the standard, so canon has been describing a system that does not exist -- and
the wrong figure propagated into a dispatch whose entire purpose was
establishing ground truth.

Nobody was careless. The information needed to notice was spread across a canon
folder, a config module, a CLAUDE.md, and a live database, and no single reader
ever held all four at once.

This tool holds all four at once.

THE ONE RULE THAT MAKES IT WORK
-------------------------------
**This tool declares nothing.** It contains no expected values -- no model name,
no dimension, no chunk count, no collection list. It knows only WHERE to look
and HOW to measure.

That is not stylistic. A reconciler with a hardcoded expectation becomes the
seventh disagreeing declaration, and then it is part of the problem it was
written to detect. Every value in the output is either read from a cited
file:line or measured from the live system at call time.

Same principle as dex-state.py, which proved it on ports. This finishes the job
for the corpus.

VERDICTS
--------
  AGREE        every declaration matches, and matches measurement
  CONFLICT     declarations disagree with EACH OTHER
  REFUTED      a declaration is contradicted by MEASUREMENT  <- the bad one
  UNMEASURABLE declared, but nothing here can measure it (stated, not dropped)
  UNDECLARED   measured, but nothing declares it

  python dex-reconcile.py           # full report
  python dex-reconcile.py --json    # machine-readable
  python dex-reconcile.py --quiet   # only problems

Exit: 0 everything reconciles - 1 a CONFLICT or REFUTED was found

Read-only. Opens ChromaDB for counts and one stored vector. Writes nothing,
ingests nothing, modifies no collection.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# WHERE declarations live. NOT what they say.
# ---------------------------------------------------------------------------
# Adding a source here is how this tool grows. Adding an expected VALUE here is
# how it breaks -- if you ever feel the urge to write `"expected": 1024`, that
# is the bug this file exists to prevent.
CANON = Path(r"C:\Users\dexjr\ddl-canon")
DEXRAG = Path(r"C:\Users\dexjr\dex-rag")
DDLINTEL = Path(r"C:\Users\dexjr\ddl-intel")


@dataclass(frozen=True)
class Source:
    """A place a fact is written down, and how to lift it out."""
    fact: str
    path: Path
    pattern: str            # regex, group(1) is the value
    note: str = ""
    normalize: str = "str"  # str | int


SOURCES: list[Source] = [
    # ---- embedding model -------------------------------------------------
    Source("embedding_model", DEXRAG / "dex_core.py",
           r"^EMBED_MODEL\s*=\s*os\.environ\.get\([^,]+,\s*[\"']([^\"']+)[\"']",
           "the value the code actually uses"),
    Source("embedding_model", CANON / "standards" / "STD-CORPUS-001.md",
           r"scoped collections use\s+([a-z0-9\-]+)",
           "canon, marked 'No exceptions'"),
    Source("embedding_model", CANON / "standards" / "STD-CORPUS-001.md",
           r"embedding_model\s*\|\s*Must match dex_canon \(([a-z0-9\-]+)",
           "canon, collection-properties table"),
    Source("embedding_model", DDLINTEL / "intel_core.py",
           r"EMBED_MODEL\s*=\s*[\"']([^\"']+)[\"']",
           "ddl-intel's own declaration"),

    # ---- embedding dimensions -------------------------------------------
    Source("embedding_dimensions", CANON / "standards" / "STD-CORPUS-001.md",
           r"\((\d+)\s*dimensions\)", "canon", normalize="int"),

    # ---- gated collections ----------------------------------------------
    Source("gated_collections", DEXRAG / "dex_core.py",
           r"^GATED_COLLECTIONS\s*=\s*\[([^\]]*)\]",
           "the only place this is declared"),

    # ---- collection suffix ----------------------------------------------
    Source("collection_suffix", DEXRAG / "dex_core.py",
           r"^COLLECTION_SUFFIX\s*=\s*os\.environ\.get\([^,]+,\s*[\"']([^\"']*)[\"']",
           "in force until the rename ceremony"),
]

# Per-collection chunk floors are declared as a dict; parsed separately because
# a floor is a claim about a RANGE, not an equality. A count below its floor is
# a real finding; a count above it is expected growth.
CHUNK_FLOOR_SOURCE = Source(
    "chunk_floors", DEXRAG / "dex_core.py",
    r"CHUNK_FLOORS\s*=\s*\{(.*?)\}", "post-rebuild floors, 2026-04-17")


@dataclass
class Declaration:
    value: object
    path: str
    line: int
    note: str

    @property
    def where(self) -> str:
        try:
            rel = os.path.relpath(self.path, r"C:\Users\dexjr")
        except ValueError:
            rel = self.path
        # line 0 means the value is declared by ABSENCE -- the constant is not
        # in the file. Rendering ":0" would imply a line that does not exist.
        return f"{rel}:{self.line}" if self.line else f"{rel} (constant absent)"


@dataclass
class Row:
    fact: str
    declarations: list = field(default_factory=list)
    measured: object = None
    measurable: bool = True
    measure_note: str = ""
    verdict: str = ""
    detail: str = ""
    # Source accounting. Without this the tool can report AGREE for a fact
    # whose only disagreeing source failed to load -- see integrity_check().
    sources_expected: int = 0
    sources_read: int = 0
    sources_failed: list = field(default_factory=list)
    # Some rows reconcile one MEASUREMENT against another -- a live model
    # probe against a stored vector width, or several collections against each
    # other. That is a genuine comparison with no declaration involved, and a
    # naive evidence count (declarations + 1 for "measured") misreads it as a
    # single unverified data point. Rows that do this say how many independent
    # measurements they compared.
    measurement_comparisons: int = 0

    @property
    def coverage_complete(self) -> bool:
        return self.sources_expected == 0 or self.sources_read == self.sources_expected


def integrity_check(rows: list) -> None:
    """Force UNCHECKED on any fact whose evidence is incomplete.

    THE DEFECT THIS FIXES, found by auditing this tool against itself:

    `embedding_model` is declared once in dex_core and twice in canon. The
    verdict asked "how many DISTINCT values did I collect?" With canon
    unreadable, exactly one value is collected, and the tool reported
    AGREE -- "all sources say mxbai-embed-large".

    That reads as "canon and code agree". It actually meant "canon was never
    consulted". Measured: findings went 3 -> 0 and the night's most important
    finding vanished, with exit code 0.

    A tool built to detect false confirmations must not be able to produce one.

    Two rules, applied after every verdict is set:

      1. INCOMPLETE COVERAGE DOMINATES. If a source that should have been read
         could not be, the fact is UNCHECKED whatever the survivors say.
         "No disagreement found" and "could not compare" must never render
         the same way.

      2. ONE PIECE OF EVIDENCE IS NOT AGREEMENT. A single declaration with
         nothing to compare it against is SINGLE_SOURCE, not AGREE. Nothing
         was reconciled; there was only one opinion in the room.

    A CONFLICT or REFUTED verdict is never downgraded -- a disagreement found
    on partial evidence is still a real disagreement. Only agreement-shaped
    verdicts are suspect, because those are the ones that claim a comparison
    happened.
    """
    for r in rows:
        if r.verdict in ("CONFLICT", "REFUTED"):
            continue

        if not r.coverage_complete:
            missing = r.sources_expected - r.sources_read
            r.verdict = "UNCHECKED"
            r.detail = (f"{missing} of {r.sources_expected} declaration source(s) "
                        f"could not be read — this fact was NOT reconciled. "
                        + (f"Unread: {', '.join(r.sources_failed)}. " if r.sources_failed else "")
                        + "Surviving sources may agree only because the "
                          "disagreeing one is missing.")
            continue

        if r.verdict == "AGREE":
            evidence = (len(r.declarations)
                        + (1 if r.measured is not None else 0)
                        + max(0, r.measurement_comparisons - 1))
            if evidence < 2:
                r.verdict = "SINGLE_SOURCE"
                if r.declarations:
                    r.detail = (f"declared in exactly one place and not independently "
                                f"measured — nothing was compared. Value: "
                                f"{r.declarations[0].value!r}")
                elif r.measured is not None:
                    r.detail = ("measured once with nothing to compare against — "
                                "a lone reading, not a reconciliation")
                else:
                    r.detail = "no evidence at all"


# ---------------------------------------------------------------------------
# READ declarations
# ---------------------------------------------------------------------------
def read_declarations() -> tuple[dict[str, list[Declaration]], list[str], dict[str, dict]]:
    """Lift every declared value out of every source.

    Also returns per-fact COVERAGE: how many sources were expected, how many
    were actually read, and which failed. Without that accounting a fact whose
    disagreeing source vanished looks identical to one where every source
    agreed -- see integrity_check().
    """
    out: dict[str, list[Declaration]] = {}
    problems: list[str] = []
    coverage: dict[str, dict] = {}

    for src in SOURCES:
        cov = coverage.setdefault(src.fact, {"expected": 0, "read": 0, "failed": []})
        cov["expected"] += 1

        def fail(msg: str) -> None:
            problems.append(msg)
            cov["failed"].append(f"{src.path.name} ({src.note})" if src.note else src.path.name)

        if not src.path.exists():
            fail(f"declaration source missing: {src.path}")
            continue
        try:
            text = src.path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            fail(f"unreadable: {src.path}: {exc}")
            continue

        m = re.search(src.pattern, text, re.M)
        if not m:
            fail(
                f"pattern did not match in {src.path.name} for '{src.fact}' "
                f"-- the file may have been restructured; this tool's reader is stale"
            )
            continue

        cov["read"] += 1

        raw = m.group(1).strip()
        value: object = int(raw) if src.normalize == "int" else raw
        if src.fact == "gated_collections":
            value = sorted(v.strip().strip("\"'") for v in raw.split(",") if v.strip())

        line = text[: m.start()].count("\n") + 1
        out.setdefault(src.fact, []).append(
            Declaration(value, str(src.path), line, src.note))

    return out, problems, coverage


def read_chunk_floors() -> tuple[dict[str, int], str | None]:
    src = CHUNK_FLOOR_SOURCE
    if not src.path.exists():
        return {}, f"missing: {src.path}"
    text = src.path.read_text(encoding="utf-8", errors="replace")
    m = re.search(src.pattern, text, re.S)
    if not m:
        return {}, "CHUNK_FLOORS block not found"
    floors = {}
    for name, num in re.findall(r"[\"']([a-z_]+)[\"']\s*:\s*([\d_]+)", m.group(1)):
        floors[name] = int(num.replace("_", ""))
    return floors, None


# ---------------------------------------------------------------------------
# MEASURE reality
# ---------------------------------------------------------------------------
def measure_collections() -> tuple[dict[str, int] | None, str]:
    """Live collection names -> chunk counts. Read-only."""
    try:
        import chromadb
        sys.path.insert(0, str(DEXRAG))
        from dex_core import CHROMA_DIR
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        out = {}
        for col in client.list_collections():
            try:
                out[col.name] = col.count()
            except Exception as exc:  # noqa: BLE001
                out[col.name] = -1
                print(f"  note: count failed for {col.name}: {exc}", file=sys.stderr)
        return out, ""
    except Exception as exc:  # noqa: BLE001
        return None, f"ChromaDB unreachable: {exc}"


def measure_dimensions_per_collection() -> tuple[dict[str, int], dict[str, str]]:
    """Stored vector width for EVERY collection, individually.

    Returns (name -> dimension, name -> why-not-measured).

    Deliberately per-collection rather than one sampled answer. The first
    version of this function took the first collection that responded and
    called it "the corpus dimension" -- and promptly sampled a legacy
    unsuffixed collection, reporting a dead corpus's geometry as the live one.

    That is the same failure this whole tool exists to detect: a value that
    looked authoritative because something returned it. Measuring every
    collection separately makes the population visible instead of sampling it,
    and turns "which one did you look at?" into a question with an answer.

    Known hazard: get(include=["embeddings"]) throws on some collections (a
    characterized defect). A collection that cannot answer is recorded as
    unmeasured, never skipped silently.
    """
    dims: dict[str, int] = {}
    why: dict[str, str] = {}
    try:
        import chromadb
        sys.path.insert(0, str(DEXRAG))
        from dex_core import CHROMA_DIR
        client = chromadb.PersistentClient(path=CHROMA_DIR)
    except Exception as exc:  # noqa: BLE001
        return {}, {"*": f"ChromaDB unreachable: {exc}"}

    for col in client.list_collections():
        try:
            if col.count() == 0:
                why[col.name] = "empty"
                continue
            got = col.get(limit=1, include=["embeddings"])
            embs = got.get("embeddings")
            if embs is not None and len(embs) and embs[0] is not None:
                dims[col.name] = len(embs[0])
            else:
                why[col.name] = "no embedding returned"
        except Exception as exc:  # noqa: BLE001
            why[col.name] = f"{type(exc).__name__}"
    return dims, why


def measure_scheduled_tasks() -> tuple[dict, str]:
    """DDL scheduled tasks and whether they can actually run unattended.

    A task with a Daily trigger DECLARES that it runs daily. `LogonType:
    Interactive` MEASURES that it runs only while that user is logged on --
    it does not fire on a rebooted, logged-out machine.

    Found by hand 2026-08-04: all six DDL tasks are Interactive. The "nightly"
    4am sweep does not run if the machine reboots overnight. Nothing declared
    that, nothing contradicted it, and nothing would have surfaced it. The
    schedule and the capability live in different fields and no one had put
    them next to each other.
    """
    ps = (
        "Get-ScheduledTask | Where-Object { $_.TaskName -like 'Dex*' } | "
        "ForEach-Object { "
        "  $t=$_; "
        "  [pscustomobject]@{ "
        "    name=$t.TaskName; "
        "    logon=[string]$t.Principal.LogonType; "
        "    user=[string]$t.Principal.UserId; "
        "    state=[string]$t.State; "
        "    triggers=(($t.Triggers | ForEach-Object { $_.CimClass.CimClassName }) -join ',') "
        "  } } | ConvertTo-Json -Compress"
    )
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=90)
        if r.returncode != 0 or not r.stdout.strip():
            return {}, f"Get-ScheduledTask returned nothing (exit {r.returncode})"
        data = json.loads(r.stdout)
        if isinstance(data, dict):
            data = [data]
        return {d["name"]: d for d in data}, ""
    except Exception as exc:  # noqa: BLE001
        return {}, f"{type(exc).__name__}: {exc}"


def measure_index_self_retrieval(name: str, sample: int = 2) -> tuple[dict, str]:
    """Does a collection return ITS OWN documents when queried with their text?

    A document embedded and searched against the collection it came from must
    come back at ~0 distance. This is the only check that distinguishes
    "retrieval works" from "retrieval returns confident, well-ranked, wrong
    results" -- and it cannot be satisfied by a metadata fallback, because a
    metadata path cannot rank by vector similarity.

    Found by hand 2026-08-04: ddl_archive_v2 (316,109 chunks, the majority of
    the corpus) scored 0/6 with best distances 0.52-0.82, against a control
    collection scoring 0.0035-0.20. count() was correct, query() returned
    plausible hits, and every declared fact about it agreed. Nothing short of
    asking it for its own documents would have found it.
    """
    try:
        import chromadb
        sys.path.insert(0, str(DEXRAG))
        from dex_core import CHROMA_DIR, embed
        col = chromadb.PersistentClient(path=CHROMA_DIR).get_collection(name)
        n = col.count()
        if n == 0:
            return {}, "collection is empty"
        got = col.get(limit=sample * 3, include=["documents"])
        ids, docs = got["ids"], got["documents"]
        results, tested = [], 0
        for cid, doc in zip(ids, docs):
            if tested >= sample:
                break
            if not doc or len(doc.strip()) < 80:
                continue
            tested += 1
            q = col.query(query_embeddings=[embed(doc[:1200])], n_results=3,
                          include=["distances"])
            hit_ids, ds = q["ids"][0], q["distances"][0]
            results.append({
                "id": cid,
                "self_rank": (hit_ids.index(cid) + 1) if cid in hit_ids else None,
                "best_distance": round(min(ds), 4) if ds else None,
            })
        if not results:
            return {}, "no document long enough to probe"
        return {"probes": results,
                "self_found": sum(1 for r in results if r["self_rank"]),
                "tested": len(results),
                "worst_best_distance": max(r["best_distance"] for r in results)}, ""
    except Exception as exc:  # noqa: BLE001
        return {}, f"{type(exc).__name__}: {str(exc)[:120]}"


def measure_model_dimension(model: str) -> tuple[int | None, str]:
    """Ask the live Ollama what width THIS model emits. Cheap probe.

    Lets the report say not just 'these two names differ' but 'the declared
    model cannot have produced the vectors that are actually stored', which is
    a much harder claim to wave away.
    """
    try:
        import requests
        sys.path.insert(0, str(DEXRAG))
        from dex_core import OLLAMA_HOST
        r = requests.post(f"{OLLAMA_HOST}/api/embeddings",
                          json={"model": model, "prompt": "dimension probe"},
                          timeout=30)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}: {r.text[:120]}"
        emb = r.json().get("embedding")
        return (len(emb), f"live probe of {model}") if emb else (None, "no embedding returned")
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# RECONCILE
# ---------------------------------------------------------------------------
def _distinct(decls: list[Declaration]) -> list:
    seen, out = set(), []
    for d in decls:
        k = json.dumps(d.value, sort_keys=True, default=str)
        if k not in seen:
            seen.add(k)
            out.append(d.value)
    return out


def build_report() -> dict:
    declared, problems, coverage = read_declarations()
    floors, floor_problem = read_chunk_floors()
    if floor_problem:
        problems.append(floor_problem)

    live, live_err = measure_collections()
    dims, dim_why = measure_dimensions_per_collection()

    # Which names are the LIVE corpus, as opposed to pre-rename leftovers.
    # Everything downstream must be explicit about which population it means --
    # conflating them is how the first version of this tool reported a dead
    # corpus's geometry as the live one.
    try:
        sys.path.insert(0, str(DEXRAG))
        import importlib, dex_core
        importlib.reload(dex_core)
        live_names = set(dex_core.get_live_collections())
        suffix_of = dex_core.suffixed
    except Exception:  # noqa: BLE001
        live_names, suffix_of = set(), (lambda n: n)

    live_dims = {n: d for n, d in dims.items() if n in live_names}
    legacy_dims = {n: d for n, d in dims.items() if n not in live_names}

    distinct_live_dims = sorted(set(live_dims.values()))
    stored_dim = distinct_live_dims[0] if len(distinct_live_dims) == 1 else None
    dim_note = (f"from stored vectors in {len(live_dims)} LIVE collection(s): "
                + ", ".join(f"{n}={d}" for n, d in sorted(live_dims.items()))) if live_dims else \
               ("no LIVE collection returned a readable embedding"
                + (f" ({'; '.join(f'{k}: {v}' for k, v in dim_why.items())})" if dim_why else ""))

    rows: list[Row] = []

    # ---- are the LIVE collections even in the same embedding space? ------
    # Checked first because if this fails, every other dimension claim below is
    # meaningless. Mixed spaces inside one corpus is a retrieval-breaking
    # emergency, not a documentation problem.
    r = Row("live_collections_share_one_embedding_space")
    r.measured = {n: d for n, d in sorted(live_dims.items())} or None
    r.measure_note = "stored vector widths, live collections only"
    # Each collection measured is an independent reading compared against the
    # others. Three collections agreeing is a real reconciliation.
    r.measurement_comparisons = len(live_dims)
    if not live_dims:
        r.measurable = False
        r.verdict, r.detail = "UNMEASURABLE", dim_note
    elif len(distinct_live_dims) > 1:
        r.verdict = "REFUTED"
        r.detail = (f"LIVE collections store DIFFERENT widths {distinct_live_dims}. "
                    "Mixed embedding spaces break retrieval (OBS-35).")
    else:
        r.verdict = "AGREE"
        r.detail = f"all {len(live_dims)} measurable LIVE collection(s) store {distinct_live_dims[0]}-d"
    rows.append(r)

    # ---- embedding model -------------------------------------------------
    r = Row("embedding_model", declared.get("embedding_model", []))
    names = _distinct(r.declarations)
    r.measurable = False
    r.measure_note = "a model NAME is not stored in ChromaDB; settled by dimension below"
    if not r.declarations:
        r.verdict, r.detail = "UNMEASURABLE", "nothing declares it"
    elif len(names) > 1:
        r.verdict = "CONFLICT"
        r.detail = f"{len(names)} different models declared: {', '.join(map(str, names))}"
    else:
        r.verdict, r.detail = "AGREE", f"all sources say {names[0]}"
    rows.append(r)

    # ---- embedding dimensions -- the load-bearing measurement ------------
    r = Row("embedding_dimensions", declared.get("embedding_dimensions", []))
    r.measured = stored_dim
    r.measure_note = dim_note
    # NOT named `dims` -- that is the per-collection measurement dict in this
    # same scope, and shadowing it here silently swapped a measurement for a
    # declaration. Caught only because the value happened to look wrong.
    declared_dims = _distinct(r.declarations)
    if stored_dim is None:
        r.measurable = False
        r.verdict = "UNMEASURABLE"
        r.detail = dim_note
    elif not declared_dims:
        r.verdict, r.detail = "UNDECLARED", f"live corpus stores {stored_dim}-d vectors; nothing declares it"
    elif any(d != stored_dim for d in declared_dims):
        bad = [d for d in declared_dims if d != stored_dim]
        r.verdict = "REFUTED"
        r.detail = (f"declared {bad} but the LIVE corpus stores {stored_dim}-d vectors. "
                    "A stored vector cannot be argued with.")
    else:
        r.verdict, r.detail = "AGREE", f"declared and live-stored both {stored_dim}"
    rows.append(r)

    # ---- did the corpus change embedding space at the rebuild? -----------
    # The row that distinguishes "this standard was never true" from "this
    # standard went stale." Those need DIFFERENT corrections, and only the
    # leftover collections still on disk can tell them apart. Without this,
    # a reader would reasonably conclude canon was simply wrong from the start.
    r = Row("legacy_vs_live_embedding_space")
    distinct_legacy = sorted(set(legacy_dims.values()))
    r.measure_note = "pre-rename collections still on disk"
    r.measured = {"legacy": dict(sorted(legacy_dims.items())),
                  "live": dict(sorted(live_dims.items()))} if legacy_dims else None
    if not legacy_dims or not distinct_live_dims:
        r.measurable = False
        r.verdict, r.detail = "UNMEASURABLE", (
            "no legacy collection returned a readable embedding" if not legacy_dims else dim_note)
    elif distinct_legacy != distinct_live_dims:
        r.verdict = "UNDECLARED"
        r.detail = (f"legacy collections store {distinct_legacy}, live store {distinct_live_dims}. "
                    "The corpus CHANGED embedding space at the rebuild, and nothing "
                    "declares that it happened — which is how a standard that was once "
                    "accurate became wrong without anyone editing it.")
    else:
        r.verdict, r.detail = "AGREE", f"legacy and live both {distinct_live_dims}"
    rows.append(r)

    # ---- can each declared model even produce the stored width? ----------
    for name in names if declared.get("embedding_model") else []:
        got, note = measure_model_dimension(str(name))
        rr = Row(f"model_can_produce_LIVE_width[{name}]")
        rr.measured = got
        rr.measure_note = note
        # Two independent measurements: a live probe of the model, and the
        # width actually stored in the corpus.
        rr.measurement_comparisons = 2 if (got is not None and stored_dim is not None) else 1
        if got is None:
            rr.measurable = False
            rr.verdict, rr.detail = "UNMEASURABLE", note
        elif stored_dim is None:
            rr.measurable = False
            rr.verdict, rr.detail = "UNMEASURABLE", "stored width unknown"
        elif got != stored_dim:
            rr.verdict = "REFUTED"
            rr.detail = (f"{name} emits {got}-d, the LIVE corpus stores {stored_dim}-d. "
                         f"{name} DID NOT build the live collections.")
        else:
            rr.verdict, rr.detail = "AGREE", f"{name} emits {got}-d, matching the live corpus"
        rows.append(rr)

    # ---- collections -----------------------------------------------------
    r = Row("collections")
    r.measured = sorted(live) if live else None
    if live is None:
        r.measurable = False
        r.verdict, r.detail = "UNMEASURABLE", live_err
    else:
        try:
            sys.path.insert(0, str(DEXRAG))
            import importlib, dex_core
            importlib.reload(dex_core)
            expected = set(dex_core.get_live_collections())
            actual = set(live)
            missing, extra = sorted(expected - actual), sorted(actual - expected)
            r.declarations = [Declaration(sorted(expected), str(DEXRAG / "dex_core.py"),
                                          39, "COLLECTIONS registry, status=LIVE")]
            if missing:
                r.verdict = "REFUTED"
                r.detail = f"declared LIVE but absent from the DB: {missing}"
                if extra:
                    r.detail += f"; present but undeclared: {extra}"
            elif extra:
                r.verdict = "UNDECLARED"
                r.detail = f"present in the DB, not declared LIVE: {extra}"
            else:
                r.verdict, r.detail = "AGREE", f"{len(actual)} collections, all declared"
        except Exception as exc:  # noqa: BLE001
            r.measurable = False
            r.verdict, r.detail = "UNMEASURABLE", f"could not read registry: {exc}"
    rows.append(r)

    # ---- chunk floors ----------------------------------------------------
    for base, floor in sorted(floors.items()):
        rr = Row(f"chunk_floor[{base}]")
        rr.declarations = [Declaration(floor, str(DEXRAG / "dex_core.py"), 52,
                                       "post-rebuild floor")]
        if live is None:
            rr.measurable = False
            rr.verdict, rr.detail = "UNMEASURABLE", live_err
            rows.append(rr)
            continue
        # EXACT suffixed name. Prefix matching here silently compared the floor
        # against the pre-rename `ddl_archive` instead of `ddl_archive_v2` and
        # reported phantom chunk loss.
        match = suffix_of(base) if suffix_of(base) in live else None
        if match is None:
            rr.verdict, rr.detail = "REFUTED", (
                f"floor declared for '{base}' but live collection "
                f"'{suffix_of(base)}' does not exist")
        else:
            rr.measured = live[match]
            if live[match] < 0:
                rr.measurable = False
                rr.verdict, rr.detail = "UNMEASURABLE", "count() failed"
            elif live[match] < floor:
                rr.verdict = "REFUTED"
                rr.detail = (f"{match} holds {live[match]:,}, below its declared floor "
                             f"of {floor:,} -- chunks were lost")
            else:
                rr.verdict = "AGREE"
                rr.detail = f"{match} {live[match]:,} >= floor {floor:,}"
        rows.append(rr)

    # ---- gated collections ----------------------------------------------
    r = Row("gated_collections", declared.get("gated_collections", []))
    vals = _distinct(r.declarations)
    if not r.declarations:
        r.verdict, r.detail = "UNMEASURABLE", "nothing declares it"
        r.measurable = False
    elif len(vals) > 1:
        r.verdict, r.detail = "CONFLICT", f"declared differently: {vals}"
    elif live is None:
        r.measurable = False
        r.verdict, r.detail = "UNMEASURABLE", live_err
    else:
        gated = vals[0]
        present = [n for n in live if any(n.startswith(g) for g in gated)]
        r.measured = present
        r.verdict = "AGREE"
        r.detail = (f"gate list {gated}; matching collections present: {present or 'none'} "
                    "(presence is expected -- gated means never INGEST, not absent)")
    rows.append(r)

    # ---- suffix ----------------------------------------------------------
    r = Row("collection_suffix", declared.get("collection_suffix", []))
    vals = _distinct(r.declarations)
    if not vals:
        r.measurable = False
        r.verdict, r.detail = "UNMEASURABLE", "not found"
    elif live is None:
        r.measurable = False
        r.verdict, r.detail = "UNMEASURABLE", live_err
    else:
        sfx = vals[0]
        r.measured = sfx
        off = [n for n in live if sfx and not n.endswith(sfx)]
        if off:
            r.verdict, r.detail = "UNDECLARED", f"collections not carrying suffix '{sfx}': {off}"
        else:
            r.verdict, r.detail = "AGREE", f"all live collections carry '{sfx}'"
    rows.append(r)

    # ---- is the refusal threshold anywhere near the real distances? ------
    #
    # Raised by Ellis Cooper (DDL-4008): two tools declare opposite floors and
    # NEITHER NUMBER WAS EVER MEASURED AGAINST THE CORPUS. That is exactly the
    # shape this tool exists for, and it had no row for it.
    #
    #   dex-openai-api.py   MAX_DISTANCE = 0.62, refuses anything above
    #   dex_jr_query.py     no floor at all -- cites whatever is in the top-k
    #
    # The absence of a floor is itself a declaration, so a missing constant is
    # reported as "none" rather than as a source that failed to load.
    #
    # The measurement is what makes this more than a lint: a floor is a claim
    # about the corpus's distance distribution, and that distribution is
    # measurable. A floor nobody measured is a number someone guessed once.
    r = Row("retrieval_distance_floor")
    r.measure_note = "top-1 distance over real questions from dex-bridge-log.jsonl"
    floors = []
    for path, const in ((DEXRAG / "dex-openai-api.py", "MAX_DISTANCE"),
                        (DEXRAG / "dex_jr_query.py", "MAX_DISTANCE")):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(rf"^{const}\s*=\s*([\d.]+)", text, re.M)
        line = text[: m.start()].count("\n") + 1 if m else 0
        floors.append(Declaration(float(m.group(1)) if m else "none",
                                  str(path), line,
                                  "refusal threshold" if m else "NO FLOOR — cites any top-k hit"))
    r.declarations = floors

    # Cite the question set from the eval tool rather than restating it here.
    # Restating would make this file the second place those questions live,
    # and they would drift.
    questions: list[str] = []
    evp = DEXRAG / "dex-eval-retrieval.py"
    if evp.exists():
        mm = re.search(r"ON_DOMAIN\s*=\s*\[(.*?)\]", evp.read_text(encoding="utf-8"), re.S)
        if mm:
            questions = re.findall(r'"([^"]{8,})"', mm.group(1))

    dists: list[float] = []
    if questions and live:
        try:
            import chromadb
            from dex_core import CHROMA_DIR as _CD, embed as _embed, suffixed as _sfx
            col = chromadb.PersistentClient(path=_CD).get_collection(_sfx("dex_canon"))
            for q in questions:
                res = col.query(query_embeddings=[_embed(q)], n_results=1,
                                include=["distances"])
                d = res["distances"][0]
                if d:
                    dists.append(d[0])
        except Exception as exc:  # noqa: BLE001
            r.measure_note += f" (probe failed: {type(exc).__name__})"

    numeric = [d.value for d in floors if isinstance(d.value, float)]
    if not dists:
        r.measurable = False
        r.verdict, r.detail = "UNMEASURABLE", "could not probe live distances"
    elif not numeric:
        r.verdict = "UNDECLARED"
        r.detail = f"no tool declares a floor; real questions span {min(dists):.3f}-{max(dists):.3f}"
    else:
        r.measured = {"real_question_top1": [round(d, 3) for d in dists]}
        r.measurement_comparisons = len(dists)
        floor = min(numeric)
        refused = [d for d in dists if d > floor]
        disagree = len(set(str(d.value) for d in floors)) > 1
        if refused:
            r.verdict = "REFUTED"
            r.detail = (
                f"the declared floor {floor} refuses {len(refused)} of {len(dists)} "
                f"REAL questions taken from the query log "
                f"(worst {max(dists):.3f}). A threshold that rejects questions the "
                f"corpus can answer was not calibrated against it."
                + (" And the two tools disagree: one declares a floor, the other none."
                   if disagree else ""))
        elif disagree:
            r.verdict = "CONFLICT"
            r.detail = ("one tool declares a floor and the other declares none; "
                        "the same hit is cited by one and refused by the other")
        else:
            r.verdict = "AGREE"
            r.detail = f"floor {floor} admits all {len(dists)} real questions probed"
    rows.append(r)

    # ---- can the scheduled tasks actually run unattended? ----------------
    # One fact, N locations. Six tasks with the same defect is one finding
    # with six sites, not six findings.
    tasks, task_err = measure_scheduled_tasks()
    r = Row("scheduled_tasks_can_run_unattended")
    r.measure_note = "LogonType per task; Interactive runs only while that user is logged on"
    if not tasks:
        r.measurable = False
        r.verdict, r.detail = "UNMEASURABLE", task_err or "no Dex* tasks found"
    else:
        interactive = {n: t for n, t in tasks.items()
                       if str(t.get("logon", "")).lower() == "interactive"}
        r.measured = {n: {"logon": t["logon"], "triggers": t["triggers"]}
                      for n, t in sorted(tasks.items())}
        r.measurement_comparisons = len(tasks)
        if interactive:
            r.verdict = "REFUTED"
            r.detail = (
                f"{len(interactive)} of {len(tasks)} DDL task(s) run LogonType=Interactive "
                f"and therefore do NOT fire on a rebooted, logged-out machine, despite "
                f"carrying recurring triggers: {', '.join(sorted(interactive))}. "
                "A daily trigger declares a schedule; Interactive determines whether it "
                "can be kept.")
        else:
            r.verdict = "AGREE"
            r.detail = f"all {len(tasks)} task(s) can run unattended"
    rows.append(r)

    # ---- does each live collection return ITS OWN documents? -------------
    if live:
        r = Row("collections_return_their_own_documents")
        r.measure_note = ("self-retrieval: a document embedded and queried against its "
                          "own collection must come back at ~0 distance")
        per, failures, unmeasured = {}, [], []
        for cname in sorted(live_names & set(live)):
            res, err = measure_index_self_retrieval(cname)
            if err:
                unmeasured.append(f"{cname} ({err})")
                continue
            per[cname] = res
            # A collection whose own documents do not come back is not merely
            # missing a feature -- it is returning other documents in their
            # place, with plausible distances and no error.
            if res["self_found"] == 0:
                failures.append(f"{cname} 0/{res['tested']} "
                                f"(best distance {res['worst_best_distance']})")
        r.measured = per or None
        r.measurement_comparisons = len(per)
        if not per:
            r.measurable = False
            r.verdict, r.detail = "UNMEASURABLE", "; ".join(unmeasured) or "no collection probed"
        elif failures:
            r.verdict = "REFUTED"
            r.detail = (f"{len(failures)} collection(s) do NOT return their own documents: "
                        f"{'; '.join(failures)}. query() still returns hits, so retrieval "
                        "looks healthy while serving the wrong chunks."
                        + (f" Not probed: {'; '.join(unmeasured)}." if unmeasured else ""))
        else:
            r.verdict = "AGREE"
            r.detail = (f"all {len(per)} probed collection(s) return their own documents"
                        + (f"; not probed: {'; '.join(unmeasured)}" if unmeasured else ""))
            if unmeasured:
                # Coverage is incomplete even though what ran passed.
                r.sources_expected = len(per) + len(unmeasured)
                r.sources_read = len(per)
                r.sources_failed = unmeasured
        rows.append(r)

    # Attach source coverage, then let integrity_check override any
    # agreement-shaped verdict that rests on incomplete evidence.
    for r in rows:
        cov = coverage.get(r.fact)
        if cov:
            r.sources_expected = cov["expected"]
            r.sources_read = cov["read"]
            r.sources_failed = list(cov["failed"])

    integrity_check(rows)

    bad = [r for r in rows if r.verdict in ("CONFLICT", "REFUTED")]
    unchecked = [r for r in rows if r.verdict in ("UNCHECKED", "UNMEASURABLE", "SINGLE_SOURCE")]
    return {"rows": rows, "problems": problems, "findings": bad, "unchecked": unchecked}


# ---------------------------------------------------------------------------
# RENDER
# ---------------------------------------------------------------------------
MARK = {"AGREE": "  ", "CONFLICT": "!!", "REFUTED": "!!",
        "UNMEASURABLE": "??", "UNDECLARED": " ?",
        "UNCHECKED": "??", "SINGLE_SOURCE": " ?"}


def render(rep: dict, quiet: bool) -> None:
    print("\nDEX RECONCILE — declared vs measured")
    print("=" * 72)
    print("This tool declares nothing. Every value below is cited or measured.\n")

    for r in rep["rows"]:
        if quiet and r.verdict == "AGREE":
            continue
        print(f"{MARK.get(r.verdict, '  ')} {r.fact}   [{r.verdict}]")
        print(f"     {r.detail}")
        for d in r.declarations:
            print(f"       declared: {d.value!r}")
            print(f"                 {d.where}  ({d.note})")
        if r.measured is not None:
            print(f"       measured: {r.measured!r}")
            if r.measure_note:
                print(f"                 {r.measure_note}")
        elif not r.measurable and r.measure_note:
            print(f"       measured: UNMEASURABLE — {r.measure_note}")
        print()

    if rep["problems"]:
        print("READER PROBLEMS (this tool could not read a source)")
        for p in rep["problems"]:
            print(f"  ?? {p}")
        print()

    # "No disagreement found" and "could not compare" must never render the
    # same way. This block is why the summary cannot be read as a clean bill
    # of health when half the sources failed to load.
    if rep["unchecked"]:
        print("=" * 72)
        print(f"  {len(rep['unchecked'])} FACT(S) NOT RECONCILED — absence of a finding here")
        print("  means NOTHING WAS COMPARED, not that everything agrees.")
        for r in rep["unchecked"]:
            print(f"    {r.verdict}: {r.fact}")
            print(f"      {r.detail}")
        print("=" * 72)
        print()

    if rep["findings"]:
        print("=" * 72)
        print(f"  {len(rep['findings'])} FINDING(S)")
        for r in rep["findings"]:
            print(f"    {r.verdict}: {r.fact} — {r.detail}")
        print("=" * 72)
    elif rep["unchecked"]:
        print("  no disagreements among the facts that COULD be checked.")
        print("  That is not the same as everything reconciling — see above.")
    else:
        print("  everything reconciles, and every fact was actually compared.")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description="reconcile declared corpus facts against measurement")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="only problems")
    a = ap.parse_args()

    rep = build_report()

    if a.json:
        print(json.dumps({
            "rows": [{"fact": r.fact, "verdict": r.verdict, "detail": r.detail,
                      "measured": r.measured, "measurable": r.measurable,
                      "measure_note": r.measure_note,
                      "sources_expected": r.sources_expected,
                      "sources_read": r.sources_read,
                      "sources_failed": r.sources_failed,
                      "declarations": [{"value": d.value, "where": d.where, "note": d.note}
                                       for d in r.declarations]} for r in rep["rows"]],
            "problems": rep["problems"],
            "finding_count": len(rep["findings"]),
            "unchecked_count": len(rep["unchecked"]),
        }, indent=2, default=str))
    else:
        render(rep, a.quiet)

    # Distinct codes so automation can tell "found a problem" from "could not
    # look". Both are non-zero: silence about an unchecked fact is the failure
    # this tool exists to prevent.
    if rep["findings"]:
        return 1
    if rep["unchecked"]:
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
