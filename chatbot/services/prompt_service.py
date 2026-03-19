"""
chatbot/services/prompt_service.py

Handles all logic for the chat prompt flow:
  - Fetch session
  - Save user message
  - Retrieve from pgvector
  - Call LLM (answer + summary in one call)
  - Save bot response
"""

import logging
from chatbot.models import Session, Chat, CMSPage
from chatbot.services.watsonx import generate_answer, watsonx_embed_single, keyword_embed, ibm_configured, KW_DIM
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
#  MAIN SERVICE
# ─────────────────────────────────────────────────────────────

# chatbot/services/prompt_service.py

def handle_chat(query: str, session_id: int = None) -> dict:
    """
    Full chat flow — called by the view.

    - If session_id is provided: load that session
    - If session_id is None/missing: create a new session automatically

    Returns:
        {
            "answer":     "...",
            "summary":    "...",
            "sources":    [...],
            "session_id": 123,       # always return this so frontend can reuse it
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
        # No session_id from frontend → new conversation, create session
        session = Session.objects.create(
            session_name="New Chat",
            is_active=True,
        )

    # ── 3. Save user message ──────────────────────────────────
    Chat.objects.create(
        session=session,
        role=Chat.ROLE_USER,
        message=query,
        summary="",
    )

    # ── 4. Fetch previous messages for context ────────────────
    previous_messages = list(
        Chat.objects.filter(session=session)
        .order_by("created_at")
        .values("role", "message")
    )

    # ── 5. Retrieve relevant pages from pgvector ──────────────
    pages, source = retrieve(query)

    # ── 6. Single LLM call — answer + summary ─────────────────
    try:
        result  = generate_answer(query, pages, previous_messages)
        answer  = result["answer"]
        summary = result["summary"]
    except Exception as e:
        logger.error(f"[prompt_service] LLM call failed: {e}")
        answer  = "Sorry, I couldn't generate an answer. Please try again."
        summary = ""

    # ── 7. Save bot response ──────────────────────────────────
    Chat.objects.create(
        session=session,
        role=Chat.ROLE_BOT,
        message=answer,
        summary=summary,
    )

    # ── 8. Return ─────────────────────────────────────────────
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