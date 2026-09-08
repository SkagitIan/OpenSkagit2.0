from django.urls import path

from . import views


app_name = "field_map"

urlpatterns = [
    path("", views.field_map, name="map"),
    path("manifest.webmanifest", views.web_manifest, name="manifest"),
    path("service-worker.js", views.service_worker, name="service_worker"),
    path("api/parcels/", views.parcels_geojson, name="parcels"),
]
