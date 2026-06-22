from django.contrib import admin

from .models import AssessorSyncChange, AssessorSyncFile, AssessorSyncReport, AssessorSyncRun


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
