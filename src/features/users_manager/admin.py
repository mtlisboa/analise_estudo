from django.contrib import admin
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    Classroom,
    ClassroomGroup,
    ClassroomMembership,
    ClassroomTest,
    EducationalRelationship,
    InstitutionDataExport,
    Organization,
    OrganizationMembership,
    School,
    SchoolApplication,
    SchoolVerificationDocument,
    SelfAssessment,
)
from .services import approve_school_application, reject_school_application


class SysadminOnlyAdminMixin:
    def _is_sysadmin(self, request):
        return request.user.is_authenticated and request.user.is_system_admin

    def has_module_permission(self, request):
        return self._is_sysadmin(request)

    def has_view_permission(self, request, obj=None):
        return self._is_sysadmin(request)

    def has_change_permission(self, request, obj=None):
        return self._is_sysadmin(request)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return self._is_sysadmin(request)


class SchoolVerificationDocumentInline(admin.TabularInline):
    model = SchoolVerificationDocument
    extra = 0
    fields = ("original_name", "protected_download", "uploaded_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="arquivo protegido")
    def protected_download(self, document):
        if not document.pk:
            return "—"
        url = reverse("users-manager:school-document-download", args=(document.pk,))
        return format_html('<a href="{}">Baixar documento</a>', url)


@admin.register(SchoolApplication)
class SchoolApplicationAdmin(SysadminOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("display_name", "school_type", "requester", "status", "created_at")
    list_filter = ("status", "school_type", "state")
    search_fields = ("display_name", "legal_name", "cnpj", "inep_code", "requester__email")
    readonly_fields = (
        "requester",
        "legal_name",
        "display_name",
        "school_type",
        "cnpj",
        "inep_code",
        "address",
        "city",
        "state",
        "status",
        "reviewed_by",
        "reviewed_at",
        "approved_school",
        "created_at",
        "updated_at",
    )
    fields = readonly_fields + ("review_notes",)
    inlines = (SchoolVerificationDocumentInline,)
    actions = ("approve_selected", "reject_selected")

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Aprovar solicitações selecionadas")
    def approve_selected(self, request, queryset):
        approved = 0
        for application in queryset:
            try:
                approve_school_application(application, request.user)
                approved += 1
            except ValidationError as exc:
                self.message_user(request, f"{application}: {'; '.join(exc.messages)}", level="error")
        if approved:
            self.message_user(request, f"{approved} solicitação(ões) aprovada(s).", level="success")

    @admin.action(description="Rejeitar solicitações selecionadas")
    def reject_selected(self, request, queryset):
        rejected = 0
        for application in queryset:
            try:
                reject_school_application(application, request.user)
                rejected += 1
            except ValidationError as exc:
                self.message_user(request, f"{application}: {'; '.join(exc.messages)}", level="error")
        if rejected:
            self.message_user(request, f"{rejected} solicitação(ões) rejeitada(s).", level="success")


@admin.register(School)
class SchoolAdmin(SysadminOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("display_name", "school_type", "city", "state", "approved_by", "approved_at")
    search_fields = ("display_name", "legal_name", "cnpj", "inep_code")
    readonly_fields = (
        "organization",
        "legal_name",
        "display_name",
        "school_type",
        "cnpj",
        "inep_code",
        "address",
        "city",
        "state",
        "approved_by",
        "approved_at",
        "created_at",
    )


@admin.register(InstitutionDataExport)
class InstitutionDataExportAdmin(SysadminOnlyAdminMixin, admin.ModelAdmin):
    list_display = (
        "organization_name",
        "organization_id_snapshot",
        "trigger",
        "row_count",
        "created_at",
        "protected_download",
    )
    list_filter = ("trigger", "created_at")
    search_fields = ("organization_name", "organization_id_snapshot")
    readonly_fields = (
        "organization_id_snapshot",
        "organization_name",
        "trigger",
        "row_count",
        "created_at",
        "protected_download",
    )
    fields = readonly_fields

    @admin.display(description="arquivo CSV")
    def protected_download(self, export):
        if not export.pk:
            return "—"
        url = reverse("users-manager:institution-export-download", args=(export.pk,))
        return format_html('<a href="{}">Baixar CSV</a>', url)

admin.site.register(EducationalRelationship)
admin.site.register(Classroom)
admin.site.register(ClassroomGroup)
admin.site.register(ClassroomMembership)
admin.site.register(SelfAssessment)
admin.site.register(Organization)
admin.site.register(OrganizationMembership)
admin.site.register(ClassroomTest)
