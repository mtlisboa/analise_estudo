from django.core.management.base import BaseCommand

from contexts.institutions.analysis.alerts import sync_offer_alerts
from contexts.institutions.analysis.models import OfferContext


class Command(BaseCommand):
    help = 'Reavalia alertas pedagógicos nas ofertas que já têm regras configuradas.'

    def handle(self, *args, **options):
        for offer_id in OfferContext.objects.values_list('offer_id', flat=True).iterator():
            sync_offer_alerts(offer_id)
