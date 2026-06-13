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


def fetch_document(conn, document_id: str) -> dict:
    """Return {filename, storage_path, mime_type} for a document, or raise if missing."""
    row = conn.execute(
        "SELECT filename, storage_path, mime_type FROM documents WHERE id = %s",
        (document_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"document {document_id} not found")
    return {"filename": row[0], "storage_path": row[1], "mime_type": row[2]}
