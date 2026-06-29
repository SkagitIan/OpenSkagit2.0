from django.db import models


class TaxStatementRun(models.Model):
    class RunType(models.TextChoices):
        BACKFILL = "backfill", "Backfill"
        SLOW_CHECK = "slow_check", "Slow check"
        SINGLE = "single", "Single parcel"

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        ERROR = "error", "Error"
        STOPPED = "stopped", "Stopped"

    run_type = models.CharField(max_length=24, choices=RunType.choices)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.RUNNING)
    years = models.JSONField(default=list, blank=True)
    options = models.JSONField(default=dict, blank=True)
    parcels_considered = models.IntegerField(default=0)
    statements_attempted = models.IntegerField(default=0)
    statements_saved = models.IntegerField(default=0)
    statements_skipped = models.IntegerField(default=0)
    errors = models.IntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.run_type} {self.started_at:%Y-%m-%d %H:%M}"


class TaxStatement(models.Model):
    class Status(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        PAID = "paid", "Paid"
        UNPAID = "unpaid", "Unpaid"
        PARTIALLY_PAID = "partially_paid", "Partially paid"

    class LeadLevel(models.TextChoices):
        CLEAR = "clear", "Clear"
        WATCH = "watch", "Watch"
        ONE_LATE = "one_late", "One late"
        BEHIND = "behind", "Behind"
        SERIOUS = "serious", "Serious"
        SEVERE = "severe", "Severe"
        UNKNOWN = "unknown", "Unknown"

    parcel_number = models.TextField(db_index=True)
    tax_account_number = models.TextField(blank=True, null=True, db_index=True)
    tax_year = models.IntegerField(db_index=True)
    owner_name = models.TextField(blank=True, null=True)
    situs_address = models.TextField(blank=True, null=True)
    levy_code = models.TextField(blank=True, null=True)
    general_tax = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    special_assessments_fees = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    total_due = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.UNKNOWN)
    lead_level = models.CharField(max_length=24, choices=LeadLevel.choices, default=LeadLevel.UNKNOWN, db_index=True)
    delinquent_installment_count = models.IntegerField(default=0)
    unpaid_installment_count = models.IntegerField(default=0)
    oldest_due_date = models.DateField(blank=True, null=True)
    source_url = models.TextField()
    source_fetched_at = models.DateTimeField(db_index=True)
    raw_data = models.JSONField(default=dict, blank=True)
    last_run = models.ForeignKey(TaxStatementRun, on_delete=models.SET_NULL, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["parcel_number", "tax_year"],
                name="uniq_tax_statement_parcel_year",
            )
        ]
        indexes = [
            models.Index(fields=["lead_level", "total_due"]),
            models.Index(fields=["source_fetched_at", "parcel_number"]),
        ]

    def __str__(self):
        return f"{self.parcel_number} {self.tax_year}"


class TaxStatementCheck(models.Model):
    parcel_number = models.TextField(db_index=True)
    tax_year = models.IntegerField(db_index=True)
    status = models.CharField(max_length=24, choices=TaxStatement.Status.choices, default=TaxStatement.Status.UNKNOWN)
    total_due = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    source_fetched_at = models.DateTimeField(db_index=True)
    last_run = models.ForeignKey(TaxStatementRun, on_delete=models.SET_NULL, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["parcel_number", "tax_year"],
                name="uniq_tax_statement_check_parcel_year",
            )
        ]
        indexes = [
            models.Index(fields=["source_fetched_at", "parcel_number"]),
        ]

    def __str__(self):
        return f"{self.parcel_number} {self.tax_year} checked"


class TaxStatementError(models.Model):
    run = models.ForeignKey(TaxStatementRun, on_delete=models.SET_NULL, blank=True, null=True)
    parcel_number = models.TextField(db_index=True)
    tax_year = models.IntegerField(blank=True, null=True, db_index=True)
    source_url = models.TextField(blank=True)
    error_type = models.TextField()
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["resolved_at", "created_at"]),
            models.Index(fields=["parcel_number", "tax_year"]),
        ]

    def __str__(self):
        return f"{self.parcel_number} {self.tax_year or ''} {self.error_type}"
