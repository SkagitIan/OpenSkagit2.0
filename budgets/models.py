from __future__ import annotations

from django.core.validators import MinValueValidator
from django.db import models

from .storage import budget_pdf_storage, budget_pdf_upload_to


class BudgetJurisdiction(models.Model):
    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=200)
    mcag = models.CharField(max_length=12, blank=True, db_index=True)
    kind = models.CharField(max_length=40, blank=True)
    official_url = models.URLField(blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class BudgetDocument(models.Model):
    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        PRELIMINARY = "preliminary", "Preliminary"
        ADOPTED = "adopted", "Adopted"
        AMENDED = "amended", "Amended"

    jurisdiction = models.ForeignKey(BudgetJurisdiction, on_delete=models.CASCADE, related_name="budget_documents")
    fiscal_year = models.PositiveSmallIntegerField(db_index=True)
    title = models.CharField(max_length=300)
    status = models.CharField(max_length=20, choices=Status.choices, db_index=True)
    version_date = models.DateField(blank=True, null=True)
    adopted_on = models.DateField(blank=True, null=True)
    source_url = models.URLField(max_length=1000)
    local_file = models.FileField(storage=budget_pdf_storage, upload_to=budget_pdf_upload_to, blank=True)
    content_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    page_count = models.PositiveIntegerField(default=0)
    extracted_summary = models.JSONField(default=dict, blank=True)
    published = models.BooleanField(default=False, db_index=True)
    is_current = models.BooleanField(default=False, db_index=True)
    retrieved_at = models.DateTimeField(blank=True, null=True)
    imported_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-fiscal_year", "-version_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["jurisdiction", "source_url", "content_sha256"],
                name="budget_document_source_hash_unique",
            )
        ]
        indexes = [
            models.Index(fields=["jurisdiction", "fiscal_year", "published"]),
            models.Index(fields=["jurisdiction", "is_current"]),
        ]

    def __str__(self) -> str:
        return f"{self.jurisdiction} {self.fiscal_year} {self.get_status_display()}"


class BudgetDocumentPage(models.Model):
    document = models.ForeignKey(BudgetDocument, on_delete=models.CASCADE, related_name="pages")
    page_number = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    text = models.TextField(blank=True)

    class Meta:
        ordering = ["page_number"]
        constraints = [
            models.UniqueConstraint(fields=["document", "page_number"], name="budget_document_page_unique")
        ]

    def __str__(self) -> str:
        return f"{self.document} page {self.page_number}"


class BudgetLineItem(models.Model):
    class Side(models.TextChoices):
        REVENUE = "revenue", "Revenue"
        EXPENDITURE = "expenditure", "Expenditure"
        FUND_BALANCE = "fund_balance", "Fund balance"
        OTHER = "other", "Other"

    class AmountKind(models.TextChoices):
        REQUESTED = "requested", "Requested"
        RECOMMENDED = "recommended", "Recommended"
        ADOPTED = "adopted", "Adopted"
        AMENDED = "amended", "Amended"
        ACTUAL = "actual", "Actual"
        UNKNOWN = "unknown", "Unknown"

    document = models.ForeignKey(BudgetDocument, on_delete=models.CASCADE, related_name="line_items")
    page_number = models.PositiveIntegerField(blank=True, null=True)
    fiscal_year = models.PositiveSmallIntegerField(db_index=True)
    side = models.CharField(max_length=20, choices=Side.choices, db_index=True)
    amount_kind = models.CharField(max_length=20, choices=AmountKind.choices, default=AmountKind.UNKNOWN)
    fund_code = models.CharField(max_length=40, blank=True)
    fund_name = models.CharField(max_length=240, blank=True)
    department_code = models.CharField(max_length=40, blank=True)
    department_name = models.CharField(max_length=240, blank=True)
    account_code = models.CharField(max_length=80, blank=True)
    account_name = models.CharField(max_length=300, blank=True)
    category_name = models.CharField(max_length=240, blank=True)
    amount = models.DecimalField(max_digits=22, decimal_places=2)
    scope = models.CharField(max_length=40, blank=True)
    is_total = models.BooleanField(default=False, db_index=True)
    reviewed = models.BooleanField(default=False, db_index=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    source_note = models.TextField(blank=True)
    raw_label = models.TextField(blank=True)
    raw_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["side", "fund_code", "department_code", "account_code", "id"]
        indexes = [
            models.Index(fields=["document", "side"]),
            models.Index(fields=["document", "reviewed", "is_total"]),
            models.Index(fields=["fiscal_year", "side"]),
            models.Index(fields=["fund_code"]),
        ]


class BudgetImportRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    document = models.ForeignKey(BudgetDocument, on_delete=models.CASCADE, related_name="import_runs")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    pages_extracted = models.PositiveIntegerField(default=0)
    candidate_line_items = models.PositiveIntegerField(default=0)
    warnings = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-started_at"]
