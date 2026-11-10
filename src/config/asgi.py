import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

django_asgi_application = get_asgi_application()

from contexts.ia_integrations.routing import websocket_urlpatterns as chat_patterns
from features.notifications.routing import websocket_urlpatterns as notification_patterns

websocket_urlpatterns = chat_patterns + notification_patterns

_django_application = ProtocolTypeRouter(
    {
        "http": django_asgi_application,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)


# MCP owns lifespan startup/shutdown; Django/Channels keep their existing routing.
from contexts.ia_integrations.rag.mcp_server import application as questions_mcp

async def application(scope, receive, send):
    if scope['type'] == 'lifespan' or (scope['type'] == 'http' and scope.get('path', '').rstrip('/') == '/mcp/questions'):
        scope = dict(scope)
        if scope['type'] == 'http':
            scope['path'] = '/mcp/questions'
        return await questions_mcp(scope, receive, send)
    return await _django_application(scope, receive, send)
