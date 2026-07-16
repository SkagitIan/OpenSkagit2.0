from django.contrib import admin
from django.urls import path, include, reverse
from django.http import HttpResponse
from django.conf import settings
from core.views import home as core_home
from opportunity.views import staff_redirect
from taxtool.views import tax_home, tax_parcel_og_image


def _taxshift_site_url():
    return getattr(settings, "TAXSHIFT_SITE_URL", "https://taxshift.co").rstrip("/")


def health(request):
    return HttpResponse("ok")


def root_home(request):
    host = request.get_host().split(":", 1)[0].lower()
    if host in settings.TAXSHIFT_HOSTS:
        return tax_home(request)
    return core_home(request)






def sentry_debug(request):
    division_by_zero = 1 / 0

def robots_txt(request):
    site_url = _taxshift_site_url()
    body = "\n".join([
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /accounts/",
        "Disallow: /staff/",
        f"Sitemap: {site_url}/sitemap.xml",
        "",
    ])
    return HttpResponse(body, content_type="text/plain")


def sitemap_xml(request):
    from django.utils import timezone

    site_url = _taxshift_site_url()
    lastmod = timezone.now().date().isoformat()
    paths = [
        "/",
        reverse("tax_login"),
        reverse("tax_data_sources"),
        reverse("tax_contact"),
        reverse("tax_privacy"),
        reverse("tax_terms"),
    ]
    urls = "".join(
        f"<url><loc>{site_url}{path}</loc><lastmod>{lastmod}</lastmod></url>"
        for path in paths
    )
    body = f"<?xml version=\"1.0\" encoding=\"UTF-8\"?>" \
           f"<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">{urls}</urlset>"
    return HttpResponse(body, content_type="application/xml")

urlpatterns = [
    path("", root_home, name="home"),
    path("robots.txt", robots_txt, name="robots_txt"),
    path("sitemap.xml", sitemap_xml, name="sitemap_xml"),
    path("og/parcel/<str:parcel_id>.png", tax_parcel_og_image, name="tax_parcel_og_image"),
    path("", include("core.urls")),
    path("", include("ask_agent.urls")),
    path("", include("land_ledger.urls")),
    path("tax/", include("taxtool.urls")),
    path("staff/tax-delinquency/", include("tax_delinquency.urls")),
    path("staff/opportunity/", staff_redirect, name="opportunity_dashboard"),
    path("staff/parcelbook/", include("parcelbook.urls")),
    path("staff/regression/", include("regression.urls")),
    path("opportunity/", include("opportunity.urls")),
    path("field/", include("field_map.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("admin/", admin.site.urls),
    path("health/", health),
]


if getattr(settings, "SENTRY_DEBUG_ROUTE", False):
    urlpatterns.append(path("sentry-debug/", sentry_debug, name="sentry_debug"))
