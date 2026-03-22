"""
chatbot/watsonx.py

IBM watsonx.ai helpers:
  - IAM token management (cached 55 min)
  - Embeddings : ibm/slate-30m-english-rtrvr-v2  (768-dim)
  - LLM        : meta-llama/llama-3-2-11b-vision-instruct
  - Uses /ml/v1/text/chat  (/text/generation is deprecated by IBM)
  - Keyword fallback when IBM credentials are not set
"""
import json
import re
import time
import math
import hashlib
import logging
import httpx
from django.conf import settings
from chatbot.services.prompt_builder import build_chat_prompt, build_context, build_history

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  IAM TOKEN  (cached 55 min to avoid hitting rate limits)
# ─────────────────────────────────────────────────────────────
_iam_cache: dict = {"token": None, "expires_at": 0.0}


def get_iam_token() -> str:
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
    _iam_cache["expires_at"] = now + 3300  # 55 min
    return _iam_cache["token"]


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_iam_token()}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }


def ibm_configured() -> bool:
    """Returns True only when real IBM credentials are present."""
    return (
        bool(getattr(settings, "IBM_API_KEY", ""))
        and settings.IBM_API_KEY not in ("", "your-ibm-cloud-api-key")
        and bool(getattr(settings, "IBM_PROJECT_ID", ""))
        and settings.IBM_PROJECT_ID not in ("", "your-watsonx-project-id")
    )


# ─────────────────────────────────────────────────────────────
#  EMBEDDINGS
#  Model    : ibm/slate-30m-english-rtrvr-v2
#  Endpoint : POST /ml/v1/text/embeddings
#  Output   : 768-dim float vectors
# ─────────────────────────────────────────────────────────────

def watsonx_embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of texts using IBM watsonx.
    Falls back to keyword hashing when IBM is not configured.
    """
    if not ibm_configured():
        logger.warning("[watsonx] IBM not configured — using keyword fallback.")
        return [keyword_embed(t) for t in texts]

    url = (
        f"{settings.IBM_WATSONX_URL}/ml/v1/text/embeddings"
        f"?version={settings.IBM_WATSONX_VERSION}"
    )
    payload = {
        "model_id":   settings.IBM_EMBED_MODEL_ID,
        "project_id": settings.IBM_PROJECT_ID,
        "inputs":     texts,
        "parameters": {
            "truncate_input_tokens": 512,
            "return_options": {"input_text": False},
        },
    }

    resp = httpx.post(url, headers=_headers(), json=payload, timeout=60)
    resp.raise_for_status()

    results = resp.json().get("results", [])
    return [item["embedding"] for item in results]


def watsonx_embed_single(text: str) -> list[float]:
    """Convenience wrapper — embed one text."""
    return watsonx_embed_batch([text])[0]


# ─────────────────────────────────────────────────────────────
#  KEYWORD FALLBACK EMBEDDINGS  (768-dim hash-based)
# ─────────────────────────────────────────────────────────────
KW_DIM = 768


def keyword_embed(text: str) -> list[float]:
    """Hash each word into a 768-dim vector bucket and L2-normalise."""
    vec = [0.0] * KW_DIM
    for word in text.lower().split():
        idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % KW_DIM
        vec[idx] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


# ─────────────────────────────────────────────────────────────
#  LLM — ANSWER GENERATION
#  Model    : meta-llama/llama-3-2-11b-vision-instruct
#  Endpoint : POST /ml/v1/text/chat
# ─────────────────────────────────────────────────────────────

def generate_answer(query: str, pages: list, previous_messages: list[dict] = None,
                    lead_context: str = "") -> dict:
    """
    Single LLM call — returns answer, summary, and lead_data.
    """

    # ── Fallback when IBM not configured ─────────────────────
    if not ibm_configured():
        if pages:
            p = pages[0]
            answer = (
                f"Based on **{p.title}**:\n\n"
                f"{p.content[:400]}...\n\n"
                f"_Source: [{p.title}]({p.url})_"
            )
        else:
            answer = "I couldn't find relevant information. Please contact Ontario Tech University directly."
        return {"answer": answer, "summary": "", "lead_data": {}}

    # ── Build prompt parts ────────────────────────────────────
    context        = build_context(pages)
    history        = build_history(previous_messages or [])
    system_prompt  = build_chat_prompt(query, context, history, lead_context)

    # ── Call IBM /ml/v1/text/chat ─────────────────────────────
    url = (
        f"{settings.IBM_WATSONX_URL}/ml/v1/text/chat"
        f"?version={settings.IBM_WATSONX_VERSION}"
    )
    payload = {
        "model_id":   settings.IBM_MODEL_ID,
        "project_id": settings.IBM_PROJECT_ID,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": query},
        ],
        "parameters": {
            "max_new_tokens":     500,
            "decoding_method":    "greedy",
            "repetition_penalty": 1.1,
        },
    }

    try:
        resp = httpx.post(url, headers=_headers(), json=payload, timeout=60)
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()

        # ✅ Robustly extract JSON — handles any extra text Llama adds before/after
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            raise json.JSONDecodeError("No JSON object found", raw, 0)

        result = json.loads(raw[start:end])

        return {
            "answer": result.get("answer", "").strip(),
            "summary": result.get("summary", "").strip(),
            "lead_data": result.get("lead_data", {}),
        }

    except (json.JSONDecodeError, KeyError):
        logger.warning("[watsonx] LLM did not return valid JSON — using raw text.")
        clean = re.sub(r'\{.*\}', '', raw, flags=re.DOTALL).strip()
        return {"answer": clean or raw, "summary": "", "lead_data": {}}
    except httpx.HTTPStatusError as e:
        logger.error(f"[watsonx] HTTP error {e.response.status_code}: {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"[watsonx] Error: {e}")
        raise