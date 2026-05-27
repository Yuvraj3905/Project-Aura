"""PostgreSQL access (psycopg 3) with pgvector type registration."""
from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector

from .config import settings


@contextmanager
def get_conn():
    """Yield a connection with the pgvector type registered."""
    conn = psycopg.connect(settings.database_url)
    try:
        register_vector(conn)
        yield conn
    finally:
        conn.close()


def fetch_document(conn, document_id: str) -> dict:
    """Return {filename, storage_path, mime_type} for a document, or raise if missing."""
    row = conn.execute(
        "SELECT filename, storage_path, mime_type FROM documents WHERE id = %s",
        (document_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"document {document_id} not found")
    return {"filename": row[0], "storage_path": row[1], "mime_type": row[2]}
