from django.urls import path
from . import views

app_name = 'coursework'
urlpatterns = [
    path('', views.index, name='index'),
    path('oferta/<uuid:code>/<str:subject>/nova/', views.create, name='create'),
    path('<int:pk>/editar/', views.edit, name='edit'),
    path('<int:pk>/questoes/nova/', views.add_question, name='question-create'),
    path('<int:pk>/questoes/<int:question_pk>/remover/', views.remove_question, name='question-remove'),
    path('<int:pk>/acao/<str:operation>/', views.action, name='action'),
    path('<int:pk>/', views.student_detail, name='student-detail'),
]
