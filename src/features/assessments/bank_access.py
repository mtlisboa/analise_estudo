"""The same visibility rules apply to browsing and assessment assembly."""
from django.db.models import Q
from features.users_manager.models import InstitutionalAccount, OrganizationMembership
from .models import QuestionBankItem


def available_questions(user):
    if not user.is_active:
        return QuestionBankItem.objects.none()
    account = InstitutionalAccount.objects.filter(user=user).first()
    if account:
        organization_ids = [account.organization_id] if account.role == 'TEACHER' else []
    else:
        organization_ids = OrganizationMembership.objects.filter(
            user=user, is_teacher=True, organization__is_active=True,
        ).values_list('organization_id', flat=True)
    return QuestionBankItem.objects.filter(is_active=True).filter(
        Q(owner=user, organization__isnull=True)
        | Q(organization_id__in=organization_ids, organization__is_active=True)
    )
