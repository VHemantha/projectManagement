from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .broadcast import LIVE_GROUP


class LiveUpdatesConsumer(AsyncJsonWebsocketConsumer):
    """One app-wide socket per tab (ws/live/) that relays change notices from
    broadcast.notify() to the browser. Receive-only: clients never send on it."""

    async def connect(self):
        user = self.scope["user"]
        if not user or not user.is_authenticated:
            await self.close(code=4003)
            return
        await self.channel_layer.group_add(LIVE_GROUP, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(LIVE_GROUP, self.channel_name)

    async def live_change(self, event):
        await self.send_json({"type": "live.change", "kind": event["kind"], "project": event["project"], "key": event["key"]})
