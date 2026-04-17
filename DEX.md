# DEX.md — dex-rag

Context status: **current**
Last reviewed: 2026-04-17
DEX.md version: 1.0
Token budget: ~2,500 (target 3,000 / hard cap 4,000)

---

## 1. Project Identity

**dex-rag** — Local RAG infrastructure and intelligence layer for Dex Jr. (Seat 1010).

- Repo: `github.com/dropdownlogistics/dex-rag`
- Machine: Reborn (RTX 3070, 32GB RAM, Windows 11)
- Secondary: Gaming Laptop (RTX 3060, Tailscale MagicDNS)
- Status: Production. Nightly automation. 396K corpus chunks.
- Role: Intelligence substrate for all DDL products and council operations

Related CRs: CR-DDL-INGEST-FAST-SCOPED-001 (closed), CR-DDL-SOAK-RENAME-001 (open, ~4/28)

---

## 2. Architectural State

**Stack:** Python 3.12 · ChromaDB (PersistentClient) · Ollama (local) · mxbai-embed-large (1024-dim) · qwen2.5-coder:7b (Modelfile v4.7)

**Corpus (4 LIVE collections + 1 provisioned):**
- `dex_canon_v2` (58,919 chunks, weight 0.90) — ratified governance, council reviews, standards
- `ddl_archive_v2` (316,109 chunks, weight 0.65) — historical material, threads, messages
- `dex_code_v2` (20,416 chunks, weight 0.85) — code artifacts
- `ext_creator_v2` (922 chunks, weight 0.85) — vetted external content
- `ext_reference_v2` (0 chunks, weight 0.75) — provisioned, empty
- `dex_dave` — HARD-GATED. Never ingest. ADR-CORPUS-001 Rule 3.

**Shared foundation:** `dex_core.py` — single source of truth for all config, connections, collection registry, council roster, host resolution, embedding, primer loading. Every Python file imports from dex_core.

**Key files (20 tracked in root):**
- `dex_core.py` — shared config + utilities
- `dex_jr_query.py` — primary query tool (B3 prefilter, B2 body-match, weighted retrieval)
- `dex-ingest.py` — corpus ingest pipeline (SHA-256 cache, hard gate)
- `dex-sweep.py` — nightly sweep (4 AM, Task Scheduler)
- `dex-backup.py` — backup with quarantine model
- `dex-council.py` — AutoCouncil v4.0 (multi-host, personas, parallel)
- `dex-bridge.py` — CC→Dex Jr. RAG bridge v1.3
- `dex-search-api.py` — FastAPI search endpoint v0.6 (4 collections)
- `dex_health.py` — 8-subsystem health check
- `dex_weights.py` — source weighting + scored retrieval
- `dex_review.py` — council review management CLI
- `dex_fetch_external.py` — CSV-driven external content pipeline
- `dex_git_stats.py` — 11-repo velocity analytics
- `dex_messages.py` — iMessage export parser (StatCheck)
- `dex_pipeline.py` — ingest pipeline helpers
- `ingest_cache.py` — per-collection file cache
- `dex-convert.py` — format converter (HTML, CSV, JSON, MBOX, VCF)
- `DDL_PRIMER.md` — deterministic system knowledge (~1,450 tokens, runtime-injected)
- `Modelfile.dexjr-v4.7` — behavioral governance for local model
- `dex.ps1` — CLI router (mobile-first)

**Automated schedule:**
- 12:30 AM Sunday — git stats (11 repos, auto-ingest)
- 1:00 AM Sunday — council self-evaluation
- 2:00 AM daily — external content fetch
- 4:00 AM daily — sweep + ingest + backup
- 4:15 AM daily — health check

**Multi-host:** Reborn + Gaming Laptop via Tailscale. AutoCouncil dispatches 3 local + 2 cloud models in parallel with persona injection.

---

## 3. Design Constraints

**Collection suffix:** `_v2` during soak period. Rename ceremony ~4/28 (CR-DDL-SOAK-RENAME-001). Change `COLLECTION_SUFFIX` in `dex_core.py` — one line, propagates everywhere.

**Ratified invariants:**
- Corpus Integrity Is Sacred — never delete chunks without backup + operator approval
- Hard gate on `dex_dave` — `sys.exit(1)` before any DB access
- Ingest cache dedup — SHA-256 content hash per file per collection
- Weighted retrieval — governance-aware ranking (canon 0.90 > archive 0.65)
- DDL_PRIMER.md runtime injection — deterministic context, every query
- No silent failures — every `except` must log (dex-convert.py v1.1)

**Standards:** ADR-CORPUS-001 (collection authority), STD-DDL-BACKUP-001 (backup triggers), STD-DDL-METADATA-001 (chunk metadata)

**Anti-patterns:** No `except: pass`. No hardcoded collection names (use `dex_core.suffixed()`). No hardcoded paths (use `dex_core` constants). No writes to `dex_dave`. No corpus modifications without backup verification.

---

## 4. Current Work Surface

- [closed] Steps 48-62 shipped (2026-04-16/17)
- [closed] Corpus rebuild — 104K garbage deleted, 95K reclassified
- [closed] dex-convert.py silent data loss — 5 bare excepts fixed
- [open] CR-DDL-SOAK-RENAME-001 — _v2 suffix retirement (~4/28)
- [pending] Retrieval quality benchmarks (gap assessment B4)
- [pending] dex_decisions collection + query router (gap assessment)
- [pending] 20 new files in DDL_Ingest awaiting next 4 AM sweep

**Operator priority:** Corpus hygiene is stable. Next focus is product work (AuditForge, WorkBench, Excelligence), not more infrastructure.

---

## 5. Output Contract

**Dex Jr. produces:** Grounded answers with source citations, council review synthesis, structured assessments, corpus analytics.

**Dex Jr. does NOT produce:** Production code (CC's job), medical/clinical advice, content for collections it cannot verify.

**CLI surface (`dex` command):**
```
q/query, b/bridge, c/council, r/review, f/fetch,
health, status, hosts, sweep, backup, ingest,
weights, stats, log, api
```

**Conflict rule:** CLAUDE.md governs build execution. DEX.md governs design constraints. dex_core.py is the runtime source of truth. Ratified CRs win for governance facts. Operator may override any.
