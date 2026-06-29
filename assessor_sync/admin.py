from django.contrib import admin

from .models import (
    AssessorSyncChange,
    AssessorSyncFile,
    AssessorSyncReport,
    AssessorSyncRun,
    AuditorRecording,
    AuditorSyncQuery,
)


class ReadOnlyAuditAdmin(admin.ModelAdmin):
    list_per_page = 50
    show_full_result_count = False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class AssessorSyncFileInline(admin.TabularInline):
    model = AssessorSyncFile
    extra = 0
    can_delete = False
    fields = ("file_name", "changed", "byte_size", "sha256", "previous_sha256")
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


class AssessorSyncReportInline(admin.StackedInline):
    model = AssessorSyncReport
    extra = 0
    can_delete = False
    fields = ("created_at", "report_text")
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(AssessorSyncRun)
class AssessorSyncRunAdmin(ReadOnlyAuditAdmin):
    list_display = ("id", "status", "started_at", "finished_at", "files_changed", "report_path")
    list_filter = ("status", "started_at")
    search_fields = ("source_url", "zip_sha256", "report_path", "error")
    readonly_fields = (
        "id",
        "started_at",
        "finished_at",
        "source_url",
        "zip_sha256",
        "status",
        "report_path",
        "summary",
        "error",
    )
    inlines = (AssessorSyncReportInline, AssessorSyncFileInline)

    @admin.display(description="Files changed")
    def files_changed(self, obj):
        if isinstance(obj.summary, dict):
            return obj.summary.get("files_changed", 0)
        return "-"


@admin.register(AssessorSyncFile)
class AssessorSyncFileAdmin(ReadOnlyAuditAdmin):
    list_display = ("id", "run", "file_name", "changed", "byte_size", "created_at")
    list_filter = ("changed", "created_at")
    search_fields = ("file_name", "sha256", "previous_sha256")
    readonly_fields = ("id", "run", "file_name", "sha256", "byte_size", "changed", "previous_sha256", "created_at")


@admin.register(AssessorSyncChange)
class AssessorSyncChangeAdmin(ReadOnlyAuditAdmin):
    list_display = ("id", "run", "table_name", "change_type", "record_key", "created_at")
    list_filter = ("table_name", "change_type", "created_at")
    search_fields = ("record_key",)
    readonly_fields = (
        "id",
        "run",
        "table_name",
        "record_key",
        "change_type",
        "changed_fields",
        "old_row",
        "new_row",
        "created_at",
    )


@admin.register(AssessorSyncReport)
class AssessorSyncReportAdmin(ReadOnlyAuditAdmin):
    list_display = ("id", "run", "created_at")
    search_fields = ("report_text",)
    readonly_fields = ("id", "run", "report_text", "created_at")


@admin.register(AuditorRecording)
class AuditorRecordingAdmin(ReadOnlyAuditAdmin):
    list_display = ("recording_number", "recorded_date", "document_type", "signal_group", "parcel_number", "last_seen_at")
    list_filter = ("document_type", "signal_group", "recorded_date")
    search_fields = ("recording_number", "parcel_number", "grantor", "grantee", "legal")
    readonly_fields = (
        "id",
        "recording_number",
        "recorded_date",
        "document_type",
        "signal_group",
        "grantor",
        "grantee",
        "filer",
        "comment",
        "legal",
        "parcel_number",
        "parcel_text",
        "assessor_url",
        "pdf_url",
        "reference_url",
        "raw_row",
        "first_seen_run",
        "last_seen_run",
        "first_seen_at",
        "last_seen_at",
    )


@admin.register(AuditorSyncQuery)
class AuditorSyncQueryAdmin(ReadOnlyAuditAdmin):
    list_display = ("id", "run", "document_type", "start_date", "end_date", "status", "parsed_count", "inserted_count", "updated_count")
    list_filter = ("status", "capped", "document_type", "created_at")
    search_fields = ("document_type", "error")
    readonly_fields = (
        "id",
        "run",
        "document_type",
        "start_date",
        "end_date",
        "result_count",
        "parsed_count",
        "page_count",
        "inserted_count",
        "updated_count",
        "status",
        "capped",
        "error",
        "created_at",
        "finished_at",
    )
