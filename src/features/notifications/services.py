import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import Notification

logger = logging.getLogger(__name__)


def group_name(user_id):
    return f"notifications.user.{user_id}"


def publish_change(user_id):
    # Persistence succeeds even if Redis is temporarily unavailable. Reconnect
    # fetches the inbox from the database, never from an ephemeral channel.
    try:
        async_to_sync(get_channel_layer().group_send)(
            group_name(user_id), {"type": "notifications.changed"}
        )
    except Exception:
        logger.exception("Could not publish notification update for user %s", user_id)


def notify_user(*, recipient, title, message=""):
    notification = Notification(recipient=recipient, title=title, message=message)
    notification.full_clean()
    notification.save()
    return notification
