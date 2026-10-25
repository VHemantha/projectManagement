"""A person writes to the coordination agent: it replies. Messages arrive both over the REST API
and through the chat WebSocket, so this listens on the model."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.chat.models import Message


@receiver(post_save, sender=Message)
def message_posted(sender, instance, created, **kwargs):
    if created:
        from .conversation import on_message

        on_message(instance)
