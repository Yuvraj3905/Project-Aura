"""Vector + hybrid retrieval over ready documents.

The "retrieve" half of RAG: embed the user's query, then find the chunks whose stored
embeddings are nearest (cosine) — the evidence the LLM will answer from.

Phase 2 adds **hybrid retrieval**: run a lexical (Postgres full-text / BM25-like) search
alongside the vector search and fuse the two rankings with Reciprocal Rank Fusion, then
optionally drop near-duplicate chunks (MMR). This catches exact-term matches a pure
vector search misses while keeping the cosine score on every chunk for the guardrail.
"""
import numpy as np

from ..config import settings
from ..db import get_conn
from ..embeddings import embed_query


def rrf_fuse(lists: list[list[dict]], k: int, limit: int) -> list[dict]:
    """Reciprocal Rank Fusion of several ranked chunk lists.

    Each chunk's fused score is the sum over the lists it appears in of 1/(k + rank)
    (rank is 1-based). Chunks ranked highly across multiple lists rise to the top.
    The first-seen payload for each chunk_id is kept (deduped). Returns the top `limit`.
    """
    fused: dict[str, float] = {}
    payload: dict[str, dict] = {}
    for ranked in lists:
        for rank, chunk in enumerate(ranked, start=1):
            cid = chunk["chunk_id"]
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (k + rank)
            payload.setdefault(cid, chunk)
    ordered = sorted(fused, key=lambda cid: fused[cid], reverse=True)
    return [payload[cid] for cid in ordered[:limit]]


def mmr_dedupe(chunks: list[dict], threshold: float) -> list[dict]:
    """Greedily drop chunks that are near-duplicates of an already-kept chunk.

    Keeps a chunk only if its cosine similarity to every kept chunk is below `threshold`.
    Embeddings are L2-normalized at ingest, so cosine == dot product. Chunks without an
    embedding are always kept (nothing to compare).
    """
    kept: list[dict] = []
    kept_embs: list[np.ndarray] = []
    for chunk in chunks:
        emb = chunk.get("embedding")
        if emb is None:
            kept.append(chunk)
            continue
        emb = np.asarray(emb, dtype=np.float32)
        if any(float(np.dot(emb, e)) > threshold for e in kept_embs):
            continue
        kept.append(chunk)
        kept_embs.append(emb)
    return kept


def dominant_doc_filter(chunks: list[dict]) -> list[dict]:
    """Keep only chunks from the single best-matching document.

    On an unscoped query against a mixed knowledge base, a tangential chunk from an
    unrelated document can otherwise bleed into the answer (e.g. a news-CMS doc surfacing
    on "what have you got"). Restricting to the top-scoring document's chunks keeps the
    answer on one product. Order is preserved.
    """
    if not chunks:
        return []
    top_doc = max(chunks, key=lambda c: c["score"])["document_id"]
    return [c for c in chunks if c["document_id"] == top_doc]


def _strip_embeddings(chunks: list[dict]) -> list[dict]:
    """Drop the internal `embedding` field before returning to callers."""
    for c in chunks:
        c.pop("embedding", None)
    return chunks


def _row_to_chunk(r) -> dict:
    return {
        "chunk_id": str(r[0]),
        "document_id": str(r[1]),
        "ordinal": r[2],
        "content": r[3],
        "score": float(r[4]),
        "embedding": r[5],
    }


def _where_and_params(q, document_ids):
    where = "d.status = 'ready'"
    params: list = [q]
    if document_ids:
        where += " AND c.document_id = ANY(%s)"
        params.append(document_ids)
    return where, params


def _vector_candidates(conn, q, document_ids, n) -> list[dict]:
    where, params = _where_and_params(q, document_ids)
    rows = conn.execute(
        f"""
        SELECT c.id, c.document_id, c.ordinal, c.content,
               1 - (c.embedding <=> %s) AS score, c.embedding
          FROM chunks c JOIN documents d ON d.id = c.document_id
         WHERE {where}
         ORDER BY c.embedding <=> %s
         LIMIT %s
        """,
        [q, *params[1:], q, n],
    ).fetchall()
    return [_row_to_chunk(r) for r in rows]


def _lexical_candidates(conn, q, query_text, document_ids, n) -> list[dict]:
    # Params MUST follow placeholder order in the SQL below:
    #   $1 score(q) | [$ doc_ids if scoped] | tsquery(WHERE) | tsquery(ORDER) | limit
    doc_filter = ""
    params: list = [q]
    if document_ids:
        doc_filter = "AND c.document_id = ANY(%s)"
        params.append(document_ids)
    params += [query_text, query_text, n]
    rows = conn.execute(
        f"""
        SELECT c.id, c.document_id, c.ordinal, c.content,
               1 - (c.embedding <=> %s) AS score, c.embedding
          FROM chunks c JOIN documents d ON d.id = c.document_id
         WHERE d.status = 'ready' {doc_filter}
           AND c.content_tsv @@ websearch_to_tsquery('english', %s)
         ORDER BY ts_rank_cd(c.content_tsv, websearch_to_tsquery('english', %s)) DESC
         LIMIT %s
        """,
        params,
    ).fetchall()
    return [_row_to_chunk(r) for r in rows]


def retrieve(
    query: str,
    top_k: int | None = None,
    document_ids: list[str] | None = None,
) -> list[dict]:
    """Return the top-k most similar chunks from `ready` documents.

    Pure vector search by default; hybrid (lexical + vector via RRF, then MMR dedupe)
    when `settings.hybrid_retrieval`. When `document_ids` is given, retrieval is
    restricted to those documents (the sticky/multi-doc scope). Each result:
    {chunk_id, document_id, ordinal, content, score} where score is cosine similarity.
    """
    k = top_k or settings.retrieval_top_k
    q = np.asarray(embed_query(query), dtype=np.float32)  # cached via embed_query

    with get_conn() as conn:
        if not settings.hybrid_retrieval:
            chunks = _vector_candidates(conn, q, document_ids, k)
        else:
            n = settings.hybrid_candidates
            vec = _vector_candidates(conn, q, document_ids, n)
            lex = _lexical_candidates(conn, q, query, document_ids, n)
            fused = rrf_fuse([vec, lex], k=settings.rrf_k,
                             limit=k * 2 if settings.mmr_dedupe else k)
            if settings.mmr_dedupe:
                fused = mmr_dedupe(fused, settings.mmr_dup_threshold)
            chunks = fused[:k]

    # Unscoped query against a mixed KB: keep the answer to the top-matching document.
    if document_ids is None and settings.answer_single_doc:
        chunks = dominant_doc_filter(chunks)
    return _strip_embeddings(chunks[:k])
