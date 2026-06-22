from django.apps import apps
from django.contrib import admin
from django.db import models


FEATURE_TABLES = {
    "assessor_sync_changes",
    "assessor_sync_files",
    "assessor_sync_reports",
    "assessor_sync_runs",
    "core_currentdraft",
    "land_ledger_city_summary",
    "land_ledger_parcels",
}


class GenericReadOnlyTableAdmin(admin.ModelAdmin):
    list_per_page = 50
    show_full_result_count = False

    def get_list_display(self, request):
        fields = [
            field.name
            for field in self.model._meta.fields
            if not isinstance(field, models.JSONField) and field.name != "geometry"
        ]
        return tuple(fields[:6] or [self.model._meta.pk.name])

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for model in apps.get_app_config("core").get_models():
    if model._meta.db_table in FEATURE_TABLES:
        continue
    if not admin.site.is_registered(model):
        admin.site.register(model, GenericReadOnlyTableAdmin)
