from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any

from django.db.models import Q
from django.utils import timezone

from features.users_manager.models import (
    Classroom,
    ClassroomMembership,
    ClassroomTest,
    MembershipStatus,
    Organization,
    OrganizationMembership,
    SelfAssessment,
)


PERIODS = {
    "30": ("Últimos 30 dias", 30),
    "90": ("Últimos 90 dias", 90),
    "180": ("Últimos 6 meses", 180),
    "365": ("Últimos 12 meses", 365),
    "all": ("Todo o período", None),
}


def _display_name(user) -> str:
    return user.get_full_name().strip() or user.username


def _integer(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


def _score(assessment: SelfAssessment) -> int:
    return round(
        (
            assessment.focus
            + assessment.organization
            + assessment.comprehension
            + assessment.motivation
        )
        / 4
        * 20
    )


def build_dashboard(user, params) -> dict[str, Any]:
    organizations = list(
        Organization.objects.filter(
            Q(owner=user) | Q(memberships__user=user),
            is_active=True,
        )
        .distinct()
        .order_by("name")
    )
    organization_ids = {organization.pk for organization in organizations}

    selected_organization_id = _integer(params.get("organization"))
    if selected_organization_id not in organization_ids:
        selected_organization_id = None

    scoped_organizations = [
        organization
        for organization in organizations
        if selected_organization_id is None or organization.pk == selected_organization_id
    ]
    scoped_organization_ids = {organization.pk for organization in scoped_organizations}

    teacher_organization_ids = set(
        OrganizationMembership.objects.filter(
            organization_id__in=scoped_organization_ids,
            user=user,
            is_teacher=True,
        ).values_list("organization_id", flat=True)
    )
    teacher_organization_ids.update(
        organization.pk
        for organization in scoped_organizations
        if organization.owner_id == user.pk
    )

    classrooms = list(
        Classroom.objects.filter(organization_id__in=scoped_organization_ids, is_active=True)
        .select_related("organization")
        .order_by("organization__name", "name")
    )
    visible_classrooms = [
        classroom
        for classroom in classrooms
        if classroom.organization_id in teacher_organization_ids
        or ClassroomMembership.objects.filter(
            classroom=classroom,
            user=user,
            status=MembershipStatus.ACTIVE,
        ).exists()
    ]
    visible_classroom_ids = {classroom.pk for classroom in visible_classrooms}

    selected_classroom_id = _integer(params.get("classroom"))
    if selected_classroom_id not in visible_classroom_ids:
        selected_classroom_id = None
    scoped_classrooms = [
        classroom
        for classroom in visible_classrooms
        if selected_classroom_id is None or classroom.pk == selected_classroom_id
    ]
    scoped_classroom_ids = {classroom.pk for classroom in scoped_classrooms}

    organization_memberships = list(
        OrganizationMembership.objects.filter(organization_id__in=scoped_organization_ids)
        .select_related("organization", "user")
        .order_by("user__username")
    )
    allowed_student_ids: set[int] = set()
    allowed_teacher_ids: set[int] = set()
    student_organization_names: dict[int, set[str]] = defaultdict(set)
    for membership in organization_memberships:
        can_view_group = membership.organization_id in teacher_organization_ids
        if membership.is_student and (can_view_group or membership.user_id == user.pk):
            allowed_student_ids.add(membership.user_id)
            student_organization_names[membership.user_id].add(membership.organization.name)
        if membership.is_teacher and can_view_group:
            allowed_teacher_ids.add(membership.user_id)

    classroom_memberships = list(
        ClassroomMembership.objects.filter(
            classroom_id__in=scoped_classroom_ids,
            status=MembershipStatus.ACTIVE,
        ).select_related("classroom", "user")
    )
    classroom_student_ids = {
        membership.user_id
        for membership in classroom_memberships
        if membership.role == ClassroomMembership.Role.STUDENT
    }
    if selected_classroom_id:
        allowed_student_ids &= classroom_student_ids

    user_model = user.__class__
    students = list(user_model.objects.filter(pk__in=allowed_student_ids).order_by("first_name", "username"))
    student_ids = {student.pk for student in students}
    selected_student_id = _integer(params.get("student"))
    if selected_student_id not in student_ids:
        selected_student_id = None
    if selected_student_id:
        students = [student for student in students if student.pk == selected_student_id]
        student_ids = {selected_student_id}

    period = params.get("period", "90")
    if period not in PERIODS:
        period = "90"
    period_label, period_days = PERIODS[period]

    assessments = SelfAssessment.objects.filter(user_id__in=student_ids).select_related("user")
    if period_days:
        assessments = assessments.filter(created_at__gte=timezone.now() - timedelta(days=period_days))
    assessment_list = list(assessments.order_by("created_at"))

    assessments_by_user: dict[int, list[SelfAssessment]] = defaultdict(list)
    assessments_by_date: dict[str, list[SelfAssessment]] = defaultdict(list)
    for assessment in assessment_list:
        assessments_by_user[assessment.user_id].append(assessment)
        assessments_by_date[assessment.created_at.date().isoformat()].append(assessment)

    tests = ClassroomTest.objects.filter(classroom_id__in=scoped_classroom_ids)
    latest_by_user = {
        user_id: user_assessments[-1]
        for user_id, user_assessments in assessments_by_user.items()
    }
    user_by_id = {student.pk: student for student in students}

    classroom_labels = []
    classroom_students = []
    classroom_tests = []
    student_classroom_names: dict[int, set[str]] = defaultdict(set)
    for classroom in scoped_classrooms:
        memberships = [
            membership
            for membership in classroom_memberships
            if membership.classroom_id == classroom.pk
        ]
        classroom_labels.append(classroom.name)
        classroom_students.append(
            len(
                {
                    membership.user_id
                    for membership in memberships
                    if membership.role == ClassroomMembership.Role.STUDENT
                    and membership.user_id in student_ids
                }
            )
        )
        classroom_tests.append(tests.filter(classroom=classroom).count())
        for membership in memberships:
            if membership.role == ClassroomMembership.Role.STUDENT:
                student_classroom_names[membership.user_id].add(classroom.name)

    role_counts = {"Alunos": 0, "Professores": 0, "Ambos": 0}
    for membership in organization_memberships:
        if membership.organization_id not in teacher_organization_ids and membership.user_id != user.pk:
            continue
        if membership.is_teacher and membership.is_student:
            role_counts["Ambos"] += 1
        elif membership.is_teacher:
            role_counts["Professores"] += 1
        elif membership.is_student:
            role_counts["Alunos"] += 1

    line_dates = sorted(assessments_by_date)
    line_series = {"score": [], "focus": [], "comprehension": [], "motivation": []}
    for date in line_dates:
        records = assessments_by_date[date]
        line_series["score"].append(round(sum(_score(item) for item in records) / len(records), 1))
        line_series["focus"].append(round(sum(item.focus for item in records) / len(records), 2))
        line_series["comprehension"].append(
            round(sum(item.comprehension for item in records) / len(records), 2)
        )
        line_series["motivation"].append(
            round(sum(item.motivation for item in records) / len(records), 2)
        )

    latest_records = [latest_by_user[user_id] for user_id in sorted(latest_by_user)]
    labels = [_display_name(record.user) for record in latest_records]
    heatmap_rows = []
    ranking = []
    for student in students:
        user_assessments = assessments_by_user.get(student.pk, [])
        if not user_assessments:
            continue
        latest = user_assessments[-1]
        heatmap_rows.append(
            {
                "name": _display_name(student),
                "values": [latest.focus, latest.organization, latest.comprehension, latest.motivation],
            }
        )
        ranking.append(
            {
                "name": _display_name(student),
                "score": round(sum(_score(item) for item in user_assessments) / len(user_assessments)),
                "assessments": len(user_assessments),
                "latest": latest.created_at.strftime("%d/%m/%Y"),
                "classrooms": ", ".join(sorted(student_classroom_names.get(student.pk, set()))) or "—",
            }
        )
    ranking.sort(key=lambda item: (-item["score"], item["name"]))

    all_scores = [_score(assessment) for assessment in assessment_list]
    payload = {
        "empty": not bool(assessment_list),
        "periodLabel": period_label,
        "classrooms": {
            "labels": classroom_labels,
            "students": classroom_students,
            "tests": classroom_tests,
        },
        "roles": {"labels": list(role_counts), "values": list(role_counts.values())},
        "timeline": {"dates": line_dates, **line_series},
        "scatter2d": {
            "names": labels,
            "focus": [record.focus for record in latest_records],
            "comprehension": [record.comprehension for record in latest_records],
            "motivation": [record.motivation for record in latest_records],
            "score": [_score(record) for record in latest_records],
        },
        "scatter3d": {
            "names": labels,
            "focus": [record.focus for record in latest_records],
            "comprehension": [record.comprehension for record in latest_records],
            "motivation": [record.motivation for record in latest_records],
            "organization": [
                ", ".join(sorted(student_organization_names.get(record.user_id, set()))) or "Sem organização"
                for record in latest_records
            ],
        },
        "heatmap": {
            "x": ["Foco", "Organização", "Compreensão", "Motivação"],
            "y": [row["name"] for row in heatmap_rows],
            "z": [row["values"] for row in heatmap_rows],
        },
    }

    if selected_student_id:
        scope_title = _display_name(user_by_id[selected_student_id])
    elif selected_classroom_id:
        scope_title = next(item.name for item in scoped_classrooms if item.pk == selected_classroom_id)
    elif selected_organization_id:
        scope_title = next(item.name for item in scoped_organizations if item.pk == selected_organization_id)
    else:
        scope_title = "Visão geral"

    return {
        "organizations": organizations,
        "classrooms": visible_classrooms,
        "students": list(user_model.objects.filter(pk__in=allowed_student_ids).order_by("first_name", "username")),
        "periods": [(key, label) for key, (label, _) in PERIODS.items()],
        "filters": {
            "organization": selected_organization_id,
            "classroom": selected_classroom_id,
            "student": selected_student_id,
            "period": period,
        },
        "scope_title": scope_title,
        "metrics": {
            "organizations": len(scoped_organizations),
            "classrooms": len(scoped_classrooms),
            "students": len(student_ids),
            "teachers": len(allowed_teacher_ids),
            "tests": tests.count(),
            "assessment_average": round(sum(all_scores) / len(all_scores)) if all_scores else None,
        },
        "ranking": ranking,
        "analytics_payload": payload,
    }
