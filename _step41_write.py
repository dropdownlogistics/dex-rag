"""Step 41 — write synthesis + extraction deliverables to DDL_Ingest."""
from __future__ import annotations
import json, sys, re

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

INGEST = r"C:\Users\dkitc\OneDrive\DDL_Ingest"

# ── Part A: WorkBench weekend synthesis ────────────────────────────
SYNTHESIS = r"""DDLSynthesis_WorkBenchWeekend_4.12.26

=====================================================================
DDL STUDIO SYNTHESIS — WorkBench Architecture Sprint
Subject:        Nine-CR Architecture Sprint, 2026-04-12 → 2026-04-13
Operator:       Dave Kitchens · Dropdown Logistics
Author:         Claude Code (Dex Jr., Seat 1010), at Marcus Caldwell's
                request
Date:           2026-04-13
Classification: Studio Synthesis / Briefing Artifact
Authority:      Derived from CR-WB-* + CR-DDL-WEEKEND-001
Note:           Extracted from chunks already ingested into dex_canon;
                intended as a single-source retrieval anchor for the
                "WorkBench architecture sprint" arc.
=====================================================================

HEADLINE

Over 36 hours spanning 2026-04-12 evening to 2026-04-13 evening,
nine council reviews landed in dex_canon. Together they specify
WorkBench from substrate to product-shipping-contract to
analytics-roadmap to meta-procedure for building further modules.
Module 1 (HR & People) ratified as the reference implementation.
A pan-studio update (CR-DDL-WEEKEND-001) frames the architectural
shift underneath. One research-intake CR (CR-WB-PITFALLS-001)
catalogs what the incumbents already learned. One meta-CR
(CR-WB-MODBUILD-001) ratifies the process that produced the rest.
The operator drafted three of five platform-spine pillars in
24 hours. Closing line that captures the signal: "The studio
started behaving like the platform it has been hinting at for
months."

=====================================================================
PER-REVIEW SUMMARY  (all 9, ordered by dependency)
=====================================================================

1. CR-WB-FACTLAYER-001 — WorkBench Fact Layer Governance
   Author: Seat 1002 (Marcus Caldwell) | Status: CLOSED
   Verdict: 8 of 8 seats ratified with revisions
   Companion standard: STD-WB-FACTLAYER-001 (drafting)

   Core thesis: Every WorkBench module writes events to the same
   governed fact layer, enabling native cross-module queries
   without integration work. 17 requirements locked (originally
   12; council added 5 for soft-delete, retention dependency,
   schema evolution, replayability, atomic imports). Grey framed
   it as "a governed dimensional-event hybrid designed for
   cross-module business-operating analytics from first principles
   rather than post hoc integration." Kai: "not a draft — a
   constitution." Most load-bearing architectural commitment in
   the sprint.

   Open items: None — exit status CLOSED. Companion standard
   returns to council after PM drafting.

2. CR-WB-CONNECTIVITY-001 — Bidirectional Integration Stance
   Author: Seat 1002 | Status: CLOSED
   Verdict: 8 of 8 seats ratified
   Companion standard: STD-WB-CONNECTIVITY-001 (drafting)

   Core thesis: "Bring Your Data" as a first-class architectural
   stance, not a connector feature. Every module ingests foreign
   data losslessly from day one. 8 requirements locked (4
   original hard + 3 reclassified SOFT-to-HARD + 1 new), plus
   Kai's proposed FORBIDDEN tier (architecturally-incompatible
   patterns). Grey's sentence travels with the standard:
   "Bring Your Data only deserves to ratify as canon if WorkBench
   treats inbound fidelity as a substrate obligation rather than
   a connector feature." Leo framed as "architectural warfare …
   a declaration of war on the B2B SaaS industry."

   Open items: Ava's app failed (one seat missing); not blocking.

3. CR-WB-ANALYTICS-001 — Three-Stage Analytics Roadmap
   Author: Seat 1002 | Status: CLOSED
   Verdict: 8 of 8 seats ratified
   Companion standards: STD-WB-MEASURE-001, STD-WB-ANALYTICS-001

   Core thesis: Analytics staged as capability, not as feature
   plan. Stage 1 scenario dashboards, Stage 2 build-your-own,
   Stage 3 natural-language interface (Claude API over measure
   layer). Each stage forces the next stage's foundation. Key
   synthesis addition: the Chart-Rendering Gate — every chart
   MUST resolve through a measureId, making the measure layer
   the only path to production analytics. Leo: "You are weaponizing
   the frontend to govern the backend." Grey: "WorkBench is not
   staging analytics UIs. It is staging semantic control over
   the measure layer."

   Open items: None.

4. CR-WB-MODULE-001 — Structural Requirements for Shipping
   Author: Seat 1002 | Status: CLOSED (with Grey addendum)
   Verdict: all ratifying seats + addendum integration
   Companion standard: STD-WB-MODULE-001 (drafting)

   Core thesis: Every WorkBench module must conform to this
   standard to ship. Composes FactLayer + Connectivity +
   Analytics + adds module-level coherence requirements. Grey's
   addendum reframed Category A requirements via inheritance
   ("the bridge that turns those standards into a shippable
   unit") and added the AppExchange / Shopify / Atlassian
   distinction: "Every module is not merely installable into
   the same ecosystem; every module is architected to deepen
   the same substrate."

   Open items: Grey answered wrong CR elsewhere; may re-run if
   operator desires. Non-blocking.

5. CR-WB-HRPEOPLE-001 — Module 1 Ratification (HR & People)
   Author: Seat 1002 | Status: RATIFY_MODULE (final verdict)
   Distribution: All seats + Adjuncts ADJ-E, ADJ-D, ADJ-B

   Core thesis: First WorkBench module. Reference implementation
   of STD-WB-MODULE-001, STD-WB-FACTLAYER-001, STD-WB-MEASURE-001,
   STD-WB-CONNECTIVITY-001. Build-ready spec. Fact tables
   (Fact_RoleChange, etc.), Dim_Employee with managerId,
   measures like avg_tenure_days. Working-review mode: council
   pressure-tested the architecture AND filled in open specs
   in the same document.

   Open items / deferrals:
     - Onboarding UI deferred (operator adds employees manually V1)
     - Offboarding checklists deferred
     - Benefits enrollment explicitly deferred
     - Excel formula template field in measure layer optional
   Future risk flagged: mini-payroll migration path — operator
   must commit to a migration plan before Payroll module begins.

6. CR-WB-CANON-001 — Canon Additions (10 nominations)
   Author: Seat 1002 | Status: MOSTLY RATIFIED
   Verdict: 9 of 10 ready for CANON draft immediately, 1 pending
   operator decision, 2 pending second-pass

   Ratified (ready for canon draft):
     1. BlueprintInversion
     2. CathedralPlanned
     4. Bring Your Data
     5. GovernedCohesion (revised definition)
     6. AllCategoriesExpand
     7. AsymmetricTaxonomy
     8. RelationalRendering
     9. ReflectivePrivacy
    10. PortableRecord

   Pending operator decision:
     3. "Everything, Everywhere, All At Once" + NativeCoherence
        (recommend ratify as stance/mechanism pair)

   Pending second-pass review:
    11. SessionAsExemplar
    12. CeilingInjection / CeilingDetection (as a pair)

   Closing note: "The cluster was not 'too many names' — it was
   a session where the underlying architecture forced latent
   concepts to crystallize."

7. CR-WB-PITFALLS-001 — Universal Pitfalls & Research Targets
   Author: Seat 1002 | Status: RESEARCH INTAKE (ongoing)
   Mode: NOT ratification / NOT cathedral vision

   Ten-plus pitfalls catalogued. Seat highlights:
     - PITFALL-5 (permission models): draft STD-WB-PERMISSION-001
       early; start with RBAC + role-scoped overrides (hybrid);
       every permission is a governed artifact. Cross-reference
       to operator manifest and CR-OPERATOR-CAPACITY-001.
     - PITFALL-6 (data export at churn): FLAGGED HIGHER priority
       than list implies. Symmetric to Bring Your Data — "Take
       Your Data" is a trust signal that should be demonstrated
       BEFORE first customer signs up. Data export spec is
       itself a commercial asset.
     - PITFALL-10 (retention vs immutable logs): parallel to
       PRO-DDL-SPIRAL-001. Solution: "tombstone + exclusion
       filter" — tombstone is an immutable fact marking the
       original as deleted. Data equivalent of the Spiral
       Protocol's landing procedure.

   Status: ongoing — more pitfalls will be contributed as they
   surface.

8. CR-WB-MODBUILD-001 — Formalizing the Module Build Process
   Author: Seat 1002 | Status: RATIFY_PROCEDURE (final verdict)
   Classification: Procedural Standard — META-REVIEW
   Companion protocol: PRO-DDL-MODBUILD-001 (ratified as written)

   Core thesis: The process that produced Module 1 was not
   designed in advance — it emerged from practice. This review
   makes the emergent process legible, formalizes it as a
   protocol, and registers the associated standards family
   supporting it. The session that produced the process became
   the canonical example of the process — "ratifying itself as
   the exemplar of CathedralPlanned (CR-WB-CANON-001 Candidate 2)."
   Meta: this review was authored under the process it describes.

   Kai's 5 non-blocking recommendations for future amendments:
     1. Extract cross-cutting principles → STD-DDL-PRINCIPLES-001
        within 30 days.
     2. Defer PRO-DDL-MODANCHOR-001 and PRO-DDL-MODPIN-001 until
        Module 2 or evidence of need.
     3. Add "Anchor escalation" note to Phase 1.
     4. Add pause-and-resume note to Phase 6.
     5. Require OBS entry after each module ship that evaluates
        the procedure itself.

   Dex Jr. seat contribution: ingest as protocol artifact,
   source_type: protocol, domain: workbench_module_design.

9. CR-DDL-WEEKEND-001 — Weekend Studio Update (pan-studio)
   Author: Seat 1002 | Status: SYNTHESIS / OPEN APERTURE
   Mode: NOT red team, NOT cathedral prompt

   Core thesis: Pan-studio status review surfacing that "the
   studio started behaving like the platform it has been
   hinting at for months" (Grey). Three-layer operational
   architecture emerged as governance primitive:
     - Products layer (WorkBench, AuditForge, Ledger, etc.)
     - Governance layer (STD/CR/ADR/PRO/OBS artifacts)
     - Retrieval layer (dex_canon, Dex Jr., B3/B2 prefilters)

   Items flagged for next sprint:
     - CR-PLATFORM-CATHEDRAL-002 — governance retrieval /
       indexing / synthesis cadence (30-day horizon)
     - CR-LAYER-SEPARATION-001 (Kai) — CC commits, council
       approvals, operator override rules
     - STD-DDL-DATAPLANE-001 (Max) — YAML schema registry
     - AuditForge → Ledger integration (Leo) as first concrete
       cross-product flow
     - Second Delta Protocol run on CR-PLATFORM-CATHEDRAL-002

   Metaphor note: the cathedral metaphor may be retiring. A
   "coral reef" alternative emerged but has not been adopted.
   The metaphor hunt is itself a signal — the studio has
   outgrown the frame it was built inside.

=====================================================================
THE ARCHITECTURAL ARC  (synthesis across all 9 CRs)
=====================================================================

Read dependency-first, the sprint specifies WorkBench from
substrate up:

  SUBSTRATE         STD-WB-FACTLAYER-001
                       ↓ (every module writes events here)
  SUBSTRATE-STANCE  STD-WB-CONNECTIVITY-001
                       ↓ (every module ingests foreign data)
  MEASURE LAYER     STD-WB-MEASURE-001 + Chart-Rendering Gate
                       ↓ (every chart resolves through measureId)
  MODULE CONTRACT   STD-WB-MODULE-001
                       ↓ (every module conforms to ship)
  REFERENCE IMPL    CR-WB-HRPEOPLE-001  ← Module 1
                       ↓ (proves the stack)
  META-PROCEDURE    PRO-DDL-MODBUILD-001
                       ↓ (defines how Module 2+ gets built)
  RESEARCH INTAKE   CR-WB-PITFALLS-001
                       ↓ (catalogs what not to repeat)
  CANON VOCABULARY  CR-WB-CANON-001
                       ↓ (9 new terms ratified ready)
  STUDIO SIGNAL     CR-DDL-WEEKEND-001
                       (platform-shaped behavior emerging)

Reading the stack top-down: HR & People is the first module,
built on a governed substrate, under a module contract, drafted
via a formalized protocol, with a measured analytics roadmap,
inside a product architecture declaring bidirectional data as
first-class. Each layer is ratified. The canon terms serve as
the stack's vocabulary.

=====================================================================
CANON TERMS RATIFIED OR SURFACED THIS SPRINT
=====================================================================

Ratified ready for canon draft (9):
  BlueprintInversion, CathedralPlanned, Bring Your Data,
  GovernedCohesion (revised), AllCategoriesExpand,
  AsymmetricTaxonomy, RelationalRendering, ReflectivePrivacy,
  PortableRecord

Pending operator decision (1):
  "Everything, Everywhere, All At Once" + NativeCoherence
  (stance/mechanism pair)

Pending second-pass review (2):
  SessionAsExemplar, CeilingInjection/CeilingDetection

Surfaced but not formally nominated:
  FORBIDDEN tier (connectivity), Chart-Rendering Gate (analytics),
  tombstone + exclusion filter (pitfalls), inheritance framing
  (module), coral reef (pan-studio metaphor candidate)

=====================================================================
OPEN QUESTIONS AND DEFERRALS (inheriting into next sprint)
=====================================================================

Operator decisions pending:
  - Canon Candidate 3: ratify "Everything, Everywhere, All At
    Once" alone, "NativeCoherence" alone, or as a pair?
  - Canon Candidates 11/12: second CR now, or fold into future
    CR-WB-CANON-002?
  - Payroll module migration path: commit a plan before Payroll
    development begins.
  - Cathedral metaphor successor: adopt coral reef, keep
    cathedral, or something else?

Companion standards awaiting PM drafting:
  STD-WB-FACTLAYER-001, STD-WB-CONNECTIVITY-001,
  STD-WB-MEASURE-001, STD-WB-ANALYTICS-001, STD-WB-MODULE-001

Proposed new standards (not yet drafted):
  STD-WB-PERMISSION-001 (from PITFALLS), STD-DDL-PRINCIPLES-001
  (from MODBUILD Kai amendment), STD-DDL-DATAPLANE-001 (Max),
  PRO-DDL-MODANCHOR-001, PRO-DDL-MODPIN-001 (deferred until
  Module 2)

Next-sprint CR candidates:
  CR-PLATFORM-CATHEDRAL-002, CR-LAYER-SEPARATION-001,
  CR-WB-CANON-002 (potential)

=====================================================================
CROSS-CUTTING PATTERNS
=====================================================================

1. Ratification density. 8-of-8 convergence appeared in three
   separate CRs (FactLayer, Connectivity, Analytics) — tighter
   than any prior Cathedral Vision cycle. Indicates the
   architecture is legible enough that independent seats reach
   similar conclusions.

2. "Gate" as architectural primitive. Chart-Rendering Gate and
   FORBIDDEN tier both add enforcement that the aspirational
   framing wouldn't. Pattern: describing a stance is not enough;
   the substrate must make violating the stance harder than
   conforming.

3. Hybrid framings as council value. Multiple reviews note the
   synthesis produced a better answer than any single seat
   proposed. REQ-10/REQ-11 (fact layer), SOFT-to-HARD reclass
   (connectivity), inheritance framing (module). The council's
   structural output > any seat's individual output.

4. Dex Jr. as participant. Multiple seat-level responses
   include a "DEX JR. (retrieval):" line specifying how the
   artifact should be indexed, queried, and surfaced. The
   retrieval layer is now a first-class council voice on
   standards authorship, not just a consumer.

5. "The operator decides. The architecture does not change. The
   data does." Closing invocation appears verbatim in 5 of 9
   reviews. Shared tagline across the sprint; functionally a
   recognition phrase.

6. Cathedral metaphor fatigue. CR-DDL-WEEKEND-001 explicitly
   flags the metaphor as possibly retiring. The sprint produced
   enough concrete architecture that the metaphorical scaffold
   is no longer load-bearing.

=====================================================================
RELATIONSHIP TO THE DEX JR. RETRIEVAL REBUILD (parallel work)
=====================================================================

While this architectural sprint was drafting WorkBench, the
Dex Jr. retrieval layer rebuilt itself through Steps 24-40
(see session log, 2026-04-12). Key intersections:

- CR-DDL-WEEKEND-001 names Dex Jr. as one of the three operational
  layers of the studio. The retrieval layer is explicitly
  platform-scoped, not product-scoped.
- CR-WB-MODBUILD-001 Dex Jr. seat response specifies
  source_type tagging for protocol artifacts. That convention
  anchors retrieval behavior.
- CR-WB-HRPEOPLE-001 Dex Jr. seat response specifies the
  Module 1 retrieval patterns ("Show me Bob's role changes"
  → Fact_RoleChange).
- CR-PLATFORM-CATHEDRAL-002 (flagged in Weekend Update) is
  explicitly governance-retrieval / indexing / synthesis cadence
  scope. That's the convergence of this sprint's output with
  Dex Jr.'s substrate.
- The corpus migration to mxbai-embed-large during soak means
  every artifact from this sprint is retrievable under an
  embedding model that actually preserves DDL identifiers. The
  FactLayer's enforcement depends on that retrievability.

=====================================================================
BRIEFING NOTES FOR MARCUS (things likely not yet in memory)
=====================================================================

1. The six unread reviews collectively close four CRs
   (Connectivity, FactLayer, Analytics, Module) and leave one
   open for second-pass (Canon candidates 11/12 + 3). One is a
   pan-studio synthesis (Weekend Update). One is a research
   intake ongoing (Pitfalls). The arc is already cleaner than
   the individual reviews suggest.

2. All 9 reviews are already in dex_canon (Monday's manual
   sweep per Step 36, +6,913 chunks). They are NOT awaiting
   tomorrow's sweep — they have been live in the corpus since
   Mon 22:36. Tomorrow's sweep picks up two different artifacts:
   STD-FCODE-001.txt and PRO-DDL-PLATINUM-BOUNCE-001.txt
   (the F-code consolidation artifacts from Step 40).

3. CR-WB-FACTLAYER-001 is the load-bearing review. If anything
   in this sprint needs re-ratification or amendment, it starts
   there. The other reviews compose against its decisions.

4. The FORBIDDEN tier (Connectivity) is quietly consequential.
   It creates a third architectural category the original draft
   didn't contemplate: patterns that are architecturally
   incompatible with the stance, not merely hard to retrofit.

5. The cathedral-metaphor-retiring signal in CR-DDL-WEEKEND-001
   is not a nostalgia beat. It's flagging that the frame the
   studio was built inside may no longer fit the structure the
   sprint produced.

6. Five platform-spine pillars per Caldwell tally: fact layer,
   connectivity, analytics (all drafted this sprint), CardType
   service (Kai's weekend proposal, not yet drafted), cross-repo
   coordination standard (Leo's weekend proposal, not yet
   drafted). Three of five drafted in 24 hours.

=====================================================================
CLOSING
=====================================================================

What Grey named: "The studio started behaving like the platform
it has been hinting at for months."

What Kai named: "not a draft — a constitution."

What Leo named: "architectural warfare … a declaration of war
on the B2B SaaS industry."

All three are correct. The substrate is specified. The cathedral
has a floor. The coral grows on the substrate the cathedral
built, and the substrate now documents its own growth.

=====================================================================
Dropdown Logistics — Chaos → Structured → Automated
DDL Studio Synthesis | 2026-04-13 | Authored by Dex Jr. (Seat 1010)
=====================================================================
"""

