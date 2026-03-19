"""
University Chatbot — Django Views (pgvector edition)

Changes from previous version:
  ✅ Retrieval now queries Postgres pgvector (NOT in-memory cosine)
  ✅ Uses CMSPage model — pages indexed by management command
  ✅ Cascade API only called during indexing, not at chat time
  ✅ Falls back to keyword search if pgvector empty
  ✅ Same API surface — frontend needs no changes
"""

import json
import httpx
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from pgvector.django import CosineDistance

from chatbot.models import CMSPage
from chatbot.services.watsonx import (
    watsonx_embed_single,
    keyword_embed,
    generate_answer,
    ibm_configured,
    KW_DIM,
)


# ─────────────────────────────────────────────────────────────
#  RETRIEVAL — query pgvector
# ─────────────────────────────────────────────────────────────

def retrieve(query: str, k: int = 3) -> tuple[list, str]:
    """
    1. Embed query with watsonx (or keyword fallback)
    2. Query Postgres pgvector for nearest neighbours
    3. Return top-k CMSPage objects + source label
    """

    # Check if vector DB has any pages
    total_pages = CMSPage.objects.count()

    if total_pages == 0:
        # Vector DB empty — return mock data with instructions
        return _mock_fallback(query, k), "mock_fallback (run index_cascade)"

    # Embed the query
    try:
        q_vec  = watsonx_embed_single(query)
        source = "pgvector_semantic"
    except Exception as e:
        print(f"[embed error] {e} — using keyword fallback")
        q_vec  = keyword_embed(query)
        source = "pgvector_keyword"

    # pgvector cosine distance search
    # <=> operator = cosine distance (lower = more similar)
    pages = (
        CMSPage.objects
        .annotate(distance=CosineDistance("embedding", q_vec))
        .order_by("distance")[:k]
    )

    results = list(pages)

    if not results:
        return _mock_fallback(query, k), "mock_fallback (no results)"

    return results, source


def _mock_fallback(query: str, k: int) -> list:
    """
    Returns mock CMSPage-like objects when DB is empty.
    Keeps the frontend working before first index run.
    """
    import math, re

    MOCK = [
        {"cascade_id": "p001", "path": "/admissions/how-to-apply",
         "title": "How to Apply — Undergraduate Admissions", "site": "admissions",
         "url": "https://greenfield.edu/admissions/undergraduate/how-to-apply",
         "content": "Submit the Common Application by November 1 (Early Decision) or January 15 (Regular Decision). Required: transcripts, two teacher recommendations, SAT/ACT (test-optional), personal essay, $65 fee."},
        {"cascade_id": "p002", "path": "/admissions/undergraduate/tuition-fees",
         "title": "Tuition & Fees 2025–2026", "site": "admissions",
         "url": "https://greenfield.edu/admissions/undergraduate/tuition-fees",
         "content": "Undergraduate tuition: $54,320. Room and board: ~$16,200. Student fees: $1,840/year. Total estimated COA: $72,360."},
        {"cascade_id": "p003", "path": "/financial-aid/scholarships",
         "title": "Scholarships & Grants", "site": "financial-aid",
         "url": "https://greenfield.edu/financial-aid/scholarships",
         "content": "Presidential Scholarship: up to $28,000/year. STEM Excellence Award: $15,000/year. FAFSA deadline: February 1."},
        {"cascade_id": "p004", "path": "/academics/programs/computer-science",
         "title": "Computer Science — BS Degree", "site": "academics",
         "url": "https://greenfield.edu/academics/programs/computer-science",
         "content": "120-credit ABET-accredited BS in CS. Concentrations: AI & ML, Cybersecurity, HCI. 96% placement rate."},
        {"cascade_id": "p005", "path": "/campus-life/housing",
         "title": "Residence Halls & On-Campus Housing", "site": "campus-life",
         "url": "https://greenfield.edu/campus-life/housing",
         "content": "Guaranteed housing for first and second year students. Room costs: $8,200–$10,400 per academic year."},
    ]

    # Simple keyword scoring for mock fallback
    q_words = set(re.split(r"\W+", query.lower()))
    scored  = []
    for p in MOCK:
        words   = set(re.split(r"\W+", (p["title"] + " " + p["content"]).lower()))
        overlap = len(q_words & words)
        scored.append((overlap, p))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Return as simple objects with same attributes as CMSPage
    class MockPage:
        def __init__(self, d):
            self.__dict__.update(d)
            self.score = None

    return [MockPage(p) for _, p in scored[:k]]


