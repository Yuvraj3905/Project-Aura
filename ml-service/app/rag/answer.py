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
    "You are Aura, a precise B2B sales engineer assistant. Answer the question using "
    "ONLY the provided context. If the context does not contain the answer, say you do "
    "not have that information in the knowledge base. Never invent facts, version "
    "numbers, or limits. Be concise."
)

NO_ANSWER = "I don't have that information in the current knowledge base."


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
        f"Context:\n{format_context(chunks)}\n\n"
        f"Question: {query}\n\n"
        "Answer using only the context above."
    )


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
) -> dict:
    """Blocking grounded answer. Cached in Redis by (query, top_k, document_ids)."""
    k = top_k or settings.retrieval_top_k

    cached = cache.get_answer(query, k, document_ids)
    if cached is not None:
        _record_cache_hit(cached)
        return {**cached, "cached": True}

    chunks = retrieve(query, k, document_ids)
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

    cache.set_answer(query, k, document_ids, result)
    return {**result, "cached": False}


def answer_stream(
    query: str,
    top_k: int | None = None,
    document_ids: list[str] | None = None,
) -> Iterator[tuple[str, object]]:
    """Stream a grounded answer for SSE.

    Yields ("token", str) for each generated token, then ("done", result_dict).
    On a cache hit or a guardrail block, yields the whole answer as one token then done,
    so the client renders identically regardless of path.
    """
    k = top_k or settings.retrieval_top_k

    cached = cache.get_answer(query, k, document_ids)
    if cached is not None:
        _record_cache_hit(cached)
        yield ("token", cached["answer"])
        yield ("done", {**cached, "cached": True})
        return

    chunks = retrieve(query, k, document_ids)
    if not is_grounded(chunks, settings.retrieval_min_score):
        result = {"answer": NO_ANSWER, "grounded": False, "citations": [],
                  "prompt_tokens": 0, "completion_tokens": 0}
        cache.set_answer(query, k, document_ids, result)
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
    cache.set_answer(query, k, document_ids, result)
    yield ("done", {**result, "cached": False})
