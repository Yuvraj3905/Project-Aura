# Phase 3 — Per-product KB routing: Test Results

Branch `feat/phase3-product-routing`. Date 2026-06-14. Fixes Finding B (broad unscoped
queries blending unrelated KB documents).

## What it does

- Migration 0006: `documents.product` (nullable, indexed).
- Ingest auto-tags each document with a short product label via one LLM call
  (`llm.classify_product`).
- `PRIMARY_PRODUCT` env restricts **unscoped** queries to docs of that product
  (case-insensitive substring of `documents.product`). Priority: manual `documentIds` >
  session sticky scope > primary-product > global. Empty = disabled (backward compatible).
- `POST /documents/retag` backfills product tags for docs ingested before tagging.

## Auto-tagging — accurate

`POST /documents/retag` on the existing 4 docs:
```
fc775c7a  → "Samsung Galaxy Watch"
4b032a81  → "News Website CMS Platform"
16960a4c  → "Ameyo Webhook API"
6e10afb3  → "Aura Gateway Software"
```
Each doc correctly identified from its summary.

## Routing — Finding B FIXED

`PRIMARY_PRODUCT="Galaxy Watch"` (matches only the watch doc):
```
Q: what have you got   → citedDocs={fc775c7a}  off_product_terms=False
   "We've got some fantastic options... **Watch 8 Series** ..."
Q: what do you sell    → honest deflection (scores below the guard within watch docs)
```
Before Phase 3 this query was dominated by the unrelated **News CMS** doc. Now the generic
opener answers from the watch product only — the CMS / Ameyo / Gateway docs are invisible
unless explicitly selected. **Cross-doc blending eliminated at the source.**

## Unit tests — PASS (78)

`test_product.py` (7): `documents_for_product` SQL/params, `set_document_product`,
`documents_missing_product`, `_primary_product_docs` disabled / match / no-match→global
fallback. **78 pytest total.**

## Regression

- `scripts/funnel_test.py` — **PASS**.
- `scripts/storyline_test.py` — **PASS, 8/8** with `PRIMARY_PRODUCT="Galaxy Watch"` active.
  Watch-specific turns route correctly; turn 8 enters the order form. Routing doesn't break
  normal product Q&A.

## Notes

- +1 LLM call per ingest for classification (ingest is already async/slow — negligible).
- `PRIMARY_PRODUCT` empty by default → no behavior change unless configured; this
  deployment sets it to `Galaxy Watch` in `.env`.
- Full multi-product (per-query LLM routing) remains future work; primary-product default
  fits a single-product deployment, which is the real use case here.
