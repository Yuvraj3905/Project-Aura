"""Transactional email for order/lead confirmations (stdlib smtplib).

Best-effort and optional: when `settings.smtp_host` is empty, `send_email` is a no-op, so
the funnel still writes its DB row and the stack runs with no mail server configured. The
message-building is split out (`build_message`) so it can be unit-tested without a network.

ponytail: stdlib `smtplib` + `email.message` — no dependency for a few dozen lines.
"""
import logging
import smtplib
from email.message import EmailMessage

from .config import settings

log = logging.getLogger("aura.email")


def build_message(to: str, subject: str, body: str) -> EmailMessage:
    """Build a plain-text email from the configured From: address."""
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def send_email(to: str, subject: str, body: str) -> bool:
    """Send one email. Returns True if sent, False if skipped (unconfigured) or failed.

    Never raises — a mail failure must not break order/lead creation.
    """
    if not settings.smtp_host or not to:
        return False
    try:
        msg = build_message(to, subject, body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001 — email is best-effort, never block the funnel
        log.warning("email send failed (to=%s): %s", to, exc)
        return False


def order_confirmation(email: str, product: str, quantity: int) -> None:
    """Email the customer their order, and notify sales if configured. Best-effort."""
    send_email(
        email,
        "Your Aura order is confirmed",
        f"Thanks for your order!\n\n"
        f"  Product:  {product}\n"
        f"  Quantity: {quantity}\n\n"
        f"We'll be in touch with shipping details shortly.",
    )
    if settings.sales_email:
        send_email(
            settings.sales_email,
            f"New order: {product}",
            f"New order placed.\n\n  Product: {product}\n  Quantity: {quantity}\n  Customer: {email}",
        )


def lead_notification(email: str, name: str | None, product_interest: str | None) -> None:
    """Notify sales of a new lead, and acknowledge to the customer. Best-effort."""
    if settings.sales_email:
        send_email(
            settings.sales_email,
            "New sales lead",
            f"New lead captured.\n\n  Name: {name or '(not given)'}\n"
            f"  Email: {email}\n  Interested in: {product_interest or '(unspecified)'}",
        )
    send_email(
        email,
        "Thanks for your interest in Aura",
        f"Hi {name or 'there'},\n\nThanks for reaching out — a specialist will follow up with "
        f"you shortly about {product_interest or 'our products'}.",
    )
