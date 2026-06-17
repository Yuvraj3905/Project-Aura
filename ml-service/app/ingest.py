"""Ingestion orchestrator: file -> summary -> chunks -> embeddings -> store.

Called by the Node worker (which picked the job off pg-boss). On any failure the
document is marked 'failed' and the error re-raised so the worker can retry / surface it.
"""
import logging
from pathlib import Path

from . import cache
from .config import settings
from .db import fetch_document, get_conn, truncate_semantic_cache
from .embeddings import embed_texts, get_model
from .llm import generate
from .pipeline.chunk import chunk_text
from .pipeline.extract import extract_text
from .pipeline.store import insert_chunks, mark_status, reset_document_chunks
from .pipeline.summarize import build_contextualized, summarize_document

log = logging.getLogger("aura.ingest")


def _resolve_upload_path(storage_path: str) -> str:
    """Resolve a stored basename to an absolute path, refusing anything that escapes
    the upload root (path-traversal guard). The caller never supplies a path."""
    root = Path(settings.upload_dir).resolve()
    real = (root / storage_path).resolve()
    try:
        real.relative_to(root)
    except ValueError as exc:
        raise ValueError("storage_path escapes upload root") from exc
    if not real.is_file():
        raise ValueError(f"file not found: {storage_path}")
    return str(real)


def ingest_document(document_id: str) -> int:
    """Run the full pipeline for one document. Returns the number of chunks stored."""
    with get_conn() as conn:
        doc = fetch_document(conn, document_id)
        mark_status(conn, document_id, "processing")
        conn.commit()

    try:
        path = _resolve_upload_path(doc["storage_path"])
        text = extract_text(path, doc["mime_type"])
        if not text.strip():
            raise ValueError("no extractable text in document")

        summary = summarize_document(text, generate)

        tokenizer = get_model().tokenizer
        chunks = chunk_text(text, tokenizer, settings.chunk_tokens, settings.chunk_overlap)
        if not chunks:
            raise ValueError("document produced no chunks")

        contextualized = [build_contextualized(summary, c) for c, _ in chunks]
        embeddings = embed_texts(contextualized)

        rows = [
            {
                "ordinal": i,
                "content": chunk_txt,
                "contextualized_content": ctx,
                "token_count": tok_count,
                "embedding": emb,
            }
            for i, ((chunk_txt, tok_count), ctx, emb) in enumerate(
                zip(chunks, contextualized, embeddings)
            )
        ]

        with get_conn() as conn:
            reset_document_chunks(conn, document_id)
            insert_chunks(conn, document_id, rows)
            mark_status(conn, document_id, "ready", summary=summary, n_chunks=len(rows))
            truncate_semantic_cache(conn)   # a new doc can change correct answers
            conn.commit()

        # A new document can change what any query should return — drop cached answers.
        dropped = cache.invalidate_answers()
        log.info("ingested document %s: %d chunks (cache: dropped %d answers)",
                 document_id, len(rows), dropped)
        return len(rows)

    except Exception as exc:  # noqa: BLE001 — mark failed, then re-raise for the worker
        log.exception("ingest failed for %s", document_id)
        with get_conn() as conn:
            mark_status(conn, document_id, "failed", error=str(exc))
            conn.commit()
        raise
