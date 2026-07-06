from django.contrib import admin

from .models import (
    ParcelSearchCache,
    TaxShiftEmailTemplate,
    TaxShiftNotification,
    TaxShiftSignup,
)


@admin.register(TaxShiftSignup)
class TaxShiftSignupAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "address_or_parcel",
        "parcel_number",
        "resolution_status",
        "is_verified",
        "is_active",
        "snapshot_captured_at",
        "source",
        "created_at",
    )
    search_fields = ("email", "address_or_parcel", "parcel_number")
    list_filter = ("resolution_status", "is_verified", "is_active", "source", "created_at")
    readonly_fields = (
        "created_at",
        "updated_at",
        "snapshot_captured_at",
        "recorded_docs_snapshot",
        "verified_at",
        "verification_email_sent_at",
        "user",
    )


@admin.register(TaxShiftNotification)
class TaxShiftNotificationAdmin(admin.ModelAdmin):
    list_display = ("signup", "parcel_number", "trigger_type", "run_id", "sent_at", "created_at")
    search_fields = ("signup__email", "parcel_number")
    list_filter = ("trigger_type", "sent_at", "created_at")
    readonly_fields = ("signup", "parcel_number", "trigger_type", "payload", "run_id", "sent_at", "created_at")


@admin.register(TaxShiftEmailTemplate)
class TaxShiftEmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "subject", "updated_at")
    fields = ("name", "subject", "body_html")


@admin.register(ParcelSearchCache)
class ParcelSearchCacheAdmin(admin.ModelAdmin):
    list_display = ("parcel_number", "address", "last_query", "last_source", "hit_count", "last_seen_at")
    search_fields = ("parcel_number", "situs_street_name", "situs_city_state_zip", "last_query")
    list_filter = ("last_source", "last_seen_at")
    readonly_fields = ("first_seen_at", "last_seen_at")
