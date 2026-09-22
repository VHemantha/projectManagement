from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.notifications.models import Notification
from apps.notifications.services import notify_many

from .models import Channel, ChannelMembership, Message, MessageMention
from .permissions import ensure_channel_membership, user_can_access_channel
from .serializers import MessageSerializer


def group_name(channel_id) -> str:
    return f"chat_{channel_id}"


PRESENCE_GROUP = "presence"

# Module-level, in-memory, single-process presence registry (consistent with this project's
# InMemoryChannelLayer — Redis was explicitly ruled out, so this can't be a distributed store).
# Keyed by user id -> open-connection count, since one user can have multiple tabs open; a
# user only flips to "offline" once their LAST connection closes.
ONLINE_USER_CONNECTIONS: dict[int, int] = {}


class PresenceConsumer(AsyncJsonWebsocketConsumer):
    """A single always-on socket per browser tab (mounted app-wide, not per chat channel) that
    reports "does this user currently have the app open" — deliberately two-state
    (online/offline), not three-state with "away", since there's no idle-detection
    infrastructure elsewhere in the app to drive a meaningful away state yet."""

    async def connect(self):
        user = self.scope["user"]
        if not user or not user.is_authenticated:
            await self.close(code=4003)
            return
        self.user_id = user.id
        await self.channel_layer.group_add(PRESENCE_GROUP, self.channel_name)
        await self.accept()

        was_offline = ONLINE_USER_CONNECTIONS.get(self.user_id, 0) == 0
        ONLINE_USER_CONNECTIONS[self.user_id] = ONLINE_USER_CONNECTIONS.get(self.user_id, 0) + 1
        if was_offline:
            await self.channel_layer.group_send(
                PRESENCE_GROUP, {"type": "presence.update", "user_id": self.user_id, "online": True}
            )
        await self.send_json({"type": "presence.snapshot", "user_ids": list(ONLINE_USER_CONNECTIONS.keys())})

    async def disconnect(self, close_code):
        if not hasattr(self, "user_id"):
            return
        await self.channel_layer.group_discard(PRESENCE_GROUP, self.channel_name)
        remaining = ONLINE_USER_CONNECTIONS.get(self.user_id, 1) - 1
        if remaining <= 0:
            ONLINE_USER_CONNECTIONS.pop(self.user_id, None)
            await self.channel_layer.group_send(
                PRESENCE_GROUP, {"type": "presence.update", "user_id": self.user_id, "online": False}
            )
        else:
            ONLINE_USER_CONNECTIONS[self.user_id] = remaining

    async def presence_update(self, event):
        # Same self-filtering as ChatConsumer.chat_typing — a user doesn't need to be told
        # about their own connect/disconnect, and without this they'd see their own "online"
        # echo arrive before the snapshot (group_add happens before the broadcast, so the
        # newly-joined socket is already a member of the group it's about to broadcast to).
        if event["user_id"] == self.user_id:
            return
        await self.send_json({"type": "presence.update", "user_id": event["user_id"], "online": event["online"]})


class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.channel_id = self.scope["url_route"]["kwargs"]["channel_id"]
        user = self.scope["user"]

        channel = await self._get_channel()
        if channel is None or not await database_sync_to_async(user_can_access_channel)(user, channel):
            await self.close(code=4003)
            return

        await database_sync_to_async(ensure_channel_membership)(user, channel)
        self.group = group_name(self.channel_id)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        msg_type = content.get("type")
        if msg_type == "message.send":
            await self._handle_send(content)
        elif msg_type == "typing":
            await self._handle_typing()

    async def _handle_send(self, content):
        user = self.scope["user"]
        body = content.get("body")
        parent_message_id = content.get("parent_message_id")
        mentioned_user_ids = content.get("mentioned_user_ids") or []
        if not body:
            return

        message_data = await self._create_message(user, body, parent_message_id, mentioned_user_ids)
        await self.channel_layer.group_send(
            self.group, {"type": "chat.message", "message": message_data}
        )

    async def _handle_typing(self):
        user = self.scope["user"]
        await self.channel_layer.group_send(
            self.group,
            {
                "type": "chat.typing",
                "user_id": user.id,
                "display_name": user.display_name,
            },
        )

    # -- group event handlers (dispatched by channel_layer.group_send's "type") --

    async def chat_message(self, event):
        await self.send_json({"type": "message.new", "message": event["message"]})

    async def chat_typing(self, event):
        if event["user_id"] == self.scope["user"].id:
            return
        await self.send_json(
            {"type": "typing", "user_id": event["user_id"], "display_name": event["display_name"]}
        )

    # -- DB helpers --

    @database_sync_to_async
    def _get_channel(self):
        return Channel.objects.filter(id=self.channel_id).first()

    @database_sync_to_async
    def _create_message(self, user, body, parent_message_id, mentioned_user_ids):
        message = Message.objects.create(
            channel_id=self.channel_id,
            author=user,
            body=body,
            parent_message_id=parent_message_id,
        )
        if mentioned_user_ids:
            from apps.accounts.models import User

            mentioned_users = list(User.objects.filter(id__in=mentioned_user_ids))
            MessageMention.objects.bulk_create(
                [MessageMention(message=message, mentioned_user=u) for u in mentioned_users]
            )
            notify_many(
                mentioned_users, Notification.Verb.MENTIONED, actor=user, target_message=message
            )
        return MessageSerializer(message).data
