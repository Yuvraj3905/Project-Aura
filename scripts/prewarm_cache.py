"""Pre-warm the answer cache with common questions.

Calls /answer once per question so the answer lands in BOTH caches: Redis (exact, 1h) and
the semantic cache (Postgres, persistent). After this runs, those questions — and their
paraphrases, via the semantic cache — return instantly with zero LLM tokens, instead of
paying a 50-130s CPU generation on the first real user who asks.

Run at deploy, after documents are ingested:
    python3 scripts/prewarm_cache.py                 # built-in FAQ list
    python3 scripts/prewarm_cache.py my_questions.txt # one question per line

ponytail: reuses the live /answer path to populate the cache — no separate cache-insert
code to keep in sync. The semantic cache is global-scope, so unscoped FAQ questions warm
the path real users hit.
"""
import sys
import time
import json
import urllib.request

ML = "http://127.0.0.1:8100"

# Default FAQ — the questions a watch shopper asks first. Edit, or pass a file argument.
DEFAULT_FAQ = [
    "What is the battery life of the Galaxy Watch 8?",
    "What is the display size of the Galaxy Watch 8 44mm?",
    "Does the Galaxy Watch 8 Classic have a rotating bezel?",
    "What health sensors does the Galaxy Watch 8 have?",
    "How is the Galaxy Watch 8 different from the Watch 7?",
    "What colors does the Galaxy Watch 8 come in?",
    "What is the price of the Galaxy Watch 8?",
    "Is the Galaxy Watch 8 water resistant?",
]


def ask(query: str) -> tuple[bool, float]:
    body = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        ML + "/answer", data=body, headers={"content-type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        res = json.loads(r.read().decode())
    return bool(res.get("cached")), time.time() - t0


def load_questions() -> list[str]:
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip()]
    return DEFAULT_FAQ


def main() -> None:
    questions = load_questions()
    print(f"Pre-warming cache with {len(questions)} question(s)…")
    for i, q in enumerate(questions, 1):
        cached, dt = ask(q)
        flag = "already cached" if cached else "generated + cached"
        print(f"  [{i}/{len(questions)}] ({dt:5.0f}s) {flag}: {q[:60]}")
    print("Done. These questions and their paraphrases now serve from cache.")


if __name__ == "__main__":
    main()
