from django.urls import path

from . import views
from .roles import WORKSPACES

app_name = 'institutions'
urlpatterns = [path('', views.index, name='index')]
urlpatterns += [
    path(f'{workspace.slug}/', views.workspace, {'slug': workspace.slug}, name=workspace.slug)
    for workspace in WORKSPACES.values()
]
