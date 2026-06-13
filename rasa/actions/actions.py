"""Rasa custom actions.

Uses only the standard library (urllib) so the action server runs on the stock
rasa/rasa-sdk image with no extra dependencies.
"""
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from rasa_sdk import Action, FormValidationAction, Tracker
from rasa_sdk.events import SlotSet
from rasa_sdk.executor import CollectingDispatcher

ML_SERVICE_URL = os.environ.get("ML_SERVICE_URL", "http://ml-service:8100")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _post_json(url: str, body: dict, timeout: float = 300.0) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"content-type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class ActionTechQuery(Action):
    """Route a technical question to the RAG pipeline.

    Rather than block on /answer, emit a `stream` directive (custom payload). The web
    client opens an SSE connection to ml-service /answer/stream and renders tokens as
    they arrive. The turn is still logged in the Rasa tracker (this action ran for the
    tech_query intent), preserving conversation state.
    """

    def name(self) -> str:
        return "action_tech_query"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: dict[str, Any],
    ) -> list[dict[str, Any]]:
        query = tracker.latest_message.get("text", "")
        dispatcher.utter_message(json_message={"stream": True, "query": query})
        return []


class ValidateTicketForm(FormValidationAction):
    """Validate the email slot; re-ask on a malformed address."""

    def name(self) -> str:
        return "validate_ticket_form"

    def validate_email(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: dict[str, Any],
    ) -> dict[str, Any]:
        if EMAIL_RE.match(str(slot_value).strip()):
            return {"email": str(slot_value).strip()}
        dispatcher.utter_message(text="That doesn't look like a valid email. Please re-enter it.")
        return {"email": None}


class ActionSubmitTicket(Action):
    """Persist the collected ticket via ml-service /tickets."""

    def name(self) -> str:
        return "action_submit_ticket"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: dict[str, Any],
    ) -> list[dict[str, Any]]:
        email = tracker.get_slot("email")
        description = tracker.get_slot("issue_description")

        try:
            _post_json(
                f"{ML_SERVICE_URL}/tickets",
                {"email": email, "description": description, "session_id": tracker.sender_id},
            )
        except (urllib.error.URLError, TimeoutError, ValueError):
            dispatcher.utter_message(response="utter_ticket_failed")
            return []

        dispatcher.utter_message(response="utter_ticket_created")
        return [SlotSet("email", None), SlotSet("issue_description", None)]


class ValidateLeadForm(FormValidationAction):
    """Validate the email slot for the lead form; re-ask on a malformed address."""

    def name(self) -> str:
        return "validate_lead_form"

    def validate_email(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: dict[str, Any],
    ) -> dict[str, Any]:
        if EMAIL_RE.match(str(slot_value).strip()):
            return {"email": str(slot_value).strip()}
        dispatcher.utter_message(text="That doesn't look like a valid email. Please re-enter it.")
        return {"email": None}


class ActionSubmitLead(Action):
    """Persist a captured lead via ml-service /leads.

    product_interest is best-effort: the most recent thing the prospect asked about
    (the last user message before the form started), so the follow-up has context.
    """

    def name(self) -> str:
        return "action_submit_lead"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: dict[str, Any],
    ) -> list[dict[str, Any]]:
        name = tracker.get_slot("contact_name")
        email = tracker.get_slot("email")
        product_interest = _recent_product_interest(tracker)

        try:
            _post_json(
                f"{ML_SERVICE_URL}/leads",
                {
                    "name": name,
                    "email": email,
                    "product_interest": product_interest,
                    "session_id": tracker.sender_id,
                },
                timeout=30.0,
            )
        except (urllib.error.URLError, TimeoutError, ValueError):
            dispatcher.utter_message(response="utter_lead_failed")
            return []

        dispatcher.utter_message(response="utter_lead_created")
        return [SlotSet("contact_name", None), SlotSet("email", None)]


class ValidateOrderForm(FormValidationAction):
    """Validate the email slot for the order form; re-ask on a malformed address."""

    def name(self) -> str:
        return "validate_order_form"

    def validate_email(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: dict[str, Any],
    ) -> dict[str, Any]:
        if EMAIL_RE.match(str(slot_value).strip()):
            return {"email": str(slot_value).strip()}
        dispatcher.utter_message(text="That doesn't look like a valid email. Please re-enter it.")
        return {"email": None}


class ActionSubmitOrder(Action):
    """Persist a purchase order via ml-service /orders."""

    def name(self) -> str:
        return "action_submit_order"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: dict[str, Any],
    ) -> list[dict[str, Any]]:
        product = tracker.get_slot("product")
        email = tracker.get_slot("email")

        try:
            _post_json(
                f"{ML_SERVICE_URL}/orders",
                {"product": product, "email": email, "session_id": tracker.sender_id},
                timeout=30.0,
            )
        except (urllib.error.URLError, TimeoutError, ValueError):
            dispatcher.utter_message(response="utter_order_failed")
            return []

        dispatcher.utter_message(response="utter_order_created")
        return [SlotSet("product", None), SlotSet("email", None)]


def _recent_product_interest(tracker: Tracker) -> str | None:
    """Best-effort: the last substantive user message before the lead form started,
    used to tag the lead with what the prospect was interested in."""
    for event in reversed(tracker.events):
        if event.get("event") == "user":
            text = (event.get("text") or "").strip()
            # Skip the trigger message and the name/email the form just collected.
            if text and "@" not in text and len(text.split()) > 2:
                return text[:200]
    return None
