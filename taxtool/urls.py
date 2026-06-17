from django.urls import path
from . import views

urlpatterns = [
    path("", views.tax_home, name="tax_home"),
    path("search/", views.tax_search, name="tax_search"),
    path("parcel/<str:parcel_number>/", views.tax_parcel, name="tax_parcel"),
    path("parcel/<str:parcel_number>/yoy/", views.tax_yoy, name="tax_yoy"),
    path("agency/<str:mcag>/", views.tax_agency, name="tax_agency"),
]
