"""Aura ml-service — FastAPI app.

Phase 1 surface: health check + embedding endpoint. Ingestion (`/ingest`) and RAG
(`/answer`) are added in later phases.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .config import settings
from .db import create_ticket, get_conn
from .embeddings import embed_texts
from .ingest import ingest_document
from .rag.answer import answer_query

app = FastAPI(title="Aura ml-service", version="0.1.0")


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


class AnswerResponse(BaseModel):
    answer: str
    grounded: bool
    citations: list[Citation]


@app.post("/answer", response_model=AnswerResponse)
def answer(req: AnswerRequest) -> AnswerResponse:
    """Retrieve grounded context and generate an answer (or refuse if unsupported)."""
    result = answer_query(req.query, req.top_k)
    return AnswerResponse(**result)


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
