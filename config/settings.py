from pathlib import Path
import os
import dj_database_url
import environ
import sentry_sdk
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

env = environ.Env(
    DEBUG=(bool, False),
)

SECRET_KEY = env(
    "SECRET_KEY",
    default="unsafe-dev-secret-key"
)

DEBUG = os.getenv("DEBUG", "false").lower() == "true"
SENTRY_DSN = env("SENTRY_DSN", default="")
SENTRY_ENVIRONMENT = env("SENTRY_ENVIRONMENT", default="production" if not DEBUG else "development")
SENTRY_SEND_DEFAULT_PII = env.bool("SENTRY_SEND_DEFAULT_PII", default=True)
SENTRY_TRACES_SAMPLE_RATE = env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.0)
SENTRY_DEBUG_ROUTE = env.bool("SENTRY_DEBUG_ROUTE", default=False)

if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        send_default_pii=SENTRY_SEND_DEFAULT_PII,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
    )

ALLOWED_HOSTS = [host.strip() for host in os.getenv("ALLOWED_HOSTS", "*").split(",") if host.strip()]
TAXSHIFT_HOSTS = {"taxshift.co", "www.taxshift.co"}
if "*" not in ALLOWED_HOSTS:
    for host in TAXSHIFT_HOSTS:
        if host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(host)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "taxtool",
    "land_ledger",
    "assessor_sync",
    "tax_delinquency",
    "opportunity",
    "ask_agent",
    "budgets.apps.BudgetsConfig",
    "discovery_agent",
    "parcelbook",
    "zoning_mcp",
    "gis_mcp",
    "regression",
    "graph",
    "field_map",
    "openskagit_tools.apps.OpenSkagitToolsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend"
)

EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)

EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")

DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL",
    default="webmaster@localhost"
)

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "core.context_processors.meta",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASE_URL = (
    os.getenv("NEW_DATABASE_URL")
    or os.getenv("POSTGIS_DATABASE_URL")
    or os.getenv("DATABASE_URL")
)

if not DATABASE_URL:
    raise ImproperlyConfigured(
        "OpenSkagit requires NEW_DATABASE_URL, POSTGIS_DATABASE_URL, or DATABASE_URL. "
        "SQLite fallback has been removed."
    )

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
    )
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    "budget_pdfs": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": MEDIA_ROOT, "base_url": MEDIA_URL},
    },
}

BUDGET_MAX_PDF_MB = env.int("BUDGET_MAX_PDF_MB", default=200)
BUDGET_PDF_DOWNLOAD_TIMEOUT_SECONDS = env.int("BUDGET_PDF_DOWNLOAD_TIMEOUT_SECONDS", default=180)
if not 1 <= BUDGET_MAX_PDF_MB <= 500:
    raise ImproperlyConfigured("BUDGET_MAX_PDF_MB must be between 1 and 500.")
if not 10 <= BUDGET_PDF_DOWNLOAD_TIMEOUT_SECONDS <= 900:
    raise ImproperlyConfigured("BUDGET_PDF_DOWNLOAD_TIMEOUT_SECONDS must be between 10 and 900.")

BUDGET_PDF_STORAGE = env("BUDGET_PDF_STORAGE", default="local").strip().lower()
if BUDGET_PDF_STORAGE == "r2":
    r2_account_id = env("R2_ACCOUNT_ID", default="").strip()
    r2_access_key_id = env("R2_ACCESS_KEY_ID", default="").strip()
    r2_secret_access_key = env("R2_SECRET_ACCESS_KEY", default="").strip()
    r2_budget_bucket = env("R2_BUDGET_BUCKET", default=env("R2_BUCKET", default="openskagit")).strip()
    missing_r2_settings = [
        name
        for name, value in {
            "R2_ACCOUNT_ID": r2_account_id,
            "R2_ACCESS_KEY_ID": r2_access_key_id,
            "R2_SECRET_ACCESS_KEY": r2_secret_access_key,
            "R2_BUDGET_BUCKET/R2_BUCKET": r2_budget_bucket,
        }.items()
        if not value
    ]
    if missing_r2_settings:
        raise ImproperlyConfigured(
            "BUDGET_PDF_STORAGE=r2 requires: " + ", ".join(missing_r2_settings)
        )
    STORAGES["budget_pdfs"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "access_key": r2_access_key_id,
            "secret_key": r2_secret_access_key,
            "bucket_name": r2_budget_bucket,
            "endpoint_url": f"https://{r2_account_id}.r2.cloudflarestorage.com",
            "region_name": "auto",
            "addressing_style": "path",
            "signature_version": "s3v4",
            "default_acl": None,
            "file_overwrite": True,
            "querystring_auth": True,
            "querystring_expire": 900,
        },
    }
elif BUDGET_PDF_STORAGE != "local":
    raise ImproperlyConfigured("BUDGET_PDF_STORAGE must be 'local' or 'r2'.")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
OPPORTUNITY_DASHBOARD_PASSWORD = env("OPPORTUNITY_DASHBOARD_PASSWORD", default="opportunity" if DEBUG else "")
SITE_URL = env("SITE_URL", default="https://openskagit.org/opportunity")
RESEND_API_KEY = env("RESEND_API_KEY", default="")
RESEND_FROM_EMAIL = env("RESEND_FROM_EMAIL", default="Parcel Book <parcelbook@openskagit.org>")

# TaxShift (taxshift.co) is a separate product hosted from this same
# deployment — it gets its own SITE_URL/from-address so changing one
# product's domain or sender never silently affects the other's email links.
TAXSHIFT_SITE_URL = env("TAXSHIFT_SITE_URL", default="https://taxshift.co")
TAXSHIFT_FROM_EMAIL = env("TAXSHIFT_FROM_EMAIL", default="TaxShift <notifications@taxshift.co>")
TAXSHIFT_TURNSTILE_SITE_KEY = env("TAXSHIFT_TURNSTILE_SITE_KEY", default="")
TAXSHIFT_TURNSTILE_SECRET_KEY = env("TAXSHIFT_TURNSTILE_SECRET_KEY", default="")
CSRF_TRUSTED_ORIGINS = [
    o for o in env("CSRF_TRUSTED_ORIGINS", default="").split(",") if o
]
for origin in ("https://taxshift.co", "https://www.taxshift.co"):
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

OPENSKAGIT_PUBLIC_ORIGIN = env("OPENSKAGIT_PUBLIC_ORIGIN", default="https://openskagit.com").rstrip("/")
OPENSKAGIT_MCP_CONNECTOR_URL = env(
    "OPENSKAGIT_MCP_CONNECTOR_URL",
    default=f"{OPENSKAGIT_PUBLIC_ORIGIN}/mcp/api/",
)
