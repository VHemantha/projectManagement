"""Inbox events behind desktop notifications: DMs, @mentions and bell notifications."""
from datetime import timedelta

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.chat.models import Channel, ChannelMembership, Message
from apps.live import broadcast
from apps.notifications import inbox
from apps.notifications.models import Notification
from apps.notifications.services import notify, notify_many
from apps.orgs.models import Organization

pytestmark = pytest.mark.django_db


def doc(*parts):
    return {"type": "doc", "content": [{"type": "paragraph", "content": list(parts)}]}


def text(t):
    return {"type": "text", "text": t}


@pytest.fixture
def pushed(monkeypatch):
    """Capture push_to_user calls instead of sending them."""
    calls = []
    monkeypatch.setattr(inbox, "push_to_user", lambda user_id, payload: calls.append((user_id, payload)))
    return calls


@pytest.fixture
def ann():
    return User.objects.create_user(username="ann", email="ann@example.com", password="x", display_name="Ann")


@pytest.fixture
def bob():
    return User.objects.create_user(username="bob", email="bob@example.com", password="x", display_name="Bob")


def dm(*users, kind=Channel.ChannelType.DIRECT_MESSAGE):
    channel = Channel.objects.create(organization=Organization.get_solo(), name="dm", channel_type=kind)
    for u in users:
        ChannelMembership.objects.create(channel=channel, user=u)
    return channel


def test_plain_text_reads_mentions_and_trims():
    body = doc(text("Hi "), {"type": "mention", "attrs": {"id": 1, "label": "Bob"}}, text(" please check"))
    assert inbox.plain_text(body) == "Hi @Bob please check"
    assert inbox.plain_text(doc(text("x" * 300)), max_length=10) == "x" * 9 + "…"


def test_a_dm_notifies_the_other_member_not_the_sender(ann, bob, pushed):
    channel = dm(ann, bob)
    message = Message.objects.create(channel=channel, author=ann, body=doc(text("Lunch?")))
    assert [uid for uid, _ in pushed] == [bob.id]
    event = pushed[0][1]
    assert event["title"] == "Ann"
    assert event["body"] == "Lunch?"
    assert event["url"] == f"/chat?channel={channel.id}"
    assert event["tag"] == f"message-{message.id}"


def test_group_dm_title_and_channel_messages_without_mentions(ann, bob, pushed):
    carl = User.objects.create_user(username="carl", email="carl@example.com", password="x")
    group = dm(ann, bob, carl, kind=Channel.ChannelType.GROUP_DM)
    Message.objects.create(channel=group, author=ann, body=doc(text("Hello all")))
    assert sorted(uid for uid, _ in pushed) == sorted([bob.id, carl.id])
    assert pushed[0][1]["title"] == "Ann in a group message"

    pushed.clear()
    topic = Channel.objects.create(organization=Organization.get_solo(), name="general", channel_type="topic")
    ChannelMembership.objects.create(channel=topic, user=bob)
    Message.objects.create(channel=topic, author=ann, body=doc(text("FYI")))
    assert pushed == []  # ordinary channel chatter isn't a desktop notification


def test_a_mention_notifies_with_the_same_tag_as_its_message(ann, bob, pushed):
    topic = Channel.objects.create(organization=Organization.get_solo(), name="payroll", channel_type="topic")
    message = Message.objects.create(channel=topic, author=ann, body=doc(text("Can you look?")))
    notify_many([bob, ann], Notification.Verb.MENTIONED, actor=ann, target_message=message)
    assert [uid for uid, _ in pushed] == [bob.id]  # never yourself
    event = pushed[0][1]
    assert event["title"] == "Ann mentioned you in #payroll"
    assert event["tag"] == f"message-{message.id}"


def test_bell_notifications_and_the_off_switch(ann, bob, pushed):
    notify(bob, Notification.Verb.ASSIGNED, actor=ann)
    assert pushed and pushed[0][1]["title"] == "Ann assigned you"
    pushed.clear()
    bob.desktop_notifications = False
    bob.save()
    notify(bob, Notification.Verb.ASSIGNED, actor=ann)
    Message.objects.create(channel=dm(ann, bob), author=ann, body=doc(text("hi")))
    assert pushed == []


def test_polling_fallback_returns_recent_events_but_not_your_own(ann, bob, pushed):
    channel = dm(ann, bob)
    since = timezone.now() - timedelta(seconds=1)
    Message.objects.create(channel=channel, author=ann, body=doc(text("Ping")))
    Message.objects.create(channel=channel, author=bob, body=doc(text("My own")))
    notify(bob, Notification.Verb.ASSIGNED, actor=ann)

    client = APIClient()
    client.force_authenticate(user=bob)
    data = client.get("/api/notifications/inbox/", {"since": since.isoformat()}).data
    assert sorted(e["kind"] for e in data["events"]) == ["message", "notification"]
    assert [e["body"] for e in data["events"] if e["kind"] == "message"] == ["Ping"]
    assert data["now"]
    later = client.get("/api/notifications/inbox/", {"since": data["now"]}).data
    assert later["events"] == []


def test_me_endpoint_exposes_the_setting(bob):
    client = APIClient()
    client.force_authenticate(user=bob)
    assert client.get("/api/auth/me/").data["desktop_notifications"] is True
    assert client.patch("/api/auth/me/", {"desktop_notifications": False}, format="json").status_code == 200
    bob.refresh_from_db()
    assert bob.desktop_notifications is False


@pytest.mark.django_db(transaction=True)
async def test_inbox_events_reach_only_their_recipients_socket():
    from trackflow.asgi import application

    ann = await database_sync_to_async(User.objects.create_user)(username="a2", email="a2@example.com", password="x")
    bob = await database_sync_to_async(User.objects.create_user)(username="b2", email="b2@example.com", password="x")
    ann_socket = WebsocketCommunicator(application, f"/ws/live/?token={RefreshToken.for_user(ann).access_token}")
    bob_socket = WebsocketCommunicator(application, f"/ws/live/?token={RefreshToken.for_user(bob).access_token}")
    assert (await ann_socket.connect())[0] and (await bob_socket.connect())[0]

    await database_sync_to_async(broadcast.push_to_user)(bob.id, {"kind": "message", "title": "Ann"})
    received = await bob_socket.receive_json_from(timeout=5)
    assert received == {"type": "inbox", "kind": "message", "title": "Ann"}
    assert await ann_socket.receive_nothing(timeout=0.3)
    await ann_socket.disconnect()
    await bob_socket.disconnect()
