"""Ollama client — local LLM inference over HTTP.

Used for document summarization (ingestion) and answer generation (RAG). No API key,
no rate limit; the model runs locally.

Every generation call forwards three speed knobs (see config) and records token usage
to the `llm_usage` table so the dashboard can report how much the LLM was used and what
the equivalent OpenAI/ChatGPT bill would have been.

Token accounting comes straight from Ollama's response:
  - prompt_eval_count = input (prompt) tokens
  - eval_count        = output (completion) tokens
  - total_duration    = wall-clock nanoseconds for the call
"""
import json
from typing import Callable, Iterator

import httpx

from . import usage
from .config import settings


def _options() -> dict:
    """Inference options forwarded to Ollama on every call (see config for rationale)."""
    return {
        "temperature": 0.2,          # low → factual, repeatable answers
        "num_ctx": settings.ollama_num_ctx,
        "num_predict": settings.ollama_num_predict,
    }


def _payload(prompt: str, system: str | None, stream: bool) -> dict:
    payload: dict = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": stream,
        "options": _options(),
        # Keep the model warm between requests so we don't pay the load cost each time.
        "keep_alive": settings.ollama_keep_alive,
    }
    if system:
        payload["system"] = system
    return payload


def _record(kind: str, obj: dict) -> dict:
    """Pull token counts out of an Ollama response object and record usage.

    Returns the usage dict {prompt_tokens, completion_tokens, duration_ms} so callers
    (e.g. the answer cache) can store it alongside the cached answer.
    """
    meta = {
        "prompt_tokens": int(obj.get("prompt_eval_count", 0) or 0),
        "completion_tokens": int(obj.get("eval_count", 0) or 0),
        "duration_ms": int((obj.get("total_duration", 0) or 0) / 1_000_000),
    }
    usage.record_usage(
        kind=kind,
        model=settings.ollama_model,
        prompt_tokens=meta["prompt_tokens"],
        completion_tokens=meta["completion_tokens"],
        duration_ms=meta["duration_ms"],
        cached=False,
    )
    return meta


def generate_full(prompt: str, system: str | None = None, kind: str = "answer") -> dict:
    """Call Ollama (non-streaming) and return {text, prompt_tokens, completion_tokens,
    duration_ms}. Records usage as a side effect.

    Raises httpx.HTTPError if Ollama is unreachable or errors, so callers can mark a job
    failed and let the queue retry.
    """
    with httpx.Client(timeout=httpx.Timeout(300.0)) as client:
        resp = client.post(
            f"{settings.ollama_host}/api/generate",
            json=_payload(prompt, system, False),
        )
        resp.raise_for_status()
        obj = resp.json()
    meta = _record(kind, obj)
    return {"text": obj["response"].strip(), **meta}


def generate(prompt: str, system: str | None = None, kind: str = "summarize") -> str:
    """Convenience wrapper returning just the completion text (used by summarization)."""
    return generate_full(prompt, system, kind)["text"]


CLASSIFY_SYSTEM = (
    "You label a document with the single product it is about. Reply with ONLY the product "
    "name in 2-4 words (e.g. 'Samsung Galaxy Watch', 'News CMS Platform'). No punctuation, "
    "no explanation."
)


def classify_product(summary: str) -> str:
    """Classify a document into a short product label from its summary. Best-effort:
    returns "" if the model is unreachable, so ingestion never fails on tagging."""
    try:
        text = generate(
            f"Document summary:\n{summary}\n\nProduct name:",
            system=CLASSIFY_SYSTEM,
            kind="classify",
        )
        return text.strip().strip('"').splitlines()[0][:60] if text.strip() else ""
    except Exception:  # noqa: BLE001 — tagging is optional, never block ingest
        return ""


def generate_stream(
    prompt: str,
    system: str | None = None,
    kind: str = "answer",
    on_usage: Callable[[dict], None] | None = None,
) -> Iterator[str]:
    """Stream completion tokens from Ollama (/api/generate with stream=true).

    Each response line is a JSON object with an incremental `response` field; yield those
    text fragments as they arrive. The final line carries the token counts — at that
    point usage is recorded and `on_usage(meta)` (if given) is invoked so the caller can
    cache the counts. Raises httpx.HTTPError on transport failure.
    """
    with httpx.Client(timeout=httpx.Timeout(300.0)) as client:
        with client.stream(
            "POST",
            f"{settings.ollama_host}/api/generate",
            json=_payload(prompt, system, True),
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                frag = obj.get("response", "")
                if frag:
                    yield frag
                if obj.get("done"):
                    meta = _record(kind, obj)
                    if on_usage:
                        on_usage(meta)
                    break
