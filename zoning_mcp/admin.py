from django.contrib import admin

from .models import Jurisdiction, Zone, ZoningCodeDocument, ZoningCodeSection, ZoningSourceTable, ZoningUseRule


@admin.register(Jurisdiction)
class JurisdictionAdmin(admin.ModelAdmin):
    list_display = ("key", "display_name", "zoning_title", "extraction_status", "updated_at")
    search_fields = ("key", "display_name", "zoning_title")


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ("jurisdiction", "zone_code", "zone_name")
    list_filter = ("jurisdiction",)
    search_fields = ("zone_code", "zone_name")


@admin.register(ZoningUseRule)
class ZoningUseRuleAdmin(admin.ModelAdmin):
    list_display = ("jurisdiction", "zone", "use_name", "normalized_status", "source_table")
    list_filter = ("jurisdiction", "normalized_status", "source_table")
    search_fields = ("use_name", "normalized_use_key", "zone__zone_code")


@admin.register(ZoningCodeDocument)
class ZoningCodeDocumentAdmin(admin.ModelAdmin):
    list_display = ("jurisdiction", "chapter", "title", "fetched_at")
    list_filter = ("jurisdiction",)
    search_fields = ("title", "chapter", "text")


@admin.register(ZoningCodeSection)
class ZoningCodeSectionAdmin(admin.ModelAdmin):
    list_display = ("jurisdiction", "section", "heading", "chapter_ref", "imported_at")
    list_filter = ("jurisdiction", "chapter_ref")
    search_fields = ("section", "heading", "text")


@admin.register(ZoningSourceTable)
class ZoningSourceTableAdmin(admin.ModelAdmin):
    list_display = ("jurisdiction", "chapter_ref", "table_index", "caption", "imported_at")
    list_filter = ("jurisdiction", "chapter_ref")
    search_fields = ("caption", "nearest_heading")
