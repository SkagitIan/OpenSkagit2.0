from django.contrib import admin

from .models import CurrentDraft


@admin.register(CurrentDraft)
class CurrentDraftAdmin(admin.ModelAdmin):
    list_display = (
        "question",
        "status",
        "probe",
        "publish_score",
        "confidence",
        "row_count",
        "created_at",
    )
    list_filter = ("status", "probe", "created_at")
    search_fields = ("question", "short_answer", "why_it_matters", "source_data")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-publish_score", "-created_at")
    fieldsets = (
        (None, {
            "fields": (
                "status",
                "probe",
                "model",
                "question",
                "short_answer",
                "why_it_matters",
                "confidence",
                "publish_score",
            )
        }),
        ("Evidence", {
            "fields": (
                "source_data",
                "caveats",
                "what_to_check_next",
                "rejection_reason",
                "row_count",
                "qa_flags",
            )
        }),
        ("Run Metadata", {
            "classes": ("collapse",),
            "fields": ("probe_metadata", "raw_payload", "created_at", "updated_at"),
        }),
    )
