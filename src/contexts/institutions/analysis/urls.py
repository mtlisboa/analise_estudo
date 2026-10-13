from django.urls import path
from . import views
app_name='institution-analysis'
urlpatterns=[path('',views.index,name='index'),path('registrar/<slug:kind>/',views.record,name='record'),path('registrar/<slug:kind>/<int:pk>/',views.record,name='edit')]
