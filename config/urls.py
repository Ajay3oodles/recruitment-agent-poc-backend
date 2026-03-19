from django.urls import path, include

urlpatterns = [
    path("api/chat-bot/v1/", include("chatbot.urls")),
]