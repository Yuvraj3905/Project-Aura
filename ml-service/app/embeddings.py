"""bge-small-en-v1.5 embeddings via Sentence Transformers.

The model is loaded once (process-wide singleton) and reused. Embeddings are
L2-normalized so cosine similarity reduces to a dot product, matching the pgvector
`vector_cosine_ops` HNSW index used for retrieval.
"""
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from . import cache
from .config import settings


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    """Load (and cache) the embedding model."""
    return SentenceTransformer(settings.embedding_model)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts into normalized vectors."""
    if not texts:
        return []
    model = get_model()
    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return vectors.tolist()


def embed_query(text: str) -> list[float]:
    """Embed a single query string, using the Redis cache when available.

    Query embeddings repeat across users/sessions far more than chunk embeddings, so
    only this single-text path is cached; bulk ingestion embeddings are not.
    """
    cached = cache.get_embedding(text)
    if cached is not None:
        return cached
    vector = embed_texts([text])[0]
    cache.set_embedding(text, vector)
    return vector
