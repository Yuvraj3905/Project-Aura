# Project Aura

Autonomous, stateful "Sales Engineer" agent. Ingests large internal engineering docs,
tracks multi-day client conversations, and answers technical questions without
hallucinating. 100% open source / free stack — local inference, no paid LLM APIs.

## Stack

| Service        | Port  | Role |
|----------------|-------|------|
| postgres       | 5440  | pgvector store + pg-boss queue + Rasa tracker store |
| ollama         | 11435 | local `llama3:8b` — summaries + answers |
| ml-service     | 8100  | Python/FastAPI — embeddings, ingestion, RAG |
| worker         | —     | Node — pg-boss consumer |
| rasa           | 5105  | dialogue manager |
| rasa-actions   | 5155  | custom action server |
| web            | 3100  | Next.js — UI + API + WebSocket |

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
2. **Ask a technical question.** Type into the chat box. Examples that exercise the
   different paths:
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
4. **Multi-day continuation.** Rasa persists session state in Postgres (24-hour
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
- **Tickets** — recent `support_tickets` rows.
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

# Direct RAG answer (skip Rasa — useful for batch / scripted Q&A over ready docs)
curl -X POST http://localhost:8100/answer \
  -H 'content-type: application/json' \
  -d '{"query":"What TLS versions are accepted?"}'

# File a ticket programmatically
curl -X POST http://localhost:8100/tickets \
  -H 'content-type: application/json' \
  -d '{"email":"ops@acme.com","description":"500 on /v2/token","session_id":"acme"}'
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

# Retrain Rasa after editing rasa/data/*.yml or rasa/domain.yml
docker compose run --rm rasa train
docker compose restart rasa

# Tear it all down (data volumes preserved)
docker compose down

# Nuke volumes too (DB, ollama model cache, uploaded files)
docker compose down -v && rm -rf data/
```

### Tuning knobs (in `.env`)

| Var | Default | Effect |
|-----|---------|--------|
| `CHUNK_TOKENS` | 512 | Chunk size before the summary prefix |
| `CHUNK_OVERLAP` | 64 | Tokens shared between adjacent chunks |
| `RETRIEVAL_TOP_K` | 5 | How many chunks feed the grounded prompt |
| `RETRIEVAL_MIN_SCORE` | 0.45 | Cosine floor — below this, the LLM is **not** called (anti-hallucination guard) |
| `OLLAMA_MODEL` | `llama3:8b` | Local LLM (swap in any Ollama-pulled tag) |

### Data flow

- **Ingestion:** upload → `/api/upload` saves the file + enqueues a `process_document`
  job (pg-boss) → Node `worker` calls ml-service `/ingest` → extract → hierarchical
  summary (Ollama) → token chunks with the summary prepended → embed (bge-small) →
  store → `NOTIFY kb_ready` → WebSocket pushes status to the UI.
- **Chat:** `/api/chat` → Rasa. `tech_query` → `action_tech_query` → ml-service
  `/answer` (vector search + grounded prompt, refuses when retrieval is weak).
  `open_ticket` → `ticket_form` collects email + description → ml-service `/tickets`.

## ml-service

Python/FastAPI. Embeddings via Sentence Transformers (`bge-small-en-v1.5`, 384-dim,
L2-normalized for cosine search). Endpoints: `GET /health`, `POST /embed`,
`POST /ingest`, `POST /answer`, `POST /tickets`.

`/ingest` accepts only a `document_id`; the file path is resolved from
`documents.storage_path` under the upload root (no caller-supplied paths). The host
port is bound to `127.0.0.1`.

Run the tests inside the image:

```bash
docker compose run --rm --no-deps ml-service pytest
```
