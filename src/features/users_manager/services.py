import csv
import io
import json

from django.core.files.base import ContentFile
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from .models import (
    Classroom,
    ClassroomMembership,
    ClassroomTest,
    InstitutionDataExport,
    Organization,
    School,
    SchoolApplication,
    SelfAssessment,
)


def _csv_row(record_type, record_id, parent_id, data):
    return (
        record_type,
        record_id,
        parent_id or "",
        json.dumps(data, ensure_ascii=False, default=str, separators=(",", ":")),
    )


def _institution_rows(organization):
    rows = [
        _csv_row(
            "organization",
            organization.pk,
            "",
            {
                "name": organization.name,
                "description": organization.description,
                "owner_id": organization.owner_id,
                "is_active": organization.is_active,
                "created_at": organization.created_at,
            },
        )
    ]
    school = School.objects.filter(organization=organization).first()
    if school:
        rows.append(
            _csv_row(
                "school",
                school.pk,
                organization.pk,
                {
                    "legal_name": school.legal_name,
                    "display_name": school.display_name,
                    "school_type": school.school_type,
                    "cnpj": school.cnpj,
                    "inep_code": school.inep_code,
                    "address": school.address,
                    "city": school.city,
                    "state": school.state,
                    "approved_by_id": school.approved_by_id,
                    "approved_at": school.approved_at,
                },
            )
        )
        application = SchoolApplication.objects.filter(approved_school=school).first()
        if application:
            rows.append(
                _csv_row(
                    "school_application",
                    application.pk,
                    school.pk,
                    {
                        "requester_id": application.requester_id,
                        "status": application.status,
                        "review_notes": application.review_notes,
                        "reviewed_by_id": application.reviewed_by_id,
                        "reviewed_at": application.reviewed_at,
                        "document_names": list(
                            application.documents.values_list("original_name", flat=True)
                        ),
                    },
                )
            )

    for membership in organization.memberships.select_related("user", "added_by"):
        rows.append(
            _csv_row(
                "organization_membership",
                membership.pk,
                organization.pk,
                {
                    "user_id": membership.user_id,
                    "username": membership.user.username,
                    "email": membership.user.email,
                    "is_teacher": membership.is_teacher,
                    "is_student": membership.is_student,
                    "added_by_id": membership.added_by_id,
                    "created_at": membership.created_at,
                },
            )
        )

    for group in organization.classroom_groups.all():
        rows.append(
            _csv_row(
                "classroom_group",
                group.pk,
                group.parent_id or organization.pk,
                {
                    "name": group.name,
                    "description": group.description,
                    "parent_group_id": group.parent_id,
                    "created_by_id": group.created_by_id,
                    "is_active": group.is_active,
                    "created_at": group.created_at,
                },
            )
        )

    classrooms = Classroom.objects.filter(organization=organization)
    classroom_ids = list(classrooms.values_list("pk", flat=True))
    for classroom in classrooms:
        rows.append(
            _csv_row(
                "classroom",
                classroom.pk,
                classroom.group_id,
                {
                    "name": classroom.name,
                    "description": classroom.description,
                    "letter": classroom.letter,
                    "shift": classroom.shift,
                    "owner_id": classroom.owner_id,
                    "is_active": classroom.is_active,
                    "created_at": classroom.created_at,
                },
            )
        )

    student_ids = set()
    for membership in ClassroomMembership.objects.filter(
        classroom_id__in=classroom_ids
    ).select_related("user"):
        student_ids.add(membership.user_id)
        rows.append(
            _csv_row(
                "classroom_membership",
                membership.pk,
                membership.classroom_id,
                {
                    "user_id": membership.user_id,
                    "username": membership.user.username,
                    "email": membership.user.email,
                    "role": membership.role,
                    "status": membership.status,
                    "invited_by_id": membership.invited_by_id,
                    "created_at": membership.created_at,
                },
            )
        )

    for classroom_test in ClassroomTest.objects.filter(classroom_id__in=classroom_ids):
        rows.append(
            _csv_row(
                "classroom_test",
                classroom_test.pk,
                classroom_test.classroom_id,
                {
                    "title": classroom_test.title,
                    "instructions": classroom_test.instructions,
                    "max_score": classroom_test.max_score,
                    "created_by_id": classroom_test.created_by_id,
                    "is_published": classroom_test.is_published,
                    "created_at": classroom_test.created_at,
                },
            )
        )

    for assessment in SelfAssessment.objects.filter(user_id__in=student_ids):
        rows.append(
            _csv_row(
                "self_assessment",
                assessment.pk,
                assessment.user_id,
                {
                    "focus": assessment.focus,
                    "organization": assessment.organization,
                    "comprehension": assessment.comprehension,
                    "motivation": assessment.motivation,
                    "notes": assessment.notes,
                    "created_at": assessment.created_at,
                },
            )
        )

    from features.analytics_dashboard.models import SavedAnalysis

    for analysis in SavedAnalysis.objects.filter(filters__organization=str(organization.pk)):
        rows.append(
            _csv_row(
                "saved_analysis",
                analysis.pk,
                organization.pk,
                {
                    "title": analysis.title,
                    "scope_title": analysis.scope_title,
                    "period_label": analysis.period_label,
                    "created_by_id": analysis.created_by_id,
                    "filters": analysis.filters,
                    "snapshot": analysis.snapshot,
                    "created_at": analysis.created_at,
                },
            )
        )
    return rows


