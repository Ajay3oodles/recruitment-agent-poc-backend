"""
chatbot/tasks.py
Daily reindex job — called by APScheduler. No Celery, no Redis.
"""

import logging
from django.core.management import call_command

logger = logging.getLogger(__name__)


def reindex_cascade():
    """
    Re-crawl Cascade CMS and update pgvector embeddings.
    Runs once a day at 02:00 AM. Only processes new/changed pages.
    """
    logger.info("[scheduler] Starting daily Cascade reindex...")
    try:
        call_command("index_cascade")
        logger.info("[scheduler] Daily reindex complete.")
    except Exception as e:
        logger.error(f"[scheduler] Reindex failed: {e}")