from django.urls import path

from . import views

app_name = "regression"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("neighborhoods/", views.neighborhoods, name="neighborhoods"),
]
