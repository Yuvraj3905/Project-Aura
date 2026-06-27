# Project Aura — Roadmap

Candidate work for Aura. Items marked ✅ are built; the rest are estimates against the
current `main`.

**Effort:** `S` small (hours–1 day) · `M` medium (multi-day) · `L` large (new model / integration).

## Where we stand

Shipped to `main`: Contextual RAG · hybrid retrieval (vector + BM25-like, RRF + MMR) ·
anti-hallucination guardrails (grounding floor, variant guard, sticky scope) · query
rewrite · sales funnel (leads + orders) · semantic answer cache · eval harness · CPU
speed tuning.

**Done 2026-06-24** — the three top value-to-effort items: **citation → source highlight**,
**cache pre-warm**, **GPU inference path**. See each below. Verified: pytest green, web
typecheck clean, `/chunks` live (valid + 404), pre-warm confirmed (exact + paraphrase both
`cached` in ~0.1 s). GPU path is config-only — needs a CUDA host to runtime-test.

## 01 · Product depth — make answers do more

| Feature | Effort | Value | Notes |
|---|---|---|---|
| ✅ **Citation → source highlight** ★ | S–M | High | **Done.** Each citation is a clickable chip that fetches the source passage (ml-service `GET /chunks/{doc}/{ordinal}` → web `/api/chunks/...`) and shows it inline — a customer can verify every claim against the document text. No new model. |
| True multi-product routing | M | High | Today `PRIMARY_PRODUCT` pins one product. Per-query LLM routing picks the right product's docs per question → real multi-catalog KB. |
| Answer feedback loop | S | Med | 👍/👎 + regenerate on each answer, logged to `llm_usage`. Turns the dashboard into a quality signal, not just a cost meter. |

## 02 · Sales funnel — deepen it

The funnel captures one order or one lead; real deals are multi-item and need follow-through.

| Feature | Effort | Value | Notes |
|---|---|---|---|
| Quote / multi-item cart | M | High | Accumulate several products before ordering; compute totals. Replaces single-product `order_form`. |
| Order & lead email | S | Med | Orders/leads write a DB row only. Send real SMTP confirmation + notify a specialist. |
| Lead scoring & handoff | M | Med | Tag leads by intent strength; push hot leads to Slack/email for fast human follow-up. |

## 03 · Answer quality — tighten and measure

Eval harness today is pass/fail. Quality work needs graded measurement to know if a change helped.

| Feature | Effort | Value | Notes |
|---|---|---|---|
| ✅ Cache pre-warm | S | High | **Done.** `scripts/prewarm_cache.py` calls `/answer` for a FAQ list at deploy so answers land in Redis + the persistent semantic cache; paraphrases then serve at 0 tokens, ~0.1 s. |
| Cross-encoder reranker | M | Med | Rerank fused top-N before prompting. Higher precision than RRF alone, but adds a second model to the CPU budget. |
| Graded LLM-judge evals | M | Med | Score answers 1–5 over a fixed question set instead of binary asserts. Track quality numerically; catch silent regressions. |

## 04 · Ops & hardening — before it leaves localhost

Today the stack is loopback-bound and trusts its caller. A real deployment needs auth, speed, visibility.

| Feature | Effort | Value | Notes |
|---|---|---|---|
| ✅ GPU inference path | S | High | **Done.** `docker-compose.gpu.yml` adds an NVIDIA device reservation to `ollama`; run with `-f docker-compose.yml -f docker-compose.gpu.yml`. Generation is 99.9% of response time; GPU is a 10–50× win, near-zero code. (Untested here — no GPU on the dev box.) |
| Chat-side auth | M | High* | Only `/dashboard` is gated; chat + upload are open on loopback. Add real auth before exposing the UI off `127.0.0.1`. |
| Metrics endpoint | S–M | Med | Structured logs + `/metrics` (latency, cache hit-rate, queue depth) for Prometheus/Grafana. |

\* High value only if deployed off-localhost; on a single dev box the network gate already covers it.

## Suggested order — best value-to-effort first

1. ~~**GPU inference path** — S~~ — ✅ done.
2. ~~**Cache pre-warm** — S~~ — ✅ done.
3. ~~**Citation → source highlight** ★ — S–M~~ — ✅ done.
4. **Order & lead email** — S — closes the loop the funnel implies. *(next up)*
5. **Answer feedback loop** — S — dashboard becomes a quality signal.
6. **Quote / multi-item cart** — M — real deals aren't single-item.
7. **True multi-product routing** — M — only if the KB goes multi-catalog.
8. **Graded LLM-judge evals** — M — needed before any quality tuning.
9. **Cross-encoder reranker** — M — precision gain vs added CPU cost.
10. **Lead scoring & handoff** — M — needs outbound integration.
11. **Chat-side auth** — M — gate before any off-localhost deploy.
