"""Shared organization/classroom scope for navigation and analytics."""
from django.db.models import F, Q

from .models import Classroom, ClassroomMembership, MembershipStatus


def active_classroom_memberships():
    legacy_role = (
        Q(role=ClassroomMembership.Role.TEACHER, user__organization_memberships__is_teacher=True)
        | Q(role=ClassroomMembership.Role.STUDENT, user__organization_memberships__is_student=True)
    ) & Q(user__organization_memberships__organization_id=F("classroom__organization_id"))
    institutional_role = (
        Q(role=ClassroomMembership.Role.TEACHER, user__institutional_account__role="TEACHER")
        | Q(role=ClassroomMembership.Role.STUDENT, user__institutional_account__role="STUDENT")
    ) & Q(user__institutional_account__organization_id=F("classroom__organization_id"),
          user__is_active=True)
    return ClassroomMembership.objects.filter(
        legacy_role | institutional_role,
        status=MembershipStatus.ACTIVE,
        classroom__is_active=True,
        classroom__organization__is_active=True,
    ).distinct()



def managed_classrooms(user):
    teaching_ids = active_classroom_memberships().filter(
        user=user, role=ClassroomMembership.Role.TEACHER,
    ).values("classroom_id")
    return Classroom.objects.filter(
        is_active=True, organization__is_active=True,
    ).filter(
        Q(pk__in=teaching_ids)
        | Q(owner=user, organization__memberships__user=user,
            organization__memberships__is_teacher=True)
    ).distinct()


def visible_classrooms(user):
    member_ids = active_classroom_memberships().filter(user=user).values("classroom_id")
    return Classroom.objects.filter(
        is_active=True, organization__is_active=True,
    ).filter(
        Q(organization__owner=user)
        | Q(pk__in=managed_classrooms(user).values("pk"))
        | Q(pk__in=member_ids)
    ).distinct()
