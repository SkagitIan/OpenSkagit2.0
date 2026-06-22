from django.urls import path

from . import views


urlpatterns = [
    path("api/land-ledger/<slug:city_slug>/summary/", views.land_ledger_summary, name="land_ledger_summary"),
    path("api/land-ledger/<slug:city_slug>/parcels/", views.land_ledger_parcels, name="land_ledger_parcels"),
]
