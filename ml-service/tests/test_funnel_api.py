"""Lead + order endpoint contract tests (DB layer monkeypatched — no real Postgres).

Mirrors the no-DB philosophy of the other tests: the SQL itself is exercised by the
live funnel integration test (scripts/funnel_test.py); here we pin the HTTP contract,
validation, and that the endpoints call the db layer with the right arguments.
"""
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app import main


@contextmanager
def _fake_conn():
    class C:
        def commit(self):
            pass
    yield C()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "get_conn", _fake_conn)
    return TestClient(main.app)


def test_create_lead_returns_id(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(main, "create_lead",
                        lambda conn, **kw: seen.update(kw) or "lead-123")
    r = client.post("/leads", json={
        "email": "buyer@example.com", "name": "Sam",
        "product_interest": "Galaxy Watch 8", "session_id": "s1",
    })
    assert r.status_code == 200
    assert r.json() == {"lead_id": "lead-123"}
    assert seen == {"name": "Sam", "email": "buyer@example.com",
                    "product_interest": "Galaxy Watch 8", "session_id": "s1"}


def test_create_lead_requires_email(client):
    r = client.post("/leads", json={"name": "Sam"})
    assert r.status_code == 422  # pydantic: email required


def test_list_leads(client, monkeypatch):
    monkeypatch.setattr(main, "list_leads", lambda conn: [{"id": "l1", "email": "a@b.co"}])
    r = client.get("/leads")
    assert r.status_code == 200
    assert r.json() == {"leads": [{"id": "l1", "email": "a@b.co"}]}


def test_create_order_returns_id(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(main, "create_order",
                        lambda conn, **kw: seen.update(kw) or "order-9")
    r = client.post("/orders", json={
        "email": "buyer@example.com", "product": "Galaxy Watch 8 44mm",
        "quantity": 2, "session_id": "s1",
    })
    assert r.status_code == 200
    assert r.json() == {"order_id": "order-9"}
    assert seen["product"] == "Galaxy Watch 8 44mm"
    assert seen["quantity"] == 2


def test_create_order_defaults_quantity_to_one(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(main, "create_order",
                        lambda conn, **kw: seen.update(kw) or "order-1")
    r = client.post("/orders", json={"email": "b@c.co", "product": "Watch 7 40mm"})
    assert r.status_code == 200
    assert seen["quantity"] == 1


def test_create_order_requires_product(client):
    r = client.post("/orders", json={"email": "b@c.co"})
    assert r.status_code == 422


def test_patch_order_status_valid(client, monkeypatch):
    monkeypatch.setattr(main, "update_order_status", lambda conn, oid, status: True)
    r = client.patch("/orders/order-9", json={"status": "confirmed"})
    assert r.status_code == 200
    assert r.json() == {"order_id": "order-9", "status": "confirmed"}


def test_patch_order_status_invalid(client):
    r = client.patch("/orders/order-9", json={"status": "bogus"})
    assert r.status_code == 400


def test_patch_order_not_found(client, monkeypatch):
    monkeypatch.setattr(main, "update_order_status", lambda conn, oid, status: False)
    r = client.patch("/orders/missing", json={"status": "confirmed"})
    assert r.status_code == 404


def test_clear_session_scope(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(main.cache, "clear_scope", lambda sid: seen.update(sid=sid))
    r = client.delete("/session/sess-42/scope")
    assert r.status_code == 200
    assert r.json() == {"session_id": "sess-42", "cleared": True}
    assert seen == {"sid": "sess-42"}
