"""Shared authorization for catalogs, images, and assessment assembly."""
from django.db.models import Q
from features.users_manager.models import InstitutionalAccount, Organization, OrganizationMembership
from .models import QuestionBankItem


def teaching_organizations(user):
    if not user or not user.is_authenticated or not user.is_active:
        return Organization.objects.none()
    account = InstitutionalAccount.objects.filter(user=user).first()
    if account:
        return Organization.objects.filter(pk=account.organization_id, is_active=True) if account.role == 'TEACHER' else Organization.objects.none()
    return Organization.objects.filter(is_active=True, memberships__user=user, memberships__is_teacher=True)


def managed_organizations(user):
    if not user or not user.is_authenticated or not user.is_active:
        return Organization.objects.none()
    return Organization.objects.filter(is_active=True, institutional_accounts__user=user,
                                       institutional_accounts__role__in=('ADMIN', 'MANAGER'))


def available_questions(user):
    if not user.is_authenticated or not user.is_active:
        return QuestionBankItem.objects.none()
    teaching = teaching_organizations(user)
    management = managed_organizations(user)
    local = Q(organization__in=teaching) | Q(organization__in=management)
    external = Q(external_visibility=QuestionBankItem.Visibility.EVERYONE)
    if teaching.exists() or management.exists():
        external |= Q(external_visibility=QuestionBankItem.Visibility.INSTITUTIONS)
    return QuestionBankItem.objects.filter(is_active=True).filter(
        Q(owner=user) | (Q(organization__is_active=True) & (local | external))
    ).distinct()
