from django.contrib import admin
from django.utils.html import format_html

from .models import CurrentDraft


@admin.register(CurrentDraft)
class CurrentDraftAdmin(admin.ModelAdmin):
    list_display = (
        "question",
        "answer_preview",
        "status",
        "probe",
        "publish_score",
        "confidence",
        "row_count",
        "created_at",
    )
    list_filter = ("status", "probe", "created_at")
    search_fields = ("question", "short_answer", "why_it_matters", "source_data")
    readonly_fields = ("draft_preview", "created_at", "updated_at")
    ordering = ("-publish_score", "-created_at")
    fieldsets = (
        ("Draft Preview", {
            "fields": ("draft_preview",),
        }),
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

    @admin.display(description="Answer")
    def answer_preview(self, obj):
        return obj.short_answer[:140] + ("..." if len(obj.short_answer) > 140 else "")

    @admin.display(description="Current draft")
    def draft_preview(self, obj):
        return format_html(
            """
            <div style="max-width: 900px; line-height: 1.45;">
              <h2 style="margin: 0 0 0.5rem;">{}</h2>
              <p><strong>Short answer:</strong><br>{}</p>
              <p><strong>Why it matters:</strong><br>{}</p>
              <p><strong>Source data:</strong><br>{}</p>
              <p><strong>What to check next:</strong><br>{}</p>
              <p><strong>Score:</strong> {} &nbsp; <strong>Confidence:</strong> {}</p>
            </div>
            """,
            obj.question,
            obj.short_answer or "-",
            obj.why_it_matters or "-",
            obj.source_data or "-",
            obj.what_to_check_next or "-",
            obj.publish_score if obj.publish_score is not None else "-",
            obj.confidence if obj.confidence is not None else "-",
        )
