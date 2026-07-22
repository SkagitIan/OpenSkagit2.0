from django.contrib import admin

from .models import AskMessage, AskThread


class AskMessageInline(admin.TabularInline):
    model = AskMessage
    extra = 0
    readonly_fields = ("role", "content", "sql", "structured_result", "response_id", "created_at")
    can_delete = False


@admin.register(AskThread)
class AskThreadAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "created_at", "updated_at")
    search_fields = ("id", "title")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [AskMessageInline]
