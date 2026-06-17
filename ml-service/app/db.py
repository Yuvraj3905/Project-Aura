"""PostgreSQL access (psycopg 3) with pgvector type registration."""
from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector
from psycopg.types.json import Json

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


def create_ticket(
    conn,
    email: str,
    description: str,
    session_id: str | None = None,
    subject: str | None = None,
) -> str:
    """Insert a support ticket and return its id."""
    row = conn.execute(
        """
        INSERT INTO support_tickets (email, subject, description, session_id)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (email, subject, description, session_id),
    ).fetchone()
    return str(row[0])


def list_tickets(conn, limit: int = 100) -> list[dict]:
    """Return recent tickets as dicts (newest first)."""
    rows = conn.execute(
        """
        SELECT id, email, subject, description, session_id, status, created_at
          FROM support_tickets
         ORDER BY created_at DESC
         LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "id": str(r[0]),
            "email": r[1],
            "subject": r[2],
            "description": r[3],
            "session_id": r[4],
            "status": r[5],
            "created_at": r[6].isoformat() if r[6] else None,
        }
        for r in rows
    ]


def update_ticket_status(conn, ticket_id: str, status: str) -> bool:
    """Set a ticket's status. Returns False if the ticket does not exist."""
    row = conn.execute(
        "UPDATE support_tickets SET status = %s WHERE id = %s RETURNING id",
        (status, ticket_id),
    ).fetchone()
    return row is not None


def create_lead(
    conn,
    email: str,
    name: str | None = None,
    product_interest: str | None = None,
    session_id: str | None = None,
) -> str:
    """Insert a sales lead and return its id."""
    row = conn.execute(
        """
        INSERT INTO leads (name, email, product_interest, session_id)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (name, email, product_interest, session_id),
    ).fetchone()
    return str(row[0])


def list_leads(conn, limit: int = 100) -> list[dict]:
    """Return recent leads as dicts (newest first)."""
    rows = conn.execute(
        """
        SELECT id, name, email, product_interest, session_id, status, created_at
          FROM leads
         ORDER BY created_at DESC
         LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "id": str(r[0]),
            "name": r[1],
            "email": r[2],
            "product_interest": r[3],
            "session_id": r[4],
            "status": r[5],
            "created_at": r[6].isoformat() if r[6] else None,
        }
        for r in rows
    ]


def create_order(
    conn,
    email: str,
    product: str,
    quantity: int = 1,
    session_id: str | None = None,
) -> str:
    """Insert a purchase order and return its id."""
    row = conn.execute(
        """
        INSERT INTO orders (email, product, quantity, session_id)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (email, product, quantity, session_id),
    ).fetchone()
    return str(row[0])


def list_orders(conn, limit: int = 100) -> list[dict]:
    """Return recent orders as dicts (newest first)."""
    rows = conn.execute(
        """
        SELECT id, email, product, quantity, session_id, status, created_at
          FROM orders
         ORDER BY created_at DESC
         LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "id": str(r[0]),
            "email": r[1],
            "product": r[2],
            "quantity": r[3],
            "session_id": r[4],
            "status": r[5],
            "created_at": r[6].isoformat() if r[6] else None,
        }
        for r in rows
    ]


def update_order_status(conn, order_id: str, status: str) -> bool:
    """Set an order's status. Returns False if the order does not exist."""
    row = conn.execute(
        "UPDATE orders SET status = %s WHERE id = %s RETURNING id",
        (status, order_id),
    ).fetchone()
    return row is not None


def semantic_cache_lookup(conn, query_embedding, scope_key: str, threshold: float):
    """Return a cached answer dict for the nearest prior query in the same scope, if its
    cosine similarity clears `threshold`; else None.

    Embeddings are normalized, so `1 - (query_embedding <=> q)` is cosine similarity.
    """
    row = conn.execute(
        """
        SELECT answer, 1 - (query_embedding <=> %s) AS sim
          FROM answer_cache_semantic
         WHERE scope_key = %s
         ORDER BY query_embedding <=> %s
         LIMIT 1
        """,
        (query_embedding, scope_key, query_embedding),
    ).fetchone()
    if row is None or row[1] < threshold:
        return None
    return row[0]


def semantic_cache_insert(conn, query: str, query_embedding, scope_key: str, answer: dict) -> None:
    """Store an answered query so future near-duplicate queries can reuse the answer."""
    conn.execute(
        """
        INSERT INTO answer_cache_semantic (query, query_embedding, scope_key, answer)
        VALUES (%s, %s, %s, %s)
        """,
        (query, query_embedding, scope_key, Json(answer)),
    )


def truncate_semantic_cache(conn) -> None:
    """Drop all semantic-cache rows (a new document can change correct answers)."""
    conn.execute("TRUNCATE answer_cache_semantic")


def documents_for_product(conn, product: str) -> list[str]:
    """READY document ids whose product matches `product` (case-insensitive substring)."""
    rows = conn.execute(
        "SELECT id FROM documents WHERE status = 'ready' AND product ILIKE %s",
        (f"%{product}%",),
    ).fetchall()
    return [str(r[0]) for r in rows]


def set_document_product(conn, document_id: str, product: str) -> None:
    """Set a document's product tag."""
    conn.execute(
        "UPDATE documents SET product = %s WHERE id = %s",
        (product, document_id),
    )


def documents_missing_product(conn) -> list[dict]:
    """READY documents with no product tag yet (for backfill): [{id, summary}]."""
    rows = conn.execute(
        "SELECT id, summary FROM documents WHERE status = 'ready' AND product IS NULL",
    ).fetchall()
    return [{"id": str(r[0]), "summary": r[1]} for r in rows]


def fetch_document(conn, document_id: str) -> dict:
    """Return {filename, storage_path, mime_type} for a document, or raise if missing."""
    row = conn.execute(
        "SELECT filename, storage_path, mime_type FROM documents WHERE id = %s",
        (document_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"document {document_id} not found")
    return {"filename": row[0], "storage_path": row[1], "mime_type": row[2]}
