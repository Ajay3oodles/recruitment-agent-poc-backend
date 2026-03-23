"""
chatbot/views/prompt_view.py

Chat view — automatically switches between two flows:

  FLOW A (existing, unchanged):
    Uses prompt_service.handle_chat()
    Direct LLM call with pgvector retrieval + prompt building
    Runs when Watson Orchestrate is NOT configured

  FLOW B (new agent flow):
    Uses agent_service.handle_agent_chat()
    Watson Orchestrate thread — no prompt building, no history sending
    Runs when WATSON_ORCHESTRATE_URL + WATSON_ORCHESTRATE_AGENT_ID are set in .env

The view itself doesn't care which flow runs — it just checks
orchestrate_configured() and routes accordingly.

No existing code was removed or modified.
"""

import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from chatbot.services.prompt_service  import handle_chat           # FLOW A — existing
from chatbot.services.agent_service   import (                     # FLOW B — new
    handle_agent_chat,
    extract_lead_from_session,
)
from chatbot.services.watson_orchestrate import orchestrate_configured
logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def chat_view(request):
    """
    POST /api/chat-bot/v1/chat/

    Body:
    {
        "query":      "What is the tuition fee?",
        "session_id": 5          <-- optional; null/omit for new session
    }

    Automatically uses agent flow if Watson Orchestrate is configured,
    otherwise falls back to the existing direct LLM flow.
    """
    try:
        body       = json.loads(request.body)
        query      = body.get("query", "").strip()
        session_id = body.get("session_id")
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not session_id:
        session_id = None

    # IP address: prefer frontend-sent value, fallback to request headers
    ip_address = (
        body.get("ip_address")
        or request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        or request.META.get("REMOTE_ADDR")
    )

    # ── Route to correct flow ─────────────────────────────────
    using_agent = orchestrate_configured()

    if using_agent:
        logger.info(f"[chat_view] Using AGENT flow (Watson Orchestrate)")
    else:
        logger.info(f"[chat_view] Using DIRECT flow (prompt_service)")

    try:
        if using_agent:
            # FLOW B — Watson Orchestrate thread
            result = handle_agent_chat(query=query, session_id=session_id)
        else:
            # FLOW A — direct LLM call with lead capture
            result = handle_chat(
                query=query, session_id=session_id,
                ip_address=ip_address,
            )

        # Tell the frontend which flow was used (useful for debugging)
        result["flow"] = "agent" if using_agent else "direct"

        return JsonResponse(result, status=200)

    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        logger.error(f"[chat_view] Unexpected error: {e}")
        return JsonResponse({"error": "Something went wrong"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def close_session_view(request):
    """
    POST /api/chat-bot/v1/chat/close/

    Called when student closes the chat widget.
    Triggers lead extraction from the Watson thread.

    Body:
    {
        "session_id": 42
    }

    Only runs in agent flow — ignored in direct flow
    (direct flow has no thread to extract from).
    """
    try:
        body       = json.loads(request.body)
        session_id = body.get("session_id")
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not session_id:
        return JsonResponse({"error": "session_id is required"}, status=400)

    if not orchestrate_configured():
        # In direct flow, nothing to do here
        return JsonResponse({"status": "skipped", "reason": "agent not configured"})

    try:
        lead_data = extract_lead_from_session(session_id)
        return JsonResponse({"status": "ok", "lead": lead_data})
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        logger.error(f"[close_session_view] Error: {e}")
        return JsonResponse({"error": "Lead extraction failed"}, status=500)