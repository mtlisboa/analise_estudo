from django.urls import path
from . import views

app_name = 'family'
urlpatterns = [
    path('', views.portal, name='index'),
    path('atendimento/', views.desk, name='desk'),
    path('vinculos/novo/', views.edit_link, name='link-create'),
    path('vinculos/<int:pk>/', views.edit_link, name='link-edit'),
    path('eventos/novo/', views.edit_event, name='event-create'),
    path('eventos/<int:pk>/editar/', views.edit_event, name='event-edit'),
    path('solicitacoes/<int:pk>/', views.request_detail, name='request'),
    path('documentos/<int:pk>/baixar/', views.attachment, name='attachment'),
    path('notificacoes/<int:pk>/ler/', views.read_notification, name='notification-read'),
    path('<slug:module>/', views.portal, name='module'),
]
