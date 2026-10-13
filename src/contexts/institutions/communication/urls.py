from django.urls import path
from . import views
app_name='communication'
urlpatterns=[path('',views.index,name='index'),path('<int:pk>/',views.index,name='detail'),
    path('iniciar/<str:kind>/<int:pk>/',views.start,name='start'),
    path('<int:pk>/enviar/',views.send,name='send'),path('<int:pk>/novas/',views.updates,name='updates'),
    path('<int:pk>/ler/',views.read,name='read')]
