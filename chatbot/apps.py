from django.apps import AppConfig

class ChatbotConfig(AppConfig):
    name = "chatbot"

    def ready(self):
        import sys
        if 'makemigrations' not in sys.argv and 'migrate' not in sys.argv:
            from chatbot import scheduler
            scheduler.start()