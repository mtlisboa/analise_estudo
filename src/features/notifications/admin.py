from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "created_at", "read_at")
    list_filter = ("read_at",)
    search_fields = ("title", "recipient__username")
    raw_id_fields = ("recipient",)
    readonly_fields = ("created_at", "read_at")

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        return (*fields, "recipient") if obj else fields
