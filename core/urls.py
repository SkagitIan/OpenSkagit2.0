from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("app/", views.app, name="app"),
    path("ask/", views.ask, name="ask"),
    path("ask/sql/", views.ask_sql, name="ask_sql"),
    path("cities/<slug:slug>/", views.city, name="city"),
    path("api/land-ledger/<slug:city_slug>/summary/", views.land_ledger_summary, name="land_ledger_summary"),
    path("api/land-ledger/<slug:city_slug>/parcels/", views.land_ledger_parcels, name="land_ledger_parcels"),

    path("login/", auth_views.LoginView.as_view(
        template_name="auth/login.html"
    ), name="login"),

    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    path("password-reset/", auth_views.PasswordResetView.as_view(
        template_name="auth/password_reset.html"
    ), name="password_reset"),

    path("password-reset/done/", auth_views.PasswordResetDoneView.as_view(
        template_name="auth/password_reset_done.html"
    ), name="password_reset_done"),
]
