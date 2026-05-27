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
