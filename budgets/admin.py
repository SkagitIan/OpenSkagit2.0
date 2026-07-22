from django.contrib import admin, messages
from django.utils import timezone

from .models import BudgetDocument, BudgetDocumentPage, BudgetImportRun, BudgetJurisdiction, BudgetLineItem
from .review import BudgetReviewError, validate_document_for_publication


@admin.register(BudgetJurisdiction)
class BudgetJurisdictionAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "mcag", "active")
    list_filter = ("kind", "active")
    search_fields = ("name", "mcag")


@admin.action(description="Publish selected reviewed documents")
def publish_documents(modeladmin, request, queryset):
    published = 0
    skipped = []
    for document in queryset:
        try:
            validate_document_for_publication(document)
        except BudgetReviewError as exc:
            skipped.append(f"{document}: {exc}")
            continue
        document.published = True
        document.reviewed_at = timezone.now()
        document.save(update_fields=["published", "reviewed_at"])
        published += 1
    if published:
        modeladmin.message_user(request, f"Published {published} reviewed budget document(s).", messages.SUCCESS)
    if skipped:
        modeladmin.message_user(request, "Skipped documents that did not pass review validation: " + "; ".join(skipped), messages.WARNING)


@admin.action(description="Set selected document as current")
def set_current_document(modeladmin, request, queryset):
    for document in queryset.select_related("jurisdiction"):
        BudgetDocument.objects.filter(jurisdiction=document.jurisdiction).update(is_current=False)
        BudgetDocument.objects.filter(pk=document.pk).update(is_current=True)


@admin.register(BudgetDocument)
class BudgetDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "jurisdiction", "fiscal_year", "status", "published", "is_current", "page_count")
    list_filter = ("status", "published", "is_current", "fiscal_year", "jurisdiction")
    search_fields = ("title", "jurisdiction__name", "source_url")
    readonly_fields = ("content_sha256", "page_count", "imported_at", "retrieved_at")
    actions = (publish_documents, set_current_document)


@admin.register(BudgetDocumentPage)
class BudgetDocumentPageAdmin(admin.ModelAdmin):
    list_display = ("document", "page_number")
    search_fields = ("document__title", "text")


@admin.register(BudgetLineItem)
class BudgetLineItemAdmin(admin.ModelAdmin):
    list_display = ("document", "reviewed", "is_total", "side", "amount_kind", "fund_name", "department_name", "category_name", "account_name", "amount")
    list_filter = ("reviewed", "is_total", "side", "amount_kind", "fiscal_year")
    search_fields = ("fund_name", "department_name", "category_name", "account_name", "raw_label", "source_note")


@admin.register(BudgetImportRun)
class BudgetImportRunAdmin(admin.ModelAdmin):
    list_display = ("document", "status", "pages_extracted", "candidate_line_items", "started_at")
    list_filter = ("status",)
    readonly_fields = ("started_at", "finished_at")
