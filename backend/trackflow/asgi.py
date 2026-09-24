"""ASGI config for trackflow project.

Routes HTTP to the normal Django app and WebSocket connections to the chat/presence and
live-update consumers,
authenticated via a JWT query-param middleware (see apps.chat.middleware).
"""

import os

import django
from channels.routing import ProtocolTypeRouter, URLRouter

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "trackflow.settings")
django.setup()

from django.core.asgi import get_asgi_application  # noqa: E402

django_asgi_app = get_asgi_application()

from apps.chat.middleware import JWTAuthMiddleware  # noqa: E402
from apps.chat.routing import websocket_urlpatterns as chat_websocket_urlpatterns  # noqa: E402
from apps.live.routing import websocket_urlpatterns as live_websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JWTAuthMiddleware(URLRouter(chat_websocket_urlpatterns + live_websocket_urlpatterns)),
    }
)
