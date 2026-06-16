# Project Aura

Autonomous, stateful "Sales Engineer" agent. Ingests large internal engineering docs,
tracks multi-day client conversations, and answers technical questions without
hallucinating. 100% open source / free stack — local inference, no paid LLM APIs.

## Stack

| Service        | Port  | Role |
|----------------|-------|------|
| postgres       | 5440  | pgvector store + pg-boss queue + Rasa tracker store |
| ollama         | 11435 | local `llama3:8b` — summaries + answers |
| redis          | 6390  | cache — query embeddings + grounded answers |
| ml-service     | 8100  | Python/FastAPI — embeddings, ingestion, RAG |
| worker         | —     | Node — pg-boss consumer |
| rasa           | 5105  | dialogue manager |
| rasa-actions   | 5155  | custom action server |
| web            | 3100  | Next.js — UI + API + WebSocket |

## Architecture

```
                     ┌─────────────────────────┐
 browser ──────────▶ │  web (Next.js)  :3100   │
 upload / chat / ws  │  UI · API · WebSocket   │
                     └───┬─────────┬───────┬───┘
                         │         │       │
            enqueue job  │   REST  │       │ SSE stream
                         ▼         ▼       ▼
            ┌────────────────┐ ┌──────┐ ┌──────────────────┐
            │ postgres :5440 │ │ rasa │ │ ml-service :8100 │
            │  pgvector      │ │:5105 │ │  embed · ingest  │
            │  pgboss.*      │ └──┬───┘ │  RAG · tickets   │
            │  rasa events   │    ▼     └───┬─────────┬────┘
            └──────┬─────────┘ ┌─────────┐  │         │
      LISTEN/NOTIFY│           │ actions │  ▼         ▼
            ┌──────┴──────┐    │  :5155  │ ┌───────┐ ┌────────┐
            │ worker (Node│    └─────────┘ │ redis │ │ ollama │
            │ pg-boss)    │───── /ingest ─▶│ :6390 │ │ :11435 │
            └─────────────┘                └───────┘ └────────┘
```

## Repository layout

```
web/            Next.js App Router + custom server (ws) + Node pg-boss worker
  app/          UI (chat + upload), /dashboard, /api routes
  worker/       pg-boss consumer entrypoint
  lib/          db pool, queue, NOTIFY helpers
ml-service/     Python / FastAPI
  app/          config, db, embeddings, llm (Ollama), cache (Redis), ingest
  app/pipeline/ extract, chunk, summarize, store
  app/rag/      retrieve, answer (+ streaming)
  tests/        pytest suite
rasa/           dialogue manager project
  data/         nlu, rules, stories
  actions/      custom action server code
db/             init.sql + migrations (mounted into postgres initdb)
docker-compose.yml
docs/           local-only docs — git-ignored, never pushed
```

## Concepts guide

A self-contained deep-dive into every concept in the system — Contextual RAG, embeddings
and the bge-small similarity baseline, pgvector/HNSW, chunking, hierarchical map-reduce
summarization, the two-layer anti-hallucination guardrail, pg-boss and the Node↔Python
split, NOTIFY/LISTEN→WebSocket, Rasa (DIET pipeline, rules vs stories, form FSM, tracker
store), SSE streaming with the stream-directive pattern, Redis cache layers and
invalidation, the security model, schema and API reference — lives at
`docs/aura-concepts.html`. Open it directly in a browser:

```bash
xdg-open docs/aura-concepts.html      # linux
```

(`docs/` is intentionally git-ignored; the guide stays local.)

## Quickstart (infra)

```bash
cp .env.example .env
docker compose up -d postgres ollama ollama-pull ml-service
```

`postgres` bootstraps the schema on a fresh volume (`db/init.sql` then
`db/migrations/0001_init_schema.sql`). `ollama-pull` downloads `llama3:8b` once, then
exits. `ml-service` bakes the `bge-small-en-v1.5` embedding model into its image, so it
starts offline. Verify:

