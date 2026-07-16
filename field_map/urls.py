from django.urls import path

from . import views


app_name = "field_map"

urlpatterns = [
    path("", views.field_map, name="map"),
    path("api/parcels/", views.parcels_geojson, name="parcels"),
]
