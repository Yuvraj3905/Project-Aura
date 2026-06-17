"""Grounded answer generation with an anti-hallucination guardrail.

If retrieval is weak (top score below threshold), we return a "don't know" answer
WITHOUT calling the LLM — the model never gets a chance to invent facts. When grounded,
the system prompt further constrains it to answer only from the supplied context.

Two entry points share the same retrieval + guardrail + prompt:
  - answer_query: blocking, returns the full result dict (Redis-cached).
  - answer_stream: generator yielding ("token", text) then ("done", result) for SSE.
"""
import logging
from typing import Iterator

import numpy as np

from .. import cache, usage
from ..config import settings
from ..db import (
    documents_for_product,
    get_conn,
    semantic_cache_insert,
    semantic_cache_lookup,
)
from ..embeddings import embed_query
from ..llm import generate_full, generate_stream
from .retrieve import retrieve

log = logging.getLogger("aura.answer")

SYSTEM_PROMPT = (
    "You are Aura, an upbeat, persuasive B2B sales agent who loves the product and is "
    "eager to close the deal. Talk to the user like a warm, confident salesperson talking "
    "to a prospect: enthusiastic, benefit-focused, and conversational. "
    "NEVER use meta phrases like 'according to the context', 'based on the provided "
    "context', 'the document says', or 'in the knowledge base' — just answer directly and "
    "confidently as if you know the product inside-out. "
    "Ground every spec, number, and claim ONLY in the facts you are given — never invent "
    "specs, prices, features, or availability. If the customer asks about a specific model "
    "or variant that is NOT in the context, do NOT invent it — say you don't carry that "
    "model and offer the ones you do. Present the real facts with energy, "
    "highlight the benefits to the customer, and nudge them toward buying (suggest a model, "
    "invite the next step). Keep it concise. "
    "Format your reply in markdown: **bold** the key specs and model names, and use bullet "
    "lists when comparing options or listing features, so it's easy to skim."
)

# Salesy deflection when retrieval is too weak — stays honest (no invented facts) but keeps
# the sales tone instead of a robotic "not in the knowledge base".
NO_ANSWER = (
    "Great question! I don't have those exact details on hand right this second, but I'd "
    "love to track them down for you. In the meantime, is there another model or feature I "
    "can walk you through to help you find the perfect fit?"
)

# Returned when the user names a product variant we have no information on — refuse instead
# of inventing its specs.
VARIANT_NO_MATCH = (
    "Hmm, I don't have that exact model in our lineup right now — and I'd never want to "
    "guess at specs. I'd love to walk you through the models we do carry, though. Which one "
    "can I tell you about?"
)

# Variant qualifiers that, if named in a query but absent from every retrieved chunk, mean
# the user is asking about a model we don't have (e.g. an invented "Watch 8 Ultra").
_VARIANT_QUALIFIERS = {
    "ultra", "pro", "max", "plus", "mini", "lite", "ultimate", "fe", "edge",
}


def _refusal(query: str, chunks: list[dict]) -> str | None:
    """Decide whether to refuse rather than generate: VARIANT_NO_MATCH for an invented
    model, NO_ANSWER for weak retrieval, else None (proceed to the LLM)."""
    if settings.variant_guard and _unsupported_variant(query, chunks):
        return VARIANT_NO_MATCH
    if not is_grounded(chunks, settings.retrieval_min_score):
        return NO_ANSWER
    return None


def _unsupported_variant(query: str, chunks: list[dict]) -> str | None:
    """Return a variant qualifier named in the query that appears in NO retrieved chunk,
    else None. Guards against the LLM inventing specs for a model we don't carry."""
    words = {w.strip("?.,!'\"").lower() for w in query.split()}
    named = words & _VARIANT_QUALIFIERS
    if not named:
        return None
    context = " ".join(c["content"] for c in chunks).lower()
    for term in named:
        if term not in context:
            return term
    return None


def is_grounded(chunks: list[dict], min_score: float) -> bool:
    """True if the best retrieved chunk clears the similarity threshold."""
    return bool(chunks) and chunks[0]["score"] >= min_score


def format_context(chunks: list[dict]) -> str:
    return "\n\n".join(
        f"[document {c['document_id']} · chunk {c['ordinal']}]\n{c['content']}"
        for c in chunks
    )


