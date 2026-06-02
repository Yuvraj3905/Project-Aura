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
