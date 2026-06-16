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
    # Model tag. Smaller models answer much faster on CPU — e.g. "llama3.2:3b" or
    # "qwen2.5:3b" roughly halve token latency vs the default 8B at a small quality cost.
    ollama_model: str = "llama3:8b"

    # --- Inference speed/quality knobs (forwarded to Ollama) ---
    # num_ctx: context window in tokens. Must be large enough to hold the system prompt
    # + top_k chunks (~512 tokens each) + query, or the prompt is silently truncated and
    # answers degrade. Bigger ctx = slower prompt evaluation, so keep it just big enough.
    ollama_num_ctx: int = 4096
    # num_predict: hard cap on generated tokens. Answers are meant to be concise; capping
    # prevents a verbose model from running for minutes on CPU.
    ollama_num_predict: int = 512
    # keep_alive: how long Ollama keeps the model resident in RAM after a request. The
    # first call pays a multi-second model-load cost; keeping it warm makes every
    # subsequent call within the window start generating immediately.
    ollama_keep_alive: str = "30m"

    # Redis cache (empty disables caching; service still works).
    redis_url: str = "redis://redis:6379/0"

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
    # When a session is scope-locked to certain docs and the scoped retrieval is weak,
    # a global retry must clear this HIGHER bar to switch the session to other docs.
    # Keeps incidental keyword overlap (e.g. "order" matching an unrelated doc) from
    # hijacking the conversation, while a genuine topic change still re-locks.
    retrieval_relock_score: float = 0.60

    # --- Phase 2: hybrid retrieval + semantic cache ---
    # Hybrid: fuse lexical (Postgres full-text/BM25-like) with vector results via
    # Reciprocal Rank Fusion. Catches exact-term matches a pure vector search misses.
    hybrid_retrieval: bool = True
    hybrid_candidates: int = 20          # top-N from each arm before fusion
    rrf_k: int = 60                      # RRF constant (standard default)
    # MMR: drop near-duplicate chunks from the fused top list so the prompt gets diverse
    # context instead of three paraphrases of the same sentence.
    mmr_dedupe: bool = True
    mmr_dup_threshold: float = 0.97      # cosine between chunks above this = duplicate
    # Semantic answer cache: reuse a prior answer when a new query embeds close to it.
    semantic_cache: bool = True
    # Cosine floor for reusing a prior answer. Measured on bge-small: real paraphrases of
    # the same question land ~0.94, genuinely different questions ~0.69 — so 0.92 catches
    # rewordings with a wide margin before any risk of reusing an unrelated answer.
    semantic_cache_threshold: float = 0.92


settings = Settings()
