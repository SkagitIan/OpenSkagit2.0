from django.contrib import admin

from .models import (
    ModelImprovementSummary,
    ModelLandSummary,
    ModelSFRSalesDataset,
    ModelSFRSalesExclusion,
    SFRComplianceLoopRun,
    SFRDatasetBuildRun,
    SFRRatioStudyRun,
    SFRSegmentExperiment,
    SFRSegmentModel,
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


@admin.register(SFRDatasetBuildRun)
class SFRDatasetBuildRunAdmin(ReadOnlyBuiltAdmin):
    list_display = ("id", "started_at", "status", "total_sales_loaded", "retained_sfr_sales")
    list_filter = ("status",)
    readonly_fields = [f.name for f in SFRDatasetBuildRun._meta.get_fields()]


@admin.register(SFRRatioStudyRun)
class SFRRatioStudyRunAdmin(ReadOnlyBuiltAdmin):
    list_display = ("id", "started_at", "status", "window_start_year", "window_end_year", "test_count", "primary_model")
    list_filter = ("status",)
    readonly_fields = [f.name for f in SFRRatioStudyRun._meta.get_fields()]


@admin.register(SFRSegmentExperiment)
class SFRSegmentExperimentAdmin(ReadOnlyBuiltAdmin):
    list_display = ("segment_value", "attempt_number", "attempt_kind", "train_count", "test_count", "passed")
    list_filter = ("attempt_kind", "passed")
    search_fields = ("segment_value",)
    readonly_fields = [f.name for f in SFRSegmentExperiment._meta.get_fields()]


@admin.register(SFRSegmentModel)
class SFRSegmentModelAdmin(ReadOnlyBuiltAdmin):
    list_display = ("segment_value", "status", "sample_count", "model_name", "attempts_made", "trained_at")
    list_filter = ("status",)
    search_fields = ("segment_value",)
    readonly_fields = [f.name for f in SFRSegmentModel._meta.get_fields()]


@admin.register(SFRComplianceLoopRun)
class SFRComplianceLoopRunAdmin(ReadOnlyBuiltAdmin):
    list_display = ("id", "started_at", "status", "segments_compliant", "segments_provisional", "segments_dropped", "ai_calls_made")
    list_filter = ("status",)
    readonly_fields = [f.name for f in SFRComplianceLoopRun._meta.get_fields()]
