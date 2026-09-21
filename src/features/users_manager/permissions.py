from django.db.models import Q, QuerySet

from .models import (
    Classroom,
    ClassroomMembership,
    MembershipStatus,
    Organization,
    OrganizationMembership,
)


def can_manage_organization(user, organization: Organization) -> bool:
    return organization.owner_id == user.pk


def has_teacher_role(user, organization: Organization) -> bool:
    return OrganizationMembership.objects.filter(
        organization=organization,
        user=user,
        is_teacher=True,
    ).exists()


def visible_classrooms(user, *, organization: Organization | None = None) -> QuerySet:
    queryset = Classroom.objects.filter(is_active=True)
    if organization is not None:
        queryset = queryset.filter(organization=organization)
    return queryset.filter(
        Q(organization__owner=user)
        | Q(
            memberships__user=user,
            memberships__status=MembershipStatus.ACTIVE,
        )
    ).distinct()


def accessible_group_ids(user, organization: Organization) -> set[int]:
    groups = list(
        organization.classroom_groups.filter(is_active=True).values(
            "id", "parent_id", "created_by_id"
        )
    )
    if can_manage_organization(user, organization):
        return {item["id"] for item in groups}

    parent_by_id = {item["id"]: item["parent_id"] for item in groups}
    visible_ids = set(
        ClassroomMembership.objects.filter(
            user=user,
            status=MembershipStatus.ACTIVE,
            classroom__organization=organization,
            classroom__is_active=True,
            classroom__group__is_active=True,
        ).values_list("classroom__group_id", flat=True)
    )
    if has_teacher_role(user, organization):
        visible_ids.update(
            item["id"] for item in groups if item["created_by_id"] == user.pk
        )

    pending = list(visible_ids)
    while pending:
        parent_id = parent_by_id.get(pending.pop())
        if parent_id and parent_id not in visible_ids:
            visible_ids.add(parent_id)
            pending.append(parent_id)
    return visible_ids


def can_view_classroom(user, classroom: Classroom) -> bool:
    return can_manage_organization(
        user, classroom.organization
    ) or ClassroomMembership.objects.filter(
        classroom=classroom,
        user=user,
        status=MembershipStatus.ACTIVE,
    ).exists()


def can_manage_classroom(user, classroom: Classroom) -> bool:
    if can_manage_organization(user, classroom.organization):
        return True
    return has_teacher_role(
        user, classroom.organization
    ) and ClassroomMembership.objects.filter(
        classroom=classroom,
        user=user,
        role=ClassroomMembership.Role.TEACHER,
        status=MembershipStatus.ACTIVE,
    ).exists()
