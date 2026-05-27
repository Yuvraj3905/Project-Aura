"""Chunking tests — use a fake whitespace tokenizer so no model load is needed."""
import pytest

from app.pipeline.chunk import chunk_text
from app.pipeline.summarize import build_contextualized


class WhitespaceTokenizer:
    """Minimal tokenizer: one token per whitespace-separated word."""

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        self._words = text.split()
        return list(range(len(self._words)))

    def decode(self, ids: list[int]) -> str:
        return " ".join(self._words[i] for i in ids)


def test_chunk_counts_and_overlap():
    tok = WhitespaceTokenizer()
    text = " ".join(f"w{i}" for i in range(100))  # 100 tokens
    chunks = chunk_text(text, tok, chunk_tokens=40, overlap=10)

    # step = 30 -> windows at 0(0-39), 30(30-69), 60(60-99) fully cover 100 tokens;
    # the window reaching the end breaks the loop, so no redundant trailing chunk.
    assert len(chunks) == 3
    assert chunks[0][1] == 40  # first window is full size
    assert all(tc <= 40 for _, tc in chunks)
    # overlap: chunk[1] starts 10 tokens before chunk[0] ends
    assert chunks[1][0].split()[0] == "w30"
    assert chunks[0][0].split()[-1] == "w39"


def test_chunk_empty_input():
    assert chunk_text("   ", WhitespaceTokenizer(), 40, 10) == []


def test_chunk_overlap_must_be_smaller():
    with pytest.raises(ValueError):
        chunk_text("a b c", WhitespaceTokenizer(), 10, 10)


def test_build_contextualized_prepends_capped_summary():
    out = build_contextualized("SUMMARY", "chunk body", summary_prefix_chars=4)
    assert out.startswith("SUMM")
    assert out.endswith("chunk body")


def test_build_contextualized_no_summary_returns_chunk():
    assert build_contextualized("", "chunk body") == "chunk body"
