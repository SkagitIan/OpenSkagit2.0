from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse

def health(request):
    return HttpResponse("ok")

urlpatterns = [
    path("", include("core.urls")),
    path("tax/", include("taxtool.urls")),
    path("admin/", admin.site.urls),
    path("health/", health),
]
