from django.db.models import Q

from features.users_manager.models import InstitutionalAccount
from features.notifications.services import notify_user
from .models import GuardianLink, FamilyRequest


def linked_children(account):
    return InstitutionalAccount.objects.filter(guardian_links__guardian=account,
        guardian_links__is_active=True, role='STUDENT', organization=account.organization,
        user__is_active=True).select_related('user').distinct()


def family_requests(account, staff=False):
    rows = FamilyRequest.objects.filter(organization=account.organization).select_related('guardian__user', 'student__user')
    if not staff:
        # Revocation immediately removes access to student-specific documents.
        rows = rows.filter(guardian=account).filter(Q(student__isnull=True) | Q(student__in=linked_children(account)))
    return rows


def notify_staff(organization, title, message):
    for account in organization.institutional_accounts.filter(role__in=['ADMIN', 'MANAGER', 'OPERATOR'], user__is_active=True).select_related('user'):
        notify_user(recipient=account.user, title=title, message=message)


def notify_event(event):
    links = GuardianLink.objects.filter(guardian__organization=event.organization,
        guardian__role='GUARDIAN', guardian__user__is_active=True, student__role='STUDENT',
        student__user__is_active=True, student__organization=event.organization, is_active=True)
    if event.classroom_id:
        links = links.filter(student__user__classroom_memberships__classroom=event.classroom,
            student__user__classroom_memberships__role='STUDENT',
            student__user__classroom_memberships__status='ACTIVE')
    user_ids = links.values_list('guardian__user_id', flat=True).distinct()
    from django.contrib.auth import get_user_model
    for user in get_user_model().objects.filter(pk__in=user_ids):
        notify_user(recipient=user, title='Evento da instituição', message=event.title)
