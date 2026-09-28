"""Institutional membership is contextual; never grant system or manager roles."""
from django.core.exceptions import ValidationError
from django.db import transaction

from features.users_manager.models import School, OrganizationMembership

ROLES = [('STUDENT', 'Estudante'), ('TEACHER', 'Professor')]


def normalize_code(value):
    return value.strip().upper()


def find_school(code, *, lock=False):
    queryset = School.objects.select_related('organization')
    if lock:
        queryset = queryset.select_for_update()
    school = queryset.filter(institutional_code=normalize_code(code), registration_enabled=True,
                             organization__is_active=True).first()
    if school is None:
        raise ValidationError('Código institucional inválido ou indisponível. Confira com sua instituição.')
    return school


@transaction.atomic
def attach_membership(user, code, role):
    if role not in dict(ROLES):
        raise ValidationError('Selecione estudante ou professor.')
    school = find_school(code, lock=True)
    membership, _ = OrganizationMembership.objects.get_or_create(
        organization=school.organization, user=user,
        defaults={'is_student': role == 'STUDENT', 'is_teacher': role == 'TEACHER',
                  'added_by': school.approved_by})
    field = 'is_student' if role == 'STUDENT' else 'is_teacher'
    if not getattr(membership, field):
        setattr(membership, field, True)
        membership.save(update_fields=[field])
    return school
