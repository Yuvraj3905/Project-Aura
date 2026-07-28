# Project Aura — Competitive Analysis

**What the rest of the chatbot market lacks, and what Aura already has.**

Date: 2026-07-28 · Scope: commercial AI support/sales chatbots, RAG platforms, bot
builders, classic NLU platforms, and self-hosted open-source stacks · Baseline: Aura on
`main` (commit `4680a3b`).

---

## 1. Executive summary

The chatbot market in 2026 is large, well funded, and failing at the one thing it sells:
being trusted. Customer preference for a human has *risen* to 85% while preference for AI
fell to 5%. Frustration with AI agents rose from 54% to 59%. AI agents score 52% CSAT
against 82% for humans. The two most-cited frustrations are "can't escalate" (22%) and
**"the chatbot is uncertain"** (22%).

That is not a model-quality problem. It is an architecture problem, and it repeats across
nearly every vendor:

1. **They answer when they shouldn't.** Commercial bots are tuned to always produce
   something, because early user testing punished "I'm not sure". There is no hard
   groundedness floor that stops generation.
2. **You cannot verify the answer.** Most vendors show a link to an article, not the
   passage the claim came from.
3. **Retrieval is a black box.** You cannot see or tune chunking, fusion, or thresholds.
4. **Your documents leave your building.** Ingest, embed, and generate are three separate
   third-party data-transfer events.
5. **Cost scales with success.** Per-resolution billing ($0.99–$2.00) means the better the
   bot deflects, the bigger the invoice — and the vendor defines "resolution".
6. **Marketed accuracy is not delivered accuracy.** Ada markets "up to 83%", ships 30–50%.
   Zendesk markets "80%+", ships 39–66%. Intercom Fin markets 76%, ships 45–53%.
7. **There is no eval harness.** Teams spot-check by hand and cannot answer "did this
   change help?"

Aura addresses items 1, 2, 3, 4, 5, and 7 by design — not as add-ons, but as the load-bearing
parts of the architecture. It is a **verifiable, self-hosted, zero-marginal-cost RAG sales
engineer** with a hard refusal floor, clickable source passages, a fully exposed retrieval
pipeline, and a gating eval harness.

Where Aura loses is equally clear and worth stating up front: **no omnichannel, no human
handoff, no SSO/RBAC, no compliance certifications, no managed hosting, and 50–130 s CPU
inference.** It is architecturally stronger and operationally narrower than the field.

Two findings from verifying the claims against source rather than against the README, both
detailed in §7.1–7.2 and both cheap to fix: **the network gate covers four of eight services,
not all eight**, and **only 8 of ~28 documented config knobs are actually passed into the
container** (which also means SMTP cannot currently be enabled the way the README describes).
Neither undermines the architecture; both undermine the claim that it is deployable today.

---

## 2. Method

- Surveyed five vendor classes (§3) against nine capability axes (§5).
- Pulled concrete limitations from vendor docs, third-party teardowns, and review
  aggregations rather than marketing pages.
- Verified Aura's claims against source: `README.md`, `.env.example`, `ml-service/app/`,
  `web/`, `rasa/`, `db/migrations/`, `scripts/`.
- Where a number is marketed vs. observed, both are given.

Bias disclosure: several "limitations of X" articles are published by competitors of X
(myaskai, sitegpt, botpress, Fini, Lorikeet, Onyx). Their *directional* claims are
corroborated across sources and against vendor documentation; treat single-source
percentages as indicative.

---

## 3. The market, in five classes

| Class | Examples | Core proposition | Structural weakness |
|---|---|---|---|
| **A. Enterprise support AI agents** | Intercom Fin, Zendesk AI, Ada, Decagon, Sierra, Forethought, Fini | Deflect tickets inside an existing helpdesk | Per-resolution billing; helpdesk lock-in; retrieval opaque; cloud-only |
| **B. Upload-and-go RAG bots** | Chatbase, CustomGPT, SiteGPT, Denser, Wonderchat, Dante | 5-minute setup over your docs | Storage caps, credit walls, no flow control, no human handoff, no on-prem |
| **C. Bot builders / agent platforms** | Botpress, Voiceflow, YourGPT, Dify, Flowise, n8n | Visual flows + LLM nodes | You build retrieval and guardrails yourself; per-editor seat cost |
| **D. Classic NLU platforms** | Rasa, Dialogflow CX, Amazon Lex, Copilot Studio, watsonx Assistant | Deterministic intent/slot dialogue | Intent-based NLU is brittle and expensive to train; LLM support bolted on |
| **E. Self-hosted open source** | AnythingLLM, Open WebUI, LibreChat, Onyx (ex-Danswer), RAGFlow, Verba | Private, free, local models | Generic Q&A only — no business funnel, no domain guardrails, no evals |

Aura is a **hybrid of D and E with the guardrail discipline of nothing else in the list**:
Rasa for deterministic transactional forms, self-hosted local inference for privacy and
cost, plus a verifiable RAG core with a refusal floor.

---

## 4. Universal failure modes (what everyone lacks)

### 4.1 No hard abstention floor — bots answer when they don't know

This is the single largest gap in the market. Research on LLM abstention finds mainstream
models "often fail to abstain appropriately on unanswerable questions", inventing missing
constraints and responding with high confidence. The reason is commercial, not technical:
vendors found that assistants saying "I'm not sure" frustrated testers, so fine-tuning
favoured answers over refusals.

Guidance now exists (`if no approved source retrieved` / `if confidence < 0.75`, abstain) but
it is advisory. **No Class A or B vendor exposes a numeric groundedness floor you can set.**

