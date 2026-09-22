from django.contrib import admin

from .models import Assessment, AssessmentTechnique, AssessmentType, Question, QuestionBankItem


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
    list_display = (
        "subject",
        "topic",
        "owner",
        "assembly_method",
        "assembly_status",
        "updated_at",
    )
    list_filter = ("assembly_method", "assembly_status", "technique", "assessment_types")
    search_fields = ("subject", "topic", "owner__username", "owner__email")
    filter_horizontal = ("assessment_types",)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("assessment", "order", "question_type", "points", "updated_at")
    list_filter = ("question_type",)
    search_fields = ("statement", "assessment__subject", "assessment__topic")
    list_select_related = ("assessment",)


@admin.register(QuestionBankItem)
class QuestionBankItemAdmin(admin.ModelAdmin):
    list_display = ("subject", "topic", "question_type", "creation_method", "owner", "updated_at")
    list_filter = ("question_type", "creation_method", "is_active")
    search_fields = ("subject", "topic", "statement", "owner__username", "owner__email")
