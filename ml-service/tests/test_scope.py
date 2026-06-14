"""Session doc-scope store tests (no real Redis — client monkeypatched)."""
import json

from app import cache


class FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value

    def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)

    def ping(self):
        return True


def test_scope_round_trip(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    cache.set_scope("sess-1", ["doc-b", "doc-a", "doc-a"])
    assert cache.get_scope("sess-1") == ["doc-a", "doc-b"]  # sorted, deduped


def test_scope_miss_returns_none(monkeypatch):
    monkeypatch.setattr(cache, "get_redis", lambda: FakeRedis())
    assert cache.get_scope("unknown") is None


def test_scope_noop_without_redis(monkeypatch):
    monkeypatch.setattr(cache, "get_redis", lambda: None)
    cache.set_scope("sess-1", ["doc-a"])  # must not raise
    assert cache.get_scope("sess-1") is None


def test_scope_ignores_empty_inputs(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    cache.set_scope("", ["doc-a"])
    cache.set_scope("sess-1", [])
    assert fake.store == {}
    assert cache.get_scope("") is None


def test_scope_key_uses_prefix(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    cache.set_scope("sess-9", ["d1"])
    assert list(fake.store) == [cache.SCOPE_PREFIX + "sess-9"]
    assert json.loads(fake.store[cache.SCOPE_PREFIX + "sess-9"]) == ["d1"]


def test_clear_scope_removes_key(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    cache.set_scope("sess-1", ["d1"])
    assert cache.get_scope("sess-1") == ["d1"]
    cache.clear_scope("sess-1")
    assert cache.get_scope("sess-1") is None


def test_clear_scope_noop_without_redis_or_id(monkeypatch):
    monkeypatch.setattr(cache, "get_redis", lambda: None)
    cache.clear_scope("sess-1")  # must not raise
    fake = FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    cache.clear_scope("")        # empty id is a no-op
