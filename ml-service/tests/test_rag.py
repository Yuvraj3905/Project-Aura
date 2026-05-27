"""RAG guardrail + context formatting tests (no DB/LLM needed)."""
from app.rag.answer import format_context, is_grounded


def _chunk(score: float, ordinal: int = 0) -> dict:
    return {
        "chunk_id": "c",
        "document_id": "d",
        "ordinal": ordinal,
        "content": f"content {ordinal}",
        "score": score,
    }


def test_guardrail_blocks_when_no_chunks():
    assert is_grounded([], min_score=0.3) is False


def test_guardrail_blocks_low_score():
    assert is_grounded([_chunk(0.10)], min_score=0.3) is False


def test_guardrail_allows_high_score():
    assert is_grounded([_chunk(0.42)], min_score=0.3) is True


def test_guardrail_uses_top_chunk_only():
    # top chunk clears threshold even if later ones don't
    assert is_grounded([_chunk(0.5), _chunk(0.1)], min_score=0.3) is True


def test_format_context_includes_doc_and_chunk_refs():
    ctx = format_context([_chunk(0.9, ordinal=2)])
    assert "document d" in ctx
    assert "chunk 2" in ctx
    assert "content 2" in ctx