# ─────────────────────────────────────────────────────────────
#  DJANGO VIEWS
# ─────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def chat(request):
    """POST /api/chat/"""
    try:
        body  = json.loads(request.body)
        query = body.get("query", "").strip()
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not query:
        return JsonResponse({"error": "query is required"}, status=400)

    # ── Retrieve from pgvector ────────────────────────────────
    pages, source = retrieve(query)

    # ── Generate answer ───────────────────────────────────────
    try:
        answer     = generate_answer(query, pages)
        llm_status = "ok"
        llm_detail = f"watsonx.ai {settings.IBM_MODEL_ID}"
    except Exception as e:
        answer     = f"LLM error: {str(e)}"
        llm_status = "err"
        llm_detail = str(e)[:80]

    # ── Build pipeline debug info ─────────────────────────────
    embed_label = (
        f"watsonx {settings.IBM_EMBED_MODEL_ID} (768-dim)"
        if ibm_configured()
        else f"keyword fallback ({KW_DIM}-dim)"
    )

    total_indexed = CMSPage.objects.count()

    pipeline = [
        {
            "step":   "embed",
            "label":  "Query Embedded",
            "status": "ok",
            "detail": embed_label,
        },
        {
            "step":   "pgvector",
            "label":  "pgvector Search",
            "status": "ok",
            "detail": f"{source} → {len(pages)} page(s) matched | {total_indexed} pages in DB",
            "pages":  [
                {
                    "title": p.title,
                    "path":  p.path,
                    "site":  p.site,
                }
                for p in pages
            ],
        },
        {
            "step":   "llm",
            "label":  "watsonx.ai Generation",
            "status": llm_status,
            "detail": llm_detail,
        },
    ]

    return JsonResponse({
        "answer":   answer,
        "sources":  [
            {"title": p.title, "url": p.url, "site": p.site}
            for p in pages
        ],
        "pipeline": pipeline,
    })


@require_http_methods(["GET"])
def health(request):
    """GET /api/health/"""
    cascade_ok  = (
        bool(settings.CASCADE_BASE_URL)
        and "your-cascade" not in settings.CASCADE_BASE_URL
        and settings.CASCADE_API_USER != "api_service_user"
    )
    watsonx_ok  = ibm_configured()
    total_pages = CMSPage.objects.count()
    last_page   = CMSPage.objects.order_by("-indexed_at").first()

    return JsonResponse({
        "status":              "ok",
        "cascade_configured":  cascade_ok,
        "watsonx_configured":  watsonx_ok,
        "vector_db":           "postgres+pgvector",
        "pages_in_db":         total_pages,
        "last_indexed":        str(last_page.indexed_at) if last_page else "never",
        "embed_model":         settings.IBM_EMBED_MODEL_ID,
        "llm_model":           settings.IBM_MODEL_ID,
        "mode": (
            "full_live"              if (cascade_ok and watsonx_ok and total_pages > 0) else
            "needs_index_run"        if (cascade_ok and watsonx_ok and total_pages == 0) else
            "mock_fallback"          if total_pages == 0 else
            "pgvector+mock_llm"      if (total_pages > 0 and not watsonx_ok) else
            "pgvector+watsonx"
        ),
    })


@require_http_methods(["GET"])
def list_pages(request):
    """GET /api/pages/?site=admissions&limit=20"""
    site  = request.GET.get("site", "")
    limit = int(request.GET.get("limit", 20))
    qs    = CMSPage.objects.all()
    if site:
        qs = qs.filter(site=site)
    pages = qs.order_by("-indexed_at")[:limit]
    return JsonResponse({
        "count": qs.count(),
        "pages": [
            {
                "id":           p.cascade_id,
                "title":        p.title,
                "path":         p.path,
                "site":         p.site,
                "url":          p.url,
                "last_modified": str(p.last_modified),
                "indexed_at":   str(p.indexed_at),
            }
            for p in pages
        ],
    })