# ── Part B: CottageHumble extraction ───────────────────────────────
with open("_step41_cottage.json", "r", encoding="utf-8") as f:
    ctg = json.load(f)

def descriptive_score(text: str, term: str) -> int:
    """Higher = more descriptive. Counts mentions + keyword-near-term hits."""
    score = text.count(term) * 2
    # Indicators of descriptive density
    descriptors = [
        "intentional", "is a feature", "is not", "means", "translates to",
        "looks like", "humble surface", "cathedral underneath",
        "Graph Holds", "feature, not a bug", "surface ", "underneath",
    ]
    for d in descriptors:
        if d in text:
            score += 1
    return score

def dedupe_and_top(chunks_per_corpus, term, n=10):
    all_chunks = []
    for label, rec in chunks_per_corpus.items():
        for r in rec.get(term, []):
            all_chunks.append((label, r["sf"], r["n"], r["text"]))
    # score + dedupe by (sf, first 200 chars) to collapse canon/archive duplicates
    scored = [(descriptive_score(t, term), lbl, sf, n_, t) for lbl, sf, n_, t in all_chunks]
    scored.sort(key=lambda x: -x[0])
    seen = set()
    out = []
    for score, lbl, sf, n_, t in scored:
        key = (sf.split("\\")[-1], t[:120])
        if key in seen:
            continue
        seen.add(key)
        out.append({"score": score, "corpus": lbl, "sf": sf, "mentions": n_, "text": t})
        if len(out) >= n:
            break
    return out


