from django.urls import path
from . import views

app_name = 'paper-exams'
urlpatterns = [
    path('alunos/', views.students, name='students'),
    path('aplicacao/<uuid:request_token>/imprimir/', views.print_application, name='print-application'),
    path('fotografar/', views.scan, name='scan'),
    path('pagina/<int:page_pk>/', views.scan_evidence, name='scan-evidence'),
    path('avaliacao/<int:assessment_pk>/', views.index, name='index'),
    path('emissao/<uuid:pk>/', views.detail, name='detail'),
    path('emissao/<uuid:pk>/baixar/<str:kind>/', views.download, name='download'),
    path('resultado/<int:result_pk>/revisar/', views.review, name='review'),
    path('resultado/<int:result_pk>/imagem/', views.evidence, name='evidence'),
]
