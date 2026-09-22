from unittest.mock import patch

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from config.asgi import application
from .models import Notification
from .services import notify_user


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class NotificationTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="recipient", onboarding_completed_at=timezone.now())
        self.other = get_user_model().objects.create_user(username="other")
        self.client.force_login(self.user)
        self.cookie = f"{settings.SESSION_COOKIE_NAME}={self.client.cookies[settings.SESSION_COOKIE_NAME].value}".encode()

    def communicator(self, cookie=None, origin=b"http://localhost"):
        headers = [(b"origin", origin), (b"host", b"localhost")]
        if cookie:
            headers.append((b"cookie", cookie))
        return WebsocketCommunicator(application, "/ws/notifications/", headers=headers)

    async def test_anonymous_and_foreign_origin_rejected(self):
        for cookie, origin in [(None, b"http://localhost"), (self.cookie, b"https://evil.example")]:
            socket = self.communicator(cookie, origin)
            connected, _ = await socket.connect()
            self.assertFalse(connected)
            await socket.disconnect()

    async def test_live_delivery_is_private_and_reconnect_restores_inbox(self):
        socket = self.communicator(self.cookie)
        self.assertTrue((await socket.connect())[0])
        self.assertEqual((await socket.receive_json_from())["unread_count"], 0)
        await sync_to_async(notify_user)(recipient=self.other, title="Private")
        self.assertTrue(await socket.receive_nothing(timeout=.1))
        note = await sync_to_async(notify_user)(recipient=self.user, title="Nova avaliação", message="Já disponível")
        payload = await socket.receive_json_from()
        self.assertEqual(payload["unread_count"], 1)
        self.assertEqual(payload["items"][0]["id"], note.pk)
        await socket.disconnect()
        socket = self.communicator(self.cookie)
        self.assertTrue((await socket.connect())[0])
        self.assertEqual((await socket.receive_json_from())["items"][0]["title"], "Nova avaliação")
        await socket.disconnect()

    async def test_read_is_scoped_and_synchronizes_tabs(self):
        own = await sync_to_async(notify_user)(recipient=self.user, title="Own")
        foreign = await sync_to_async(notify_user)(recipient=self.other, title="Foreign")
        sockets = [self.communicator(self.cookie), self.communicator(self.cookie)]
        for socket in sockets:
            self.assertTrue((await socket.connect())[0])
            await socket.receive_json_from()
        await sockets[0].send_json_to({"type": "notifications.read", "id": foreign.pk})
        for socket in sockets:
            self.assertEqual((await socket.receive_json_from())["unread_count"], 1)
        await sockets[0].send_json_to({"type": "notifications.read", "id": own.pk})
        for socket in sockets:
            self.assertEqual((await socket.receive_json_from())["unread_count"], 0)
            await socket.disconnect()
        await foreign.arefresh_from_db()
        self.assertIsNone(foreign.read_at)

    async def test_read_all_is_private(self):
        await sync_to_async(notify_user)(recipient=self.user, title="Own")
        foreign = await sync_to_async(notify_user)(recipient=self.other, title="Foreign")
        socket = self.communicator(self.cookie)
        await socket.connect()
        await socket.receive_json_from()
        await socket.send_json_to({"type": "notifications.read_all"})
        self.assertEqual((await socket.receive_json_from())["unread_count"], 0)
        await foreign.arefresh_from_db()
        self.assertIsNone(foreign.read_at)
        await socket.disconnect()

    async def test_logout_revokes_open_socket(self):
        socket = self.communicator(self.cookie)
        await socket.connect()
        await socket.receive_json_from()
        await sync_to_async(self.client.logout)()
        await socket.send_json_to({"type": "notifications.sync"})
        self.assertEqual((await socket.receive_output())["code"], 4401)
        await socket.disconnect()

    async def test_malformed_messages_do_not_break_socket(self):
        socket = self.communicator(self.cookie)
        await socket.connect()
        await socket.receive_json_from()
        for text in ['{', '[]', '{"type":"notifications.read","id":true}', '{"type":"unexpected"}']:
            await socket.send_to(text_data=text)
            self.assertEqual((await socket.receive_json_from())["type"], "notifications.error")
        await socket.send_json_to({"type": "notifications.sync"})
        self.assertEqual((await socket.receive_json_from())["type"], "notifications.snapshot")
        await socket.disconnect()

    def test_publish_only_after_commit_and_not_after_rollback(self):
        with patch("features.notifications.signals.publish_change") as publish:
            with transaction.atomic():
                notify_user(recipient=self.user, title="Committed")
                publish.assert_not_called()
            publish.assert_called_once_with(self.user.pk)
            publish.reset_mock()
            try:
                with transaction.atomic():
                    notify_user(recipient=self.user, title="Rollback")
                    raise ValueError("abort")
            except ValueError:
                pass
            publish.assert_not_called()
            self.assertFalse(Notification.objects.filter(title="Rollback").exists())

    def test_bell_only_in_operational_layout(self):
        self.assertContains(self.client.get(reverse("accounts:dashboard")), 'id="notification-bell"')
        self.assertNotContains(self.client.get(reverse("accounts:landing")), 'id="notification-bell"')
        self.client.logout()
        self.assertNotContains(self.client.get(reverse("accounts:login")), 'id="notification-bell"')