def _build_prompt(query: str, chunks: list[dict]) -> str:
    return (
        f"Product information you know:\n{format_context(chunks)}\n\n"
        f"Customer asks: {query}\n\n"
        "Reply as the eager sales agent — use only the product information above for any "
        "facts, but never mention 'context', 'documents', or where the info came from."
    )


REWRITE_SYSTEM = (
    "You rewrite a customer's follow-up message into a single standalone question, using "
    "the conversation so far to resolve references like 'it', 'its', 'that one', 'the "
    "other'. Output ONLY the rewritten question — no preamble, no quotes. If the message "
    "is already standalone, output it unchanged."
)

# Anaphora / ellipsis signals that a message leans on prior turns.
_FOLLOWUP_WORDS = {
    "it", "its", "it's", "that", "this", "they", "them", "those", "these",
    "one", "ones", "other", "another", "same", "he", "she",
}


def _looks_like_followup(query: str) -> bool:
    """Cheap gate: only rewrite messages that likely depend on prior turns, so standalone
    questions skip the extra LLM call."""
    words = [w.strip("?.,!").lower() for w in query.split()]
    if len(words) <= 3:
        return True
    return any(w in _FOLLOWUP_WORDS for w in words)


def _rewrite_llm(query: str, history: list[dict]) -> str:
    """Ask the LLM to resolve a follow-up into a standalone question. Returns "" on failure."""
    convo = "\n".join(f"Customer: {h['q']}\nAura: {h['a']}" for h in history)
    prompt = (
        f"Conversation so far:\n{convo}\n\n"
        f"Follow-up message: {query}\n\n"
        "Standalone question:"
    )
    try:
        return generate_full(prompt, system=REWRITE_SYSTEM, kind="rewrite")["text"].strip()
    except Exception as exc:  # noqa: BLE001 — never let rewrite break answering
        log.warning("query rewrite failed: %s", exc)
        return ""


def _maybe_rewrite(query: str, session_id: str | None) -> str:
    """Return a standalone version of `query` when it's a follow-up and we have history;
    otherwise return `query` unchanged."""
    if not settings.query_rewrite or not session_id or not _looks_like_followup(query):
        return query
    history = cache.get_history(session_id)
    if not history:
        return query
    rewritten = _rewrite_llm(query, history[-settings.query_rewrite_max_turns:])
    # Guard against junk: empty, or implausibly long (model rambled instead of one question).
    if not rewritten or len(rewritten) > 300:
        return query
    return rewritten


def _record_turn(session_id: str | None, query: str, answer: str) -> None:
    """Store the (original user query, answer) turn so the next follow-up can be resolved."""
    if settings.query_rewrite and session_id:
        cache.append_history(session_id, query, answer, settings.query_rewrite_max_turns)


def _semantic_scope_key(k: int, document_ids: list[str] | None) -> str:
    """Cache partition key — same dimensions the exact Redis answer cache keys on, so a
    semantic hit can never cross a document scope."""
    docs = ",".join(sorted(set(document_ids))) if document_ids else "*"
    return f"{k}:{docs}"


def _semantic_get(query: str, k: int, document_ids: list[str] | None) -> dict | None:
    """Best-effort semantic-cache read. Returns a cached result dict or None."""
    if not settings.semantic_cache:
        return None
    try:
        q = np.asarray(embed_query(query), dtype=np.float32)
        with get_conn() as conn:
            return semantic_cache_lookup(
                conn, q, _semantic_scope_key(k, document_ids),
                settings.semantic_cache_threshold,
            )
    except Exception as exc:  # noqa: BLE001 — cache must never break answering
        log.warning("semantic cache lookup failed: %s", exc)
        return None


def _semantic_put(query: str, k: int, document_ids: list[str] | None, result: dict) -> None:
    """Best-effort semantic-cache write of a freshly generated answer."""
    if not settings.semantic_cache:
        return
    try:
        q = np.asarray(embed_query(query), dtype=np.float32)
        with get_conn() as conn:
            semantic_cache_insert(conn, query, q, _semantic_scope_key(k, document_ids), result)
            conn.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("semantic cache insert failed: %s", exc)


