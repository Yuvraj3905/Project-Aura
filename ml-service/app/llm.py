"""Ollama client — local LLM inference over HTTP.

Used for document summarization (ingestion) and answer generation (RAG). No API key,
no rate limit; the model runs locally.
"""
import httpx

from .config import settings


def generate(prompt: str, system: str | None = None, temperature: float = 0.2) -> str:
    """Call Ollama /api/generate (non-streaming) and return the completion text.

    Raises httpx.HTTPError if Ollama is unreachable or returns an error status, so
    callers can mark a job failed and let the queue retry.
    """
    payload: dict = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if system:
        payload["system"] = system

    with httpx.Client(timeout=httpx.Timeout(300.0)) as client:
        resp = client.post(f"{settings.ollama_host}/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json()["response"].strip()
