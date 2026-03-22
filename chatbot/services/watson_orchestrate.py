"""
chatbot/services/watson_orchestrate.py

Low-level IBM Watson Orchestrate API calls.
Handles: IAM token, create_thread, send_message, get_thread_messages.

This file is ONLY for Watson Orchestrate (agent/thread API).
The existing watsonx.py handles embeddings and direct LLM calls — untouched.
"""

import logging
import httpx
import time
from django.conf import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  IAM TOKEN  (reuses same logic as watsonx.py but separate cache)
# ─────────────────────────────────────────────────────────────
_iam_cache: dict = {"token": None, "expires_at": 0.0}


def _get_iam_token() -> str:
    now = time.time()
    if _iam_cache["token"] and now < _iam_cache["expires_at"]:
        return _iam_cache["token"]

    resp = httpx.post(
        "https://iam.cloud.ibm.com/identity/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey":     settings.IBM_API_KEY,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    _iam_cache["token"]      = data["access_token"]
    _iam_cache["expires_at"] = now + 3300
    return _iam_cache["token"]


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_iam_token()}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }


def orchestrate_configured() -> bool:
    """
    Returns True only when Watson Orchestrate credentials are present in settings.
    This is the flag the view uses to decide which flow to run.
    """
    return (
        bool(getattr(settings, "WATSON_ORCHESTRATE_URL",   ""))
        and bool(getattr(settings, "WATSON_ORCHESTRATE_AGENT_ID", ""))
        and bool(getattr(settings, "IBM_API_KEY", ""))
    )


# ─────────────────────────────────────────────────────────────
#  THREAD MANAGEMENT
# ─────────────────────────────────────────────────────────────

def create_thread() -> str:
    """
    Create a new conversation thread in Watson Orchestrate.
    Returns the thread_id string.

    Called once per session — when the student sends their first message.
    """
    url = (
        f"{settings.WATSON_ORCHESTRATE_URL}"
        f"/instances/{settings.WATSON_ORCHESTRATE_AGENT_ID}/v1/threads"
    )

    resp = httpx.post(url, headers=_headers(), json={}, timeout=30)
    resp.raise_for_status()

    thread_id = resp.json().get("thread_id") or resp.json().get("id")
    logger.info(f"[watson_orchestrate] Thread created: {thread_id}")
    return thread_id


def send_message(thread_id: str, message: str) -> str:
    """
    Send a user message into an existing thread.
    Watson Agent handles:
      - searching the knowledge base (calls /api/watson-search/ on your backend)
      - maintaining conversation context
      - calling the LLM and generating the answer

    Returns the agent's answer as a plain string.
    """
    url = (
        f"{settings.WATSON_ORCHESTRATE_URL}"
        f"/instances/{settings.WATSON_ORCHESTRATE_AGENT_ID}/v1/threads/{thread_id}/messages"
    )

    payload = {
        "input": {
            "message_type": "text",
            "text":         message,
        }
    }

    resp = httpx.post(url, headers=_headers(), json=payload, timeout=60)
    resp.raise_for_status()

    data   = resp.json()
    answer = (
        data.get("output", {})
            .get("generic", [{}])[0]
            .get("text", "")
    )

    logger.info(f"[watson_orchestrate] Message sent to thread {thread_id}")
    return answer.strip()


def get_thread_messages(thread_id: str) -> list[dict]:
    """
    Fetch all messages in a thread.
    Used at end of session for lead extraction.

    Returns list of:
        [{"role": "user"|"assistant", "text": "..."}]
    """
    url = (
        f"{settings.WATSON_ORCHESTRATE_URL}"
        f"/instances/{settings.WATSON_ORCHESTRATE_AGENT_ID}/v1/threads/{thread_id}/messages"
    )

    resp = httpx.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()

    messages = []
    for item in resp.json().get("messages", []):
        role = item.get("role", "user")
        text = item.get("input", {}).get("text") or item.get("output", {}).get("generic", [{}])[0].get("text", "")
        if text:
            messages.append({"role": role, "text": text})

    return messages