"""Anti-hallucination variant guard + dominant-document scoping (pure helpers, no DB)."""
from app.rag import answer as answer_mod
from app.rag.retrieve import dominant_doc_filter


def _chunk(doc, content, score=0.6):
    return {"chunk_id": "c", "document_id": doc, "ordinal": 0, "content": content, "score": score}


# --- variant guard ---------------------------------------------------------------

def test_variant_guard_flags_invented_model():
    chunks = [_chunk("watch", "Galaxy Watch 8 Classic 46mm rotating bezel")]
    # "ultra" is not in any chunk → unsupported
    assert answer_mod._unsupported_variant("what are features of watch 8 ultra", chunks) == "ultra"


def test_variant_guard_allows_real_variant():
    chunks = [_chunk("watch", "Galaxy Watch 8 Classic 46mm")]
    # "classic" appears in context → supported, not flagged
    assert answer_mod._unsupported_variant("tell me about the watch 8 classic", chunks) is None


def test_variant_guard_ignores_queries_without_qualifiers():
    chunks = [_chunk("watch", "Galaxy Watch 8 44mm display 1.47")]
    assert answer_mod._unsupported_variant("what is the display size", chunks) is None


def test_variant_guard_passes_when_qualifier_in_context():
    chunks = [_chunk("watch", "The Watch 8 Pro has an ultra-bright display")]
    # "pro" present in context → not flagged even though query mentions it
    assert answer_mod._unsupported_variant("tell me about the watch 8 pro", chunks) is None


def test_variant_guard_empty_chunks():
    assert answer_mod._unsupported_variant("watch 8 ultra", []) == "ultra"


# --- dominant-document scoping ---------------------------------------------------

def test_dominant_doc_filters_to_top_document():
    chunks = [
        _chunk("watch", "watch a", 0.80),
        _chunk("cms", "news b", 0.55),
        _chunk("watch", "watch c", 0.50),
        _chunk("ameyo", "webhook d", 0.48),
    ]
    kept = dominant_doc_filter(chunks)
    assert {c["document_id"] for c in kept} == {"watch"}
    assert [c["content"] for c in kept] == ["watch a", "watch c"]


def test_dominant_doc_noop_single_doc():
    chunks = [_chunk("watch", "a", 0.8), _chunk("watch", "b", 0.7)]
    assert len(dominant_doc_filter(chunks)) == 2


def test_dominant_doc_empty():
    assert dominant_doc_filter([]) == []
