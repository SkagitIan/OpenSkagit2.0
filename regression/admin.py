from django.contrib import admin

from .models import (
    ModelImprovementSummary,
    ModelLandSummary,
    ModelSFRSalesDataset,
    ModelSFRSalesExclusion,
)


class ReadOnlyBuiltAdmin(admin.ModelAdmin):
    """Every table here is fully rebuilt by a management command -- never hand-edited."""

    list_per_page = 50
    show_full_result_count = False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ModelLandSummary)
class ModelLandSummaryAdmin(ReadOnlyBuiltAdmin):
    list_display = ("parcel_number", "land_segment_count", "total_land_acres", "primary_land_type", "has_open_space_value")
    search_fields = ("parcel_number",)
    readonly_fields = [f.name for f in ModelLandSummary._meta.get_fields()]


@admin.register(ModelImprovementSummary)
class ModelImprovementSummaryAdmin(ReadOnlyBuiltAdmin):
    list_display = ("parcel_number", "primary_living_area", "primary_actual_year_built", "primary_building_style", "has_garage")
    search_fields = ("parcel_number",)
    readonly_fields = [f.name for f in ModelImprovementSummary._meta.get_fields()]


@admin.register(ModelSFRSalesDataset)
class ModelSFRSalesDatasetAdmin(ReadOnlyBuiltAdmin):
    list_display = ("saleid", "parcel_number", "sale_date", "sale_price", "city_name", "neighborhood_code")
    list_filter = ("sale_year", "city_name", "school_district")
    search_fields = ("saleid", "parcel_number")
    readonly_fields = [f.name for f in ModelSFRSalesDataset._meta.get_fields()]


@admin.register(ModelSFRSalesExclusion)
class ModelSFRSalesExclusionAdmin(ReadOnlyBuiltAdmin):
    list_display = ("saleid", "parcel_number", "exclusion_reason", "sale_price_num")
    list_filter = ("exclusion_reason",)
    search_fields = ("saleid", "parcel_number", "details")
    readonly_fields = [f.name for f in ModelSFRSalesExclusion._meta.get_fields()]
