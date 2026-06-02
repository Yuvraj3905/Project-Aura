"""Cache key + graceful-degrade tests (no Redis required)."""
from app import cache


def test_answer_key_stable_and_doc_order_independent():
    k1 = cache.answer_key("q", 5, ["b", "a"])
    k2 = cache.answer_key("q", 5, ["a", "b"])
    assert k1 == k2  # document_ids sorted before hashing


def test_answer_key_varies_on_inputs():
    base = cache.answer_key("q", 5, None)
    assert base != cache.answer_key("q2", 5, None)
    assert base != cache.answer_key("q", 3, None)
    assert base != cache.answer_key("q", 5, ["a"])


def test_embed_key_depends_on_text():
    assert cache.embed_key("a") != cache.embed_key("b")


def test_graceful_when_redis_unreachable(monkeypatch):
    # Force the client getter to report no cache; helpers must not raise.
    monkeypatch.setattr(cache, "get_redis", lambda: None)
    assert cache.get_embedding("x") is None
    cache.set_embedding("x", [0.1, 0.2])  # no-op, no raise
    assert cache.get_answer("q", 5, None) is None
    cache.set_answer("q", 5, None, {"answer": "a"})  # no-op
    assert cache.invalidate_answers() == 0
