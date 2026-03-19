from django.db import transaction
from django.shortcuts import get_object_or_404

from chatbot.models import Session, Chat


class SessionChatService:
    """
    Handles retrieval of chats for a session.
    Summary is INTERNAL and never returned.
    """

    @staticmethod
    def get_session(session_id):
        return Session.objects.filter(
            id=session_id,
            is_deleted=False
        ).first()

    @staticmethod
    def get_chats_for_session(session):
        return (
            session.chats
            .filter(is_deleted=False)
            .order_by("created_at")
        )

    # -------------------------
    # DELETE SESSION + CHATS
    # -------------------------

    @staticmethod
    @transaction.atomic
    def delete_session(session_id: int) -> None:
        session = get_object_or_404(
            Session,
            id=session_id,
            is_deleted=False
        )

        # Soft delete chats
        Chat.objects.filter(
            session=session,
            is_deleted=False
        ).update(is_deleted=True)

        # Soft delete session
        session.is_deleted = True
        session.is_active = False
        session.save(update_fields=["is_deleted", "is_active"])

    @staticmethod
    def update_session_name(session_id, name):
        session = SessionChatService.get_session(session_id)
        if not session:
            raise ValueError("Session not found")

        session.session_name = name
        session.save(update_fields=["session_name"])

        return session

    @staticmethod
    def get_all_sessions():
        """
        Retrieve all sessions which are not deleted
        """
        return (
            Session.objects
            .filter(is_deleted=False)
            .order_by("-created_at")
        )