```bash
docker compose exec postgres psql -U aura -d aura -c '\dt'
docker compose exec ollama ollama list
curl -s localhost:8100/health
```

`/health` returns the active embedding model and dimension (384).

## Full stack

```bash
cp .env.example .env

# 1. Train the Rasa model (writes rasa/models/<...>.tar.gz)
docker compose run --rm rasa train

# 2. Bring everything up
docker compose up -d --build
```

Then open <http://localhost:3100>: upload a `.pdf` / `.docx` / `.txt` / `.md`, watch
its status flip to **ready** over WebSocket, then ask a technical question or say
"open a support ticket".

## How to use

### A. Web UI — <http://localhost:3100>

1. **Upload a document.** Pick a `.pdf`, `.docx`, `.txt`, or `.md` (≤50 MB). The doc
   appears in the **Knowledge base** list with status `processing`. The WebSocket
   pushes a live update to `ready` (or `failed`) when ingestion completes; no refresh
   needed. Large docs take longer — hierarchical summarization, chunking, and
   embedding run on the local LLM.
2. **Ask a technical question.** Type into the chat box. The answer **streams token by
   token** (SSE) as the local LLM generates it; a `cached` badge appears when the
   answer came from Redis instead of the model. Tick the checkboxes next to ready
   documents to **restrict the answer to a chosen subset** of the knowledge base
   (leave all unticked to search everything). Examples that exercise the different
   paths:
   - `does the API support OAuth 2.0 with custom claims` — `tech_query` → grounded
     answer + `Sources: doc <id>·#<chunk>` line.
   - `what is the request timeout limit for the billing service` — same path; cites
     the chunk that mentions the limit.
   - `what is the capital of France` — off-topic; the cosine score falls below the
     `0.45` floor, so the LLM is never called and Aura replies "I don't have that
     information in the current knowledge base."
