"""Aura ml-service — FastAPI app.

Phase 1 surface: health check + embedding endpoint. Ingestion (`/ingest`) and RAG
(`/answer`) are added in later phases.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .config import settings
from .embeddings import embed_texts
from .ingest import ingest_document

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
