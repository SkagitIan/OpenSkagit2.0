from django.contrib import admin

from .models import TaxShiftSignup


@admin.register(TaxShiftSignup)
class TaxShiftSignupAdmin(admin.ModelAdmin):
    list_display = ("email", "address_or_parcel", "source", "created_at")
    search_fields = ("email", "address_or_parcel")
    list_filter = ("source", "created_at")
    readonly_fields = ("created_at", "updated_at")
