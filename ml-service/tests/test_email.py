"""Email confirmation logic — message building + the unconfigured no-op path.

No SMTP server is contacted: we check the message is well-formed and that send_email
short-circuits to False when no host is configured (so the funnel never blocks on mail).
"""
from app import email as email_mod
from app.config import settings


def test_build_message_sets_headers_and_body():
    msg = email_mod.build_message("buyer@acme.com", "Your order", "Thanks!")
    assert msg["To"] == "buyer@acme.com"
    assert msg["Subject"] == "Your order"
    assert msg["From"] == settings.smtp_from
    assert "Thanks!" in msg.get_content()


def test_send_email_noop_when_unconfigured(monkeypatch):
    """Empty smtp_host → no send attempted, returns False (DB row still gets written)."""
    monkeypatch.setattr(settings, "smtp_host", "")
    assert email_mod.send_email("buyer@acme.com", "subject", "body") is False


def test_send_email_noop_when_no_recipient(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    assert email_mod.send_email("", "subject", "body") is False
