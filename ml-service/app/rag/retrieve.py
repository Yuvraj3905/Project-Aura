"""Vector retrieval over ready documents.

The "retrieve" half of RAG: embed the user's query, then ask pgvector for the chunks
whose stored embeddings are nearest (cosine) — the evidence the LLM will answer from.
"""
import numpy as np

from ..config import settings
from ..db import get_conn
from ..embeddings import embed_query


def retrieve(
    query: str,
    top_k: int | None = None,
    document_ids: list[str] | None = None,
) -> list[dict]:
    """Return the top-k most similar chunks (cosine) from `ready` documents.

    When `document_ids` is given, retrieval is restricted to those documents (the
    multi-doc filter), so a query can be answered against a chosen subset of the
    knowledge base. Each result: {chunk_id, document_id, ordinal, content, score}
    where score is cosine similarity in [-1, 1]. Embeddings are normalized, so
    `1 - (embedding <=> q)` is the cosine similarity.
    """
    k = top_k or settings.retrieval_top_k
    q = np.asarray(embed_query(query), dtype=np.float32)  # cached via embed_query

    # Build WHERE incrementally. The query vector `q` appears twice in the SQL (SELECT
    # score + ORDER BY distance), so params are ordered: [q (score), (ids?), q (order), k].
    where = "d.status = 'ready'"          # never retrieve from a doc still ingesting/failed
    params: list = [q]
    if document_ids:
        where += " AND c.document_id = ANY(%s)"   # multi-doc filter
        params.append(document_ids)
    params += [q, k]

    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT c.id, c.document_id, c.ordinal, c.content,
                   1 - (c.embedding <=> %s) AS score
              FROM chunks c
              JOIN documents d ON d.id = c.document_id
             WHERE {where}
             ORDER BY c.embedding <=> %s
             LIMIT %s
            """,
            params,
        ).fetchall()

    return [
        {
            "chunk_id": str(r[0]),
            "document_id": str(r[1]),
            "ordinal": r[2],
            "content": r[3],
            "score": float(r[4]),
        }
        for r in rows
    ]
