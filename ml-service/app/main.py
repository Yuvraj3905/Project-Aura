"""Aura ml-service — FastAPI app.

Surface: health, embeddings, ingestion (`/ingest`), RAG (`/answer`, `/answer/stream`),
and support tickets (`/tickets` CRUD-lite).
"""
import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import cache
from .config import settings
from .db import (
    create_lead,
    create_order,
    create_feedback,
    create_ticket,
    documents_missing_product,
    feedback_stats,
    fetch_chunk,
    get_conn,
    list_leads,
    list_orders,
    list_tickets,
    set_document_product,
    update_order_status,
    update_ticket_status,
)
from .email import lead_notification, order_confirmation
from .llm import classify_product
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
    result = answer_query(req.query, req.top_k, req.document_ids, req.session_id)
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
            for kind, payload in answer_stream(req.query, req.top_k, req.document_ids, req.session_id):
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


# --- Sales funnel: leads + orders --------------------------------------------------


class LeadRequest(BaseModel):
    email: str
    name: str | None = None
    product_interest: str | None = None
    session_id: str | None = None


class LeadResponse(BaseModel):
    lead_id: str


@app.post("/leads", response_model=LeadResponse)
def create_lead_endpoint(req: LeadRequest) -> LeadResponse:
    """Capture a sales lead (called by the Rasa lead form on a buying signal)."""
    with get_conn() as conn:
        lead_id = create_lead(
            conn,
            email=req.email,
            name=req.name,
            product_interest=req.product_interest,
            session_id=req.session_id,
        )
        conn.commit()
    # Best-effort: acknowledge to the prospect + notify sales (no-op if SMTP unconfigured).
    lead_notification(req.email, req.name, req.product_interest)
    return LeadResponse(lead_id=lead_id)


@app.get("/leads")
def get_leads() -> dict:
    """List captured leads (newest first)."""
    with get_conn() as conn:
        return {"leads": list_leads(conn)}


class OrderRequest(BaseModel):
    email: str
    product: str
    quantity: int = 1
    session_id: str | None = None


class OrderResponse(BaseModel):
    order_id: str


@app.post("/orders", response_model=OrderResponse)
def create_order_endpoint(req: OrderRequest) -> OrderResponse:
    """Place a purchase order (called by the Rasa order form on purchase intent)."""
    with get_conn() as conn:
        order_id = create_order(
            conn,
            email=req.email,
            product=req.product,
            quantity=req.quantity,
            session_id=req.session_id,
        )
        conn.commit()
    # Best-effort: email the customer their confirmation (no-op if SMTP unconfigured).
    order_confirmation(req.email, req.product, req.quantity)
    return OrderResponse(order_id=order_id)


@app.get("/orders")
def get_orders() -> dict:
    """List orders (newest first)."""
    with get_conn() as conn:
        return {"orders": list_orders(conn)}


ORDER_STATES = ("pending", "confirmed", "fulfilled", "cancelled")


class OrderStatusRequest(BaseModel):
    status: str


@app.patch("/orders/{order_id}")
def patch_order(order_id: str, req: OrderStatusRequest) -> dict:
    """Transition an order's status: pending -> confirmed -> fulfilled (or cancelled)."""
    if req.status not in ORDER_STATES:
        raise HTTPException(status_code=400, detail=f"status must be one of {ORDER_STATES}")
    with get_conn() as conn:
        ok = update_order_status(conn, order_id, req.status)
        conn.commit()
    if not ok:
        raise HTTPException(status_code=404, detail="order not found")
    return {"order_id": order_id, "status": req.status}


@app.delete("/session/{session_id}/scope")
def clear_session_scope(session_id: str) -> dict:
    """Dispose a conversation's sticky document scope.

    Called when the user starts a new chat so the fresh session begins with global
    retrieval instead of inheriting the previous conversation's locked documents.
    """
    cache.clear_scope(session_id)
    return {"session_id": session_id, "cleared": True}


@app.post("/documents/retag")
def retag_documents() -> dict:
    """Backfill product tags for ready documents that don't have one yet (classify from
    their summary). One-off after migration 0006 / for docs ingested before tagging."""
    with get_conn() as conn:
        pending = documents_missing_product(conn)
    tagged = []
    for doc in pending:
        product = classify_product(doc["summary"] or "")
        if product:
            with get_conn() as conn:
                set_document_product(conn, doc["id"], product)
                conn.commit()
            tagged.append({"id": doc["id"], "product": product})
    return {"retagged": tagged, "count": len(tagged)}


@app.get("/chunks/{document_id}/{ordinal}")
def get_chunk(document_id: str, ordinal: int) -> dict:
    """Return the source text behind a citation, so the UI can let a customer verify a
    claim against the actual document passage the answer was grounded in."""
    with get_conn() as conn:
        chunk = fetch_chunk(conn, document_id, ordinal)
    if chunk is None:
        raise HTTPException(status_code=404, detail="chunk not found")
    return chunk


class FeedbackRequest(BaseModel):
    query: str
    rating: str  # "up" | "down"
    answer: str | None = None
    session_id: str | None = None


@app.post("/feedback")
def post_feedback(req: FeedbackRequest) -> dict:
    """Record a 👍/👎 on an answer so the dashboard can track answer quality."""
    if req.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="rating must be 'up' or 'down'")
    with get_conn() as conn:
        fid = create_feedback(conn, req.query, req.rating, req.answer, req.session_id)
        conn.commit()
    return {"feedback_id": fid, "rating": req.rating}


@app.get("/feedback")
def get_feedback() -> dict:
    """Aggregate feedback counts (up / down / total) for the dashboard."""
    with get_conn() as conn:
        return feedback_stats(conn)


@app.get("/usage")
def usage_stats() -> dict:
    """LLM usage aggregates (calls, tokens, latency, cache hit rate).

    The dashboard layers OpenAI/ChatGPT pricing on top of these raw counts to estimate
    what the same token volume would have cost on a paid API.
    """
    return get_usage_stats()
