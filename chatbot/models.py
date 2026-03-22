"""
chatbot/models.py

CMSPage — stores every Cascade CMS page with its
          768-dim watsonx embedding vector in Postgres pgvector.
"""

from django.db import models
from pgvector.django import VectorField
from django.db import models
from django.utils import timezone
import uuid
from django.contrib.auth.models import AbstractUser

class BaseEntity(models.Model):
    created_by = models.CharField(max_length=255, null=True, blank=True)
    updated_by = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    is_deleted = models.BooleanField(default=False)

    class Meta:
        abstract = True

class CMSPage(models.Model):
    """
    One row per Cascade CMS page.
    Populated by the index_cascade management command.
    Queried by cosine similarity at chat time.
    """

    # ── Cascade identifiers ───────────────────────────────────
    cascade_id    = models.TextField(unique=True)   # page id from Cascade
    path          = models.TextField()              # /admissions/how-to-apply
    site          = models.TextField()              # www.university.edu

    # ── Content ───────────────────────────────────────────────
    title         = models.TextField()
    content       = models.TextField()              # stripped HTML, max 2000 chars
    url           = models.TextField()              # full public URL

    # ── Vector ───────────────────────────────────────────────
    # 768-dim for ibm/slate-30m-english-rtrvr-v2
    # Change to 37 if using keyword fallback
    embedding = VectorField(dimensions=384, null=True)

    # ── Timestamps ────────────────────────────────────────────
    last_modified = models.DateTimeField(null=True, blank=True)
    indexed_at    = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cms_pages"
        indexes  = [
            # ivfflat index for fast approximate nearest neighbour search
            # lists=100 is good for up to ~1M rows
            models.Index(
                fields=["site"],
                name="cms_pages_site_idx",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.site})"

class Session(BaseEntity):
    """
    Conversation container.
    Each session belongs to a Lead.
    """

    session_name = models.CharField(max_length=255)

    session_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        db_index=True
    )

    is_active = models.BooleanField(default=True)


    # 🔹 New field for IBM Watson Orchestrator thread
    thread_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Thread ID from IBM Watson Orchestrator"
    )

    metadata = models.JSONField(default=dict, blank=True, null=True)

    class Meta:
        db_table = "session"

    def __str__(self):
        return self.session_name
    

class Chat(BaseEntity):
    ROLE_USER = "user"
    ROLE_BOT = "bot"
    ROLE_CHOICES = [
        (ROLE_USER, "User"),
        (ROLE_BOT, "Bot"),
    ]
    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name="chats"
    )
    role = models.CharField(  # ← ADD THIS FIELD
        max_length=10,
        choices=ROLE_CHOICES,
        default=ROLE_USER,
    )

    message = models.TextField()
    summary = models.TextField()

    class Meta:
        db_table = "chat"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["session", "created_at"]),
        ]

class User(AbstractUser):
    """
    Custom user model.
    """
    name  = models.CharField(max_length=255, blank=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return self.username

    class Meta:
        db_table = "user"

class Lead(BaseEntity):
    """
    Stores website visitor details.
    One lead can have multiple sessions.
    """

    first_name = models.CharField(max_length=255, blank=True, default="")
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_synced = models.BooleanField(default=False)
    meeting_date = models.DateField(null=True, blank=True)
    meeting_time = models.TimeField(null=True, blank=True)
    conversation_summary = models.TextField(blank=True, null=True)
    # Lead Classification
    LEAD_TYPE_CHOICES = [
        ('student_undergrad', 'Prospective Undergraduate Student'),
        ('student_grad', 'Prospective Graduate Student'),
        ('student_international', 'International Student'),
        ('research_industry', 'Research/Industry Partnership'),
        ('lifelong_learning', 'Lifelong Learning/Executive Education'),
        ('other', 'Other'),
    ]
    lead_type = models.CharField(
        max_length=50,
        choices=LEAD_TYPE_CHOICES,
        blank=True,
        null=True,
        help_text="Type of lead identified through conversation"
    )
    # Lead Scoring & Engagement Tracking
    intent_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        help_text="Calculated lead score based on engagement and behavior (0-100)"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "lead"
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["phone"]),
        ]

    def __str__(self):
        return f"{self.first_name or self.email or self.phone or 'Unknown'} ({self.ip_address or 'no IP'})"