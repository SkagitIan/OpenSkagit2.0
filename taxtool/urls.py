from django.urls import path
from . import views

urlpatterns = [
    path("", views.tax_home, name="tax_home"),
    path("search/", views.tax_search, name="tax_search"),
    path("signup/", views.tax_signup, name="tax_signup"),
    path("contact/", views.tax_contact, name="tax_contact"),
    path("data-sources/", views.tax_data_sources, name="tax_data_sources"),
    path("parcel/<str:parcel_number>/", views.tax_parcel, name="tax_parcel"),
    path("parcel/<str:parcel_number>/yoy/", views.tax_yoy, name="tax_yoy"),
    path("agency/<str:mcag>/", views.tax_agency, name="tax_agency"),
]