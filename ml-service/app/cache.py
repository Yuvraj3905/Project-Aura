"""Redis cache for query embeddings and grounded answers.

Two caches, both keyed by a stable hash so identical requests are cheap:
  - emb:<hash(model+text)>           -> JSON float list, TTL 24h (embeddings are static)
  - answer:<hash(query+top_k+docs)>  -> JSON {answer, grounded, citations}, TTL 1h

The answer cache is flushed whenever a new document becomes ready, since a fresh
document can change what any query should return.

All operations degrade gracefully: if Redis is unreachable, helpers return cache-miss
(None) or no-op rather than raising, so the service keeps working without the cache.
"""
import hashlib
import json
import logging
from typing import Any

import redis

from .config import settings

log = logging.getLogger("aura.cache")

EMBED_TTL = 24 * 3600
ANSWER_TTL = 3600
ANSWER_PREFIX = "answer:"

_client: redis.Redis | None = None


def get_redis() -> redis.Redis | None:
    """Return a shared Redis client, or None if caching is disabled/unreachable."""
    global _client
    if not settings.redis_url:
        return None
    if _client is None:
        try:
            _client = redis.Redis.from_url(settings.redis_url, socket_timeout=2)
            _client.ping()
        except redis.RedisError as exc:  # noqa: BLE001
            log.warning("redis unavailable, caching disabled: %s", exc)
            _client = None
    return _client


def _hash(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()


# --- embedding cache ---------------------------------------------------------------

def embed_key(text: str) -> str:
    return "emb:" + _hash(settings.embedding_model, text)


def get_embedding(text: str) -> list[float] | None:
    r = get_redis()
    if not r:
        return None
    try:
        raw = r.get(embed_key(text))
        return json.loads(raw) if raw else None
    except (redis.RedisError, ValueError):
        return None


def set_embedding(text: str, vector: list[float]) -> None:
    r = get_redis()
    if not r:
        return
    try:
        r.set(embed_key(text), json.dumps(vector), ex=EMBED_TTL)
    except redis.RedisError:
        pass


# --- answer cache ------------------------------------------------------------------

def answer_key(query: str, top_k: int, document_ids: list[str] | None) -> str:
    docs = ",".join(sorted(document_ids)) if document_ids else "*"
    return ANSWER_PREFIX + _hash(query, str(top_k), docs)


def get_answer(query: str, top_k: int, document_ids: list[str] | None) -> dict[str, Any] | None:
    r = get_redis()
    if not r:
        return None
    try:
        raw = r.get(answer_key(query, top_k, document_ids))
        return json.loads(raw) if raw else None
    except (redis.RedisError, ValueError):
        return None


def set_answer(
    query: str, top_k: int, document_ids: list[str] | None, value: dict[str, Any]
) -> None:
    r = get_redis()
    if not r:
        return
    try:
        r.set(answer_key(query, top_k, document_ids), json.dumps(value), ex=ANSWER_TTL)
    except redis.RedisError:
        pass


def invalidate_answers() -> int:
    """Drop all cached answers (called when the knowledge base changes)."""
    r = get_redis()
    if not r:
        return 0
    try:
        keys = list(r.scan_iter(match=ANSWER_PREFIX + "*", count=500))
        if keys:
            r.delete(*keys)
        return len(keys)
    except redis.RedisError:
        return 0
