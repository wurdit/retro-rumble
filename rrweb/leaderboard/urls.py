from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('update', views.update),
    path('refresh_games', views.refresh_games)
]