"""The coordination agent's identity in the Messages section, its audit trail, and who may control it.

The agent is a user account that cannot sign in. Each person has one private conversation with it
(a direct message channel). Only the CEO may change its policies and controls; every attempt by
anyone else is refused and logged.
"""
from django.db import transaction
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import User

from .models import AgentAction, AuditEntry

AGENT_EMAIL = "coordinator@loca.internal"
AGENT_NAME = "Loca Coordinator"
WELCOME = ("Hi {name}, I'm the Loca Coordinator, the AI that helps keep jobs on track. I'll check in here about deadlines, "
           "hours and timesheets, and you can ask me about your own jobs at any time. When I ask for an update, a short "
           "reply with what's left, the hours you need and when you expect to finish is all I need.")


def is_ceo(user) -> bool:
    return bool(user and user.is_authenticated and getattr(user, "role", "") == User.Role.CEO)


def ceo() -> User | None:
    return User.objects.filter(role=User.Role.CEO, is_active=True).first()


def audit(actor, action: str, target: str = "", *, allowed: bool = True, **detail) -> AuditEntry:
    return AuditEntry.objects.create(actor=actor if getattr(actor, "is_authenticated", False) else None, action=action[:60],
                                     target=target[:200], allowed=allowed, detail=detail)


def require_ceo(user, action: str, target: str = "") -> None:
    """Only the CEO controls the agent. Anyone else is refused, and the attempt is logged."""
    if not is_ceo(user):
        audit(user, action, target, allowed=False)
        raise PermissionDenied("Only the CEO can change the coordination agent's settings. You can chat with it in Messages.")


def agent_user() -> User:
    user = User.objects.filter(email=AGENT_EMAIL).first()
    if user is None:
        user = User(email=AGENT_EMAIL, username="loca-coordinator", display_name=AGENT_NAME, job_title="AI project coordinator", is_agent=True)
        user.set_unusable_password()
        user.save()
    return user


def _doc(text: str) -> dict:
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": p}]} for p in paragraphs]}


def post_as_agent(channel, text: str):
    """A message from the agent in a channel, shown live to whoever has it open."""
    from apps.chat.models import Message
    from apps.chat.serializers import MessageSerializer
    from apps.chat.views import broadcast_message

    message = Message.objects.create(channel=channel, author=agent_user(), body=_doc(text))
    transaction.on_commit(lambda: broadcast_message(channel.id, MessageSerializer(message).data))
    return message


def conversation_for(user):
    """The person's private conversation with the agent: found, or created with a welcome."""
    from apps.chat.models import Channel, ChannelMembership
    from apps.orgs.models import Organization

    if user.is_agent:
        raise ValueError("The agent has no conversation with itself.")
    bot = agent_user()
    with transaction.atomic():
        mine = set(ChannelMembership.objects.filter(user=user).values_list("channel_id", flat=True))
        for channel in Channel.objects.filter(id__in=mine, channel_type=Channel.ChannelType.DIRECT_MESSAGE, archived_at__isnull=True,
                                              memberships__user=bot):
            if set(channel.memberships.values_list("user_id", flat=True)) == {user.id, bot.id}:
                return channel
        channel = Channel.objects.create(organization=Organization.get_solo(), name=f"{bot.username}, {user.username}"[:100],
                                         channel_type=Channel.ChannelType.DIRECT_MESSAGE, created_by=bot)
        ChannelMembership.objects.bulk_create([ChannelMembership(channel=channel, user=user), ChannelMembership(channel=channel, user=bot)])
        message = post_as_agent(channel, WELCOME.format(name=user.display_name or user.username))
        AgentAction.objects.create(trigger="conversation_started", target=user, reason="First conversation with the agent", message=message)
    return channel
