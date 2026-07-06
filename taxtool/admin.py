from django.contrib import admin

from .models import ParcelSearchCache, TaxShiftSignup


@admin.register(TaxShiftSignup)
class TaxShiftSignupAdmin(admin.ModelAdmin):
    list_display = ("email", "address_or_parcel", "source", "created_at")
    search_fields = ("email", "address_or_parcel")
    list_filter = ("source", "created_at")
    readonly_fields = ("created_at", "updated_at")

@admin.register(ParcelSearchCache)
class ParcelSearchCacheAdmin(admin.ModelAdmin):
    list_display = ("parcel_number", "address", "last_query", "last_source", "hit_count", "last_seen_at")
    search_fields = ("parcel_number", "situs_street_name", "situs_city_state_zip", "last_query")
    list_filter = ("last_source", "last_seen_at")
    readonly_fields = ("first_seen_at", "last_seen_at")
