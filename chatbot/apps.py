from django.apps import AppConfig

class ChatbotConfig(AppConfig):
    name = "chatbot"

    def ready(self):
        from chatbot import scheduler
        scheduler.start()