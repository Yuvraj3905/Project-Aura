"""LLM usage accounting.

Every call to the local model records a row in `llm_usage`. The dashboard reads the
aggregate to answer two questions:
  1. How much is the LLM actually being used (calls, tokens, latency)?
  2. What would the same tokens have cost on a paid API (ChatGPT/OpenAI)?

A "cached" row represents an answer served from Redis WITHOUT calling the model. It
carries the token counts of the original generation so we can show how many tokens
(and how much money) the cache saved.

All writes are best-effort: a failure here must never break an answer, so exceptions
are swallowed.
"""
import logging

from .db import get_conn

log = logging.getLogger("aura.usage")


def record_usage(
    kind: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    duration_ms: int,
    cached: bool = False,
) -> None:
    """Insert one usage row. `kind` is 'answer' or 'summarize'. Best-effort."""
    try:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO llm_usage
                    (kind, model, prompt_tokens, completion_tokens, total_tokens,
                     duration_ms, cached)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    kind,
                    model,
                    prompt_tokens,
                    completion_tokens,
                    prompt_tokens + completion_tokens,
                    duration_ms,
                    cached,
                ),
            )
            conn.commit()
    except Exception:  # noqa: BLE001 — usage tracking must never break the request
        log.exception("failed to record llm usage")


def get_usage_stats() -> dict:
    """Aggregate usage for the dashboard.

    'actual' figures count only real model calls (cached=false); 'saved' figures come
    from cache hits (cached=true) and represent work the cache avoided.
    """
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
                count(*)                                                AS total_requests,
                count(*) FILTER (WHERE NOT cached)                      AS llm_calls,
                count(*) FILTER (WHERE cached)                          AS cache_hits,
                coalesce(sum(prompt_tokens)     FILTER (WHERE NOT cached), 0) AS prompt_tokens,
                coalesce(sum(completion_tokens) FILTER (WHERE NOT cached), 0) AS completion_tokens,
                coalesce(sum(total_tokens)      FILTER (WHERE NOT cached), 0) AS total_tokens,
                coalesce(sum(prompt_tokens)     FILTER (WHERE cached), 0)     AS saved_prompt_tokens,
                coalesce(sum(completion_tokens) FILTER (WHERE cached), 0)     AS saved_completion_tokens,
                coalesce(round(avg(duration_ms) FILTER (WHERE NOT cached AND duration_ms > 0)), 0) AS avg_latency_ms
              FROM llm_usage
            """
        ).fetchone()

    cols = [
        "total_requests", "llm_calls", "cache_hits", "prompt_tokens", "completion_tokens",
        "total_tokens", "saved_prompt_tokens", "saved_completion_tokens", "avg_latency_ms",
    ]
    stats = {c: int(v) for c, v in zip(cols, row)}
    total = stats["total_requests"]
    stats["cache_hit_rate"] = round(stats["cache_hits"] / total, 3) if total else 0.0
    return stats
