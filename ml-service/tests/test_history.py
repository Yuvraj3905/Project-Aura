"""Conversation history store for query rewriting (no real Redis)."""
import json

from app import cache


class FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value

    def ping(self):
        return True


def test_history_append_and_get(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    cache.append_history("s1", "tell me about the Classic", "It has a rotating bezel.", max_turns=3)
    cache.append_history("s1", "what is its battery", "445 mAh.", max_turns=3)
    hist = cache.get_history("s1")
    assert [h["q"] for h in hist] == ["tell me about the Classic", "what is its battery"]
    assert hist[1]["a"] == "445 mAh."


def test_history_capped_to_max_turns(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    for i in range(5):
        cache.append_history("s1", f"q{i}", f"a{i}", max_turns=3)
    hist = cache.get_history("s1")
    assert [h["q"] for h in hist] == ["q2", "q3", "q4"]   # only last 3 kept


def test_history_answer_snippet_truncated(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    cache.append_history("s1", "q", "x" * 1000, max_turns=3)
    assert len(cache.get_history("s1")[0]["a"]) <= 300


def test_history_empty_and_noredis(monkeypatch):
    monkeypatch.setattr(cache, "get_redis", lambda: None)
    assert cache.get_history("s1") == []
    cache.append_history("s1", "q", "a", max_turns=3)  # no-op, no raise
    fake = FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    assert cache.get_history("unknown") == []
