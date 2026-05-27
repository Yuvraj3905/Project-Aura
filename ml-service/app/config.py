"""Runtime configuration, loaded from environment variables.

Defaults match the docker-compose service names/ports so the service works in-container
with no .env file. Override via environment for host-side runs or tuning.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres (in-container DSN by default).
    database_url: str = "postgresql://aura:aura@postgres:5432/aura"

    # Upload root — files are read only from within this directory (path-traversal guard).
    upload_dir: str = "/data/uploads"

    # Ollama (local LLM).
    ollama_host: str = "http://ollama:11434"
    ollama_model: str = "llama3:8b"

    # Embeddings.
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384

    # Chunking + retrieval tuning.
    chunk_tokens: int = 512
    chunk_overlap: int = 64
    retrieval_top_k: int = 5
    # Cosine-similarity floor for the hard anti-hallucination guard. bge-small baselines
    # unrelated text around ~0.3, relevant matches ~0.5-0.8, so 0.45 blocks off-topic
    # queries before the LLM is ever called.
    retrieval_min_score: float = 0.45


settings = Settings()
