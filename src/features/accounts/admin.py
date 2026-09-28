from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class ApplicationUserAdmin(UserAdmin):
    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj and hasattr(obj, 'institutional_account'):
            return tuple(fields) + ('username', 'email')
        return fields

    fieldsets = UserAdmin.fieldsets + (
        (
            "Lumini",
            {
                "fields": (
                    "system_role",
                    "onboarding_role",
                    "discovery_source",
                    "education_level",
                    "app_goal",
                    "app_goal_details",
                    "diagnostic_test_choice",
                    "onboarding_completed_at",
                )
            },
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (("Lumini", {"fields": ("system_role",)}),)
    list_display = UserAdmin.list_display + (
        "system_role",
        "onboarding_role",
        "onboarding_completed_at",
    )

