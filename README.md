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
docker compose up -d postgres ollama ollama-pull
```

`postgres` bootstraps the schema on a fresh volume (`db/init.sql` then
`db/migrations/0001_init_schema.sql`). `ollama-pull` downloads `llama3:8b` once, then
exits. Verify:

```bash
docker compose exec postgres psql -U aura -d aura -c '\dt'
docker compose exec ollama ollama list
```

Application services (`ml-service`, `worker`, `rasa`, `rasa-actions`, `web`) are added
in later build phases.
