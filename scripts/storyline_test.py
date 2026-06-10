"""Drive a multi-turn customer storyline through the live app to test the sales agent.

Hits the real web stack on :3100 (POST /api/chat -> Rasa dialog, then follows the
SSE /api/chat/stream when a stream directive comes back), keeping one sessionId so
Rasa tracks the conversation. Prints each customer line and Aura's reply with timing.
"""
import json
import time
import urllib.request

WEB = "http://127.0.0.1:3100"
SESSION = "storyline-demo-1"

STORYLINE = [
    "Hi there!",
    "I'm shopping for a new smartwatch, what have you got?",
    "Tell me about the Galaxy Watch 8",
    "How is it different from the Watch 7?",
    "What size displays does the 44mm have?",
    "Does the Classic have a rotating bezel?",
    "Which one would you recommend for everyday use?",
    "Great, how do I place an order?",
]


def post(path, payload, timeout=240):
    req = urllib.request.Request(
        WEB + path,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )
    return urllib.request.urlopen(req, timeout=timeout)


def stream_answer(query):
    parts = []
    with post("/api/chat/stream", {"query": query, "documentIds": []}) as r:
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
    for i, msg in enumerate(STORYLINE, 1):
        t0 = time.time()
        print(f"\n{'='*70}\n[{i}] CUSTOMER: {msg}", flush=True)
        with post("/api/chat", {"sessionId": SESSION, "message": msg}) as r:
            data = json.loads(r.read().decode())
        for reply in data.get("replies", []):
            print(f"    AURA: {reply}", flush=True)
        if data.get("stream"):
            ans = stream_answer(data["stream"]["query"])
            print(f"    AURA: {ans}", flush=True)
        print(f"    ({time.time()-t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
