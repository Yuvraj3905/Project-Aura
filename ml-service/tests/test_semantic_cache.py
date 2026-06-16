"""Semantic answer cache db helpers + scope_key (no real DB — fake connection)."""
import numpy as np

from app import db
from app.rag.answer import _semantic_scope_key


class FakeCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class FakeConn:
    def __init__(self, row=None):
        self._row = row
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return FakeCursor(self._row)


def test_scope_key_global_vs_scoped():
    assert _semantic_scope_key(5, None) == "5:*"
    assert _semantic_scope_key(5, []) == "5:*"
    # order-independent + deduped
    assert _semantic_scope_key(5, ["b", "a", "a"]) == "5:a,b"
    assert _semantic_scope_key(3, ["a"]) == "3:a"


def test_semantic_lookup_hit_above_threshold():
    emb = np.array([1.0, 0.0], dtype=np.float32)
    conn = FakeConn(row=({"answer": "hi", "grounded": True}, 0.97))  # (answer, sim)
    got = db.semantic_cache_lookup(conn, emb, "5:*", threshold=0.95)
    assert got == {"answer": "hi", "grounded": True}


def test_semantic_lookup_miss_below_threshold():
    emb = np.array([1.0, 0.0], dtype=np.float32)
    conn = FakeConn(row=({"answer": "hi"}, 0.80))
    assert db.semantic_cache_lookup(conn, emb, "5:*", threshold=0.95) is None


def test_semantic_lookup_miss_no_row():
    emb = np.array([1.0, 0.0], dtype=np.float32)
    conn = FakeConn(row=None)
    assert db.semantic_cache_lookup(conn, emb, "5:*", threshold=0.95) is None


def test_semantic_insert_executes():
    emb = np.array([1.0, 0.0], dtype=np.float32)
    conn = FakeConn()
    db.semantic_cache_insert(conn, "display size?", emb, "5:*", {"answer": "1.47\""})
    assert conn.executed, "insert should run a statement"
    sql, params = conn.executed[0]
    assert "INSERT INTO answer_cache_semantic" in sql
    assert params[0] == "display size?" and params[2] == "5:*"
