from django.urls import path

from .features.chat_bot.presentation.consumers import ChatBotConsumer

websocket_urlpatterns = [
    path("ws/ia-integrations/chat-bot/", ChatBotConsumer.as_asgi()),
]
