from functools import partial

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Notification
from .services import publish_change


@receiver(post_save, sender=Notification)
@receiver(post_delete, sender=Notification)
def notification_changed(sender, instance, using, **kwargs):
    transaction.on_commit(partial(publish_change, instance.recipient_id), using=using)
