"""Ollama client — local LLM inference over HTTP.

Used for document summarization (ingestion) and answer generation (RAG). No API key,
no rate limit; the model runs locally.
"""
import json
from typing import Iterator

import httpx

from .config import settings


def _payload(prompt: str, system: str | None, stream: bool, temperature: float) -> dict:
    payload: dict = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": stream,
        "options": {"temperature": temperature},
    }
    if system:
        payload["system"] = system
    return payload


def generate(prompt: str, system: str | None = None, temperature: float = 0.2) -> str:
    """Call Ollama /api/generate (non-streaming) and return the completion text.

    Raises httpx.HTTPError if Ollama is unreachable or returns an error status, so
    callers can mark a job failed and let the queue retry.
    """
    with httpx.Client(timeout=httpx.Timeout(300.0)) as client:
        resp = client.post(
            f"{settings.ollama_host}/api/generate",
            json=_payload(prompt, system, False, temperature),
        )
        resp.raise_for_status()
        return resp.json()["response"].strip()


def generate_stream(
    prompt: str, system: str | None = None, temperature: float = 0.2
) -> Iterator[str]:
    """Stream completion tokens from Ollama (/api/generate with stream=true).

    Each line of the response is a JSON object with an incremental `response` field;
    yield those text fragments as they arrive. Raises httpx.HTTPError on transport
    failure so the caller can surface a graceful message.
    """
    with httpx.Client(timeout=httpx.Timeout(300.0)) as client:
        with client.stream(
            "POST",
            f"{settings.ollama_host}/api/generate",
            json=_payload(prompt, system, True, temperature),
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
                    break
