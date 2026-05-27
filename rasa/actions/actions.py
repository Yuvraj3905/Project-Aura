"""Rasa custom actions.

Uses only the standard library (urllib) so the action server runs on the stock
rasa/rasa-sdk image with no extra dependencies.
"""
import json
import os
import urllib.error
import urllib.request
from typing import Any

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

ML_SERVICE_URL = os.environ.get("ML_SERVICE_URL", "http://ml-service:8100")


def _post_json(url: str, body: dict, timeout: float = 300.0) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"content-type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class ActionTechQuery(Action):
    """Route a technical question to the RAG pipeline (ml-service /answer)."""

    def name(self) -> str:
        return "action_tech_query"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: dict[str, Any],
    ) -> list[dict[str, Any]]:
        query = tracker.latest_message.get("text", "")

        try:
            result = _post_json(
                f"{ML_SERVICE_URL}/answer",
                {"query": query, "session_id": tracker.sender_id},
            )
        except (urllib.error.URLError, TimeoutError, ValueError):
            dispatcher.utter_message(
                text="The knowledge engine is unavailable right now. Please try again shortly."
            )
            return []

        answer = result.get("answer", "")
        citations = result.get("citations", [])

        if result.get("grounded") and citations:
            refs = ", ".join(
                f"doc {c['document_id'][:8]}·#{c['ordinal']}" for c in citations
            )
            dispatcher.utter_message(text=f"{answer}\n\nSources: {refs}")
        else:
            dispatcher.utter_message(text=answer)

        return []
