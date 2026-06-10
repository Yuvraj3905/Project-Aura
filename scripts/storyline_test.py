"""Storyline regression test: drive a multi-turn customer conversation through the
live app and assert on each reply.

Hits the real web stack on :3100 (POST /api/chat -> Rasa dialog, then follows the
SSE /api/chat/stream when a stream directive comes back), keeping one sessionId so
Rasa AND the ml-service sticky doc-scope track the conversation.

Each turn carries `must` / `must_not` substring checks (case-insensitive). Failures
are collected and reported at the end; exit code 1 if any check failed.
"""
import json
import sys
import time
import urllib.request
import uuid

WEB = "http://127.0.0.1:3100"
SESSION = f"storyline-{uuid.uuid4().hex[:8]}"

# Meta phrases the sales persona must never use (leaks RAG internals).
BANNED_META = [
    "according to the context",
    "provided context",
    "based on the context",
    "knowledge base",
    "the document",
    "provided document",
]

OLD_FALLBACK = "could you rephrase your technical question"

STORYLINE = [
    {
        "msg": "Hi there!",
        "must": [],
        "must_not": ["solutions architect"],  # old persona greeting
    },
    {
        "msg": "I'm shopping for a new smartwatch, what have you got?",
        "must": [],
        "must_not": [OLD_FALLBACK, "i'm not sure i understood"],
    },
    {
        "msg": "Tell me about the Galaxy Watch 8",
        "must": ["watch 8"],
        "must_not": [],
    },
    {
        "msg": "How is it different from the Watch 7?",
        "must": ["watch 7"],
        "must_not": [],
    },
    {
        # Sticky scope: after Watch 8 discussion this must answer the WATCH 8 44mm
        # (1.47"), not drift to the Watch 7 44mm (1.5").
        "msg": "What size display does the 44mm Watch 8 have?",
        "must": ["1.47"],
        "must_not": [],
    },
    {
        "msg": "Does the Classic have a rotating bezel?",
        "must": ["rotating"],
        "must_not": [],
    },
    {
        "msg": "Which one would you recommend for everyday use?",
        "must": [],
        "must_not": [],
    },
    {
        # The turn-8 bug: must NOT pull the news-CMS document on the word "order".
        "msg": "Great, how do I place an order?",
        "must": [],
        "must_not": ["article", "headline", "publish", "breaking news", "drag-and-drop"],
    },
]


def post(path, payload, timeout=400):
    req = urllib.request.Request(
        WEB + path,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )
    return urllib.request.urlopen(req, timeout=timeout)


def stream_answer(query):
    parts = []
    with post("/api/chat/stream", {"query": query, "documentIds": [], "sessionId": SESSION}) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data:"):
                continue
            try:
                p = json.loads(line[5:])
            except ValueError:
                continue
            if "text" in p:
                parts.append(p["text"])
            if "answer" in p:  # done frame carries the full answer
                return p.get("answer", "".join(parts))
    return "".join(parts)


def main():
    failures = []
    for i, turn in enumerate(STORYLINE, 1):
        msg = turn["msg"]
        t0 = time.time()
        print(f"\n{'='*70}\n[{i}] CUSTOMER: {msg}", flush=True)

        replies = []
        with post("/api/chat", {"sessionId": SESSION, "message": msg}) as r:
            data = json.loads(r.read().decode())
        replies.extend(data.get("replies", []))
        if data.get("stream"):
            replies.append(stream_answer(data["stream"]["query"]))

        full = "\n".join(replies)
        for reply in replies:
            print(f"    AURA: {reply}", flush=True)
        print(f"    ({time.time()-t0:.0f}s)", flush=True)

        low = full.lower()
        if not full.strip():
            failures.append(f"turn {i}: empty reply")
        for needle in turn["must"]:
            if needle.lower() not in low:
                failures.append(f"turn {i}: missing required {needle!r}")
        for needle in turn["must_not"] + BANNED_META:
            if needle.lower() in low:
                failures.append(f"turn {i}: contains banned {needle!r}")

    print(f"\n{'='*70}")
    if failures:
        print(f"FAIL — {len(failures)} assertion(s):")
        for f in failures:
            print(f"  ✗ {f}")
        sys.exit(1)
    print(f"PASS — all {len(STORYLINE)} turns clean (session {SESSION})")


if __name__ == "__main__":
    main()
