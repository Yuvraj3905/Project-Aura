"""Query-rewrite (conversation-aware follow-up) live test.

Two-turn conversation in one session:
  Q1 establishes a subject (Galaxy Watch 8 Classic).
  Q2 is a pronoun follow-up ("what is its battery") — with rewriting, this must resolve
     to the Classic and answer its battery (445 mAh), NOT a generic battery rundown.

Exit 1 on failure.
"""
import json
import sys
import time
import urllib.request
import uuid

ML = "http://127.0.0.1:8100"
failures = []
sid = f"rewrite-{uuid.uuid4().hex[:8]}"


def answer(query):
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
    print(f"=== QUERY REWRITE coreference (session {sid}) ===")
    r1, dt1 = answer("Tell me about the Galaxy Watch 8 Classic")
    print(f"\nQ1 ({dt1:.0f}s): Tell me about the Galaxy Watch 8 Classic")
    print(f"  A1: {r1['answer'][:140]}")
    check("Q1 grounded", r1["grounded"])

    r2, dt2 = answer("what is its battery")
    print(f"\nQ2 ({dt2:.0f}s): what is its battery   (pronoun follow-up)")
    print(f"  A2: {r2['answer'][:200]}")
    # The Classic is 445 mAh. Resolution worked if the answer is about the Classic / 445.
    a2 = r2["answer"].lower()
    check("Q2 resolved to the Classic's battery (445 mAh)", "445" in a2)
    check("Q2 stays on the Classic subject", "classic" in a2 or "46mm" in a2 or "445" in a2)

    print(f"\n{'='*56}")
    if failures:
        print(f"FAIL — {failures}")
        sys.exit(1)
    print("PASS — follow-up resolved via query rewrite")


if __name__ == "__main__":
    main()
