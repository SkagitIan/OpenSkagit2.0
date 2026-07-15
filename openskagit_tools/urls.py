from django.urls import path

from . import views

urlpatterns = [
    path("", views.mcp_catalog, name="mcp_catalog"),
]
