from django.urls import path, include

from . import manager, student, views, classrooms, teacher_analysis, teacher_administration
from .roles import WORKSPACES

app_name = 'institutions'
urlpatterns = [
    path('analise/', include('contexts.institutions.analysis.urls')),
    path('professor/administracao/<slug:section>/', teacher_administration.index, name='teacher-administration-section'),
    path('professor/administracao/', teacher_administration.index, name='teacher-administration'),
    path('professor/analise/', teacher_analysis.index, name='teacher-analysis'),
    path('turmas/', classrooms.index, name='classrooms'),
    path('turmas/<int:pk>/', classrooms.detail, name='classroom'),
    path('aluno/disciplinas/', student.disciplines, name='student-disciplines'),
    path('aluno/disciplinas/<uuid:code>/<str:subject>/', student.disciplines, name='student-discipline'),
    path('', views.index, name='index'),
    path('gestor/academico/desempenho/', manager.module_view,
         {'module': 'desempenho'}, name='manager-performance'),
    path('gestor/<slug:module>/', manager.module_view, name='manager-module'),
]
urlpatterns += [
    path(f'{workspace.slug}/', views.workspace, {'slug': workspace.slug}, name=workspace.slug)
    for workspace in WORKSPACES.values()
]
