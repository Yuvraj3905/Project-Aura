"""Query-rewrite follow-up detection + rewrite orchestration (LLM mocked)."""
from app.rag import answer as answer_mod


def test_followup_detects_pronouns():
    assert answer_mod._looks_like_followup("what is its battery")
    assert answer_mod._looks_like_followup("how about that one")
    assert answer_mod._looks_like_followup("and the other model?")
    assert answer_mod._looks_like_followup("does it have GPS")


def test_followup_detects_very_short():
    assert answer_mod._looks_like_followup("battery?")
    assert answer_mod._looks_like_followup("the 44mm")


def test_standalone_not_followup():
    assert not answer_mod._looks_like_followup(
        "What is the display size of the Galaxy Watch 8 Classic 46mm model?")
    assert not answer_mod._looks_like_followup("Tell me about the Galaxy Watch 8 design")


def test_maybe_rewrite_resolves_with_history(monkeypatch):
    monkeypatch.setattr(answer_mod.cache, "get_history",
                        lambda sid: [{"q": "tell me about the Watch 8 Classic", "a": "It has a rotating bezel."}])
    monkeypatch.setattr(answer_mod, "_rewrite_llm",
                        lambda query, hist: "What is the battery of the Galaxy Watch 8 Classic?")
    out = answer_mod._maybe_rewrite("what is its battery", "s1")
    assert out == "What is the battery of the Galaxy Watch 8 Classic?"


def test_maybe_rewrite_skips_standalone(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(answer_mod.cache, "get_history", lambda sid: [{"q": "x", "a": "y"}])
    monkeypatch.setattr(answer_mod, "_rewrite_llm",
                        lambda query, hist: called.__setitem__("n", called["n"] + 1) or "X")
    q = "What is the display size of the Galaxy Watch 8 Classic 46mm?"
    assert answer_mod._maybe_rewrite(q, "s1") == q   # unchanged
    assert called["n"] == 0                          # LLM not called


def test_maybe_rewrite_skips_without_history(monkeypatch):
    monkeypatch.setattr(answer_mod.cache, "get_history", lambda sid: [])
    q = "what is its battery"
    assert answer_mod._maybe_rewrite(q, "s1") == q   # no history → can't resolve, use as-is


def test_maybe_rewrite_falls_back_on_bad_llm(monkeypatch):
    monkeypatch.setattr(answer_mod.cache, "get_history", lambda sid: [{"q": "x", "a": "y"}])
    monkeypatch.setattr(answer_mod, "_rewrite_llm", lambda query, hist: "")   # empty → bad
    q = "what is its battery"
    assert answer_mod._maybe_rewrite(q, "s1") == q   # fall back to original
