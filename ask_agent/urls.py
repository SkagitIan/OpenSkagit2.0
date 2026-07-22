from django.urls import path

from . import views


urlpatterns = [
    path("app/", views.app, name="app"),
    path("ask/", views.ask, name="ask"),
    path("ask/t/<uuid:thread_id>/", views.ask, name="ask_thread"),
    path("ask/sql/", views.ask_sql, name="ask_sql"),
    path("ask/stream/", views.ask_stream, name="ask_stream"),
]