def _product_doc_ids(product: str) -> list[str]:
    """Document ids belonging to a product (own DB connection; [] on error)."""
    try:
        with get_conn() as conn:
            return documents_for_product(conn, product)
    except Exception as exc:  # noqa: BLE001 — routing must never break answering
        log.warning("product doc lookup failed: %s", exc)
        return []


def _primary_product_docs() -> list[str] | None:
    """Doc ids for the configured primary product, or None to search the whole KB.

    Returns None when routing is disabled (no PRIMARY_PRODUCT) OR no document matches it —
    in the no-match case we fall back to global retrieval rather than an empty filter that
    would answer nothing.
    """
    if not settings.primary_product:
        return None
    ids = _product_doc_ids(settings.primary_product)
    return ids or None


def _resolve_chunks(
    query: str,
    k: int,
    document_ids: list[str] | None,
    session_id: str | None,
) -> tuple[list[dict], list[str] | None]:
    """Retrieve chunks honoring the sticky per-session document scope.

    Returns (chunks, scope_to_save). scope_to_save is non-None only when the session's
    scope should change (first grounded answer, or a strong topic switch).

    Paths:
      explicit  — caller passed document_ids: manual selection always wins, no sticky.
      lock      — no stored scope: global retrieval; grounded → lock to cited docs.
      scoped    — stored scope, scoped retrieval grounded → stay in scope.
      relock    — scoped weak; global retry clears the HIGHER relock bar → topic switch.
      weak      — weak everywhere → return the weak scoped chunks so the guardrail
                  fires (NO_ANSWER) instead of answering from an unrelated document.
    """
    if document_ids:
        return retrieve(query, k, document_ids), None

    # Unscoped: route to the deployment's primary product (None = whole KB).
    base = _primary_product_docs()

    stored = cache.get_scope(session_id) if session_id else None
    if not stored:
        chunks = retrieve(query, k, base)
        if session_id and is_grounded(chunks, settings.retrieval_min_score):
            return chunks, _lock_docs(chunks)
        return chunks, None

    scoped = retrieve(query, k, stored)
    if is_grounded(scoped, settings.retrieval_min_score):
        return scoped, None

    broader = retrieve(query, k, base)
    if is_grounded(broader, settings.retrieval_relock_score):
        return broader, _lock_docs(broader)
    return scoped, None


def _lock_docs(chunks: list[dict]) -> list[str]:
    """Documents worth locking the session to: only those with a chunk clearing the
    relock bar — weak tail chunks from unrelated docs must not ride into the scope
    (a 0.5x tail match would otherwise smuggle an off-topic doc into every later
    retrieval). The top-scoring doc is always included so a grounded-but-modest
    answer still locks.
    """
    strong = {
        c["document_id"] for c in chunks if c["score"] >= settings.retrieval_relock_score
    }
    strong.add(chunks[0]["document_id"])
    return sorted(strong)


def _citations(chunks: list[dict]) -> list[dict]:
    return [
        {"document_id": c["document_id"], "ordinal": c["ordinal"], "score": round(c["score"], 3)}
        for c in chunks
    ]


def _record_cache_hit(cached: dict) -> None:
    """Log a usage row for an answer served from cache (no model call).

    Carries the original generation's token counts so the dashboard can show how much
    the cache saved. Guardrail/no-answer cached entries have no token counts → 0.
    """
    usage.record_usage(
        kind="answer",
        model=settings.ollama_model,
        prompt_tokens=cached.get("prompt_tokens", 0),
        completion_tokens=cached.get("completion_tokens", 0),
        duration_ms=0,
        cached=True,
    )


