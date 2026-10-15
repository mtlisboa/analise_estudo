from django.urls import path
from . import views, pdf_modules, submissions, application

app_name = 'coursework'
urlpatterns = [
    path('pdf/<int:pk>/pagina/<int:page>/', pdf_modules.page_image, name='pdf-page'),
    path('oferta/<uuid:code>/<str:subject>/pdf/', pdf_modules.create, name='pdf-create'),
    path('pdf/<int:pk>/', pdf_modules.reader, name='pdf-reader'),
    path('pdf/<int:pk>/abrir/', pdf_modules.open_pdf, name='pdf-open'),
    path('pdf/<int:pk>/remover/', pdf_modules.remove, name='pdf-remove'),
    path('aplicar/<int:assessment_pk>/', application.apply, name='apply'),
    path('<int:pk>/entrega/<int:submission_pk>/', submissions.review, name='submission-review'),
    path('', views.index, name='index'),
    path('oferta/<uuid:code>/<str:subject>/nova/', views.create, name='create'),
    path('<int:pk>/editar/', views.edit, name='edit'),
    path('<int:pk>/questoes/nova/', views.add_question, name='question-create'),
    path('<int:pk>/questoes/<int:question_pk>/remover/', views.remove_question, name='question-remove'),
    path('<int:pk>/acao/<str:operation>/', views.action, name='action'),
    path('<int:pk>/', submissions.student_detail, name='student-detail'),
]
