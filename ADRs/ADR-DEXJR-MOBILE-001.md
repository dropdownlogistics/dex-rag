# ADR-DEXJR-MOBILE-001 — Dex Jr. on mobile: we are the backend, the client is dumb

**Status:** Accepted — built and verified 2026-07-31
**Author:** Silas Reeve (DDL-3004) · dispatched by Operator via Marcus Caldwell (Seat 1002)
**Service:** `dex-openai-api.py`, port **8788**

---

## Decision

Expose the **existing** DDL corpus as an OpenAI-compatible endpoint and point a
phone client at it. **Do not let any client build its own index.**

The obvious integration is backwards. Open WebUI and most self-hosted clients
want to own the RAG layer — ingest your files, build their index, answer from
it. Open WebUI is *explicitly designed not to read a ChromaDB that has existing
collections*: it will populate its own collections in an external Chroma but
never read yours. Adopting that would mean **a second index over the same
files** — two sources of truth that can silently diverge.

So the integration is inverted. This service is the backend, reading the live
Chroma collections read-only. The client is a chat surface and nothing more.

## Ports

`8765` ddl-intel · `8787` dex-search-api · **`8788` this** · `8791` dex-chat ·
`8792` ddl-voice · `8801` campaign-cockpit

## The refusal contract

Retrieval without refusal is worse than no retrieval: it launders a guess
through the appearance of a citation. Enforced **twice, on purpose**:

1. **In code, deterministically.** If no chunk scores under `MAX_DISTANCE`
   (0.62 cosine), the service returns a fixed refusal **without calling the
   model at all**. Not a request the model may decline to honour — a code path.
2. **In the prompt, for weak evidence.** Ordered rules, restated after the
   context block for recency.

**A client cannot switch either off.** Client-supplied `system` messages are
*subordinated* — appended as a style preference explicitly ranked below the
rules — never authoritative. A phone must not be able to disable the refusal
contract.

## Verified by execution, 2026-07-31

| check | result |
|---|---|
| starts with no token | **refuses to start** |
| token < 24 chars | **refuses to start** |
| request with no bearer token | **401** |
| request with wrong token | **401** |
| unanswerable query (*capital of Burkina Faso*) | **refused via code path** — model never called |
| answerable query (*What is MindFrame?*) | **answered with sources cited** |
| Chroma collections before vs after | **identical — no second index** |

The refusal test used general knowledge the model certainly holds in training
data. Refusing it proves the contract binds. The positive test is the necessary
counter-test: an endpoint that refuses everything would pass the first test
trivially and be useless.

## Auth — fails closed

Bearer token from `DEXJR_API_TOKEN`, minimum 24 chars. **The service exits
rather than start unauthenticated, even on localhost.** It can query the entire
institutional memory; that does not run open.

Binds `127.0.0.1` by default. `--tailscale` opts into `0.0.0.0` for Tailscale.
No CORS wildcard — this is for native clients, not arbitrary browser origins.
Never expose to the open internet.

`/healthz` is deliberately unauthenticated and deliberately boring: chunk counts
and GPU free, never content.

## Gated collections

`GATED_COLLECTIONS` (currently `dex_dave`) are filtered out at startup and are
unreachable from this service. Collections are opened with `get_collection`,
never `get_or_create` — the service cannot bring a collection into existence.

## GPU gate

Below `VRAM_FLOOR_MB` (1200MB) free, the endpoint returns **503 with an explicit
`gpu_contended` error** rather than answering.

This is the 2026-07-30 lesson applied: a contended run exits clean and reports
plausible garbage. A degraded answer is indistinguishable from a good one; an
explicit error is not. **Fail loudly rather than silently.**

## Consequences

**Gained:** one index, ours. Refusal enforced where it belongs. Any
OpenAI-compatible client works — Conduit is verified real and current, but
nothing is coupled to it.

**Accepted:** answers are bounded by the corpus. That is the point, and it will
sometimes feel worse than a model answering freely. It is not worse.

**Not done:** streaming (`stream: true` is accepted and ignored — responses are
whole). Clients that require streaming will need it added.

**Cosmetic defect, unfixed:** the model-name shortener double-prefixes, yielding
`dex-dex-canon` and `dex-dex-code`. Harmless, ugly, worth a one-line fix.

**Untested:** Conduit itself. The endpoint is verified by curl against the
OpenAI contract; no phone client has connected yet. Per dispatch — if Conduit
does not work as advertised, report and stop rather than shopping for
alternatives.

## Related

- `reborn-cowork/work/MOBILE-ACCESS-EVALUATION.md` (ddl-org) — why the
  integration is inverted; Paseo held pending enforcement
- `dex-search-api.py` — the older service this borrows retrieval shape from.
  **Note:** its `/mindframe/chat` has *no* refusal instruction and tells the
  model to use context "to inform your questions" — the opposite posture. That
  endpoint should not be exposed to mobile without the same contract.
