from django.urls import path
from . import views

urlpatterns = [
    path("", views.tax_home, name="tax_home"),
    path("search/", views.tax_search, name="tax_search"),
    path("signup/", views.tax_signup, name="tax_signup"),
    path("login/", views.tax_login, name="tax_login"),
    path("login/<str:token>/", views.tax_login_token, name="tax_login_token"),
    path("account/", views.tax_account, name="tax_account"),
    path("unsubscribe/<str:token>/", views.tax_unsubscribe, name="tax_unsubscribe"),
    path("verify/<str:token>/", views.tax_verify, name="tax_verify"),
    path("contact/", views.tax_contact, name="tax_contact"),
    path("data-sources/", views.tax_data_sources, name="tax_data_sources"),
    path("privacy/", views.tax_privacy, name="tax_privacy"),
    path("terms/", views.tax_terms, name="tax_terms"),
    path("parcel/<str:parcel_number>/", views.tax_parcel, name="tax_parcel"),
    path("parcel/<str:parcel_number>/yoy/", views.tax_yoy, name="tax_yoy"),
    path("agency/<str:mcag>/", views.tax_agency, name="tax_agency"),
]