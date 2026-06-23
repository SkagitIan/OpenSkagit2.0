from django.urls import path

from . import views


urlpatterns = [
    path("", views.dashboard, name="tax_delinquency_dashboard"),
]
