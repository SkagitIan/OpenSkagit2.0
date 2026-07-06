from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from django.conf import settings
from core.views import home as core_home
from opportunity.views import staff_redirect
from taxtool.views import tax_home


def health(request):
    return HttpResponse("ok")


def root_home(request):
    host = request.get_host().split(":", 1)[0].lower()
    if host in settings.TAXSHIFT_HOSTS:
        return tax_home(request)
    return core_home(request)


urlpatterns = [
    path("", root_home, name="home"),
    path("", include("core.urls")),
    path("", include("ask_agent.urls")),
    path("", include("land_ledger.urls")),
    path("tax/", include("taxtool.urls")),
    path("staff/tax-delinquency/", include("tax_delinquency.urls")),
    path("staff/opportunity/", staff_redirect, name="opportunity_dashboard"),
    path("staff/parcelbook/", include("parcelbook.urls")),
    path("opportunity/", include("opportunity.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("admin/", admin.site.urls),
    path("health/", health),
]
