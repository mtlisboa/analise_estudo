from django.urls import path

from . import manager, views
from .roles import WORKSPACES

app_name = 'institutions'
urlpatterns = [
    path('', views.index, name='index'),
    path('gestor/academico/desempenho/', manager.module_view,
         {'module': 'desempenho'}, name='manager-performance'),
    path('gestor/<slug:module>/', manager.module_view, name='manager-module'),
]
urlpatterns += [
    path(f'{workspace.slug}/', views.workspace, {'slug': workspace.slug}, name=workspace.slug)
    for workspace in WORKSPACES.values()
]