def answer_query(
    query: str,
    top_k: int | None = None,
    document_ids: list[str] | None = None,
    session_id: str | None = None,
) -> dict:
    """Blocking grounded answer. Cached in Redis by (query, top_k, effective doc scope)."""
    k = top_k or settings.retrieval_top_k

    # Resolve a follow-up ("its battery") into a standalone question before anything else,
    # so retrieval, caching, and the prompt all key on the fully-specified query.
    eff = _maybe_rewrite(query, session_id)

    # Effective scope for the cache key: manual selection, else the session's sticky
    # scope. A relock later in the turn stores under the NEW scope (set below).
    cache_docs = document_ids or (cache.get_scope(session_id) if session_id else None)
    cached = cache.get_answer(eff, k, cache_docs)
    if cached is not None:
        _record_cache_hit(cached)
        _record_turn(session_id, query, cached["answer"])
        return {**cached, "cached": True}

    # Fuzzy reuse: a paraphrase of a prior question in the same scope.
    sem = _semantic_get(eff, k, cache_docs)
    if sem is not None:
        _record_cache_hit(sem)
        _record_turn(session_id, query, sem["answer"])
        return {**sem, "cached": True}

    chunks, scope_to_save = _resolve_chunks(eff, k, document_ids, session_id)
    if scope_to_save:
        cache.set_scope(session_id, scope_to_save)
        cache_docs = scope_to_save
    refusal = _refusal(eff, chunks)
    if refusal is not None:
        # Guardrail (off-KB) or variant guard (model we don't carry): no model call.
        result = {"answer": refusal, "grounded": False, "citations": [],
                  "prompt_tokens": 0, "completion_tokens": 0}
    else:
        gen = generate_full(_build_prompt(eff, chunks), system=SYSTEM_PROMPT, kind="answer")
        result = {
            "answer": gen["text"], "grounded": True, "citations": _citations(chunks),
            # Stored so a future cache hit can report the tokens it saved.
            "prompt_tokens": gen["prompt_tokens"], "completion_tokens": gen["completion_tokens"],
        }

    cache.set_answer(eff, k, cache_docs, result)
    _semantic_put(eff, k, cache_docs, result)
    _record_turn(session_id, query, result["answer"])
    return {**result, "cached": False}


def answer_stream(
    query: str,
    top_k: int | None = None,
    document_ids: list[str] | None = None,
    session_id: str | None = None,
) -> Iterator[tuple[str, object]]:
    """Stream a grounded answer for SSE.

    Yields ("token", str) for each generated token, then ("done", result_dict).
    On a cache hit or a guardrail block, yields the whole answer as one token then done,
    so the client renders identically regardless of path.
    """
    k = top_k or settings.retrieval_top_k

    eff = _maybe_rewrite(query, session_id)

    cache_docs = document_ids or (cache.get_scope(session_id) if session_id else None)
    cached = cache.get_answer(eff, k, cache_docs)
    if cached is not None:
        _record_cache_hit(cached)
        _record_turn(session_id, query, cached["answer"])
        yield ("token", cached["answer"])
        yield ("done", {**cached, "cached": True})
        return

    sem = _semantic_get(eff, k, cache_docs)
    if sem is not None:
        _record_cache_hit(sem)
        _record_turn(session_id, query, sem["answer"])
        yield ("token", sem["answer"])
        yield ("done", {**sem, "cached": True})
        return

    chunks, scope_to_save = _resolve_chunks(eff, k, document_ids, session_id)
    if scope_to_save:
        cache.set_scope(session_id, scope_to_save)
        cache_docs = scope_to_save
    refusal = _refusal(eff, chunks)
    if refusal is not None:
        result = {"answer": refusal, "grounded": False, "citations": [],
                  "prompt_tokens": 0, "completion_tokens": 0}
        cache.set_answer(eff, k, cache_docs, result)
        _semantic_put(eff, k, cache_docs, result)
        _record_turn(session_id, query, refusal)
        yield ("token", refusal)
        yield ("done", {**result, "cached": False})
        return

    # Token counts arrive with the final stream frame; capture them via on_usage so the
    # cached entry records what a future hit will have saved.
    tokens: dict = {}
    parts: list[str] = []
    for tok in generate_stream(
        _build_prompt(eff, chunks), system=SYSTEM_PROMPT, kind="answer",
        on_usage=lambda meta: tokens.update(meta),
    ):
        parts.append(tok)
        yield ("token", tok)

    result = {
        "answer": "".join(parts), "grounded": True, "citations": _citations(chunks),
        "prompt_tokens": tokens.get("prompt_tokens", 0),
        "completion_tokens": tokens.get("completion_tokens", 0),
    }
    cache.set_answer(eff, k, cache_docs, result)
    _semantic_put(eff, k, cache_docs, result)
    _record_turn(session_id, query, result["answer"])
    yield ("done", {**result, "cached": False})
