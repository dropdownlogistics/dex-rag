# Modelfile v4.1 — Changelog

## Basis
- v4.0 system prompt + CR-MODELFILE-V4-001 council review (10 seats, 9 responding)
- 9/9 responding seats returned REVISE
- All REVISE items addressed below

## Decision Authority
- CottageHumble tokens: RESTORE (operator call)
- Canon/archive distinction: RESTORE (operator call)
- All other open items: Seat 1002 judgment (operator delegated)

## Changes from v4.0

### Parameters
| Parameter | v4.0 | v4.1 | Basis |
|-----------|------|------|-------|
| num_ctx | 4096 | 8192 | Unanimous (9/9). 4096 starved CR prompts. |
| num_predict | 1024 | 2048 | Caldwell/DeepSeek/Bennett. CR reviews need room. |
| temperature | 0.3 | 0.3 | No change. |
| top_p | 0.9 | 0.9 | No change. |

### System Prompt Additions

**BANNED OUTPUT PATTERNS (expanded)**
- v4.0 had 3 anti-patterns
- v4.1 has 18 anti-patterns
- Sources: LeChat (conversational closers), Grok/Perplexity/Bennett (Key Takeaways), Grey (SWOT/consulting frameworks), Gemini (conversational filler), Sinclair (advisor-speak hedges)
- Rationale: 7B model needs explicit negative constraints. Dense blacklist > short hints.

**COTTAGEHUMBLE DESIGN SYSTEM (restored)**
- Full palette: navy, card, cream, crimson, amber, violet, green, blue
- Full font stack: Space Grotesk, JetBrains Mono, Source Serif 4
- Explicit bans: no #ffffff, no Inter, no light mode, no white tables
- Rationale: Operator call. Q12 calibration scored Partner with tokens present, regresses without them.

**SOURCE AUTHORITY (restored)**
- Four-tier model: dex_canon > ext_canon > ddl_archive > ext_social
- Conflict resolution rule: canon over archive, flag conflicts
- Rationale: Operator call. Prevents archive material being treated as authoritative.

**OPERATOR CONTEXT (restored)**
- ADHD awareness, burst-mode sessions, evening build time
- No manufactured urgency, no pathologizing velocity
- Star schema thinking as universal architecture
- Rationale: Seat 1002 judgment. Calibration scores proved behavioral context matters. DeepSeek and Grok concurred.

### System Prompt Preserved from v4.0
- Reframe (document analyst): LOCK, no changes
- Task framing + authorization clause: LOCK, no changes
- Response rules: LOCK, minor addition (cite minimally)
- CR- posture (strict LOCK/REVISE/REJECT): LOCK, no flex mode added
- Long prompt handling + [TRUNCATED]: LOCK, no changes
- Identity boundary (seat 1010): LOCK, no changes
- "I don't know" fallback: LOCK, no changes

### What Was NOT Added
- Gemini's "closed-loop internal audit environment" clause: solves no documented failure
- DeepSeek/LeChat's flex mode for CR- posture: reintroduces ambiguity that caused Test 1
- Sinclair's social/network analysis clause: seat-specific, not model-level governance
- LeChat's TASK_TYPE prefix system: adds routing complexity the 7B doesn't need

## Token Budget
- v3: ~2,100 tokens
- v4.0: ~350 tokens
- v4.1: ~580 tokens (estimated)
- Reduction from v3: 76%
- Increase from v4.0: justified by restored governance (CottageHumble, canon/archive, operator context)

## Estimated Context Budget at num_ctx 8192
| Component | Tokens |
|-----------|--------|
| System prompt | ~580 |
| Script governance injection | ~800 (pre-refactor) |
| RAG chunks (5 chunks) | ~2,000 |
| User prompt | ~500 |
| **Available for generation** | **~4,312** |
| num_predict cap | 2,048 |

Comfortable headroom. No starvation risk.

## Deployment
```bash
ollama create dexjr -f Modelfile.dexjr-v4.1
ollama list | grep dexjr
```

## Test Sequence
Re-run all three evidence prompts:
1. CR-CORPUS-ARCH-001 → expect: line-item verdicts, no PM template, no banned patterns
2. CR-CONTENT-SOURCES-001 → expect: completion within 120s, no truncation at 8192
3. CR-MEMOREASE-001 → expect: document analysis, no refusal

## Rollback
```bash
ollama create dexjr -f Modelfile.dexjr-v4
```
Preserve v4.0 and v3 as known-good fallbacks.

### Rollback Triggers
1. Hard refusal on non-clinical prompt: 1 instance = investigate, 2 instances = rollback
2. PM template output (Identified Risks, Recommendations, etc.): pattern across 3 prompts = rollback
3. CottageHumble violation (#ffffff, Inter font): immediate rollback on first occurrence
4. Calibration regression below 70% Judgment+: rollback and diagnose
5. Sustained truncation (>20% of bridge queries): reduce num_predict or investigate chunk count

## Next Step (Separate Task)
Refactor bridge and council script injection to:
- Remove governance blocks duplicated by v4.1 system prompt
- Align injection framing with "document analyst" language
- Target: ~400 tokens injection (down from ~800)
