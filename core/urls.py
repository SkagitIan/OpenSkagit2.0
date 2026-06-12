from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("app/", views.app, name="app"),

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
