"""
chatbot/views/search_view.py

Custom search endpoint for Watson Orchestrate Agent.

Watson calls this endpoint automatically whenever a student asks a question.
It runs the existing pgvector search and returns results in the exact format
Watson expects.

Endpoint: POST /api/chat-bot/v1/watson-search/

Watson sends:
    { "query": "...", "filter": "", "metadata": {} }

We return:
    {
        "search_results": [
            {
                "title": "...",
                "body":  "...",
                "url":   "...",
                "result_metadata": { "score": 0.94 }
            }
        ]
    }

This view is ONLY called by Watson Orchestrate — not by the frontend.
Auth is via API key in the Authorization header (configured in Watson dashboard).
"""

import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings

from chatbot.services.prompt_service import retrieve   # reuse existing retrieve()

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def watson_search(request):
    """
    Watson Orchestrate calls this endpoint when it needs to search
    for relevant university content.

    This is the ONLY new endpoint you need to build for the agent flow.
    Everything else (pgvector, embeddings, CMS pages) stays exactly the same.
    """

    # ── Optional API key auth ─────────────────────────────────
    # Configure WATSON_SEARCH_API_KEY in settings + in Watson dashboard
    api_key = getattr(settings, "WATSON_SEARCH_API_KEY", "")
    if api_key:
        auth_header = request.headers.get("Authorization", "")
        provided    = auth_header.replace("Bearer ", "").replace("ApiKey ", "").strip()
        if provided != api_key:
            logger.warning("[watson_search] Unauthorized request — invalid API key")
            return JsonResponse({"error": "Unauthorized"}, status=401)

    # ── Parse request ─────────────────────────────────────────
    try:
        body  = json.loads(request.body)
        query = body.get("query", "").strip()
    except Exception:
        return JsonResponse({"search_results": []}, status=400)

    if not query:
        return JsonResponse({"search_results": []})

    logger.info(f"[watson_search] Query received: {query[:80]}")

    # ── Run existing pgvector search ──────────────────────────
    # retrieve() is unchanged from prompt_service.py
    # We just format the results the way Watson expects
    try:
        pages, source = retrieve(query, k=3)
    except Exception as e:
        logger.error(f"[watson_search] Retrieve failed: {e}")
        return JsonResponse({"search_results": []})

    # ── Format for Watson ─────────────────────────────────────
    search_results = []
    for page in pages:
        result = {
            "title": page.title,
            "body":  page.content[:1500],   # Watson has a 100KB response limit
            "url":   page.url,
        }
        # Include score if distance is available (annotated by retrieve())
        if hasattr(page, "distance") and page.distance is not None:
            result["result_metadata"] = {
                "score": round(1 - float(page.distance), 4)
            }
        search_results.append(result)

    logger.info(f"[watson_search] Returning {len(search_results)} results via {source}")

    return JsonResponse({"search_results": search_results})