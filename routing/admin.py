from django.contrib import admin

from .models import PreinspectionWorkspace, RoutingImport, RoutingImportRow, RoutingPlan, RoutingRoute, RoutingStop


@admin.register(PreinspectionWorkspace)
class PreinspectionWorkspaceAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "year", "revision", "updated_at", "last_opened_at")
    list_filter = ("year",)
    search_fields = ("name", "owner__username", "owner__email")
    readonly_fields = ("owner", "name", "year", "state", "revision", "created_at", "updated_at", "last_opened_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RoutingImport)
class RoutingImportAdmin(admin.ModelAdmin):
    list_display = ("filename", "row_count", "unique_stop_count", "status", "uploaded_at")
    readonly_fields = ("uploaded_at", "original_headers", "summary")


@admin.register(RoutingPlan)
class RoutingPlanAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "mode", "target_stop_count", "route_count", "status", "created_at")


@admin.register(RoutingImportRow, RoutingRoute, RoutingStop)
class RoutingChildAdmin(admin.ModelAdmin):
    list_display = ("id",)
