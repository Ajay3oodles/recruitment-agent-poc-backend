"""
chatbot/services/agent_service.py

Agent-based chat flow using Watson Orchestrate threads.

This is the NEW flow — runs only when WATSON_ORCHESTRATE_URL and
WATSON_ORCHESTRATE_AGENT_ID are configured in settings.

The EXISTING prompt_service.py is untouched and still runs when
the agent is not configured.

Flow:
  1. Get or create Session
  2. If first message → create Watson thread → save thread_id to Session
  3. Send message into thread (no prompt, no history, no context building)
  4. Watson calls /api/watson-search/ automatically for pgvector results
  5. Watson returns the answer
  6. Save messages to DB
  7. Return answer + session_id to view

Lead extraction (called separately when session ends):
  - Fetch full thread from Watson
  - Run one LLM call to extract lead data
  - Save Lead to DB
"""

import json
import logging
from django.conf import settings
from chatbot.models import Session, Chat
from chatbot.services.watson_orchestrate import (
    create_thread,
    send_message,
    get_thread_messages,
    orchestrate_configured,
)
from chatbot.services.watsonx import generate_answer   # reuse for lead extraction LLM call

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  MAIN AGENT CHAT HANDLER
# ─────────────────────────────────────────────────────────────

def handle_agent_chat(query: str, session_id: int = None) -> dict:
    """
    Agent-based chat flow.

    - If session_id provided: load session, reuse existing thread
    - If session_id is None: create new session + new Watson thread

    Returns:
        {
            "answer":     "...",
            "session_id": 123,
        }
    """

    # ── 1. Validate ───────────────────────────────────────────
    if not query:
        raise ValueError("query is required")

    # ── 2. Get or create session ──────────────────────────────
    if session_id:
        try:
            session = Session.objects.get(id=session_id, is_active=True, is_deleted=False)
        except Session.DoesNotExist:
            raise ValueError(f"Session {session_id} not found or inactive")
    else:
        session = Session.objects.create(
            session_name="New Chat",
            is_active=True,
        )
        logger.info(f"[agent_service] New session created: {session.id}")

    # ── 3. Create Watson thread if first message ──────────────
    if not session.thread_id:
        thread_id          = create_thread()
        session.thread_id  = thread_id
        session.save(update_fields=["thread_id"])
        logger.info(f"[agent_service] Thread created for session {session.id}: {thread_id}")

    # ── 4. Save user message to DB ────────────────────────────
    Chat.objects.create(
        session=session,
        role=Chat.ROLE_USER,
        message=query,
        summary="",
    )

    # ── 5. Send message to Watson — that's it ─────────────────
    #   Watson handles: search, context, LLM call, answer
    #   No prompt building. No history. No pgvector call from here.
    try:
        answer = send_message(session.thread_id, query)
    except Exception as e:
        logger.error(f"[agent_service] Watson send_message failed: {e}")
        answer = "Sorry, I couldn't process your request. Please try again."

    # ── 6. Save bot response to DB ────────────────────────────
    Chat.objects.create(
        session=session,
        role=Chat.ROLE_BOT,
        message=answer,
        summary="",    # No per-message summary needed — thread maintains context
    )

    # ── 7. Return ─────────────────────────────────────────────
    return {
        "answer":     answer,
        "session_id": session.id,
    }


# ─────────────────────────────────────────────────────────────
#  LEAD EXTRACTION  (called when session ends)
# ─────────────────────────────────────────────────────────────

def extract_lead_from_session(session_id: int) -> dict:
    """
    Fetch full thread from Watson, run one LLM call to extract lead data.
    Called when:
      - Student closes the chat widget (frontend sends close event)
      - Session goes idle (scheduler picks up stale sessions)

    Returns extracted lead dict.
    """
    try:
        session = Session.objects.get(id=session_id)
    except Session.DoesNotExist:
        raise ValueError(f"Session {session_id} not found")

    if not session.thread_id:
        logger.warning(f"[agent_service] Session {session_id} has no thread_id — skipping lead extraction")
        return {}

    # ── Fetch full conversation from Watson thread ────────────
    messages = get_thread_messages(session.thread_id)

    if not messages:
        return {}

    # ── Format conversation for LLM ──────────────────────────
    conversation = "\n".join(
        f"{'Student' if m['role'] == 'user' else 'Assistant'}: {m['text']}"
        for m in messages
    )

    # ── One LLM call — extract everything ────────────────────
    extraction_prompt = f"""
Analyze this university chatbot conversation and extract the following in valid JSON only.
No extra text, no markdown fences, just the JSON object.

{{
    "name":       "student full name if mentioned, else null",
    "email":      "email address if mentioned, else null",
    "phone":      "phone number if mentioned, else null",
    "program":    "program or course they asked about, else null",
    "intent":     "one of: applying / exploring / current_student / other",
    "sentiment":  "one of: positive / neutral / negative",
    "lead_score": "integer 1-10 based on how likely they are to apply",
    "summary":    "2-3 sentence summary of the full conversation"
}}

Conversation:
{conversation}
"""

    try:
        # Reuse existing generate_answer with no pages — pure extraction call
        result = generate_answer(
            query=extraction_prompt,
            pages=[],
            previous_messages=[],
        )
        lead_data = json.loads(result.get("answer", "{}"))
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"[agent_service] Lead extraction failed: {e}")
        lead_data = {}

    logger.info(f"[agent_service] Lead extracted for session {session_id}: {lead_data}")
    return lead_data