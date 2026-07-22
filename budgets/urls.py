from django.urls import path

from . import views

app_name = "budgets"

urlpatterns = [
    path("", views.budget_home, name="home"),
    path("ask/", views.budget_ask, name="ask"),
    path("ask/stream/", views.budget_ask_stream, name="ask_stream"),
    path("compare/", views.budget_compare, name="compare"),
]