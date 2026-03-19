# chatbot/views/prompt_view.py

import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from chatbot.services.prompt_service import handle_chat, get_chat_history

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def chat_view(request):
    """
    POST /api/chat/

    Body:
    {
        "query":      "What is the tuition fee?",
        "session_id": 5          <-- optional int; omit or null for new session
    }

    Response always includes session_id so frontend can persist it.
    """
    try:
        body       = json.loads(request.body)
        query      = body.get("query", "").strip()
        session_id = body.get("session_id")   # None if not sent
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    # Normalize: treat 0 / empty string as None (new session)
    if not session_id:
        session_id = None

    try:
        result = handle_chat(query=query, session_id=session_id)
        return JsonResponse(result, status=200)

    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        logger.error(f"[chat_view] Unexpected error: {e}")
        return JsonResponse({"error": "Something went wrong"}, status=500)