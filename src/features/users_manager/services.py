from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Organization, School, SchoolApplication


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
