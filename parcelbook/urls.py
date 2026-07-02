from django.urls import path

from . import views

app_name = "parcelbook"

urlpatterns = [
    path("queries/", views.staff_query_lab, name="query_lab"),
]
