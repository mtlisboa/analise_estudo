import logging
from uuid import uuid4

from django.db import transaction
from .models import User

logger = logging.getLogger(__name__)


def delete_avatar(storage, name):
    try:
        storage.delete(name)
    except OSError:
        logger.exception("Could not remove replaced avatar")


def change_avatar(user_id, photo=None):
    storage = User._meta.get_field("avatar").storage
    new_name = storage.save(f"avatars/{uuid4().hex}.jpg", photo) if photo else ""
    try:
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=user_id)
            old_name = user.avatar.name
            user.avatar = new_name
            user.save(update_fields=["avatar"])
            if old_name:
                transaction.on_commit(lambda: delete_avatar(storage, old_name))
    except Exception:
        if new_name:
            delete_avatar(storage, new_name)
        raise
