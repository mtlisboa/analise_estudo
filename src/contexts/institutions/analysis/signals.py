from functools import partial

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from features.paper_exams.models import SheetResult

from ..coursework.models import Submission
from ..planning.models import Offer
from .alerts import sync_offer_alerts
from .models import Attendance, Evidence, OfferContext


@receiver(post_save, sender=Attendance)
@receiver(post_delete, sender=Attendance)
@receiver(post_save, sender=Evidence)
@receiver(post_delete, sender=Evidence)
@receiver(post_save, sender=OfferContext)
@receiver(post_delete, sender=OfferContext)
def schedule_offer_alerts(sender, instance, using, raw=False, **kwargs):
    if not raw:
        transaction.on_commit(partial(sync_offer_alerts, instance.offer_id), using=using, robust=True)


@receiver(post_save, sender=SheetResult)
def schedule_paper_alerts(sender, instance, using, raw=False, **kwargs):
    if not raw:
        offer_id = Offer.objects.filter(classroom_id=instance.sheet.run.classroom_id).values_list('pk', flat=True).first()
        if offer_id:
            transaction.on_commit(partial(sync_offer_alerts, offer_id), using=using, robust=True)


@receiver(post_save, sender=Submission)
def schedule_online_alerts(sender, instance, using, raw=False, **kwargs):
    if not raw and instance.score is not None:
        transaction.on_commit(
            partial(sync_offer_alerts, instance.publication.offer_id), using=using, robust=True,
        )