3. **Open a support ticket.** Say `I want to open a support ticket` (or "raise a
   ticket", "report a problem", etc.). Rasa runs the `ticket_form`:
   - Asks for your email — malformed emails are rejected and re-asked.
   - Asks for an issue description.
   - Confirms the ticket and writes a row to `support_tickets` via ml-service
     `/tickets`.
4. **Place an order (sales funnel).** Say `I want to buy the Galaxy Watch 8 44mm`
   (or "I'll take the 44mm", "how do I place an order"). The `buy_order` intent runs
   the `order_form`:
   - Asks which model you want (`product`).
   - Asks for your email — malformed emails are rejected and re-asked.
   - Confirms and writes a row to `orders` (status `pending`) via ml-service `/orders`.
5. **Request a callback (lead capture).** Say `please have someone contact me` (or
   "send me more info", "I'm interested, follow up"). The `request_contact` intent runs
   the `lead_form`:
   - Asks for your name, then email.
   - Writes a row to `leads` (status `new`, tagged with what you were asking about)
     via ml-service `/leads`, so a specialist can follow up.
6. **Multi-day continuation.** Rasa persists session state in Postgres (24-hour
   default expiration, slots carry over), so re-opening a conversation with the same
   `sessionId` resumes context.

### A2. Dashboard — <http://localhost:3100/dashboard>

Auto-refreshing operations view of the request travel across services:

- **Documents** — every upload with status pill (`uploaded` → `processing` →
  `ready`/`failed`), chunk count, age. Click a row for the full trail (doc-level
  summary + matching pg-boss job history with retries, durations, errors).
- **pg-boss jobs** — queue name, state, retry count, linked `documentId`, durations.
- **Chat sessions** — distinct Rasa `sender_id` with user/bot turn counts. Click one
  to see the event stream (intents + actions in order).
- **Tickets** — recent `support_tickets` rows with **status transition buttons**
  (`open` ↔ `in_progress` → `closed`); writes go through ml-service.
- **LLM usage & cost vs ChatGPT** — calls, cache hit rate, tokens, avg latency, and the
  estimated OpenAI bill for the same tokens (vs Aura's $0 local inference).
- **Filter** by `documentId`, `sessionId`, or email across all panels.
- **Raw container logs** — link in the header opens **Dozzle** at
  <http://localhost:9999> (live stdout/stderr per service, search, multi-tail).

**Auth.** Two layers protect the dashboard (it surfaces chat content, ticket emails,
and document filenames/summaries):

1. **Network gate** — `web` is bound to `127.0.0.1` in `docker-compose.yml`, so the
   dashboard is unreachable from the LAN by default.
2. **Opt-in token** — set `DASHBOARD_TOKEN` in `.env` to require it on every
   `/api/dashboard/*` and `/dashboard` request. API callers send
   `x-dashboard-token: <token>`; browsers visit `/dashboard?t=<token>` once to mint
   an `aura_dash` cookie (httpOnly, SameSite=Strict). Required if you ever change
   the host port binding to expose the UI beyond loopback.

### B. HTTP API (curl)

The web UI just talks to these endpoints — they're directly useful for scripting,
RFP automation, or service-to-service integration.

```bash
# Upload + enqueue (returns 202 with a documentId)
curl -X POST -F "file=@./manual.pdf" http://localhost:3100/api/upload

# Poll ingestion status (WebSocket fallback)
curl http://localhost:3100/api/documents/<documentId>

# Chat turn through Rasa
curl -X POST http://localhost:3100/api/chat \
  -H 'content-type: application/json' \
  -d '{"sessionId":"sales-acme-2026-05","message":"Does v1 support custom claims?"}'

# Direct RAG answer (skip Rasa — useful for batch / scripted Q&A over ready docs).
# Optional document_ids restricts retrieval to a subset; response includes "cached".
curl -X POST http://localhost:8100/answer \
  -H 'content-type: application/json' \
  -d '{"query":"What TLS versions are accepted?","document_ids":["<id>"]}'

# Streaming answer (Server-Sent Events: token frames then a done frame with citations)
curl -N -X POST http://localhost:8100/answer/stream \
  -H 'content-type: application/json' \
  -d '{"query":"What TLS versions are accepted?"}'

# File a ticket programmatically
curl -X POST http://localhost:8100/tickets \
  -H 'content-type: application/json' \
  -d '{"email":"ops@acme.com","description":"500 on /v2/token","session_id":"acme"}'

# List tickets / transition status (open -> in_progress -> closed)
curl http://localhost:8100/tickets
curl -X PATCH http://localhost:8100/tickets/<ticketId> \
  -H 'content-type: application/json' -d '{"status":"in_progress"}'

# Sales funnel — capture a lead (buying signal → follow-up)
curl -X POST http://localhost:8100/leads \
  -H 'content-type: application/json' \
  -d '{"name":"Sam Buyer","email":"sam@acme.com","product_interest":"Galaxy Watch 8","session_id":"acme"}'
curl http://localhost:8100/leads

# Place an order (purchase intent) / transition status (pending -> confirmed -> fulfilled | cancelled)
curl -X POST http://localhost:8100/orders \
  -H 'content-type: application/json' \
  -d '{"email":"sam@acme.com","product":"Galaxy Watch 8 44mm","quantity":1,"session_id":"acme"}'
curl http://localhost:8100/orders
curl -X PATCH http://localhost:8100/orders/<orderId> \
  -H 'content-type: application/json' -d '{"status":"confirmed"}'
```

### C. Operations

```bash
# Tail logs for a service
docker compose logs -f ml-service worker

# Inspect what's been ingested
docker compose exec postgres psql -U aura -d aura \
  -c "select id, filename, status, n_chunks from documents order by created_at desc;"

# Tickets queue
docker compose exec postgres psql -U aura -d aura \
  -c "select id, email, status, created_at from support_tickets order by created_at desc;"

# Sales funnel — captured leads and orders
docker compose exec postgres psql -U aura -d aura \
  -c "select id, name, email, product_interest, status, created_at from leads order by created_at desc;"
docker compose exec postgres psql -U aura -d aura \
  -c "select id, product, quantity, email, status, created_at from orders order by created_at desc;"

# Retrain Rasa after editing rasa/data/*.yml or rasa/domain.yml
docker compose run --rm rasa train
docker compose restart rasa
# IMPORTANT: after editing rasa/actions/actions.py (new/changed custom actions),
# restart the action server too — `rasa run actions` does NOT hot-reload:
docker compose restart rasa-actions

# Tear it all down (data volumes preserved)
docker compose down

# Nuke volumes too (DB, ollama model cache, uploaded files)
docker compose down -v && rm -rf data/
```

### Speed

Answer latency on CPU is dominated by the local model. Biggest levers, in order:

1. **Use a smaller model** — the single biggest win. Pull a 3B model and point Aura at it:
   ```bash
   docker compose exec ollama ollama pull llama3.2:3b
   # set OLLAMA_MODEL=llama3.2:3b in .env, then: docker compose up -d ml-service
   ```
   3B answers ~2× faster than the default 8B at a modest quality cost.
2. **Keep the model warm** — `OLLAMA_KEEP_ALIVE=30m` (default) keeps it resident in RAM, so
   only the *first* request pays the model-load cost.
3. **Cap generation / context** — `OLLAMA_NUM_PREDICT` (max output tokens) and
   `OLLAMA_NUM_CTX` (context window) bound the work per call.
4. **Fewer/smaller chunks** — lower `RETRIEVAL_TOP_K` / `CHUNK_TOKENS` to shrink the prompt.
5. **Cache** — repeat questions return from Redis in ~30 ms regardless of model (see below).
6. **Streaming** — the UI shows tokens as they generate, so perceived latency ≈ time-to-first-token, not total.

### LLM usage & cost analytics

The dashboard's **LLM usage & cost vs ChatGPT** panel reports, from the `llm_usage` table:
calls, cache hits + hit rate, prompt/completion tokens, average latency — and estimates
what the same tokens would have cost on `gpt-4o` / `gpt-4o-mini` / `gpt-3.5-turbo`
(prices configurable in `.env`). Aura's actual spend is **$0** (local inference); the panel
also shows what the answer-cache saved by not re-generating. Raw aggregates: `GET /usage`.

### Tuning knobs (in `.env`)

| Var | Default | Effect |
|-----|---------|--------|
| `CHUNK_TOKENS` | 512 | Chunk size before the summary prefix |
| `CHUNK_OVERLAP` | 64 | Tokens shared between adjacent chunks |
| `RETRIEVAL_TOP_K` | 5 | How many chunks feed the grounded prompt (fewer = faster) |
| `RETRIEVAL_MIN_SCORE` | 0.45 | Cosine floor — below this, the LLM is **not** called (anti-hallucination guard) |
| `HYBRID_RETRIEVAL` | true | Fuse lexical (BM25-like) + vector results via RRF |
| `HYBRID_CANDIDATES` | 20 | Top-N from each arm before fusion |
| `MMR_DEDUPE` | true | Drop near-duplicate chunks from the fused list |
| `MMR_DUP_THRESHOLD` | 0.97 | Cosine above which two chunks count as duplicates |
| `SEMANTIC_CACHE` | true | Reuse a prior answer for a near-identical query embedding |
| `SEMANTIC_CACHE_THRESHOLD` | 0.92 | Cosine floor to reuse (paraphrases ~0.94, different questions ~0.69) |
| `OLLAMA_MODEL` | `llama3:8b` | Local LLM; use `llama3.2:3b` for speed |
| `OLLAMA_NUM_CTX` | 4096 | Context window (must hold prompt + chunks; bigger = slower) |
| `OLLAMA_NUM_PREDICT` | 512 | Max generated tokens per answer |
| `OLLAMA_KEEP_ALIVE` | 30m | How long the model stays resident in RAM |
| `REDIS_URL` | `redis://redis:6379/0` | Cache backend; empty string disables caching (service still works) |
| `OPENAI_PRICE_GPT_4O` etc. | `2.50,10.00` | ChatGPT prices ($/1M in,out) for the cost-comparison panel |

### Data flow

- **Ingestion:** upload → `/api/upload` saves the file + enqueues a `process_document`
  job (pg-boss) → Node `worker` calls ml-service `/ingest` → extract → hierarchical
  summary (Ollama) → token chunks with the summary prepended → embed (bge-small) →
  store → `NOTIFY kb_ready` → WebSocket pushes status to the UI.
- **Chat:** `/api/chat` → Rasa. `tech_query` → `action_tech_query` returns a stream
  directive → web opens SSE to `/api/chat/stream` → ml-service `/answer/stream`
  (vector search + grounded prompt, streamed token by token, refuses when retrieval is
  weak). `open_ticket` → `ticket_form` collects email + description → ml-service
  `/tickets`. `buy_order` → `order_form` (product + email) → `/orders`;
  `request_contact` → `lead_form` (name + email) → `/leads` — the sales funnel.
- **Retrieval:** hybrid by default — a lexical (Postgres full-text/BM25-like) search and
  the vector search each return candidates, fused with Reciprocal Rank Fusion, then
  de-duplicated (MMR). Catches exact-term matches a pure vector search misses. Every chunk
  keeps its cosine score, so the anti-hallucination guard is unchanged. Disable with
  `HYBRID_RETRIEVAL=false`.
- **Cache:** query embeddings (24h) and grounded answers (1h) are cached in Redis (exact
  match); the answer cache is flushed whenever a new document becomes ready. A **semantic
  answer cache** (pgvector) additionally reuses a prior answer when a new query embeds
  within `SEMANTIC_CACHE_THRESHOLD` cosine of an earlier one *in the same doc-scope* — so
  paraphrases ("how big is the screen" ≈ "display size") return instantly instead of
  re-running the LLM. Disable with `SEMANTIC_CACHE=false`.

## ml-service

Python/FastAPI. Embeddings via Sentence Transformers (`bge-small-en-v1.5`, 384-dim,
L2-normalized for cosine search). Endpoints: `GET /health`, `POST /embed`,
`POST /ingest`, `POST /answer`, `POST /answer/stream` (SSE), `POST /tickets`,
`GET /tickets`, `PATCH /tickets/{id}`, `POST /leads`, `GET /leads`, `POST /orders`,
`GET /orders`, `PATCH /orders/{id}`, `GET /usage`.

`/answer` and `/answer/stream` accept an optional `document_ids` filter (restrict
retrieval to a subset) plus an optional `session_id` (enables the per-session sticky
document scope — the first grounded answer locks retrieval to the documents it cited)
and are Redis-cached. `/ingest` accepts only a `document_id`; the file path is resolved
from `documents.storage_path` under the upload root (no caller-supplied paths). The host
port is bound to `127.0.0.1`.

Run the tests inside the image:

```bash
docker compose run --rm --no-deps ml-service pytest
```

### Schema migrations

Migrations live in `db/migrations/*.sql` and are mounted into the Postgres init dir, so a
**fresh volume** bootstraps the full schema automatically. To apply a new migration to an
**existing** volume, run it by hand, e.g.:

```bash
docker exec -i aura-postgres psql -U aura -d aura < db/migrations/0004_leads_orders.sql
```

### End-to-end test scripts

Two Python scripts drive the live stack (`:3100`) and assert on behavior — both exit
non-zero on failure, so they double as regression checks:

```bash
python3 scripts/storyline_test.py   # sales persona, sticky doc-scope, no cross-doc bleed (LLM — slow)
python3 scripts/funnel_test.py       # order + lead capture flows, bad-email rejection (Rasa forms — fast)
python3 scripts/phase2_test.py       # hybrid retrieval + semantic-cache paraphrase reuse (LLM — slow)
```

Phase 2 retrieval-quality test results (API + UI) are logged in
`scripts/phase2_results.md` (with `scripts/phase2_ui_markdown.png` showing rendered
markdown answers).