lines = []
lines.append("DDLExtraction_CottageHumble_SourceMaterial_4.13.26")
lines.append("")
lines.append("=" * 70)
lines.append("COTTAGEHUMBLE SOURCE EXTRACTION")
lines.append("=" * 70)
lines.append("""
Read-only extraction, 2026-04-13, for Marcus's gloss-drafting
session with the operator. Raw source material only — no synthesis.

Methodology:
  1. CLAUDE.md grep for any CottageHumble reference
  2. $contains queries across dex_canon_v2 and ddl_archive_v2
  3. Chunks ranked by descriptive density (mention count +
     presence of descriptor phrases like 'intentional',
     'humble surface', 'cathedral underneath', 'feature, not a bug')
  4. Specific-phrase searches for design-token references

All counts are minimum floors — every category hit the 100-chunk
cap in at least one corpus (`$contains` limit imposed for
inventory pass). True density is higher than reported.
""")

# Section 1: CLAUDE.md
lines.append("=" * 70)
lines.append("SECTION 1 — CLAUDE.md references")
lines.append("=" * 70)
lines.append("""
None. CLAUDE.md grep for 'CottageHumble', 'cottagehumble',
'Cottage Humble' returns zero matches. The term is operator-
internal language that has never been written into the repo's
constitution file.
""")

