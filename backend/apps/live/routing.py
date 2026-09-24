from django.urls import re_path

from .consumers import LiveUpdatesConsumer

websocket_urlpatterns = [
    re_path(r"^ws/live/$", LiveUpdatesConsumer.as_asgi()),
]
