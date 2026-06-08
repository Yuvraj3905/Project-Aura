"""Persistence for the ingestion pipeline: chunk writes + document status.

Final stage of ingestion. All three functions operate on a caller-managed connection
(the caller owns the transaction / commit), so a single ingest can delete-then-insert
chunks and flip the document to 'ready' atomically.
"""


def reset_document_chunks(conn, document_id: str) -> None:
    """Delete existing chunks so re-ingest is idempotent (no duplicates).

    Re-uploading or retrying a document re-runs the whole pipeline; clearing prior chunks
    first means a retry never leaves duplicate or stale vectors behind.
    """
    conn.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))


def insert_chunks(conn, document_id: str, rows: list[dict]) -> None:
    """Batch-insert chunk rows in a single round-trip.

    Each row: {ordinal, content, contextualized_content, token_count, embedding}.
    `executemany` sends all rows at once rather than one INSERT per chunk — large docs
    produce hundreds of chunks, so this matters.
    """
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO chunks
                (document_id, ordinal, content, contextualized_content, token_count, embedding)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    document_id,
                    r["ordinal"],
                    r["content"],
                    r["contextualized_content"],
                    r["token_count"],
                    r["embedding"],
                )
                for r in rows
            ],
        )


def mark_status(
    conn,
    document_id: str,
    status: str,
    *,
    summary: str | None = None,
    n_chunks: int | None = None,
    error: str | None = None,
) -> None:
    """Update a document's processing status (and optional metadata).

    COALESCE keeps the existing summary/n_chunks when those args are None, so an
    intermediate `mark_status(..., 'processing')` call doesn't wipe values a later
    'ready' call will set. `error` is set unconditionally (cleared to NULL on success).
    """
    conn.execute(
        """
        UPDATE documents
           SET status   = %s,
               summary  = COALESCE(%s, summary),
               n_chunks = COALESCE(%s, n_chunks),
               error    = %s
         WHERE id = %s
        """,
        (status, summary, n_chunks, error, document_id),
    )
