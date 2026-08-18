from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("manager/", include("features.users_manager.urls")),
    path("", include("features.accounts.urls")),
]
