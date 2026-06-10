"""Scope-aware retrieval resolution tests (retrieve + cache monkeypatched).

Covers the four sticky-scope paths:
  lock      — no stored scope, grounded global answer locks scope to cited docs
  scoped    — stored scope, scoped retrieval strong enough → stays in scope
  relock    — scoped weak, global strong (>= relock score) → topic switch, new scope
  weak      — weak everywhere → ungrounded, scope unchanged
"""
from app import cache
from app.config import settings
from app.rag import answer as answer_mod


def chunk(doc, score, content="c"):
    return {"chunk_id": "x", "document_id": doc, "ordinal": 0, "content": content, "score": score}


def setup_fakes(monkeypatch, by_filter):
    """retrieve() returns by_filter[doc_ids_tuple_or_None]. Scope stored in a dict."""
    scopes = {}
    monkeypatch.setattr(answer_mod, "retrieve",
                        lambda q, k=None, document_ids=None: by_filter[tuple(document_ids) if document_ids else None])
    monkeypatch.setattr(cache, "get_scope", lambda sid: scopes.get(sid))
    monkeypatch.setattr(cache, "set_scope", lambda sid, ids: scopes.__setitem__(sid, sorted(set(ids))))
    return scopes


def test_lock_on_first_grounded_answer(monkeypatch):
    scopes = setup_fakes(monkeypatch, {None: [chunk("watch-doc", 0.75)]})
    chunks, scope_to_save = answer_mod._resolve_chunks("q", 5, None, "s1")
    assert chunks[0]["document_id"] == "watch-doc"
    assert scope_to_save == ["watch-doc"]


def test_lock_excludes_weak_tail_documents(monkeypatch):
    """Weak tail chunks from unrelated docs must NOT ride into the scope lock.

    Regression for the storyline turn-8 bug: an unrelated CMS doc scored 0.546 on the
    first watch query, entered the scope, and later answered 'place an order'.
    """
    scopes = setup_fakes(monkeypatch, {None: [
        chunk("watch-doc", 0.75),
        chunk("watch-doc", 0.72),
        chunk("cms-doc", 0.55),     # below relock bar (0.60) — must be excluded
        chunk("other-doc", 0.50),
    ]})
    chunks, scope_to_save = answer_mod._resolve_chunks("q", 5, None, "s1")
    assert scope_to_save == ["watch-doc"]


def test_lock_keeps_top_doc_even_if_below_relock_bar(monkeypatch):
    """Grounded (>= min_score) but modest top score: still lock to the top doc."""
    scopes = setup_fakes(monkeypatch, {None: [
        chunk("watch-doc", 0.50),
        chunk("cms-doc", 0.48),
    ]})
    chunks, scope_to_save = answer_mod._resolve_chunks("q", 5, None, "s1")
    assert scope_to_save == ["watch-doc"]


def test_scoped_hit_keeps_scope(monkeypatch):
    scopes = setup_fakes(monkeypatch, {("watch-doc",): [chunk("watch-doc", 0.70)]})
    scopes["s1"] = ["watch-doc"]
    chunks, scope_to_save = answer_mod._resolve_chunks("q", 5, None, "s1")
    assert chunks[0]["document_id"] == "watch-doc"
    assert scope_to_save is None  # unchanged


def test_relock_on_strong_topic_switch(monkeypatch):
    scopes = setup_fakes(monkeypatch, {
        ("watch-doc",): [chunk("watch-doc", 0.30)],          # weak in scope
        None: [chunk("cms-doc", 0.72)],                       # strong globally
    })
    scopes["s1"] = ["watch-doc"]
    chunks, scope_to_save = answer_mod._resolve_chunks("q", 5, None, "s1")
    assert chunks[0]["document_id"] == "cms-doc"
    assert scope_to_save == ["cms-doc"]


def test_weak_everywhere_keeps_scope_and_ungrounded(monkeypatch):
    scopes = setup_fakes(monkeypatch, {
        ("watch-doc",): [chunk("watch-doc", 0.30)],
        None: [chunk("cms-doc", 0.50)],                       # < relock score (0.60)
    })
    scopes["s1"] = ["watch-doc"]
    chunks, scope_to_save = answer_mod._resolve_chunks("q", 5, None, "s1")
    assert not answer_mod.is_grounded(chunks, settings.retrieval_min_score) \
        or chunks[0]["score"] < settings.retrieval_relock_score
    assert scope_to_save is None
    # the weak-global result must NOT be answerable as cms-doc
    assert chunks == [] or chunks[0]["score"] < settings.retrieval_relock_score


def test_explicit_document_ids_bypass_sticky(monkeypatch):
    scopes = setup_fakes(monkeypatch, {("manual-doc",): [chunk("manual-doc", 0.9)]})
    scopes["s1"] = ["watch-doc"]  # would conflict if sticky used
    chunks, scope_to_save = answer_mod._resolve_chunks("q", 5, ["manual-doc"], "s1")
    assert chunks[0]["document_id"] == "manual-doc"
    assert scope_to_save is None


def test_no_session_id_is_global(monkeypatch):
    setup_fakes(monkeypatch, {None: [chunk("watch-doc", 0.8)]})
    chunks, scope_to_save = answer_mod._resolve_chunks("q", 5, None, None)
    assert chunks[0]["document_id"] == "watch-doc"
    assert scope_to_save is None  # nowhere to store it
