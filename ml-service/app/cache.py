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


# --- session scope (sticky doc-scope per conversation) -------------------------------
# First grounded answer locks the conversation to the documents it cited; later queries
# retrieve within that scope so ambiguous follow-ups ("the 44mm") stay on-product and
# unrelated documents in the KB can't hijack an answer.

SCOPE_TTL = 24 * 3600   # matches Rasa session_expiration_time (24h)
SCOPE_PREFIX = "scope:"


def get_scope(session_id: str) -> list[str] | None:
    r = get_redis()
    if not r or not session_id:
        return None
    try:
        raw = r.get(SCOPE_PREFIX + session_id)
        return json.loads(raw) if raw else None
    except (redis.RedisError, ValueError):
        return None


def set_scope(session_id: str, document_ids: list[str]) -> None:
    r = get_redis()
    if not r or not session_id or not document_ids:
        return
    try:
        r.set(SCOPE_PREFIX + session_id, json.dumps(sorted(set(document_ids))), ex=SCOPE_TTL)
    except redis.RedisError:
        pass


# --- conversation history (for query rewriting) -------------------------------------

HISTORY_PREFIX = "hist:"
HISTORY_TTL = 24 * 3600
_ANSWER_SNIPPET = 300


def get_history(session_id: str) -> list[dict]:
    """Recent [{q, a}, ...] turns for a session (oldest first); [] if none/disabled."""
    r = get_redis()
    if not r or not session_id:
        return []
    try:
        raw = r.get(HISTORY_PREFIX + session_id)
        return json.loads(raw) if raw else []
    except (redis.RedisError, ValueError):
        return []


def append_history(session_id: str, query: str, answer: str, max_turns: int) -> None:
    """Append a (query, answer-snippet) turn, keeping only the last `max_turns`."""
    r = get_redis()
    if not r or not session_id:
        return
    try:
        hist = get_history(session_id)
        hist.append({"q": query, "a": (answer or "")[:_ANSWER_SNIPPET]})
        r.set(HISTORY_PREFIX + session_id, json.dumps(hist[-max_turns:]), ex=HISTORY_TTL)
    except redis.RedisError:
        pass


def clear_scope(session_id: str) -> None:
    """Drop a conversation's sticky doc scope (called when a chat session is disposed)."""
    r = get_redis()
    if not r or not session_id:
        return
    try:
        r.delete(SCOPE_PREFIX + session_id, HISTORY_PREFIX + session_id)
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
