"""Token-based chunking with overlap.

Chunks are sized in tokens using the embedding model's own tokenizer, so chunk
boundaries line up with what actually gets embedded (bge-small max sequence = 512).
The tokenizer is injected (anything exposing `encode`/`decode`) to keep this unit
testable without loading the model.
"""
from typing import Protocol


# Structural interface for any tokenizer (HuggingFace's, or a fake in tests). Using a
# Protocol means chunk_text depends on behavior, not on importing the model.
class Tokenizer(Protocol):
    def encode(self, text: str, add_special_tokens: bool = ...) -> list[int]: ...
    def decode(self, ids: list[int]) -> str: ...


def chunk_text(
    text: str,
    tokenizer: Tokenizer,
    chunk_tokens: int,
    overlap: int,
) -> list[tuple[str, int]]:
    """Split text into overlapping token windows.

    Returns a list of (chunk_text, token_count). Empty/whitespace input → [].

    Windows advance by `step = chunk_tokens - overlap`, so consecutive chunks share
    `overlap` tokens — a fact straddling a boundary survives intact in at least one chunk.
    """
    if not text.strip():
        return []
    # overlap >= chunk_tokens would make step <= 0 → the window never advances (infinite loop).
    if overlap >= chunk_tokens:
        raise ValueError("overlap must be smaller than chunk_tokens")

    # Encode once; slice the token-id list into windows. add_special_tokens=False so
    # [CLS]/[SEP] markers don't eat into the content budget or distort token_count.
    ids = tokenizer.encode(text, add_special_tokens=False)
    if not ids:
        return []

    step = chunk_tokens - overlap
    chunks: list[tuple[str, int]] = []
    for start in range(0, len(ids), step):
        window = ids[start : start + chunk_tokens]
        if not window:
            break
        chunk = tokenizer.decode(window).strip()
        if chunk:
            chunks.append((chunk, len(window)))
        # This window already reached the end → stop, otherwise the next `step` would
        # emit a redundant near-duplicate tail chunk.
        if start + chunk_tokens >= len(ids):
            break
    return chunks
