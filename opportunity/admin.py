from django.contrib import admin

from .models import OpportunitySavedParcel, OpportunitySearch, OpportunitySearchFeedback, ParcelBookSyncNarrative


@admin.register(OpportunitySavedParcel)
class OpportunitySavedParcelAdmin(admin.ModelAdmin):
    list_display = ("parcel_number", "user", "source_tab", "updated_at")
    search_fields = ("parcel_number", "user__username", "user__email")
    list_filter = ("source_tab", "created_at", "updated_at")


@admin.register(OpportunitySearch)
class OpportunitySearchAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "status", "result_count", "saved_at", "updated_at")
    search_fields = ("title", "prompt", "criteria_summary", "user__username", "user__email")
    list_filter = ("status", "model", "saved_at", "created_at", "updated_at")
    readonly_fields = (
        "user",
        "prompt",
        "title",
        "criteria_summary",
        "assumptions",
        "search_plan",
        "plan_review",
        "result_diagnostics",
        "generated_sql",
        "generated_params",
        "model",
        "result_rows",
        "result_count",
        "status",
        "error",
        "saved_at",
        "created_at",
        "updated_at",
    )


@admin.register(OpportunitySearchFeedback)
class OpportunitySearchFeedbackAdmin(admin.ModelAdmin):
    list_display = ("search", "user", "rating", "parcel_number", "reason_code", "updated_at")
    search_fields = ("search__title", "search__prompt", "parcel_number", "comment", "user__username", "user__email")
    list_filter = ("rating", "reason_code", "created_at", "updated_at")
    readonly_fields = ("search", "user", "parcel_number", "rating", "reason_code", "comment", "created_at", "updated_at")


@admin.register(ParcelBookSyncNarrative)
class ParcelBookSyncNarrativeAdmin(admin.ModelAdmin):
    list_display = ("assessor_sync_report", "headline", "model", "generated_by_ai", "updated_at")
    search_fields = ("headline", "narrative", "assessor_sync_report__report_text")
    list_filter = ("generated_by_ai", "model", "created_at", "updated_at")
    readonly_fields = (
        "assessor_sync_report",
        "model",
        "headline",
        "narrative",
        "bullets",
        "summary_snapshot",
        "generated_by_ai",
        "error",
        "created_at",
        "updated_at",
    )