@csrf_exempt
@require_http_methods(["POST"])
def cascade_publish_webhook(request):
    """
    POST /api/webhook/publish/
    Called by Cascade CMS Publish Trigger when a page is published.
    Re-indexes that specific page immediately.
    Usage: configure in Cascade → Administration → Publish Triggers
    """
    try:
        body = json.loads(request.body)
        path = body.get("path", "")
        site = body.get("site", settings.CASCADE_SITE)
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not path:
        return JsonResponse({"error": "path required"}, status=400)

    # Import here to avoid circular imports
    from chatbot.management.commands.index_cascade import Command
    cmd = Command()
    page = cmd._read_page(site, path)

    if not page:
        return JsonResponse({"error": "Could not read page from Cascade"}, status=404)

    from chatbot.watsonx import watsonx_embed_batch, keyword_embed
    from django.utils import timezone
    try:
        vec = watsonx_embed_batch([f"{page['title']} {page['content']}"])[0]
    except Exception:
        vec = keyword_embed(f"{page['title']} {page['content']}")

    CMSPage.objects.update_or_create(
        cascade_id=page["cascade_id"],
        defaults={**page, "embedding": vec, "indexed_at": timezone.now()},
    )

    return JsonResponse({"status": "indexed", "path": path, "site": site})


from rest_framework.views import APIView
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from chatbot.serializers.chat_serializer import ChatSerializer
from chatbot.serializers.session_serializer import SessionSerializer
from chatbot.services.session_chat_service import SessionChatService
from chatbot.utils.response_utils import success_response, error_response


class SessionChatListApi(APIView):

    @swagger_auto_schema(
        operation_summary="Get chats of a session",
        manual_parameters=[
            openapi.Parameter(
                "session_id",
                openapi.IN_PATH,
                description="Session primary key",
                type=openapi.TYPE_INTEGER,
                required=True
            )
        ],
        responses={200: ChatSerializer(many=True)}
    )
    def get(self, request, session_id):
        try:
            # 1️⃣ Get session safely
            session = SessionChatService.get_session(session_id)
            if not session:
                return error_response(
                    message="Session not found",
                    status_code=404
                )

            chats = SessionChatService.get_chats_for_session(session)

            serializer = ChatSerializer(chats, many=True)

            return success_response(
                serializer.data,
                "Chats fetched successfully"
            )

        except Exception as e:
            return error_response(
                message=str(e),
                status_code=400
            )

class SessionDeleteAndUpdateApi(APIView):

    @swagger_auto_schema(
        operation_summary="Delete a session and all related chats",
        manual_parameters=[
            openapi.Parameter(
                "session_id",
                openapi.IN_PATH,
                type=openapi.TYPE_INTEGER
            )
        ],
        responses={200: "Session deleted"}
    )
    def delete(self, request, session_id):
        SessionChatService.delete_session(session_id)

        return success_response(
            message="Session and its chats deleted successfully"
        )

    @swagger_auto_schema(
        operation_summary="Update session name",
        tags=["sessions"],
        manual_parameters=[
            openapi.Parameter(
                "session_id",
                openapi.IN_PATH,
                description="Session primary key",
                type=openapi.TYPE_INTEGER,
                required=True
            ),
            openapi.Parameter(
                "name",
                openapi.IN_QUERY,
                description="New session name",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        responses={200: "Session name updated successfully"}
    )
    def put(self, request, session_id):
        name = request.query_params.get("name")

        if not name:
            return error_response(
                message="name is required",
                status_code=400
            )

        try:
            session = SessionChatService.update_session_name(
                session_id=session_id,
                name=name
            )

            return success_response(
                data={
                    "session_id": session.id,
                    "session_name": session.session_name
                },
                message="Session name updated successfully"
            )

        except ValueError as e:
            return error_response(str(e), 404)

        except Exception as e:
            return error_response(str(e), 400)

class SessionListApi(APIView):
        @swagger_auto_schema(
            operation_summary="List all sessions (non-deleted)",
            tags=["sessions"],
            responses={200: SessionSerializer(many=True)}
        )
        def get(self, request):
            sessions = SessionChatService.get_all_sessions()
            serializer = SessionSerializer(sessions, many=True)
            return success_response(
                data=serializer.data,
                message="Sessions fetched successfully"
            )
