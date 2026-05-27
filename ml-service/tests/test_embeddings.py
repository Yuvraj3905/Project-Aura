"""Embedding contract tests: dimension and normalization must match the schema."""
from app.config import settings
from app.embeddings import embed_query, embed_texts


def test_embed_dim_matches_schema():
    vectors = embed_texts(["hello world", "OAuth 2.0 with custom claims"])
    assert len(vectors) == 2
    assert all(len(v) == settings.embedding_dim for v in vectors)
    assert settings.embedding_dim == 384


def test_embed_is_normalized():
    v = embed_query("The timeout limit is 30 seconds.")
    norm = sum(x * x for x in v) ** 0.5
    assert abs(norm - 1.0) < 1e-3


def test_embed_empty_returns_empty():
    assert embed_texts([]) == []
