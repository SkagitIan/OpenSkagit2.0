from django.contrib import admin

from .models import TaxStatement, TaxStatementCheck, TaxStatementError, TaxStatementRun


@admin.register(TaxStatement)
class TaxStatementAdmin(admin.ModelAdmin):
    list_display = (
        "parcel_number",
        "tax_year",
        "tax_account_number",
        "total_due",
        "status",
        "lead_level",
        "delinquent_installment_count",
        "source_fetched_at",
    )
    list_filter = ("tax_year", "status", "lead_level")
    search_fields = ("parcel_number", "tax_account_number", "owner_name", "situs_address")
    ordering = ("-total_due", "parcel_number", "-tax_year")


@admin.register(TaxStatementRun)
class TaxStatementRunAdmin(admin.ModelAdmin):
    list_display = (
        "run_type",
        "status",
        "started_at",
        "finished_at",
        "statements_attempted",
        "statements_saved",
        "errors",
    )
    list_filter = ("run_type", "status")
    ordering = ("-started_at",)


@admin.register(TaxStatementCheck)
class TaxStatementCheckAdmin(admin.ModelAdmin):
    list_display = ("parcel_number", "tax_year", "status", "total_due", "source_fetched_at")
    list_filter = ("tax_year", "status")
    search_fields = ("parcel_number",)
    ordering = ("-source_fetched_at", "parcel_number", "-tax_year")


@admin.register(TaxStatementError)
class TaxStatementErrorAdmin(admin.ModelAdmin):
    list_display = ("parcel_number", "tax_year", "error_type", "created_at", "resolved_at")
    list_filter = ("error_type", "resolved_at")
    search_fields = ("parcel_number", "message")
    ordering = ("-created_at",)
