"""Inbox events: what can pop up as a desktop notification.

Three sources, one shape:
- a new direct / group-direct message to you,
- an @mention of you in any channel (it is also a bell notification),
- any other bell notification (assigned to you, a comment on your job, …).

Each event is {"id", "kind", "tag", "title", "body", "url", "channel_id", "created_at"}.
`tag` is shared by every event about the same chat message, so a DM that also @mentions you
shows one desktop notification, not two. Your own messages and actions never produce events.

Events are pushed live over the user's socket (apps.live.broadcast.push_to_user) and can also
be read back with recent_events() — the polling fallback for when the socket is down.
"""
from apps.chat.models import Channel, ChannelMembership, Message
from apps.live.broadcast import push_to_user

from .models import Notification

PREVIEW_LENGTH = 140
DM_TYPES = (Channel.ChannelType.DIRECT_MESSAGE, Channel.ChannelType.GROUP_DM)


def plain_text(doc, max_length: int = PREVIEW_LENGTH) -> str:
    """Readable text from a rich-text (ProseMirror JSON) message body; @mentions as @Name."""
    parts: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "mention":
                label = (node.get("attrs") or {}).get("label")
                if label:
                    parts.append(f"@{label}")
            if isinstance(node.get("text"), str):
                parts.append(node["text"])
            for child in node.get("content") or []:
                walk(child)
        elif isinstance(node, str):
            parts.append(node)

    walk(doc)
    text = " ".join(" ".join(parts).split())
    return text if len(text) <= max_length else text[: max_length - 1] + "…"


def _name(user) -> str:
    return (user.display_name or user.username) if user else "Someone"


def _chat_url(message) -> str:
    return f"/chat?channel={message.channel_id}"


def message_event(message: Message) -> dict:
    channel = message.channel
    sender = _name(message.author)
    title = sender if channel.channel_type == Channel.ChannelType.DIRECT_MESSAGE else f"{sender} in a group message"
    return {
        "id": f"message-{message.id}",
        "kind": "message",
        "tag": f"message-{message.id}",
        "title": title,
        "body": plain_text(message.body) or "Sent an attachment",
        "url": _chat_url(message),
        "channel_id": message.channel_id,
        "created_at": message.created_at.isoformat(),
    }


def notification_event(notification: Notification) -> dict:
    actor = _name(notification.actor)
    message = notification.target_message
    issue = notification.target_issue
    if message is not None:
        where = "" if message.channel.channel_type in DM_TYPES else f" in #{message.channel.name}"
        title = f"{actor} mentioned you{where}" if notification.verb == Notification.Verb.MENTIONED else f"{actor} {notification.get_verb_display()}"
        body = plain_text(message.body)
        url, tag, channel_id = _chat_url(message), f"message-{message.id}", message.channel_id
    else:
        title = f"{actor} {notification.get_verb_display()}"
        body = f"{issue.key}: {issue.summary}" if issue else ""
        url = f"/projects/{issue.project.key}/issues/{issue.key}" if issue else "/"
        tag, channel_id = f"notification-{notification.id}", None
    return {
        "id": f"notification-{notification.id}",
        "kind": "notification",
        "tag": tag,
        "title": title,
        "body": body,
        "url": url,
        "channel_id": channel_id,
        "created_at": notification.created_at.isoformat(),
    }


def _wants_desktop(user) -> bool:
    return bool(user and user.is_active and user.desktop_notifications)


def push_notification(notification: Notification) -> None:
    if _wants_desktop(notification.user):
        push_to_user(notification.user_id, notification_event(notification))


def push_direct_message(message: Message) -> None:
    """New message in a DM or group DM: tell every other member."""
    if message.is_system or message.channel.channel_type not in DM_TYPES:
        return
    event = None
    memberships = ChannelMembership.objects.filter(channel_id=message.channel_id).exclude(user_id=message.author_id)
    for membership in memberships.select_related("user"):
        if _wants_desktop(membership.user):
            event = event or message_event(message)
            push_to_user(membership.user_id, event)


def recent_events(user, since, limit: int = 20) -> list[dict]:
    """The user's inbox events after `since` (a datetime), oldest first."""
    notifications = (
        Notification.objects.filter(user=user, created_at__gt=since)
        .exclude(actor=user)
        .select_related("actor", "target_issue__project", "target_message__channel")
        .order_by("-created_at")[:limit]
    )
    dm_channels = ChannelMembership.objects.filter(user=user, channel__channel_type__in=DM_TYPES).values("channel_id")
    messages = (
        Message.objects.filter(channel_id__in=dm_channels, created_at__gt=since, is_system=False)
        .exclude(author=user)
        .select_related("author", "channel")
        .order_by("-created_at")[:limit]
    )
    events = [notification_event(n) for n in notifications] + [message_event(m) for m in messages]
    events.sort(key=lambda e: e["created_at"])
    return events[-limit:]

