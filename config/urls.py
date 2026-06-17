from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from core import views as core_views

def health(request):
    return HttpResponse("ok")

urlpatterns = [
    path("ask/stream/", core_views.ask_stream, name="ask_stream"),
    path("", include("core.urls")),
    path("tax/", include("taxtool.urls")),
    path("admin/", admin.site.urls),
    path("health/", health),
]
