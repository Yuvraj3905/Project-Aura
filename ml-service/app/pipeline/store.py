"""Persistence for the ingestion pipeline: chunk writes + document status."""


def reset_document_chunks(conn, document_id: str) -> None:
    """Delete existing chunks so re-ingest is idempotent (no duplicates)."""
    conn.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))


def insert_chunks(conn, document_id: str, rows: list[dict]) -> None:
    """Batch-insert chunk rows.

    Each row: {ordinal, content, contextualized_content, token_count, embedding}.
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
    """Update a document's processing status (and optional metadata)."""
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