# Section 2: Top-10 descriptive chunks for CottageHumble
lines.append("=" * 70)
lines.append("SECTION 2 — Top 10 most-descriptive CottageHumble chunks")
lines.append("=" * 70)
lines.append("")
top_ch = dedupe_and_top(ctg, "CottageHumble", n=10)
for i, r in enumerate(top_ch, 1):
    lines.append(f"--- #{i}  score={r['score']}  mentions={r['mentions']}  corpus={r['corpus']} ---")
    lines.append(f"source_file: {r['sf']}")
    # locate term in text and print surrounding context (up to 1200 chars)
    text = r["text"]
    idx = text.find("CottageHumble")
    start = max(0, idx - 300)
    end = min(len(text), idx + 900)
    lines.append(text[start:end])
    lines.append("")

# Section 3: Top source_files by occurrence
lines.append("=" * 70)
lines.append("SECTION 3 — Top source_files containing CottageHumble")
lines.append("=" * 70)
lines.append("")
fcount: dict[str, int] = {}
for lbl, rec in ctg.items():
    for r in rec.get("CottageHumble", []):
        fcount[r["sf"]] = fcount.get(r["sf"], 0) + 1
top_sf = sorted(fcount.items(), key=lambda x: -x[1])[:15]
for sf, n in top_sf:
    lines.append(f"  {n:>3}  {sf}")