def create_institution_export(organization, *, trigger):
    rows = _institution_rows(organization)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("record_type", "record_id", "parent_id", "data_json"))
    writer.writerows(rows)
    timestamp = timezone.now().strftime("%Y%m%d-%H%M%S-%f")
    filename = f"{slugify(organization.name) or 'instituicao'}-{organization.pk}-{timestamp}.csv"
    export = InstitutionDataExport(
        organization_id_snapshot=organization.pk,
        organization_name=organization.name,
        trigger=trigger,
        row_count=len(rows),
    )
    export.file.save(
        filename,
        ContentFile(output.getvalue().encode("utf-8-sig")),
        save=False,
    )
    export.save()
    return export


def _require_sysadmin(user) -> None:
    if not user or not user.is_authenticated or not user.is_system_admin:
        raise PermissionDenied("Somente o administrador de sistema pode revisar escolas.")


@transaction.atomic
def approve_school_application(application, reviewer) -> School:
    _require_sysadmin(reviewer)
    application = SchoolApplication.objects.select_for_update().get(pk=application.pk)
    if application.status == SchoolApplication.Status.APPROVED:
        return application.approved_school
    if application.status != SchoolApplication.Status.PENDING:
        raise ValidationError("Somente solicitações pendentes podem ser aprovadas.")
    if not application.documents.exists():
        raise ValidationError("A solicitação precisa ter ao menos um documento comprobatório.")

    organization = Organization.objects.create(
        name=application.display_name,
        description=(
            f"Escola {application.get_school_type_display().lower()} credenciada na plataforma."
        ),
        owner=application.requester,
    )
    school = School.objects.create(
        organization=organization,
        legal_name=application.legal_name,
        display_name=application.display_name,
        school_type=application.school_type,
        cnpj=application.cnpj or None,
        inep_code=application.inep_code or None,
        address=application.address,
        city=application.city,
        state=application.state,
        approved_by=reviewer,
    )
    application.status = SchoolApplication.Status.APPROVED
    application.reviewed_by = reviewer
    application.reviewed_at = timezone.now()
    application.approved_school = school
    application.save(
        update_fields=(
            "status",
            "reviewed_by",
            "reviewed_at",
            "approved_school",
            "updated_at",
        )
    )
    return school


@transaction.atomic
def reject_school_application(application, reviewer) -> SchoolApplication:
    _require_sysadmin(reviewer)
    application = SchoolApplication.objects.select_for_update().get(pk=application.pk)
    if application.status != SchoolApplication.Status.PENDING:
        raise ValidationError("Somente solicitações pendentes podem ser rejeitadas.")
    application.status = SchoolApplication.Status.REJECTED
    application.reviewed_by = reviewer
    application.reviewed_at = timezone.now()
    application.save(
        update_fields=("status", "reviewed_by", "reviewed_at", "updated_at")
    )
    return application
