"""Grounded answer generation with an anti-hallucination guardrail.

If retrieval is weak (top score below threshold), we return a "don't know" answer
WITHOUT calling the LLM — the model never gets a chance to invent facts. When grounded,
the system prompt further constrains it to answer only from the supplied context.

Two entry points share the same retrieval + guardrail + prompt:
  - answer_query: blocking, returns the full result dict (Redis-cached).
  - answer_stream: generator yielding ("token", text) then ("done", result) for SSE.
"""
from typing import Iterator

from .. import cache, usage
from ..config import settings
from ..llm import generate_full, generate_stream
from .retrieve import retrieve

SYSTEM_PROMPT = (
    "You are Aura, an upbeat, persuasive B2B sales agent who loves the product and is "
    "eager to close the deal. Talk to the user like a warm, confident salesperson talking "
    "to a prospect: enthusiastic, benefit-focused, and conversational. "
    "NEVER use meta phrases like 'according to the context', 'based on the provided "
    "context', 'the document says', or 'in the knowledge base' — just answer directly and "
    "confidently as if you know the product inside-out. "
    "Ground every spec, number, and claim ONLY in the facts you are given — never invent "
    "specs, prices, features, or availability — but present those facts with energy, "
    "highlight the benefits to the customer, and nudge them toward buying (suggest a model, "
    "invite the next step). Keep it concise."
)

# Salesy deflection when retrieval is too weak — stays honest (no invented facts) but keeps
# the sales tone instead of a robotic "not in the knowledge base".
NO_ANSWER = (
    "Great question! I don't have those exact details on hand right this second, but I'd "
    "love to track them down for you. In the meantime, is there another model or feature I "
    "can walk you through to help you find the perfect fit?"
)


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

    stored = cache.get_scope(session_id) if session_id else None
    if not stored:
        chunks = retrieve(query, k, None)
        if session_id and is_grounded(chunks, settings.retrieval_min_score):
            return chunks, _lock_docs(chunks)
        return chunks, None

    scoped = retrieve(query, k, stored)
    if is_grounded(scoped, settings.retrieval_min_score):
        return scoped, None

    global_chunks = retrieve(query, k, None)
    if is_grounded(global_chunks, settings.retrieval_relock_score):
        return global_chunks, _lock_docs(global_chunks)
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

    # Effective scope for the cache key: manual selection, else the session's sticky
    # scope. A relock later in the turn stores under the NEW scope (set below).
    cache_docs = document_ids or (cache.get_scope(session_id) if session_id else None)
    cached = cache.get_answer(query, k, cache_docs)
    if cached is not None:
        _record_cache_hit(cached)
        return {**cached, "cached": True}

    chunks, scope_to_save = _resolve_chunks(query, k, document_ids, session_id)
    if scope_to_save:
        cache.set_scope(session_id, scope_to_save)
        cache_docs = scope_to_save
    if not is_grounded(chunks, settings.retrieval_min_score):
        # Guardrail: off-knowledge-base query. No model call, no tokens.
        result = {"answer": NO_ANSWER, "grounded": False, "citations": [],
                  "prompt_tokens": 0, "completion_tokens": 0}
    else:
        gen = generate_full(_build_prompt(query, chunks), system=SYSTEM_PROMPT, kind="answer")
        result = {
            "answer": gen["text"], "grounded": True, "citations": _citations(chunks),
            # Stored so a future cache hit can report the tokens it saved.
            "prompt_tokens": gen["prompt_tokens"], "completion_tokens": gen["completion_tokens"],
        }

    cache.set_answer(query, k, cache_docs, result)
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

    cache_docs = document_ids or (cache.get_scope(session_id) if session_id else None)
    cached = cache.get_answer(query, k, cache_docs)
    if cached is not None:
        _record_cache_hit(cached)
        yield ("token", cached["answer"])
        yield ("done", {**cached, "cached": True})
        return

    chunks, scope_to_save = _resolve_chunks(query, k, document_ids, session_id)
    if scope_to_save:
        cache.set_scope(session_id, scope_to_save)
        cache_docs = scope_to_save
    if not is_grounded(chunks, settings.retrieval_min_score):
        result = {"answer": NO_ANSWER, "grounded": False, "citations": [],
                  "prompt_tokens": 0, "completion_tokens": 0}
        cache.set_answer(query, k, cache_docs, result)
        yield ("token", NO_ANSWER)
        yield ("done", {**result, "cached": False})
        return

    # Token counts arrive with the final stream frame; capture them via on_usage so the
    # cached entry records what a future hit will have saved.
    tokens: dict = {}
    parts: list[str] = []
    for tok in generate_stream(
        _build_prompt(query, chunks), system=SYSTEM_PROMPT, kind="answer",
        on_usage=lambda meta: tokens.update(meta),
    ):
        parts.append(tok)
        yield ("token", tok)

    result = {
        "answer": "".join(parts), "grounded": True, "citations": _citations(chunks),
        "prompt_tokens": tokens.get("prompt_tokens", 0),
        "completion_tokens": tokens.get("completion_tokens", 0),
    }
    cache.set_answer(query, k, cache_docs, result)
    yield ("done", {**result, "cached": False})
