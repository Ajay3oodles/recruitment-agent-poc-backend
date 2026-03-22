"""
chatbot/services/prompt_service.py

Handles all logic for the chat prompt flow:
  - Fetch session
  - Save user message
  - Retrieve from pgvector
  - Call LLM (answer + summary + lead capture in one call)
  - Save bot response
  - Update Lead record progressively
"""

import json
import logging
from chatbot.models import Session, Chat, CMSPage, Lead
from chatbot.services.watsonx import generate_answer, watsonx_embed_single, keyword_embed, ibm_configured, KW_DIM
from chatbot.services.prompt_builder import build_lead_context
from pgvector.django import CosineDistance
from django.conf import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  RETRIEVAL
# ─────────────────────────────────────────────────────────────

def retrieve(query: str, k: int = 3) -> tuple[list, str]:
    """
    Embed query and find top-k nearest CMS pages from pgvector.
    """
    total_pages = CMSPage.objects.count()

    if total_pages == 0:
        return [], "empty_db"

    try:
        q_vec  = watsonx_embed_single(query)
        source = "pgvector_semantic"
    except Exception as e:
        logger.warning(f"[prompt_service] Embed failed: {e} — keyword fallback")
        q_vec  = keyword_embed(query)
        source = "pgvector_keyword"

    pages = (
        CMSPage.objects
        .annotate(distance=CosineDistance("embedding", q_vec))
        .order_by("distance")[:k]
    )

    return list(pages), source


# ─────────────────────────────────────────────────────────────
#  LEAD HELPERS
# ─────────────────────────────────────────────────────────────

def _get_or_create_lead(session: Session) -> Lead:
    """
    Get the Lead linked to this session, or create one.
    Uses session metadata to store the lead FK.
    """
    meta = session.metadata or {}
    lead_id = meta.get("lead_id")

    if lead_id:
        try:
            return Lead.objects.get(id=lead_id, is_deleted=False)
        except Lead.DoesNotExist:
            pass

    lead = Lead.objects.create()
    meta["lead_id"] = lead.id
    session.metadata = meta
    session.save(update_fields=["metadata"])
    return lead


def _get_current_lead_data(lead: Lead) -> dict:
    """
    Extract current lead fields into a dict for the prompt context.
    """
    data = {}
    if lead.first_name:
        data["name"] = lead.first_name
    if lead.email:
        data["email"] = lead.email
    if lead.phone:
        data["phone"] = lead.phone
    if lead.lead_type:
        data["lead_type"] = lead.lead_type
    if lead.intent_score:
        data["intent_score"] = float(lead.intent_score)
    if lead.meeting_date:
        data["meeting_date"] = str(lead.meeting_date)
    if lead.meeting_time:
        data["meeting_time"] = str(lead.meeting_time)
    if lead.conversation_summary:
        data["conversation_summary"] = lead.conversation_summary
    return data


def _update_lead_from_response(lead: Lead, lead_data: dict) -> None:
    """
    Update Lead model fields from the LLM's extracted lead_data.
    Only updates non-null fields — never overwrites existing data with null.
    """
    updated_fields = []

    if lead_data.get("name") and not lead.first_name:
        lead.first_name = lead_data["name"]
        updated_fields.append("first_name")

    if lead_data.get("email") and not lead.email:
        lead.email = lead_data["email"]
        updated_fields.append("email")

    if lead_data.get("phone") and not lead.phone:
        lead.phone = lead_data["phone"]
        updated_fields.append("phone")

    if lead_data.get("lead_type"):
        lead.lead_type = lead_data["lead_type"]
        updated_fields.append("lead_type")

    if lead_data.get("intent_score") is not None:
        new_score = lead_data["intent_score"]
        if isinstance(new_score, (int, float)) and new_score > float(lead.intent_score):
            lead.intent_score = min(new_score, 100)
            updated_fields.append("intent_score")

    if lead_data.get("meeting_date") and not lead.meeting_date:
        from datetime import date
        try:
            lead.meeting_date = date.fromisoformat(lead_data["meeting_date"])
            updated_fields.append("meeting_date")
        except (ValueError, TypeError):
            pass

    if lead_data.get("meeting_time") and not lead.meeting_time:
        from datetime import time
        try:
            lead.meeting_time = time.fromisoformat(lead_data["meeting_time"])
            updated_fields.append("meeting_time")
        except (ValueError, TypeError):
            pass

    if lead_data.get("conversation_summary"):
        lead.conversation_summary = lead_data["conversation_summary"]
        updated_fields.append("conversation_summary")

    if updated_fields:
        lead.save(update_fields=updated_fields)
        logger.info(f"[prompt_service] Lead {lead.id} updated: {updated_fields}")


# ─────────────────────────────────────────────────────────────
#  MAIN SERVICE
# ─────────────────────────────────────────────────────────────

def handle_chat(query: str, session_id: int = None) -> dict:
    """
    Full chat flow — called by the view.

    Returns:
        {
            "answer":     "...",
            "summary":    "...",
            "sources":    [...],
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

    # ── 3. Get or create Lead for this session ────────────────
    lead = _get_or_create_lead(session)
    current_lead_data = _get_current_lead_data(lead)

    # ── 4. Save user message ──────────────────────────────────
    Chat.objects.create(
        session=session,
        role=Chat.ROLE_USER,
        message=query,
        summary="",
    )

    # ── 5. Fetch previous messages for context ────────────────
    previous_messages = list(
        Chat.objects.filter(session=session)
        .order_by("created_at")
        .values("role", "message")
    )

    # ── 6. Retrieve relevant pages from pgvector ──────────────
    pages, source = retrieve(query)

    # ── 7. Single LLM call — answer + summary + lead data ─────
    lead_context = build_lead_context(current_lead_data)

    try:
        result  = generate_answer(query, pages, previous_messages, lead_context)
        answer  = result["answer"]
        summary = result["summary"]

        # ── 8. Update Lead from LLM response ──────────────────
        lead_data = result.get("lead_data", {})
        if lead_data:
            _update_lead_from_response(lead, lead_data)

    except Exception as e:
        logger.error(f"[prompt_service] LLM call failed: {e}")
        answer  = "Sorry, I couldn't generate an answer. Please try again."
        summary = ""

    # ── 9. Save bot response ──────────────────────────────────
    Chat.objects.create(
        session=session,
        role=Chat.ROLE_BOT,
        message=answer,
        summary=summary,
    )

    # ── 10. Return ────────────────────────────────────────────
    return {
        "answer":     answer,
        "summary":    summary,
        "sources":    [
            {"title": p.title, "url": p.url, "site": p.site}
            for p in pages
        ],
        "session_id": session.id,
    }


# ─────────────────────────────────────────────────────────────
#  CHAT HISTORY
# ─────────────────────────────────────────────────────────────

def get_chat_history(session_token: str) -> dict:
    """
    Returns all messages in a session in order.
    """
    try:
        session = Session.objects.get(session_token=session_token, is_active=True)
    except Session.DoesNotExist:
        raise ValueError("Session not found")

    chats = Chat.objects.filter(session=session).order_by("created_at")

    return {
        "session_name":  session.session_name,
        "session_token": str(session.session_token),
        "messages": [
            {
                "role":       c.role,
                "message":    c.message,
                "summary":    c.summary,
                "created_at": c.created_at.isoformat(),
            }
            for c in chats
        ]
    }
