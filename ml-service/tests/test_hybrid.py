"""Hybrid-retrieval pure helpers: Reciprocal Rank Fusion + MMR dedupe (no DB)."""
import numpy as np

from app.rag.retrieve import mmr_dedupe, rrf_fuse


def _c(cid, score=0.5, emb=None):
    return {"chunk_id": cid, "document_id": "d", "ordinal": 0,
            "content": cid, "score": score, "embedding": emb}


def test_rrf_rewards_agreement_across_lists():
    # `a` appears in BOTH lists; b and c each appear in one. Consensus should win.
    vec = [_c("a"), _c("b")]
    lex = [_c("c"), _c("a")]
    fused = rrf_fuse([vec, lex], k=60, limit=10)
    ids = [c["chunk_id"] for c in fused]
    assert ids[0] == "a"                      # appears in both → highest fused score
    assert set(ids) == {"a", "b", "c"}        # union, deduped


def test_rrf_preserves_chunk_payload_and_dedupes():
    vec = [_c("a", score=0.8)]
    lex = [_c("a", score=0.8), _c("e", score=0.2)]
    fused = rrf_fuse([vec, lex], k=60, limit=10)
    assert len([c for c in fused if c["chunk_id"] == "a"]) == 1   # a appears once
    assert fused[0]["score"] == 0.8                              # payload kept


def test_rrf_respects_limit():
    vec = [_c(x) for x in "abcde"]
    fused = rrf_fuse([vec], k=60, limit=3)
    assert len(fused) == 3


def test_mmr_drops_near_duplicates():
    same = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    nearly = np.array([0.999, 0.044, 0.0], dtype=np.float32)  # cosine ~0.999 to `same`
    diff = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    chunks = [_c("a", emb=same), _c("b", emb=nearly), _c("c", emb=diff)]
    kept = mmr_dedupe(chunks, threshold=0.97)
    ids = [c["chunk_id"] for c in kept]
    assert "a" in ids and "c" in ids
    assert "b" not in ids                 # duplicate of a, dropped


def test_mmr_keeps_all_when_distinct():
    chunks = [
        _c("a", emb=np.array([1.0, 0, 0], dtype=np.float32)),
        _c("b", emb=np.array([0, 1.0, 0], dtype=np.float32)),
        _c("c", emb=np.array([0, 0, 1.0], dtype=np.float32)),
    ]
    assert len(mmr_dedupe(chunks, threshold=0.97)) == 3


def test_mmr_noop_without_embeddings():
    chunks = [_c("a", emb=None), _c("b", emb=None)]
    assert len(mmr_dedupe(chunks, threshold=0.97)) == 2
