from django.urls import path

from . import views

app_name = "regression"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("neighborhoods/", views.neighborhoods, name="neighborhoods"),
    path("neighborhoods/run-all/", views.run_all_neighborhoods, name="run_all_neighborhoods"),
    path("neighborhoods/run-one/", views.run_one_neighborhood, name="run_one_neighborhood"),
]