> **Aura:** `RETRIEVAL_MIN_SCORE=0.45`. If the best retrieved chunk's cosine score is below
> the floor, **the LLM is never called** and Aura returns a fixed refusal. Not a prompt
> instruction — a code path (`ml-service/app/rag/answer.py:94-96`, `345-349`). Rationale is
> in the source: bge-small baselines unrelated text ~0.3, relevant matches ~0.5–0.8, so 0.45
> blocks off-topic before spending a token. Refusal is written salesy on purpose ("I'd love
> to track them down for you") rather than as a dead end.
>
> Two known weaknesses, stated honestly: the guard tests **only the top chunk's score**, so
> one spuriously-high chunk admits the whole (possibly weak) context to the prompt; and
> refusals are written into both the 1 h Redis cache and the persistent semantic cache, so a
> transient retrieval failure can serve "I don't have that" to paraphrases for an hour.

### 4.2 Citations without verifiability

Citation support exists at the *link* level almost everywhere. Passage-level verification is
rare — Denser (paragraph-level jump), Palantir AIP, and CustomGPT are the notable
exceptions. Class A vendors typically surface "based on article X" with no way to see the
sentence the claim came from.

> **Aura:** every answer renders clickable source chips; clicking one fetches
> `GET /chunks/{doc}/{ordinal}` (proxied at `web /api/chunks/...`) and reveals the exact
> passage inline. A customer can audit every claim against the document text without
> leaving the chat.

### 4.3 Opaque, un-tunable retrieval

Best practice in 2026 is well established: contextual chunk enrichment, hybrid
sparse+dense retrieval, RRF fusion, diversity-aware selection, reranking. The measured gains
are large:

- Contextual embeddings: **−35%** retrieval failures; + contextual BM25: **−49%**; +
  reranking: **−67%** (Anthropic).
- Hybrid + RRF: recall@10 from **65–78% → 91%**; +7.4% NDCG on WANDS.

Yet almost no Class A/B product lets you *see*, let alone tune, chunk size, fusion weights,
candidate depth, or dedupe thresholds. Zendesk goes the other way and warns that "too many
sources can reduce accuracy and increase latency" — pushing the trade-off onto you with no
knobs. Chatbase users report temperature changes producing no meaningful difference.

> **Aura:** the entire pipeline is *readable and tunable in source* — `CHUNK_TOKENS=512`,
> `CHUNK_OVERLAP=64`, `HYBRID_RETRIEVAL=true`, `HYBRID_CANDIDATES=20`, `MMR_DEDUPE=true`,
> `MMR_DUP_THRESHOLD=0.97`, `RETRIEVAL_TOP_K=4`, `RETRIEVAL_MIN_SCORE=0.45`, `RRF_K=60`.
> Contextual RAG is a hierarchical map-reduce document summary (`SECTION_CHARS=6000` map
> windows, 400-char prefix) prepended to every chunk before embedding. Every retrieved chunk
> carries its cosine score all the way to the guard.
>
> ⚠️ **Caveat found during verification:** `docker-compose.yml` passes only **8** env vars to
> `ml-service` and there is no `env_file:`, so the other ~20 documented knobs are **inert in
> the Docker deployment** and pinned to `config.py` defaults. Behaviour is currently correct
> by coincidence (the booleans default `True`, chunk sizes match), but the knobs are not
> actually live. Plumbed today: `REDIS_URL`, `OLLAMA_MODEL`, `OLLAMA_NUM_CTX`,
> `OLLAMA_NUM_PREDICT`, `OLLAMA_KEEP_ALIVE`, `RETRIEVAL_TOP_K`, `RETRIEVAL_MIN_SCORE`,
> `PRIMARY_PRODUCT`. Fixing this is a one-line `env_file:` addition and is the cheapest
> credibility win in the repo — the transparency claim is real in code but not yet real in
> deployment.

### 4.4 Data leaves your perimeter

A typical cloud RAG pipeline routes documents through at least three external APIs; under
GDPR each is a transfer event needing a DPA, a data-flow record, and an answer when the
regulator asks where the client's contract went. Add the US CLOUD Act and the EU AI Act and
regulated European buyers cannot use most of Class A or B at all. Zendesk explicitly
"can't guarantee 100% removal" of PII.

On-prem is not legally *mandated* by GDPR or HIPAA — but it makes both structurally
trivial to satisfy, which is why it keeps appearing as a hard procurement requirement.

> **Aura:** every component is local — Postgres+pgvector, Redis, Ollama (`llama3:8b`),
> `bge-small-en-v1.5` baked into the image so it starts offline. No document, query, chunk,
> embedding, or answer touches a third party. Zero DPAs required.

### 4.5 Cost that grows with success

| Vendor | Model | Notes |
|---|---|---|
| Intercom Fin | **$0.99 / resolution** + seats (~$85/seat/yr-billed) | 20 seats + 1,350 resolutions ≈ **$3,036/mo** |
| Zendesk AI | **$1.50** committed / **$2.00** PAYG per resolution | Requires Enterprise (~$115/agent/mo); 5–15 free resolutions/mo |
| Ada | ~**$30K/yr** entry, median ~**$70K**, up to **$300K+** | Needs ≥300k annual conversations to fit; no trial |
| Decagon | median ~**$386K/yr** | White-glove onboarding |
| Chatbase | $19–$500/mo credits; **credits don't roll over**; +$15–20/1k extra; **$199/mo** white-label | Agent stops when credits run out |
| Voiceflow | ~$50/mo Pro, **per-editor**; 5-person Business ≈ **$750/mo in seats alone** | Before credits |
| Botpress | Free tier, 100 conversations/mo, usage-scaled | Most generous of the class |

Two structural problems: **"resolution" is vendor-defined**, and **cost rises as the AI
improves**. Chatbase and Voiceflow users report being unable to forecast a monthly bill.

> **Aura:** marginal cost per answer is **$0**. Local inference, no token metering, no
> per-seat charge, no per-resolution charge. The dashboard's *LLM usage & cost vs ChatGPT*
> panel reads `llm_usage` and prices the same token volume against `gpt-4o` /
> `gpt-4o-mini` / `gpt-3.5-turbo` so the avoided spend is a number, not a claim.
>
> Honest framing: self-hosting breaks even against frontier APIs somewhere around
> **35M tokens/month** (with vLLM serving) to **160–256M tokens/month** (Ollama-class
> serving, mid-2026). Below that, Aura's cost advantage is about *predictability and
> privacy*, not raw dollars — the infra still has to run.

### 4.6 No semantic caching

31% of LLM queries are semantically similar to a previous request. Semantic caching cuts
inference cost 30–70%; GPT Semantic Cache measured **68.8% fewer API calls** at
**61.6–68.8% hit rates** with **>97% positive-hit accuracy**. Almost no chatbot vendor ships
this — and those on per-resolution billing have a direct financial disincentive to.

> **Aura:** three cache layers. Redis exact-match query-embedding cache (24 h) and grounded
> answer cache (1 h, flushed when a new document goes ready), plus a **pgvector semantic
> answer cache** that reuses an answer when a new query embeds within
> `SEMANTIC_CACHE_THRESHOLD=0.92` cosine *within the same doc scope* — paraphrases land
> ~0.94, unrelated questions ~0.69. Cached answers return in **~30 ms** vs 50–130 s CPU
> generation. `scripts/prewarm_cache.py` seeds an FAQ list at deploy so the first real user
> gets an instant, zero-token answer.

### 4.7 Multi-turn context collapse

**60% of follow-up messages contain unresolved coreferences.** "What about that one?"
retrieves nothing. Query rewriting is the fix and is an active differentiator for a handful
of vendors (Alhena's 4-layer contextualizer, Haystack recipes) — meaning most platforms
still send the raw pronoun-laden turn to the retriever. It is also the mechanism behind
Ada's "stuck in a playbook" complaint and the 62% of escalations attributed to
comprehension failures.

> **Aura:** `QUERY_REWRITE=true`. Likely follow-ups (pronouns, very short messages) are
> rewritten into standalone questions using `QUERY_REWRITE_MAX_TURNS=3` recent (q,a) pairs
> held per session in Redis; standalone questions skip the step to avoid the latency.
> "what is *its* battery" → "…battery of the Galaxy Watch 8 Classic".
> `scripts/rewrite_test.py` asserts it.

### 4.8 Cross-document and variant bleed

Class A/B products retrieve over one flat index. Ask about the 44 mm variant of a product
and you get the 40 mm spec, confidently. Nothing in the market names this failure mode, let
alone guards it.

> **Aura:** three distinct guards.
> - **`VARIANT_GUARD=true`** — if the query names a model variant that appears in *no*
>   retrieved chunk, refuse rather than substitute a sibling variant's spec. Origin is a real
>   logged failure: "what are the features of the watch 8 ultra" invented a non-existent
>   product with fabricated specs (`scripts/guardfix_results.md`). Implementation is a
>   hardcoded 9-word English set (`ultra, pro, max, plus, mini, lite, ultimate, fe, edge`),
>   so it will miss a qualifier outside the list — e.g. "Watch 8 **Titanium**".
> - **`ANSWER_SINGLE_DOC=true`** — an unscoped query is answered from the top-matching
>   document only; no cross-document blending.
> - **Sticky session scope** — the first grounded answer in a session locks retrieval to
>   the documents it cited (`session_id` on `/answer`), so a conversation cannot drift into
>   another product's manual mid-thread.
>
> `scripts/storyline_test.py` asserts no cross-doc bleed; `scripts/comparison_test.py`
> asserts a genuine "Watch 8 vs Watch 7" question still covers both products while staying
> grounded.

### 4.9 No eval harness — "did we actually improve anything?"

Teams still validate with manual spot-checks and one-off experiments, producing slow
iteration and mystery production failures. Dedicated eval tooling exists (DeepEval,
Braintrust, Botium, Cekura, bottest.ai) but is a *separate purchase and separate
integration*; Class A/B vendors ship no regression gate with the product. Automated scoring
also struggles with nuance, which is why domain-specific assertions still matter.

> **Aura:** `scripts/run_evals.sh` runs pytest plus five live-stack assertion scripts and
> gates on exit codes — `funnel_test` (order/lead capture, bad-email rejection),
> `phase2_test` (hybrid retrieval + semantic-cache paraphrase reuse), `rewrite_test`
> (follow-up resolution), `comparison_test` (multi-product coverage without hallucination),
> `storyline_test` (persona, sticky scope, no bleed). `--fast` skips the slow LLM scripts.
> A passing run *is* the definition of no regression. Retrieval-quality results are logged
> in `scripts/phase2_results.md`.

### 4.10 Knowledge ingestion limits nobody advertises

- **Ada** cannot natively ingest past support tickets, PDF uploads, internal wikis, Google
  Docs, Confluence, or Notion; caps at 50,000 articles. One reviewer: "pretty limited by
  what was only in our official help center."
- **Zendesk** imports knowledge "on a one-time or recurring basis — not queried live",
  so answers go stale between syncs.
- **Chatbase** caps training content at **400 KB free / 60 MB Pro** and acknowledges
  "data-size limits can hurt performance on large or complex datasets"; most plans require
  manual re-upload to refresh.
- **Intercom Fin** is bounded by help-centre prose — "the model has never seen how your team
  actually resolves tickets, only what you've written about how you think you resolve them."

> **Aura:** `.pdf`, `.docx`, `.txt`, `.md` up to **50 MB per file**, unlimited documents
> (bounded only by disk). Ingestion is a real async pipeline: upload → BullMQ job (Redis
> db1) → Node worker → ml-service `/ingest` → extract → hierarchical map-reduce summary →
> 512-token chunks with the summary prepended → `bge-small` 384-dim embeddings → pgvector
> → `NOTIFY kb_ready` → WebSocket status push. Documents are auto-tagged with a product at
> ingest, and `POST /documents/retag` backfills older ones.

### 4.11 Implementation burden hidden behind "no-code"

Ada's enterprise deployment runs **8–16 weeks** despite no-code marketing; reviewers call it
"a huge, time-consuming project" and "not something you can just sign up for and get
running by yourself". Ada also requires Zendesk or Salesforce for full features. Zendesk's
own progression to headline resolution rates requires "flows, backend data, and regular QA".

> **Aura:** `cp .env.example .env` → `docker compose run --rm rasa train` →
> `docker compose up -d --build`. Two commands and a model train. No vendor call, no
> onboarding contract, no helpdesk prerequisite.

### 4.12 Intent-based NLU is a dead end — but the alternative loses determinism

Intent/entity NLU is now widely considered outdated: predefined intents constrain what the
bot can absorb, and training data cost is "in the millions of examples and dollars".
Dialogflow struggles with rigid workflows and limited data control; Lex's LLM support is an
add-on bolted onto slot-filling; Rasa demands Python fluency and spaCy is memory-hungry.

But pure-LLM platforms lost something real: **a deterministic transactional path**. An LLM
asked to collect an email and write an order row will sometimes not.

> **Aura takes both sides deliberately.** Rasa handles *transactions* — `ticket_form`,
> `order_form`, `lead_form` are finite state machines with real validation (malformed emails
> are rejected and re-asked) writing real rows. The LLM handles *knowledge*. Routing is per
> intent: `tech_query` → grounded RAG stream, `open_ticket` → `/tickets`, `buy_order` →
> `/orders`, `request_contact` → `/leads`. Deterministic where determinism matters,
> generative where it doesn't.

### 4.13 Support bots and sales bots are different products

Class A is support-shaped: deflect a ticket. Class B is FAQ-shaped. Conversational commerce
is a separate market (Tolstoy, ChatBot.com, ManyChat) where AI depth is thin — "ManyChat's
AI layer is lighter than what dedicated conversational AI tools offer". Almost nothing
answers a deep technical question *and* closes.

> **Aura is one funnel.** The same session that answers "does the API support OAuth 2.0 with
> custom claims" from the spec can then run `order_form` and write an `orders` row, or
> `lead_form` and write a `leads` row tagged with what the prospect was asking about, or
> `ticket_form` and open a `support_tickets` row — with SMTP notifications to the customer
> and `SALES_EMAIL` on order and lead (no-op when `SMTP_HOST` is unset, so the funnel never
> blocks on mail). Rasa persists slots in Postgres with a 24-hour session expiry, so a
> multi-day client conversation resumes on the same `sessionId`.

### 4.14 Vendor lock-in

The standard 2026 lock-in checklist asks: can we swap the model, is the knowledge layer
separate from the model layer, does it cite sources, does it do hybrid search, can it
connect to our sources, can we govern permissions, does it speak open standards like MCP,
do we keep control of our data? Hyperscaler RAG services fail the first; per-resolution
Class A vendors fail the last.

| Lock-in criterion | Aura |
|---|---|
| Swap the LLM | ✅ `OLLAMA_MODEL` env var — `llama3:8b` → `llama3.2:3b` in one line |
| Knowledge layer separate from model layer | ✅ pgvector store, independent of Ollama |
| Cites sources | ✅ passage-level, clickable |
| Hybrid keyword + vector | ✅ default on, RRF-fused |
| Connect to our knowledge sources | ⚠️ file upload only — no Confluence/Drive/Slack connectors |
| Permissions & governance | ❌ single-tenant, no RBAC |
| Open standards / MCP | ❌ REST only |
| We keep control of our data | ✅ 100% — own Postgres, own disk |

**6 of 8, and the two failures are missing features, not architectural traps.** Every byte is
in a Postgres database you own; there is no export to negotiate.

---

## 5. Head-to-head matrix

Legend: ✅ full · ⚠️ partial / paid tier / DIY · ❌ absent

| Capability | Aura | Intercom Fin | Zendesk AI | Ada | Chatbase | Botpress / Voiceflow | AnythingLLM / Open WebUI |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Hard numeric groundedness floor (refuse below threshold) | ✅ 0.45 | ❌ | ❌ | ❌ | ❌ | ⚠️ DIY | ❌ |
| Passage-level clickable citation | ✅ | ⚠️ article link | ⚠️ article link | ⚠️ | ⚠️ | ⚠️ DIY | ⚠️ |
| Variant / cross-document bleed guard | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Sticky per-session document scope | ✅ | ❌ | ❌ | ❌ | ❌ | ⚠️ DIY | ❌ |
| Hybrid lexical + vector, RRF fused | ✅ ¹ | ⚠️ opaque | ⚠️ opaque | ⚠️ opaque | ⚠️ opaque | ⚠️ DIY | ⚠️ (LibreChat: Meilisearch) |
| MMR / diversity dedupe | ✅ 0.97 ² | ❌ | ❌ | ❌ | ❌ | ⚠️ DIY | ❌ |
| Contextual chunk enrichment (summary prefix) | ✅ | ❌ | ❌ | ❌ | ❌ | ⚠️ DIY | ❌ |
| Conversational query rewrite | ✅ | ⚠️ | ⚠️ | ⚠️ | ❌ | ⚠️ DIY | ❌ |
| Semantic answer cache | ✅ pgvector | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Cache pre-warm at deploy | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Every retrieval knob exposed | ✅ 20+ env vars | ❌ | ❌ | ❌ | ⚠️ few | ⚠️ code-level | ⚠️ some |
| Self-hosted, zero data egress | ✅ | ❌ | ❌ | ❌ | ❌ | ⚠️ Botpress/Dify OSS | ✅ |
| $0 marginal cost per answer | ✅ | ❌ $0.99/res | ❌ $1.50–2.00/res | ❌ | ❌ credits | ❌ seats+credits | ✅ |
| Cost-vs-ChatGPT analytics panel | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Built-in gating eval harness | ✅ 6 suites | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Deterministic transactional forms w/ validation | ✅ Rasa FSM | ⚠️ | ⚠️ | ✅ playbooks | ❌ | ✅ | ❌ |
| Order capture → DB row | ✅ | ❌ | ❌ | ❌ | ❌ | ⚠️ integration | ❌ |
| Lead capture → DB row | ✅ | ⚠️ CRM sync | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ❌ |
| Ticket create + status transitions | ✅ | ✅ | ✅ | ✅ | ❌ | ⚠️ | ❌ |
| 👍/👎 answer feedback → dashboard | ✅ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ⚠️ |
| Token-by-token streaming | ✅ SSE | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Live ingestion status push | ✅ NOTIFY→WS | n/a | ❌ | ❌ | ❌ | ❌ | ⚠️ |
| Ops dashboard w/ per-request trail | ✅ | ⚠️ | ⚠️ | ⚠️ (1–3 h lag) | ⚠️ | ⚠️ | ❌ |
| Omnichannel (WhatsApp/SMS/voice/email) | ❌ | ✅ | ✅ | ✅ | ⚠️ | ✅ | ❌ |
| Human handoff / live agent | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ Plus | ❌ |
| Helpdesk/CRM connectors | ❌ | ✅ | ✅ | ✅ | ⚠️ Zapier | ✅ | ⚠️ |
| SSO / RBAC / audit logs | ❌ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ⚠️ |
| SOC 2 / ISO 27001 / HIPAA BAA | ❌ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ❌ |
| Multilingual | ❌ | ✅ | ✅ 63 langs chat | ✅ | ✅ | ✅ | ⚠️ |
| Chat-side auth | ❌ loopback only | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| Managed hosting / SLA | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Cross-encoder reranker | ❌ | ⚠️ | ⚠️ | ⚠️ | ❌ | ⚠️ | ⚠️ |
| Multi-item cart / totals | ❌ | ❌ | ❌ | ❌ | ❌ | ⚠️ | ❌ |
| Multi-product LLM routing | ⚠️ `PRIMARY_PRODUCT` pin | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ |

¹ Aura's lexical arm is Postgres full-text search (`websearch_to_tsquery` + `ts_rank_cd` over
a generated `tsvector` column with a GIN index), **not** a true BM25 implementation. It gets
the exact-term recall benefit that pure vector search misses, which is the point, but the
scoring function differs from BM25 proper. Fused via RRF at *k*=60 over 20 candidates per arm.

² Aura's "MMR" is duplicate suppression — drop a chunk if its cosine to any already-kept chunk
exceeds 0.97 — not the classic λ-weighted relevance/diversity trade-off. Narrower than the
name suggests, and the repo says so.

---

## 6. Aura's twelve genuine differentiators

Ranked by how rare the capability is in the market.

1. **Hard refusal floor (`RETRIEVAL_MIN_SCORE=0.45`) that skips the LLM entirely.** Nothing
   else in Class A/B exposes a numeric abstention threshold. Zero tokens spent on
   off-topic questions, and the #2 customer frustration ("chatbot uncertainty") is answered
   with an honest, cheap "I don't have that."
2. **Passage-level source verification via `GET /chunks/{doc}/{ordinal}`.** Click a chip,
   see the sentence. Matched only by Denser, Palantir AIP, and CustomGPT.
3. **Variant guard.** Refuse rather than substitute a sibling model's spec. No competitor
   names this failure mode.
4. **Sticky per-session document scope.** The first grounded answer locks the scope; a
   conversation cannot drift across products.
5. **Single-document answering (`ANSWER_SINGLE_DOC`).** No silent cross-document blending —
   directly addressing the "three contradictory versions of the same policy" failure mode
   every RAG buyer's guide warns about.
6. **pgvector semantic answer cache + deploy-time pre-warm.** Paraphrases at ~0.94 cosine
   return in ~30 ms at zero cost. Measured effect of this technique class: 30–70% cost
   reduction, 68.8% fewer model calls.
7. **A gating eval harness in the repo.** `run_evals.sh` runs **81 pytest tests** plus five
   live-stack assertion scripts, exit-code gated. Everyone else sells this separately or not
   at all. Caveat: no CI runs it, and the assertions are binary rather than graded.
8. **Full retrieval transparency — every stage readable and tunable in source.** Chunk size,
   overlap, fusion candidates, dedupe threshold, top-k, floor, RRF *k*. The opposite of
   Zendesk telling you "too many sources hurts accuracy" and offering no dial. Caveat: only
   8 of the ~28 documented knobs are currently plumbed into the container (see §4.3).
9. **$0 marginal cost, and a dashboard panel that prices the counterfactual.** No
   per-resolution meter, so improving deflection doesn't raise the bill — the exact
   incentive inversion Class A buyers complain about.
10. **Complete data sovereignty.** Local embeddings, local LLM, local vector store, local
    queue, image ships with the embedding model so it boots offline. Zero DPAs.
11. **Deterministic transactional funnel alongside generative Q&A.** Rasa FSMs with email
    validation writing `orders` / `leads` / `support_tickets` rows, plus SMTP
    notifications — the same session that answers a deep spec question can close.
12. **Real ingestion observability.** BullMQ job history with retries, durations, and
    errors; `NOTIFY kb_ready` → WebSocket status push; per-document trail in the dashboard;
    Dozzle for raw container logs. Ada's reporting lags 1–3 hours.

---

## 7. Where Aura loses (honest)

| Gap | Impact | Nearest fix |
|---|---|---|
| **CPU generation 50–130 s** | Unshippable to real customers as-is. Retrieval is ~50 ms; generation is ~99.9% of latency. | `docker-compose.gpu.yml` already exists — 10–50× on CUDA, no code change. Untested (no GPU on dev box). Or `llama3.2:3b` for ~2×. |
| **No chat-side auth, and the network gate is partial** | See the security note below — this is the most material finding in the review. | Roadmap item, M — **promote to blocking**. |
| **No omnichannel** | Web widget only. No WhatsApp, SMS, email, voice, Instagram. Enterprise buyers expect 15+ channels with context carried across them. | Large; probably out of scope. |
| **No human handoff** | 72% of users escalate after 1–2 mistakes and 22% cite inability to escalate as their top frustration. Aura refuses gracefully but has no live-agent path. | Highest-value missing UX feature. |
| **No SSO / RBAC / multi-tenant** | Single-tenant by construction. Fails enterprise procurement outright. Onyx, by contrast, inherits source-system permissions. | Large. |
| **No compliance certifications** | No SOC 2 Type II, ISO 27001, HIPAA BAA, FedRAMP. Self-hosting makes the *technical* case easy but does not produce an audit report. | Organizational, not code. |
| **Single-product pin** | `PRIMARY_PRODUCT` pins one product for unscoped queries; no per-query LLM routing across a multi-catalog KB. | Roadmap item, M. |
| **Single-item orders** | `order_form` captures one product; no cart, no totals, no payment link. Conversational-commerce platforms treat checkout as a first-class system. | Roadmap item, M — *next up*. |
| **No cross-encoder reranker** | Anthropic's numbers put reranking at the difference between −49% and −67% retrieval failures. Costs a second model on the CPU budget. | Roadmap item, M. |
| **Binary evals only** | Harness is pass/fail. Cannot measure "did quality improve by how much". | Roadmap item, M — graded LLM-judge. |
| **No `/metrics` endpoint** | Dashboard exists but no Prometheus scrape for latency, hit rate, queue depth. | Roadmap item, S–M. |
| **File upload only** | No Confluence, Drive, Slack, Notion, or website-crawl connectors. Onyx ships 40+. | Medium each. |
| **English only** | No multilingual retrieval or generation. `bge-small-en-v1.5` is English. | Swap to a multilingual embedding model + larger LLM. |
| **No MCP / tool-calling** | REST only. The lock-in checklists now ask about MCP explicitly. | Medium. |

Note that **Ada cannot ingest a PDF and Aura can**, while **Ada has SOC 2 and Aura does
not**. The gaps run in both directions, and they are different *kinds* of gap: Aura's are
features to build, the market's are architectural commitments already sold to customers.

### 7.1 Security note — the network gate is narrower than documented

**This is important and worth reading in full rather than skimming.** The README describes
the stack as loopback-bound. That is true for four services and false for four others.

Bound to `127.0.0.1` (safe): `web:3100`, `ml-service:8100`, `redis:6390`, `dozzle:9999`.

Bound to **all interfaces** — reachable from any host on the LAN:

- **`rasa:5105`** — runs with `--enable-api --cors "*"`. Any machine on the network can drive
  dialogues, read the tracker, and write conversation state for any `sessionId`.
- **`rasa-actions:5155`** — the action-server webhook, which is what writes `orders`, `leads`,
  and `support_tickets` rows.
- **`postgres:5440`** — credentials are `aura:aura`, committed to git in **two** places
  (`docker-compose.yml` and `rasa/endpoints.yml`).
- **`ollama:11435`** — open inference endpoint.

Compounding factors: no ml-service endpoint has any auth, API key, or CORS policy at all;
`session_id` is a client-generated UUID with no verification, so any caller can read or write
any other session's sticky scope and history; the WebSocket broadcast fans every
`kb_ready`/`kb_failed` event (including document IDs) to every connected client; and
`DASHBOARD_TOKEN` ships empty in `.env`, which makes `authorized()` return `true`
unconditionally — so on a stock checkout the dashboard is not gated either.

**Practical read:** Aura is currently safe on an isolated single-user dev box and unsafe on
any shared network. The fix is small — bind the four services to `127.0.0.1`, set
`DASHBOARD_TOKEN`, move the Postgres credentials out of git — and it should land before the
chat-side auth work, not after. This does not weaken the data-sovereignty argument in §4.4
(nothing leaves the host), but it does mean "self-hosted" is not yet the same as "secured".

### 7.2 Other defects found during verification

- **SMTP cannot be enabled the way the README documents.** `SMTP_HOST` and friends are not
  passed into the `ml-service` container, so `send_email` always short-circuits to a no-op.
  The email module itself is correct; only the wiring is missing.
- **`.env` sets `OLLAMA_MODEL=llama3.2:3b`, but `ollama-pull` only pulls `llama3:8b`.** The
  configured model must be pulled by hand or generation fails on a fresh volume.
- **The chat page's knowledge-base list is React state only.** A page reload loses it, so
  previously-uploaded documents can no longer be ticked for scoped retrieval. There is no
  list-documents endpoint on the chat page and no delete-document endpoint anywhere.
- **Redis runs `allkeys-lru` shared between the answer cache (db0) and the BullMQ queue
  (db1).** Under memory pressure it can silently evict job keys and drop queued ingests. The
  repo already flags this in a `ponytail:` comment with the upgrade path.
- **The semantic cache is global-scope, not per-session, and is `TRUNCATE`d on every
  ingest** — all-or-nothing invalidation, and one run's answer can be served to another's
  identical question.
- **Leads and orders have no dashboard panel** — visible only via `GET /leads` / `GET /orders`
  or raw psql. `leads.status` has no PATCH endpoint, so it can never move off `new`.
- **No CI, no dependency pinning, no lockfile for Python, `:latest` image tags.** Every claim
  in §4.9 about the eval harness is true, but nothing runs it automatically.
- **`docs/` is gitignored in full**, so the README's pointer to the concepts guide is a dead
  link for anyone cloning the repo, and `docs/INTERVIEW_QA.md` still documents pg-boss as the
  queue (BullMQ replaced it in `4680a3b`).

---

## 8. Accuracy: marketed vs. delivered

| Vendor | Marketed | Observed in production | Gap |
|---|---|---|---|
| Ada | "up to 83%" resolution | 30–50% | −33 to −53 pts |
| Zendesk AI | "80%+" automation | 39–66% | −14 to −41 pts |
| Intercom Fin | 76% resolution | 45–53% | −23 to −31 pts |
| Fini | 98% accuracy over 2M+ queries | published, reasoning-first + grounded retrieval | — |
| Zendesk | — | publishes no single accuracy number; case studies 30–60% | — |
| **Aura** | **publishes no resolution-rate claim** | **6-suite eval harness gates every change** | *measures instead of marketing* |

Aura's honest position: it has no resolution-rate number because it has not run at
production volume. What it has instead is a reproducible, exit-code-gated test suite that
any reviewer can run — which is more than any Class A vendor hands you.

---

## 9. Who Aura is actually for

**Strong fit**
- Regulated or IP-sensitive orgs (legal, healthcare, defence, hardware/semiconductor) where
  sending product specs or contracts through a commercial inference endpoint is not a policy
  anyone will sign.
- Technical pre-sales / sales-engineering, where a wrong spec is worse than no answer and
  the buyer will ask "where does it say that?"
- Teams under ~300k conversations/year — below Ada's minimum viable size and above
  Chatbase's 60 MB content ceiling.
- Anyone who needs a predictable bill instead of a per-resolution meter.

**Poor fit**
- Consumer support at scale needing WhatsApp/voice/omnichannel and live-agent handoff.
- Enterprises whose procurement gate is SOC 2 + SSO + RBAC.
- Teams with no ops capability and no GPU.
- Multilingual global support.

**One-line positioning:** *the chatbot that refuses to guess, shows you the sentence it read,
and costs nothing per answer — because none of it leaves your building.*

---

## 10. Roadmap implications

The remaining roadmap items, re-prioritised by what this analysis says the market actually
punishes:

0. **Close the network gate and plumb the config** *(new, S)* — bind `rasa`, `rasa-actions`,
   `postgres`, `ollama` to `127.0.0.1`; move the `aura:aura` credentials out of git; add
   `env_file:` to `ml-service` so the documented knobs (and SMTP) actually take effect. Hours
   of work, and it removes both the security exposure in §7.1 and the credibility gap between
   README and deployment.
1. **GPU path validation** *(already built, untested)* — 50–130 s is the only thing
   preventing a real deployment. Highest value, near-zero code.
2. **Chat-side auth** *(M, was #11)* — **promote.** Without it nothing ships off loopback,
   which blocks every other item's value.
3. **Human handoff** *(not on roadmap)* — **add.** 22% of users name this as their top
   frustration and 72% escalate after two mistakes. A refusal floor without an escalation
   path converts a good "I don't know" into a dead end.
4. **Quote / multi-item cart** *(M, currently next up)* — keep. Real deals aren't
   single-item, and it is the differentiator against support-only Class A.
5. **Graded LLM-judge evals** *(M)* — keep. Already ahead of the market here; graded scoring
   turns a pass/fail gate into a quality trend line.
6. **Cross-encoder reranker** *(M)* — the −49% → −67% retrieval-failure step. Gate on GPU
   landing first, since it adds a second model.
7. **Metrics endpoint** *(S–M)* — cheap, and every enterprise buyer's guide lists it.
8. **True multi-product routing** *(M)* — only once the KB is genuinely multi-catalog.
9. **Lead scoring & handoff** *(M)* — needs an outbound integration; lower leverage than
   the above.

New candidates this analysis surfaces, not currently on the roadmap:

- **Human handoff** (see above) — highest-value new item.
- **Website / URL crawl ingestion** — the single most common competitor onboarding path
  (Chatbase's "point at a URL" is why it beats Voiceflow on time-to-value).
- **Multilingual embedding + LLM swap** — Zendesk offers 63 chat languages; Aura offers one.
- **MCP server exposure** — now an explicit line item on lock-in checklists.
- **Groundedness score surfaced in the UI** — Aura already computes the cosine; showing it
  next to the answer would make the guard visible instead of invisible, which is the whole
  trust argument in one UI change.

---

## 11. Sources

Market state, customer sentiment, and failure statistics
- [50+ Customer Support Chatbot Statistics, 2026 — Botpress](https://botpress.com/blog/customer-service-statistics)
- [Customers Prefer Humans Over Bots — AnswerConnect](https://www.answerconnect.com/blog/news/consumers-turning-away-from-ai-customer-service/)
- [Chatbot Frustration is Real — California Management Review](https://cmr.berkeley.edu/2026/04/chatbot-frustration-is-real-hidden-costs-and-best-practices/)
- [Customer Service AI Agent Statistics 2026 — Digital Applied](https://www.digitalapplied.com/blog/customer-service-ai-agent-statistics-2026-data)
- [30 AI Customer Service Statistics — Lorikeet](https://www.lorikeetcx.ai/articles/ai-customer-service-statistics)
- [Customers Hate Your AI Chatbot — Forbes](https://www.forbes.com/sites/terdawn-deboe/2026/04/20/customers-hate-your-ai-chatbot-small-businesses-should-listen/)

Vendor limitations and pricing
- [Ada AI: Features, Pricing & Limitations 2026 — MyAskAI](https://myaskai.com/blog/ada-ai-agent-complete-guide-2026)
- [Zendesk AI: Features, Pricing & Limitations 2026 — MyAskAI](https://myaskai.com/blog/zendesk-ai-agent-complete-guide-2026)
- [Intercom Fin vs Zendesk AI: Pricing Compared — Macha](https://www.getmacha.com/blog/intercom-fin-vs-zendesk-ai-pricing)
- [Intercom Fin Limitations: 3 Failure Modes Behind the 45–53% Production Rate](https://clonedesk.ai/blog/intercom-fin-limitations)
- [Intercom Fin for Regulated Industries — Lorikeet](https://www.lorikeetcx.ai/articles/intercom-fin-regulated-industries-limitations)
- [Chatbase Review 2026 — SiteGPT](https://sitegpt.ai/blog/chatbase-review)
- [Voiceflow Review 2026 — Botpress](https://botpress.com/blog/voiceflow-review)
- [Botpress vs Voiceflow vs YourGPT](https://yourgpt.ai/botpress-vs-voiceflow-vs-yourgpt)
- [AI Chatbot Pricing Comparison: 8 Platforms — Alhena](https://alhena.ai/blog/ai-chatbot-pricing-comparison/)
- [Best AI Support Agent Providers Compared — Fini Labs](https://www.usefini.com/guides/best-ai-support-agent-providers-platforms-compared)

RAG architecture, retrieval quality, and evaluation
- [Contextual Retrieval in Anthropic — AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/contextual-retrieval-in-anthropic-using-amazon-bedrock-knowledge-bases/)
- [Anthropic's Contextual Retrieval: Implementation Guide — DataCamp](https://www.datacamp.com/tutorial/contextual-retrieval-anthropic)
- [Hybrid Search for RAG: BM25 + Dense Vector — Denser](https://denser.ai/blog/hybrid-search-for-rag/)
- [Hybrid Search: BM25, Vector & Reranking Reference 2026 — Digital Applied](https://www.digitalapplied.com/blog/hybrid-search-bm25-vector-reranking-reference-2026)
- [Why Vector Search Alone Isn't Enough — InfoQ](https://www.infoq.com/articles/vector-search-hybrid-retrieval-rag/)
- [RAG Query Rewriting: 4 Layers That Fix Multi-Turn Retrieval — Alhena](https://alhena.ai/blog/query-rewriting-before-retrieval-multi-turn-rag/)
- [Know Your Limits: A Survey of Abstention in LLMs — arXiv 2407.18418](https://arxiv.org/pdf/2407.18418)
- [Why AI Models Always Answer — Even When They Shouldn't](https://medium.com/@markus_brinsa/why-ai-models-always-answer-even-when-they-shouldnt-e95081e3f46b)
- [GPT Semantic Cache — arXiv 2411.05276](https://arxiv.org/abs/2411.05276)
- [Semantic Caching for AI Agents: Cut LLM Costs 40–80%](https://www.buildmvpfast.com/blog/semantic-caching-ai-agents-cost-optimization)
- [Chatbot Evaluation: 3 Methods and 8 Metrics — Cekura](https://www.cekura.ai/blogs/chatbot-evaluation-methods-metrics)
- [Best RAG Evaluation Tools 2026 — Braintrust](https://www.braintrust.dev/articles/best-rag-evaluation-tools)

Citations, sovereignty, and lock-in
- [AI Chatbot Source Citations — Denser](https://denser.ai/blog/ai-chatbot-source-citations-enterprise/)
- [RAG Observability With Citations And Sources — CustomGPT](https://customgpt.ai/sources-citations-observability/)
- [AIP Chatbot Studio: Citations — Palantir](https://www.palantir.com/docs/foundry/chatbot-studio/citations)
- [AI Agent Vendor Lock-In: 2026 Buyer's Guide — Chitika](https://www.chitika.com/ai-agent-vendor-lock-in-in-2026-how-to-choose-a-flexible-rag-platform-before-you-buy/)
- [Best Enterprise RAG Platforms 2026 — Onyx](https://onyx.app/insights/enterprise-rag-platforms-2026)
- [Self-Hosted RAG Architecture: Open Models, Private Deployment, Real Cost — Tensoria](https://tensoria.fr/en/blog/self-hosted-rag-architecture)
- [Local RAG for Business Data: GDPR-Compliant AI — PromptQuorum](https://www.promptquorum.com/power-local-llm/local-rag-for-private-business-data)
- [Deploy A Secure RAG Chatbot On-Prem — CustomGPT](https://customgpt.ai/deploy-rag-chatbot-private-cloud-on-premise-server/)
- [Self-Host LLM vs API 2026: Break-Even — TokenMix](https://tokenmix.ai/blog/self-host-llm-vs-api)
- [LLM Hosting Cost 2026 — AI Superior](https://aisuperior.com/llm-hosting-cost/)

Platform classes and NLU
- [OpenWebUI vs LibreChat vs Onyx — Onyx](https://onyx.app/insights/openwebui-vs-librechat-vs-onyx)
- [Production RAG Frameworks Compared: The 2026 Landscape](https://karbouch.substack.com/p/production-rag-frameworks-compared)
- [Intent/entity NLU vs GenAI/LLM NLU — Seasalt.ai](https://seasalt.ai/en/blog/73-Intent-entity-based-NLU-vs-GenAI-LLM-based-NLU/)
- [Rasa vs Dialogflow vs Lex — Ideas2IT](https://www.ideas2it.com/blogs/battle-of-the-bots-rasa-vs-google-dialogflow-vs-aws-lex)
- [Top 8 Dialogflow Alternatives — Rasa](https://rasa.com/blog/dialogflow-alternatives)
- [7 Best Conversational Commerce Platforms 2026 — Guideflow](https://www.guideflow.com/blog/conversational-commerce-platform)
- [10 Best Enterprise Chatbot Platforms 2026 — Guideflow](https://www.guideflow.com/blog/enterprise-chatbot-platform)
- [Which AI Knowledge Manager Enforces RBAC and SOC 2 Best — Fini Labs](https://www.usefini.com/guides/ai-knowledge-managers-rbac-soc2-hosting-enterprise-support)

Aura internals verified against: `README.md`, `ROADMAP.md`, `.env.example`,
`docker-compose.yml`, `docker-compose.gpu.yml`, `ml-service/app/`, `web/`, `rasa/`,
`db/migrations/`, `scripts/`.
