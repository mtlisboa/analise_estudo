from channels.auth import get_user
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from .models import Notification
from .services import group_name


class NotificationsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.group = None
        user = self.scope.get("user")
        if not user or not user.is_authenticated or not user.is_active:
            await self.close(code=4401)
            return
        self.user_id = user.pk
        self.group = group_name(user.pk)
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self.send_snapshot()

    async def disconnect(self, close_code):
        if self.group:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def valid_session(self):
        # Re-read the persisted session so logout in another tab revokes access.
        session = self.scope["session"]
        session._session_cache = await database_sync_to_async(session.load)()
        user = await get_user(self.scope)
        if not user.is_authenticated or not user.is_active or user.pk != self.user_id:
            await self.close(code=4401)
            return False
        return True

    async def receive(self, text_data=None, bytes_data=None, **kwargs):
        if bytes_data is not None or (text_data is not None and len(text_data) > 4096):
            await self.close(code=4400)
            return
        try:
            content = await self.decode_json(text_data or "null")
        except ValueError:
            await self.send_json({"type": "notifications.error", "message": "Mensagem inválida."})
            return
        await self.receive_json(content)

    async def receive_json(self, content, **kwargs):
        if not await self.valid_session():
            return
        if not isinstance(content, dict):
            await self.send_json({"type": "notifications.error", "message": "Mensagem inválida."})
            return
        action = content.get("type")
        if action == "notifications.sync":
            await self.send_snapshot()
        elif action in {"notifications.read", "notifications.read_all"}:
            notification_id = content.get("id")
            if action == "notifications.read" and (type(notification_id) is not int or not 0 < notification_id < 2**63):
                await self.send_json({"type": "notifications.error", "message": "ID inválido."})
                return
            await self.mark_read(notification_id if action == "notifications.read" else None)
            await self.channel_layer.group_send(self.group, {"type": "notifications.changed"})
        else:
            await self.send_json({"type": "notifications.error", "message": "Ação inválida."})

    async def notifications_changed(self, event):
        if await self.valid_session():
            await self.send_snapshot()

    async def send_snapshot(self):
        await self.send_json(await self.snapshot())

    @database_sync_to_async
    def snapshot(self):
        queryset = Notification.objects.filter(recipient_id=self.user_id)
        return {
            "type": "notifications.snapshot",
            "unread_count": queryset.filter(read_at__isnull=True).count(),
            "items": [
                {"id": n.pk, "title": n.title, "message": n.message,
                 "created_at": n.created_at.isoformat(), "is_read": n.read_at is not None}
                for n in queryset[:30]
            ],
        }

    @database_sync_to_async
    def mark_read(self, notification_id):
        queryset = Notification.objects.filter(recipient_id=self.user_id, read_at__isnull=True)
        if notification_id is not None:
            queryset = queryset.filter(pk=notification_id)
        queryset.update(read_at=timezone.now())
