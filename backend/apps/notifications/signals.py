from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.chat.models import Message

from .inbox import push_direct_message


@receiver(post_save, sender=Message)
def direct_message_sent(sender, instance, created, **kwargs):
    # Covers both ways messages are sent (chat socket and REST).
    if created:
        push_direct_message(instance)
