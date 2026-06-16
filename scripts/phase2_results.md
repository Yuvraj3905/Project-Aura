# Phase 2 — Retrieval Quality + Chat Formatting: Test Results

Branch `feat/phase2-retrieval-quality`. Stack: `llama3.2:3b` on CPU. Date 2026-06-14.
Drivers: `scripts/phase2_test.py` (API), Chrome DevTools (UI), `scripts/storyline_test.py`
+ `scripts/funnel_test.py` (regression).

## Unit tests — PASS (53)

`docker compose run --rm --no-deps --entrypoint pytest ml-service tests/` → **53 passed**.
New: `test_hybrid.py` (RRF fusion ordering/dedupe/limit, MMR dedupe),
`test_semantic_cache.py` (scope_key, lookup hit/miss/threshold, insert).

## API tests — PASS (`scripts/phase2_test.py`)

```
=== HYBRID: keyword retrieval ===
  (118s) grounded=True cites=5
  answer: ...rotating bezel... **Watch 8 Classic (46mm)** ...
  PASS — keyword query is grounded
  PASS — mentions the Classic / bezel

=== SEMANTIC CACHE: paraphrase reuse ===
  Q1 (90s) cached=False: ...44mm ... **1.47 ”** ...
  PASS — first ask not cached
  Q2 (0.0s) cached=True   ← paraphrase "How big is the screen on the 44mm Watch 8?"
  PASS — paraphrase served from cache
  PASS — cache hit is fast (<5s) :: 0.0s
  PASS — cached answer matches original
```

- **Hybrid retrieval (BM25+vector RRF)** returns grounded answers; keyword queries surface
  the right chunk. Lexical arm wired with `websearch_to_tsquery` + `ts_rank_cd`.
- **Semantic answer cache** turns a 90s generation into a **0.0s** cache hit on a
  paraphrase — directly attacks the latency complaint. Threshold tuned to **0.92** from
  measured data: bge-small scores real paraphrases ~0.94 and different questions ~0.69, so
  0.92 catches rewordings with a wide safety margin.

## UI tests — PASS (Chrome DevTools, screenshot `scripts/phase2_ui_markdown.png`)

- **Markdown rendering** ✓ — bot answers render **bold** specs/model names and bullet
  lists (react-markdown + remark-gfm) instead of raw `*`/`**`. Screenshot confirms styled
  headings + bullets in the chat bubble.
- **`+ New chat` button** ✓ — present, resets the conversation, disposes the old session.
- **`cached` badge** ✓ — shows when an answer is served from cache.

## Bugs found + fixed during testing

1. **500 on scoped hybrid query** — `_lexical_candidates` built SQL params in the wrong
   order when `document_ids` was present (the `ANY(%s)` doc-filter placeholder precedes the
   tsquery, but the query text was passed first → `malformed array literal`). Fixed by
   constructing params in placeholder order. Caught because the 2nd turn of a session is
   scope-locked. **Re-tested: PASS.**
2. **Semantic cache never hit** — 0.95 threshold sat just above real paraphrase similarity
   (~0.94). Lowered to 0.92 (measured). **Re-tested: PASS.**

## Findings (pre-existing / out of Phase-2 scope) — RECOMMEND follow-up

- **A. NLU misrouted product-spec questions to `buy_order` — FIXED.** "Tell me about the
  Galaxy Watch 8" / "What size display does the 44mm have?" triggered the **order form**
  instead of RAG, derailing the whole conversation (storyline went 8/8 → broken: turns
  4-8 stuck in the order form). Root cause: `tech_query` training examples were all
  API/OAuth/TLS flavored (zero product-spec phrasing), while the funnel phase added
  watch-heavy `buy_order` examples that stole spec questions. Introduced on `main` by the
  funnel work; caught here by the regression run. **Fix:** added 16 product-spec examples
  to the `tech_query` intent and retrained (`aura-phase3`). Post-fix routing: spec
  questions → `tech_query` 1.00, purchase intent → `buy_order` 1.00. Storyline back to 8/8.
- **B. Global (unscoped) queries mix unrelated KB documents.** "what have you got" returned
  an answer dominated by the unrelated **news-CMS** doc (`Changes & Requirements.pdf`)
  alongside watch content — the test KB holds 3 unrelated products (watch, news-CMS, Ameyo
  webhook). Sticky scope only engages *after* the first grounded answer locks it, so a
  broad opener locks to a mixed set; hybrid's lexical arm can amplify cross-doc keyword
  matches. This is the "many products in one KB" challenge — real fix is per-product KB
  routing (a future phase). For single-product deployments this does not occur.

## Regression

- `scripts/funnel_test.py` — **PASS** (order + lead + bad-email).
- `scripts/storyline_test.py` — **PASS, 8/8** after the finding-A NLU fix. Spec turns route
  to RAG and render markdown (bold specs, bullet comparisons, a model/spec table); turn 8
  "how do I place an order?" correctly enters the order form with no news-CMS bleed.

## Net result

Phase 2 retrieval-quality features (hybrid RRF retrieval, MMR dedupe, semantic answer
cache) and chat markdown rendering all verified at unit, API, and UI levels. Two bugs
fixed during testing (scoped-hybrid SQL param order; semantic threshold). One regression
fixed (tech_query NLU). Finding B (multi-product KB cross-doc mixing on broad unscoped
queries) remains — it is the "many products in one KB" problem, slated for a future
per-product routing phase; single-product deployments are unaffected.
