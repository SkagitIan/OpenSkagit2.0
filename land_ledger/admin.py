from django.contrib import admin

from .models import LandLedgerCitySummary, LandLedgerParcel


class ReadOnlyLandLedgerAdmin(admin.ModelAdmin):
    list_per_page = 50
    show_full_result_count = False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LandLedgerCitySummary)
class LandLedgerCitySummaryAdmin(ReadOnlyLandLedgerAdmin):
    list_display = (
        "city_slug",
        "city_name",
        "parcel_count",
        "eligible_parcel_count",
        "city_current_opportunity_10yr",
        "city_policy_opportunity_10yr",
        "rebuilt_at",
    )
    search_fields = ("city_slug", "city_name")
    readonly_fields = tuple(field.name for field in LandLedgerCitySummary._meta.fields)


@admin.register(LandLedgerParcel)
class LandLedgerParcelAdmin(ReadOnlyLandLedgerAdmin):
    list_display = ("parcel_number", "city_name", "address", "zone_id", "category", "current_tax")
    list_filter = ("city_slug", "zone_group", "category", "productivity_label")
    search_fields = ("parcel_number", "address", "zone_id", "zone_name")
    readonly_fields = tuple(field.name for field in LandLedgerParcel._meta.fields)
