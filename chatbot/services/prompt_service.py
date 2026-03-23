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
import httpx
from datetime import date, datetime, timedelta, time
from zoneinfo import ZoneInfo
from chatbot.models import Session, Chat, CMSPage, Lead
from chatbot.services.watsonx import generate_answer, watsonx_embed_single, keyword_embed, ibm_configured, KW_DIM
from chatbot.services.prompt_builder import build_lead_context
from pgvector.django import CosineDistance
from django.conf import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  TIMEZONE HELPERS
# ─────────────────────────────────────────────────────────────

# Business hours in Canada Eastern Time
BUSINESS_TZ = ZoneInfo("America/Toronto")
BUSINESS_START = 9   # 9 AM ET
BUSINESS_END = 18    # 6 PM ET

# Simple in-memory cache for IP -> timezone lookups
_tz_cache: dict[str, str | None] = {}


def _get_timezone_from_ip(ip_address: str | None) -> str | None:
    """
    Resolve timezone string from an IP address using ip-api.com (free, no key).
    Returns e.g. "Asia/Kolkata" or None on failure.
    Caches results to avoid repeated API calls.
    """
    if not ip_address or ip_address in ("127.0.0.1", "::1", "localhost"):
        return None

    if ip_address in _tz_cache:
        return _tz_cache[ip_address]

    try:
        resp = httpx.get(
            f"http://ip-api.com/json/{ip_address}?fields=timezone",
            timeout=3,
        )
        if resp.status_code == 200:
            tz = resp.json().get("timezone")
            _tz_cache[ip_address] = tz
            return tz
    except Exception as e:
        logger.warning(f"[prompt_service] IP timezone lookup failed for {ip_address}: {e}")

    _tz_cache[ip_address] = None
    return None


def get_available_hours_for_user(user_tz_str: str | None) -> str:
    """
    Convert our business hours (9 AM - 6 PM Eastern) to the user's timezone.
    Returns a human-readable string like "7:30 PM - 4:30 AM".
    If no timezone provided, returns Eastern time hours.
    """
    if not user_tz_str:
        return "9:00 AM to 6:00 PM"

    try:
        user_tz = ZoneInfo(user_tz_str)
    except (KeyError, Exception):
        return "9:00 AM to 6:00 PM"

    # Create a reference datetime in Eastern time
    now_et = datetime.now(BUSINESS_TZ)
    start_et = now_et.replace(hour=BUSINESS_START, minute=0, second=0, microsecond=0)
    end_et = now_et.replace(hour=BUSINESS_END, minute=0, second=0, microsecond=0)

    # Convert to user's timezone
    start_user = start_et.astimezone(user_tz)
    end_user = end_et.astimezone(user_tz)

    # Windows doesn't support %-I, use %I and strip leading zero
    start_str = start_user.strftime("%I:%M %p").lstrip("0")
    end_str = end_user.strftime("%I:%M %p").lstrip("0")

    return f"{start_str} to {end_str}"


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

def _get_lead_for_session(session: Session) -> Lead | None:
    """
    Get the Lead linked to this session, if one exists.
    Returns None if no lead has been created yet.
    """
    meta = session.metadata or {}
    lead_id = meta.get("lead_id")

    if lead_id:
        try:
            return Lead.objects.get(id=lead_id, is_deleted=False)
        except Lead.DoesNotExist:
            pass

    return None


def _create_lead_for_session(session: Session, email: str,
                              ip_address: str = None) -> Lead:
    """
    Create a Lead only when the user provides an email.
    Links the Lead to the session via metadata.
    """
    lead = Lead.objects.create(email=email, ip_address=ip_address)
    meta = session.metadata or {}
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

    # Meeting date — always update (user might reschedule)
    if lead_data.get("meeting_date"):
        try:
            lead.meeting_date = date.fromisoformat(lead_data["meeting_date"])
            updated_fields.append("meeting_date")
        except (ValueError, TypeError):
            pass

    # Meeting time — always update (user might reschedule)
    if lead_data.get("meeting_time"):
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

def handle_chat(query: str, session_id: int = None,
                ip_address: str = None) -> dict:
    """
    Full chat flow — called by the view.

    Args:
        query:      User's message
        session_id: Existing session ID (None for new conversation)
        ip_address: User's IP address (from frontend or request headers)

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

    # ── 3. Check if Lead already exists for this session ──────
    lead = _get_lead_for_session(session)
    current_lead_data = _get_current_lead_data(lead) if lead else {}

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

    # Count user messages (including current one) to determine turn number
    turn_number = sum(1 for m in previous_messages if m["role"] == "user")

    # Resolve timezone from IP and convert business hours
    user_tz = _get_timezone_from_ip(ip_address)
    available_hours = get_available_hours_for_user(user_tz)

    # Today's date so LLM can resolve "tomorrow" etc.
    today_str = date.today().strftime("%Y-%m-%d (%A)")

    try:
        result = generate_answer(
            query, pages, previous_messages, lead_context,
            turn_number=turn_number, lead_data=current_lead_data,
            today_date=today_str, available_hours=available_hours,
        )
        answer  = result["answer"]
        summary = result["summary"]

        # ── 8. Handle Lead creation/update from LLM response ──
        lead_data = result.get("lead_data", {})
        if lead_data:
            extracted_email = lead_data.get("email")

            # Lead doesn't exist yet — create ONLY when email is captured
            if not lead and extracted_email:
                lead = _create_lead_for_session(
                    session, email=extracted_email, ip_address=ip_address
                )
                # Remove email from lead_data since we already set it
                lead_data.pop("email", None)
                _update_lead_from_response(lead, lead_data)

            elif lead:
                # Lead already exists — update with new data
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
