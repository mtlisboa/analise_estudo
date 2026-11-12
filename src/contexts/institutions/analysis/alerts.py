from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.urls import reverse

from features.notifications.services import notify_user
from features.users_manager.models import InstitutionalAccount

from ..planning.models import Offer
from .models import ActiveAlert, OfferContext
from .scope import Scope
from .services import build


def sync_offer_alerts(offer_id):
    if not OfferContext.objects.filter(offer_id=offer_id).exists() and not ActiveAlert.objects.filter(offer_id=offer_id).exists():
        return

    with transaction.atomic():
        offer = Offer.objects.select_for_update().select_related('period').filter(pk=offer_id).first()
        if offer is None:
            return
        active = ActiveAlert.objects.filter(offer=offer)
        accounts = InstitutionalAccount.objects.filter(
            organization_id=offer.period.organization_id,
            role__in=('ADMIN', 'MANAGER', 'TEACHER'),
            user__is_active=True,
        ).select_related('user')
        active.exclude(recipient__in=accounts).delete()
        for account in accounts:
            current = active.filter(recipient=account)
            try:
                scope = Scope(account.user)
            except PermissionDenied:
                current.delete()
                continue
            if scope.account.pk != account.pk or not scope.offers.filter(pk=offer.pk).exists():
                current.delete()
                continue

            alerts = build(scope, {'offer': offer})['alerts']
            current.exclude(key__in=[alert['key'] for alert in alerts]).delete()
            for alert in alerts:
                _, created = current.get_or_create(recipient=account, offer=offer, key=alert['key'])
                if created:
                    route = 'institutions:manager-performance' if scope.manager else 'institutions:teacher-analysis'
                    notify_user(
                        recipient=account.user,
                        title='Alerta pedagógico',
                        message='Há um novo alerta pedagógico em uma oferta sob seu acompanhamento.',
                        target_url=f'{reverse(route)}?section=alerts&offer={offer.pk}#alertas-pedagogicos',
                    )
