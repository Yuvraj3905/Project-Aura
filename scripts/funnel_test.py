"""Sales-funnel integration test: drive the order + lead capture flows through the
full app (web :3100 -> Rasa dialog -> ml-service) and assert rows land in the DB.

Unlike the storyline test, these flows are Rasa-form driven (no LLM), so they're fast.
Each flow uses its own sessionId. Exit code 1 on any failed assertion.
"""
import json
import sys
import time
import urllib.request
import uuid

WEB = "http://127.0.0.1:3100"
ML = "http://127.0.0.1:8100"


def chat(session_id, message, timeout=60):
    req = urllib.request.Request(
        WEB + "/api/chat",
        data=json.dumps({"sessionId": session_id, "message": message}).encode(),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def get(path):
    with urllib.request.urlopen(ML + path, timeout=15) as r:
        return json.loads(r.read().decode())


def replies_text(data):
    return " ".join(data.get("replies", []))


def run_order_flow(failures):
    sid = f"funnel-order-{uuid.uuid4().hex[:8]}"
    email = f"order-{sid}@example.com"
    print(f"\n=== ORDER FLOW ({sid}) ===")

    steps = [
        ("I want to buy the Galaxy Watch 8 44mm", "product"),  # triggers order_form, asks product
        ("Galaxy Watch 8 44mm", "email"),                       # product slot -> asks email
        (email, "done"),                                        # email slot -> submits
    ]
    for msg, _ in steps:
        data = chat(sid, msg)
        print(f"  CUSTOMER: {msg}\n  AURA: {replies_text(data)}")

    orders = get("/orders")["orders"]
    mine = [o for o in orders if o["session_id"] == sid]
    if not mine:
        failures.append("order flow: no order row created for session")
        return
    o = mine[0]
    if email not in o["email"]:
        failures.append(f"order flow: email mismatch ({o['email']})")
    if "watch 8" not in o["product"].lower():
        failures.append(f"order flow: product not captured ({o['product']})")
    if o["status"] != "pending":
        failures.append(f"order flow: unexpected status {o['status']}")
    print(f"  -> order row: product={o['product']!r} email={o['email']!r} status={o['status']}")


def run_lead_flow(failures):
    sid = f"funnel-lead-{uuid.uuid4().hex[:8]}"
    email = f"lead-{sid}@example.com"
    print(f"\n=== LEAD FLOW ({sid}) ===")

    steps = [
        ("Please have someone contact me about the watches", "name"),  # triggers lead_form
        ("Jordan Lee", "email"),                                       # name slot -> asks email
        (email, "done"),                                               # email slot -> submits
    ]
    for msg, _ in steps:
        data = chat(sid, msg)
        print(f"  CUSTOMER: {msg}\n  AURA: {replies_text(data)}")

    leads = get("/leads")["leads"]
    mine = [l for l in leads if l["session_id"] == sid]
    if not mine:
        failures.append("lead flow: no lead row created for session")
        return
    l = mine[0]
    if email not in l["email"]:
        failures.append(f"lead flow: email mismatch ({l['email']})")
    if (l["name"] or "").strip() != "Jordan Lee":
        failures.append(f"lead flow: name not captured ({l['name']!r})")
    if l["status"] != "new":
        failures.append(f"lead flow: unexpected status {l['status']}")
    print(f"  -> lead row: name={l['name']!r} email={l['email']!r} status={l['status']}")


def run_bad_email_flow(failures):
    """Order form must reject a malformed email and re-ask, not submit garbage."""
    sid = f"funnel-bademail-{uuid.uuid4().hex[:8]}"
    print(f"\n=== BAD-EMAIL FLOW ({sid}) ===")
    chat(sid, "I'll take the Watch 8 Classic")
    chat(sid, "Watch 8 Classic 46mm")
    data = chat(sid, "not-an-email")
    txt = replies_text(data).lower()
    print(f"  AURA (after bad email): {replies_text(data)}")
    if "valid email" not in txt:
        failures.append("bad-email flow: form did not re-ask on malformed email")
    # No order should exist for this session yet.
    if any(o["session_id"] == sid for o in get("/orders")["orders"]):
        failures.append("bad-email flow: order created despite invalid email")


def main():
    failures = []
    run_order_flow(failures)
    run_lead_flow(failures)
    run_bad_email_flow(failures)

    print(f"\n{'='*60}")
    if failures:
        print(f"FAIL — {len(failures)} assertion(s):")
        for f in failures:
            print(f"  ✗ {f}")
        sys.exit(1)
    print("PASS — order + lead + bad-email flows all good")


if __name__ == "__main__":
    main()
