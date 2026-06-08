"""Aura ml-service — FastAPI app.

Surface: health, embeddings, ingestion (`/ingest`), RAG (`/answer`, `/answer/stream`),
and support tickets (`/tickets` CRUD-lite).
"""
import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .config import settings
from .db import create_ticket, get_conn, list_tickets, update_ticket_status
from .embeddings import embed_texts
from .ingest import ingest_document
from .rag.answer import answer_query, answer_stream
from .usage import get_usage_stats

app = FastAPI(title="Aura ml-service", version="0.2.0")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
    }


class EmbedRequest(BaseModel):
    texts: list[str]


class EmbedResponse(BaseModel):
    dim: int
    embeddings: list[list[float]]


@app.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest) -> EmbedResponse:
    """Debug/utility endpoint: embed texts and return normalized vectors."""
    vectors = embed_texts(req.texts)
    dim = len(vectors[0]) if vectors else settings.embedding_dim
    return EmbedResponse(dim=dim, embeddings=vectors)


class IngestRequest(BaseModel):
    document_id: str  # path is derived server-side from documents.storage_path


class IngestResponse(BaseModel):
    document_id: str
    status: str
    n_chunks: int


@app.post("/ingest", response_model=IngestResponse)
def ingest(req: IngestRequest) -> IngestResponse:
    """Run the ingestion pipeline for one document (called by the worker)."""
    try:
        n_chunks = ingest_document(req.document_id)
    except Exception as exc:  # noqa: BLE001 — surface as 500 so the worker retries
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return IngestResponse(document_id=req.document_id, status="ready", n_chunks=n_chunks)


class Citation(BaseModel):
    document_id: str
    ordinal: int
    score: float


class AnswerRequest(BaseModel):
    query: str
    session_id: str | None = None  # forwarded by Rasa; state lives in Rasa, not here
    top_k: int | None = None
    document_ids: list[str] | None = None  # restrict retrieval to these docs (optional)


class AnswerResponse(BaseModel):
    answer: str
    grounded: bool
    citations: list[Citation]
    cached: bool = False


@app.post("/answer", response_model=AnswerResponse)
def answer(req: AnswerRequest) -> AnswerResponse:
    """Retrieve grounded context and generate an answer (or refuse if unsupported)."""
    result = answer_query(req.query, req.top_k, req.document_ids)
    return AnswerResponse(**result)


@app.post("/answer/stream")
def answer_stream_endpoint(req: AnswerRequest) -> StreamingResponse:
    """Server-Sent Events stream of a grounded answer.

    Emits `event: token` frames with `{"text": ...}` per token, then a final
    `event: done` frame carrying `{answer, grounded, citations, cached}`. On LLM
    transport failure, emits an `event: error` frame instead of crashing the stream.
    """

    def sse() -> "object":
        try:
            for kind, payload in answer_stream(req.query, req.top_k, req.document_ids):
                if kind == "token":
                    yield f"event: token\ndata: {json.dumps({'text': payload})}\n\n"
                else:
                    yield f"event: done\ndata: {json.dumps(payload)}\n\n"
        except Exception as exc:  # noqa: BLE001 — surface as an SSE error frame
            yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class TicketRequest(BaseModel):
    email: str
    description: str
    session_id: str | None = None
    subject: str | None = None


class TicketResponse(BaseModel):
    ticket_id: str


@app.post("/tickets", response_model=TicketResponse)
def tickets(req: TicketRequest) -> TicketResponse:
    """Create a support ticket (called by the Rasa ticket form)."""
    with get_conn() as conn:
        ticket_id = create_ticket(conn, req.email, req.description, req.session_id, req.subject)
        conn.commit()
    return TicketResponse(ticket_id=ticket_id)


TICKET_STATES = ("open", "in_progress", "closed")


@app.get("/tickets")
def get_tickets() -> dict:
    """List support tickets (newest first)."""
    with get_conn() as conn:
        return {"tickets": list_tickets(conn)}


class TicketStatusRequest(BaseModel):
    status: str


@app.patch("/tickets/{ticket_id}")
def patch_ticket(ticket_id: str, req: TicketStatusRequest) -> dict:
    """Transition a ticket's status: open -> in_progress -> closed (any order)."""
    if req.status not in TICKET_STATES:
        raise HTTPException(status_code=400, detail=f"status must be one of {TICKET_STATES}")
    with get_conn() as conn:
        ok = update_ticket_status(conn, ticket_id, req.status)
        conn.commit()
    if not ok:
        raise HTTPException(status_code=404, detail="ticket not found")
    return {"ticket_id": ticket_id, "status": req.status}


@app.get("/usage")
def usage_stats() -> dict:
    """LLM usage aggregates (calls, tokens, latency, cache hit rate).

    The dashboard layers OpenAI/ChatGPT pricing on top of these raw counts to estimate
    what the same token volume would have cost on a paid API.
    """
    return get_usage_stats()
