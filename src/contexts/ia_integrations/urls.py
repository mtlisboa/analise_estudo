from django.urls import path

from .features.chat_bot.presentation.views import chat_bot

app_name = "ia-integrations"

urlpatterns = [
    path("", chat_bot, name="chat-bot"),
]
