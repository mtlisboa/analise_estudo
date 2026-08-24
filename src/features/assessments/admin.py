from django.contrib import admin

from .models import Assessment, AssessmentTechnique, AssessmentType


@admin.register(AssessmentTechnique)
class AssessmentTechniqueAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


@admin.register(AssessmentType)
class AssessmentTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "default_technique")
    list_select_related = ("default_technique",)
    search_fields = ("name", "code")


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ("subject", "topic", "owner", "technique", "updated_at")
    list_filter = ("technique", "assessment_types")
    search_fields = ("subject", "topic", "owner__username", "owner__email")
    filter_horizontal = ("assessment_types",)
