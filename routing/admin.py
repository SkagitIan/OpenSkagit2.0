from django.contrib import admin

from .models import RoutingImport, RoutingImportRow, RoutingPlan, RoutingRoute, RoutingStop


@admin.register(RoutingImport)
class RoutingImportAdmin(admin.ModelAdmin):
    list_display = ("filename", "row_count", "unique_stop_count", "status", "uploaded_at")
    readonly_fields = ("uploaded_at", "original_headers", "summary")


@admin.register(RoutingPlan)
class RoutingPlanAdmin(admin.ModelAdmin):
    list_display = ("id", "mode", "target_stop_count", "route_count", "status", "created_at")


@admin.register(RoutingImportRow, RoutingRoute, RoutingStop)
class RoutingChildAdmin(admin.ModelAdmin):
    list_display = ("id",)
