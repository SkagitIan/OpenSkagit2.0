from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from opportunity.views import staff_redirect

def health(request):
    return HttpResponse("ok")

urlpatterns = [
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
