from django.urls import path

from . import views

app_name = "budgets"

urlpatterns = [
    path("", views.budget_home, name="home"),
    path("ask/", views.budget_ask, name="ask"),
]