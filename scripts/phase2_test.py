"""Phase 2 API tests: hybrid retrieval + semantic answer cache, against the live stack.

- Hybrid: a keyword-heavy query should retrieve the right watch chunk.
- Semantic cache: a paraphrase of a just-answered question should return cached=true
  WITHOUT a fresh LLM call (so it returns near-instantly).

Exit 1 on any failed assertion. Uses Python (rtk mangles streaming curl).
"""
import json
import sys
import time
import urllib.request
import uuid

ML = "http://127.0.0.1:8100"
failures = []


def answer(query, session_id=None, document_ids=None):
    """Call /answer (blocking) and return (result_dict, elapsed_seconds)."""
    body = {"query": query}
    if session_id:
        body["session_id"] = session_id
    if document_ids is not None:
        body["document_ids"] = document_ids
    req = urllib.request.Request(ML + "/answer", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode()), time.time() - t0


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} — {name}{(' :: ' + detail) if detail else ''}")
    if not cond:
        failures.append(name)


def test_hybrid_keyword():
    print("\n=== HYBRID: keyword retrieval ===")
    res, dt = answer("rotating bezel", session_id=f"p2-hybrid-{uuid.uuid4().hex[:6]}")
    print(f"  ({dt:.0f}s) grounded={res['grounded']} cites={len(res['citations'])}")
    print(f"  answer: {res['answer'][:160]}")
    check("keyword query is grounded", res["grounded"])
    check("mentions the Classic / bezel", "bezel" in res["answer"].lower())


def test_semantic_cache():
    print("\n=== SEMANTIC CACHE: paraphrase reuse ===")
    sid = f"p2-sem-{uuid.uuid4().hex[:6]}"
    # First ask — real generation (slow), cached=false.
    res1, dt1 = answer("What is the display size of the Galaxy Watch 8 44mm?", session_id=sid)
    print(f"  Q1 ({dt1:.0f}s) cached={res1.get('cached')}: {res1['answer'][:120]}")
    check("first ask not cached", res1.get("cached") is False)

    # Paraphrase — should hit semantic cache: fast + cached=true + same answer.
    res2, dt2 = answer("How big is the screen on the 44mm Watch 8?", session_id=sid)
    print(f"  Q2 ({dt2:.1f}s) cached={res2.get('cached')}: {res2['answer'][:120]}")
    check("paraphrase served from cache", res2.get("cached") is True,
          f"cached={res2.get('cached')}")
    check("cache hit is fast (<5s)", dt2 < 5.0, f"{dt2:.1f}s")
    check("cached answer matches original", res2["answer"] == res1["answer"])


def main():
    test_hybrid_keyword()
    test_semantic_cache()
    print(f"\n{'='*60}")
    if failures:
        print(f"FAIL — {len(failures)}: {failures}")
        sys.exit(1)
    print("PASS — hybrid + semantic cache verified")


if __name__ == "__main__":
    main()
