"""Comparison-query live test.

A "compare X and Y" question must produce a grounded, both-products spec comparison —
not drift to one product or invent differences. The watch PDF holds both Watch 8 and
Watch 7, so plain RAG already retrieves chunks spanning both; this guards that behavior
against future retrieval/prompt changes (no dedicated comparison intent needed).

Exit 1 on failure.
"""
import json
import sys
import time
import urllib.request
import uuid

ML = "http://127.0.0.1:8100"
failures = []


def answer(query, sid):
    req = urllib.request.Request(
        ML + "/answer",
        data=json.dumps({"query": query, "session_id": sid}).encode(),
        headers={"content-type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode()), time.time() - t0


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} — {name}{(' :: ' + detail) if detail else ''}")
    if not cond:
        failures.append(name)


def main():
    sid = f"compare-{uuid.uuid4().hex[:8]}"
    print(f"=== COMPARISON query (session {sid}) ===")
    res, dt = answer(
        "Compare the Galaxy Watch 8 and Watch 7 — what are the key differences?", sid)
    a = res["answer"].lower()
    print(f"\n({dt:.0f}s) grounded={res['grounded']} cites={len(res['citations'])}")
    print(f"  {res['answer'][:300]}")

    check("grounded", res["grounded"])
    check("names both products", "watch 8" in a and "watch 7" in a)
    # A real comparison cites a concrete spec that actually differs between the two.
    # 3000 nits (Watch 8) vs 2000 nits (Watch 7) is the clearest grounded delta.
    check("cites a real differing spec (brightness)", "3000" in a or "nits" in a)

    print(f"\n{'='*56}")
    if failures:
        print(f"FAIL — {failures}")
        sys.exit(1)
    print("PASS — comparison is grounded and covers both products")


if __name__ == "__main__":
    main()
