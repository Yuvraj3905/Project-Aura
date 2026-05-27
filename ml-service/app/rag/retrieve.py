"""Vector retrieval over ready documents."""
import numpy as np

from ..config import settings
from ..db import get_conn
from ..embeddings import embed_query


def retrieve(query: str, top_k: int | None = None) -> list[dict]:
    """Return the top-k most similar chunks (cosine) from `ready` documents.

    Each result: {chunk_id, document_id, ordinal, content, score} where score is
    cosine similarity in [-1, 1] (1 = identical). Embeddings are normalized, so
    `1 - (embedding <=> q)` is the cosine similarity.
    """
    k = top_k or settings.retrieval_top_k
    q = np.asarray(embed_query(query), dtype=np.float32)

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.document_id, c.ordinal, c.content,
                   1 - (c.embedding <=> %s) AS score
              FROM chunks c
              JOIN documents d ON d.id = c.document_id
             WHERE d.status = 'ready'
             ORDER BY c.embedding <=> %s
             LIMIT %s
            """,
            (q, q, k),
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