lines.append("")

# Section 4: Phrase-specific searches
def phrase_section(title, term, n=5):
    lines.append("=" * 70)
    lines.append(f"SECTION — {title}")
    lines.append("=" * 70)
    lines.append("")
    top = dedupe_and_top(ctg, term, n=n)
    if not top:
        lines.append("(no hits)")
        lines.append("")
        return
    for i, r in enumerate(top, 1):
        text = r["text"]
        idx = text.find(term)
        start = max(0, idx - 200)
        end = min(len(text), idx + 700)
        lines.append(f"--- #{i}  corpus={r['corpus']}  src={r['sf']} ---")
        lines.append(text[start:end])
        lines.append("")


phrase_section("'humble surface, cathedral underneath'",
               "humble surface, cathedral underneath", n=6)
phrase_section("'humble surface' (broader, includes any form)",
               "humble surface", n=4)
phrase_section("'Graph Holds'", "Graph Holds", n=4)

# Section 5: Design tokens
lines.append("=" * 70)
lines.append("SECTION 5 — Design-token context (colors, typography)")
lines.append("=" * 70)
lines.append("")
for term in ["#0D1B2A", "#F5F1EB", "#B23531", "Space Grotesk",
             "JetBrains Mono", "Source Serif 4"]:
    top = dedupe_and_top(ctg, term, n=2)
    lines.append(f"--- {term} ---")
    for r in top:
        text = r["text"]
        idx = text.find(term)
        start = max(0, idx - 150)
        end = min(len(text), idx + 400)
        lines.append(f"  src={r['sf']}")
        lines.append(f"  {text[start:end]}")
    lines.append("")

lines.append("=" * 70)
lines.append("END OF EXTRACTION")
lines.append("=" * 70)
lines.append("")
lines.append("Dropdown Logistics — Chaos → Structured → Automated")
lines.append("CottageHumble Source Extraction | 2026-04-13 | Authored by Dex Jr. (Seat 1010)")
lines.append("=" * 70)

extraction = "\n".join(lines)

# Write both files
import os
os.makedirs(INGEST, exist_ok=True)
synth_path = os.path.join(INGEST, "DDLSynthesis_WorkBenchWeekend_4.12.26.md")
with open(synth_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(SYNTHESIS)
extr_path = os.path.join(INGEST, "DDLExtraction_CottageHumble_SourceMaterial_4.13.26.md")
with open(extr_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(extraction)

print(f"Synthesis:   {synth_path}")
print(f"  chars={len(SYNTHESIS):,}  lines={SYNTHESIS.count(chr(10)):,}")
print(f"Extraction:  {extr_path}")
print(f"  chars={len(extraction):,}  lines={extraction.count(chr(10)):,}")
