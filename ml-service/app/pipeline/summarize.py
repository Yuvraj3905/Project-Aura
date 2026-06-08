"""Hierarchical document summarization (the "Contextual" in Contextual RAG).

A 500-page manual will not fit in the LLM context window, so we summarize the document
in sections (map) and then summarize the section summaries (reduce). The resulting
document-level summary is prepended to every chunk before embedding, so an isolated
chunk like "the timeout limit is 30 seconds" keeps the context of which product /
service / API it belongs to.

`generate` is injected (a callable str -> str) so this is testable without Ollama.
"""
from typing import Callable

SECTION_CHARS = 6000  # ~1.5k tokens per map step — comfortably within llama3:8b context

_MAP_SYSTEM = (
    "You summarize technical engineering documentation. Be concise and factual. "
    "Preserve product names, service names, API names, version numbers, protocols, "
    "and hard limits. Do not invent anything."
)


def _summarize_one(text: str, generate: Callable[[str], str], *, reduce: bool = False) -> str:
    what = "section summaries" if reduce else "documentation excerpt"
    prompt = (
        f"Summarize the following {what} in 3-6 sentences. Capture the key technical "
        f"facts: products/services, APIs, protocols, version numbers, and limits.\n\n"
        f"{text}"
    )
    return generate(prompt)


def summarize_document(text: str, generate: Callable[[str], str]) -> str:
    """Produce a document-level summary via map-reduce over sections."""
    text = text.strip()
    if not text:
        return ""

    # Split into context-window-sized sections.
    sections = [text[i : i + SECTION_CHARS] for i in range(0, len(text), SECTION_CHARS)]
    # Small doc → one LLM call, no reduce step needed.
    if len(sections) == 1:
        return _summarize_one(sections[0], generate)

    # MAP: summarize each section independently. REDUCE: summarize the summaries into one.
    partials = [_summarize_one(s, generate) for s in sections]
    return _summarize_one("\n\n".join(partials), generate, reduce=True)


def build_contextualized(summary: str, chunk: str, summary_prefix_chars: int = 400) -> str:
    """Prepend a (capped) document summary to a chunk for embedding.

    The summary is capped so the combined text stays close to the embedding model's
    512-token limit and the chunk's own content is not truncated away.
    """
    prefix = (summary or "").strip()[:summary_prefix_chars]
    if not prefix:
        return chunk
    return f"{prefix}\n\n{chunk}"
