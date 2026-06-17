"""Per-product routing db helpers + primary-product resolution (no real DB)."""
from app import db
from app.rag import answer as answer_mod


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConn:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return FakeCursor(self._rows)


def test_documents_for_product_query_and_params():
    conn = FakeConn(rows=[("id-a",), ("id-b",)])
    ids = db.documents_for_product(conn, "Galaxy Watch")
    assert ids == ["id-a", "id-b"]
    sql, params = conn.executed[0]
    assert "product ILIKE" in sql and "status = 'ready'" in sql
    assert params == ("%Galaxy Watch%",)


def test_set_document_product():
    conn = FakeConn()
    db.set_document_product(conn, "doc-1", "News CMS Platform")
    sql, params = conn.executed[0]
    assert "UPDATE documents SET product" in sql
    assert params == ("News CMS Platform", "doc-1")


def test_documents_missing_product():
    conn = FakeConn(rows=[("id-x", "summary x")])
    rows = db.documents_missing_product(conn)
    assert rows == [{"id": "id-x", "summary": "summary x"}]
    assert "product IS NULL" in conn.executed[0][0]


# --- primary-product resolution ---------------------------------------------------

def test_primary_product_docs_disabled(monkeypatch):
    monkeypatch.setattr(answer_mod.settings, "primary_product", "")
    assert answer_mod._primary_product_docs() is None


def test_primary_product_docs_match(monkeypatch):
    monkeypatch.setattr(answer_mod.settings, "primary_product", "Galaxy Watch")
    monkeypatch.setattr(answer_mod, "_product_doc_ids", lambda p: ["w1", "w2"])
    assert answer_mod._primary_product_docs() == ["w1", "w2"]


def test_primary_product_docs_no_match_falls_back_to_global(monkeypatch):
    monkeypatch.setattr(answer_mod.settings, "primary_product", "Galaxy Watch")
    monkeypatch.setattr(answer_mod, "_product_doc_ids", lambda p: [])
    # No docs match → None so retrieval falls back to global, not an empty filter.
    assert answer_mod._primary_product_docs() is None
