from django.contrib import admin

from .models import SavedAnalysis


@admin.register(SavedAnalysis)
class SavedAnalysisAdmin(admin.ModelAdmin):
    list_display = ("title", "scope_title", "period_label", "created_by", "created_at")
    list_filter = ("period_label", "created_at")
    search_fields = ("title", "scope_title", "created_by__username")
