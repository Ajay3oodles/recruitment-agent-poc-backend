from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views
from .views.views import SessionChatListApi, SessionListApi, SessionDeleteAndUpdateApi
from .views.auth_view import SignupView, LoginView, LogoutView
from .views.prompt_view import chat_view   # ← ADD

urlpatterns = [
    # Auth endpoints
    path("auth/signup/", SignupView.as_view(), name="auth-signup"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),

    # Chat endpoints
    path("chat/", chat_view, name="chat"),    # ← CHANGED (was views.views.chat)

    # Session endpoints
    path("sessions/", SessionListApi.as_view(), name="session-list"),
    path("sessions/<int:session_id>/", SessionDeleteAndUpdateApi.as_view(), name="delete-session"),
    path("sessions/<int:session_id>/chats/", SessionChatListApi.as_view(), name="session-chats"),

    # Utility endpoints
    path("pages/", views.views.list_pages, name="list_pages"),
    path("health/", views.views.health, name="health"),

    # Webhook
    path("webhook/publish/", views.views.cascade_publish_webhook, name="publish_webhook"),
]