from django.contrib import admin
from django.db import transaction
from urllib.parse import urlencode
from .institutional_forms import SchoolRegistrationAdminForm
from .models import InstitutionalContact, generate_institutional_code
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
        "institutional_code",
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


    list_filter = ('registration_enabled', 'school_type', 'state')
    actions = ('regenerate_codes',)

    def has_add_permission(self, request):
        return self._is_sysadmin(request)

    def get_fields(self, request, obj=None):
        if obj is None:
            return ('contact', 'organization_owner', 'legal_name', 'display_name', 'school_type',
                    'cnpj', 'inep_code', 'address', 'city', 'state', 'registration_enabled')
        return self.readonly_fields + ('registration_enabled',)

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields if obj else ()

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs['form'] = SchoolRegistrationAdminForm
        return super().get_form(request, obj, **kwargs)

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if not self._is_sysadmin(request):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        if not change:
            obj.organization = Organization.objects.create(name=obj.display_name[:120],
                description=f'Instituição cadastrada pela administração: {obj.display_name}',
                owner=form.cleaned_data.get('organization_owner') or request.user)
            obj.approved_by = request.user
        super().save_model(request, obj, form, change)
        if not change and form.cleaned_data.get('contact'):
            contact = form.cleaned_data['contact']
            contact.school = obj
            contact.status = InstitutionalContact.Status.COMPLETED
            contact.save(update_fields=['school', 'status'])

    @admin.action(description='Gerar novos códigos institucionais (invalida os anteriores)')
    def regenerate_codes(self, request, queryset):
        if not self._is_sysadmin(request):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        with transaction.atomic():
            for school in queryset.select_for_update():
                school.institutional_code = generate_institutional_code()
                school.save(update_fields=['institutional_code'])
                self.log_change(request, school, 'Código institucional substituído.')
        self.message_user(request, 'Novos códigos gerados. Consulte cada instituição; os vínculos existentes foram mantidos.')


@admin.register(InstitutionalContact)
class InstitutionalContactAdmin(SysadminOnlyAdminMixin, admin.ModelAdmin):
    list_display = ('institution_name', 'contact_name', 'email', 'phone', 'status', 'created_at')
    list_filter = ('status', 'state', 'created_at')
    search_fields = ('institution_name', 'contact_name', 'email', 'phone')
    readonly_fields = ('institution_name', 'contact_name', 'email', 'phone', 'city', 'state', 'message', 'created_at', 'register_institution')
    fields = readonly_fields + ('status', 'school', 'internal_notes')

    @admin.display(description='Cadastro institucional')
    def register_institution(self, contact):
        if contact.school_id:
            return format_html('<a href="{}">Abrir instituição e consultar código</a>', reverse('admin:users_manager_school_change', args=[contact.school_id]))
        query = urlencode({'contact': contact.pk, 'display_name': contact.institution_name,
                           'legal_name': contact.institution_name, 'city': contact.city, 'state': contact.state})
        return format_html('<a href="{}?{}">Cadastrar instituição a partir deste contato</a>', reverse('admin:users_manager_school_add'), query)


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

