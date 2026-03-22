from pathlib import Path
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-secret-key-change-in-production")

DEBUG = True

ALLOWED_HOSTS = ["*"]


# ─────────────────────────────────────────────────────────────
# INSTALLED APPS
# ─────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    "corsheaders",

    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "rest_framework",
    "rest_framework_simplejwt",
    "drf_yasg",

    "chatbot",
    "django_apscheduler",]


# ─────────────────────────────────────────────────────────────
# MIDDLEWARE
# ─────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]


ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "config.wsgi.application"


# ─────────────────────────────────────────────────────────────
# DATABASE (Postgres + pgvector)
# ─────────────────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "university_chatbot"),
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}


# ─────────────────────────────────────────────────────────────
# STATIC FILES
# ─────────────────────────────────────────────────────────────
STATIC_URL = "/static/"


# ─────────────────────────────────────────────────────────────
# CORS
# ─────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
]


# ─────────────────────────────────────────────────────────────
# DJANGO REST FRAMEWORK
# ─────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.AllowAny",
    ),
}


# ─────────────────────────────────────────────────────────────
# JWT SETTINGS
# ─────────────────────────────────────────────────────────────
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}


# ─────────────────────────────────────────────────────────────
# SWAGGER SETTINGS
# ─────────────────────────────────────────────────────────────
SWAGGER_SETTINGS = {
    "SECURITY_DEFINITIONS": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
        }
    },
    "USE_SESSION_AUTH": False,
}


# ─────────────────────────────────────────────────────────────
# CASCADE CMS
# ─────────────────────────────────────────────────────────────
CASCADE_BASE_URL = os.getenv("CASCADE_BASE_URL", "https://your-cascade.edu")
CASCADE_API_USER = os.getenv("CASCADE_API_USER", "api_service_user")
# CASCADE_API_PASS = os.getenv("CASCADE_API_PASS", "api_service_pass")
CASCADE_SITE = os.getenv("CASCADE_SITE", "university.edu")

CASCADE_CRAWL_BATCH = int(os.getenv("CASCADE_CRAWL_BATCH", "50"))


# ─────────────────────────────────────────────────────────────
# IBM WATSONX AI
# ─────────────────────────────────────────────────────────────
IBM_API_KEY = os.getenv("IBM_API_KEY", "")
IBM_PROJECT_ID = os.getenv("IBM_PROJECT_ID", "")

IBM_WATSONX_URL = os.getenv(
    "IBM_WATSONX_URL",
    "https://us-south.ml.cloud.ibm.com"
)

IBM_WATSONX_VERSION = os.getenv(
    "IBM_WATSONX_VERSION",
    "2024-05-31"
)

IBM_MODEL_ID = os.getenv(
    "IBM_MODEL_ID",
    "ibm/granite-13b-instruct-v2"
)

IBM_EMBED_MODEL_ID = os.getenv(
    "IBM_EMBED_MODEL_ID",
    "ibm/slate-30m-english-rtrvr-v2"
)


# ─────────────────────────────────────────────────────────────
# CELERY (Scheduled indexing)
# ─────────────────────────────────────────────────────────────
CELERY_BROKER_URL = "redis://localhost:6379/0"

CELERY_BEAT_SCHEDULE = {
    "reindex-cascade-daily": {
        "task": "chatbot.tasks.reindex_cascade",
        "schedule": float(os.getenv("INDEX_REFRESH_HOURS", "24")) * 3600,
    },
}

AUTH_USER_MODEL = 'chatbot.User'
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


WATSON_ORCHESTRATE_URL      = os.getenv("WATSON_ORCHESTRATE_URL",      "")
WATSON_ORCHESTRATE_AGENT_ID = os.getenv("WATSON_ORCHESTRATE_AGENT_ID", "")
WATSON_SEARCH_API_KEY       = os.getenv("WATSON_SEARCH_API_KEY",       "")