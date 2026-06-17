# Anti-hallucination + cross-doc fixes — Test Results

Branch `feat/phase2-retrieval-quality`. Date 2026-06-14. Follows the two issues found in
Phase 2 testing.

## FIX-1: Model-name hallucination guard — PASS

Problem: "what are the features of the watch 8 ultra" invented a non-existent "Watch 8
Ultra" with fabricated specs (the retrieval guard only checks chunk relevance, not invented
entities — generic Watch 8 chunks scored high, the LLM bolted "Ultra" on top).

Fix (`ml-service/app/rag/answer.py`):
- `_unsupported_variant(query, chunks)` — if the query names a variant qualifier
  (`ultra/pro/max/plus/mini/lite/ultimate/fe/edge`) that appears in **no** retrieved chunk,
  the model isn't in the KB. `_refusal()` then returns `VARIANT_NO_MATCH` (a salesy "I don't
  carry that model" deflection) **without calling the LLM**.
- SYSTEM_PROMPT hardened: never invent a model/variant not in the context.
- Flag `VARIANT_GUARD`.

Live:
```
Q: what are the features of the watch 8 ultra
   (8s) grounded=False
   A: "Hmm, I don't have that exact model in our lineup right now — and I'd never want to
       guess at specs..."
   → no invented "Ultra", no fake specs. ✓
```

## FIX-2: Cross-document blending — IMPROVED (blending eliminated)

Problem: broad unscoped queries blended an unrelated KB doc (news-CMS
`Changes & Requirements.pdf`) into a watch answer.

Fix (`ml-service/app/rag/retrieve.py`): `dominant_doc_filter` — on an unscoped query, keep
only chunks from the single top-scoring document, so unrelated docs can't bleed into one
answer. Scope then locks to that doc. Flag `ANSWER_SINGLE_DOC`.

Live:
```
Q: tell me about the galaxy watch 8        → citedDocs={fc775c7a}  news_bleed=False ✓
Q: does the watch have GPS and what battery → citedDocs={fc775c7a}  news_bleed=False ✓
Q: what have you got                        → citedDocs={4b032a81}  (single doc, no blend)
```
Product-specific queries (the realistic case) now stay cleanly on the watch doc — **no
more blending**. The deliberately-generic opener ("what have you got") still lands on
whichever single doc lexically wins (here the news-CMS doc), because nothing tells
retrieval that watches are *the* product. Fully resolving generic cross-product queries
needs **per-product KB routing** (document product tags + a routing/default step) — a
dedicated future phase. `dominant_doc_filter` is the deterministic, no-extra-LLM
mitigation: it guarantees a single-product answer instead of a blended one.

## Unit tests — PASS (72)

`test_guards.py` (8): variant-guard flags invented model / allows real variant / ignores
qualifier-free queries / passes when qualifier in context / empty chunks; dominant-doc
filters to top document / no-ops single doc / empty. **72 pytest total.**

## Regression
- `scripts/funnel_test.py` — **PASS**.
- `scripts/storyline_test.py` — **PASS, 8/8** (guards didn't regress; watch-specific turns
  stay grounded on the watch doc, turn 8 enters the order form). Confirms the variant guard
  and dominant-doc scoping don't break normal product Q&A.

Note: during this work the previously-killed stray `docker compose up` had taken several
containers down; restored with `docker compose up -d` (rasa reloaded `aura-phase3`).
