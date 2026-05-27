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

## ml-service

Python/FastAPI. Embeddings via Sentence Transformers (`bge-small-en-v1.5`, 384-dim,
L2-normalized for cosine search). Endpoints so far: `GET /health`, `POST /embed`.

Run the tests inside the image:

```bash
docker compose run --rm --no-deps ml-service pytest
```

The remaining services (`worker`, `rasa`, `rasa-actions`, `web`) are added in later
build phases.
