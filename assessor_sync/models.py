from django.db import models


class LiveCheckRun(models.Model):
    """Tracks each nightly run of check_watched_parcels."""

    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_PARTIAL = "partial"
    STATUS_FAILED = "failed"

    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(blank=True, null=True)
    status = models.TextField(default=STATUS_RUNNING)
    summary = models.JSONField(default=dict)
    error = models.TextField(blank=True)

    class Meta:
        db_table = "assessor_live_check_runs"
        ordering = ["-started_at"]

    def __str__(self):
        return f"LiveCheckRun {self.pk} ({self.status})"


class ParcelLiveSnapshot(models.Model):
    """
    Stores the last-known live API values for a parcel.
    Only updated when data changes; used to diff against new fetches.
    """

    parcel_number = models.TextField(unique=True)
    tracked_fields = models.JSONField(default=dict)
    last_checked_at = models.DateTimeField()
    last_changed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "assessor_parcel_live_snapshots"
        ordering = ["-last_checked_at"]

    def __str__(self):
        return f"Snapshot {self.parcel_number}"


class AssessorSyncRun(models.Model):
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(blank=True, null=True)
    source_url = models.TextField(blank=True, null=True)
    zip_sha256 = models.TextField(blank=True, null=True)
    status = models.TextField()
    report_path = models.TextField(blank=True, null=True)
    summary = models.JSONField(default=dict)
    error = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "assessor_sync_runs"
        ordering = ["-started_at"]

    def __str__(self):
        return f"Run {self.pk} ({self.status})"


class AssessorSyncFile(models.Model):
    run = models.ForeignKey(AssessorSyncRun, on_delete=models.DO_NOTHING, db_column="run_id", related_name="files")
    file_name = models.TextField()
    sha256 = models.TextField()
    byte_size = models.BigIntegerField()
    changed = models.BooleanField()
    previous_sha256 = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "assessor_sync_files"
        ordering = ["run_id", "file_name"]

    def __str__(self):
        return self.file_name


class AssessorSyncChange(models.Model):
    run = models.ForeignKey(AssessorSyncRun, on_delete=models.DO_NOTHING, db_column="run_id", related_name="changes")
    table_name = models.TextField()
    record_key = models.TextField()
    change_type = models.TextField()
    changed_fields = models.JSONField(default=dict)
    old_row = models.JSONField(blank=True, null=True)
    new_row = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "assessor_sync_changes"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.table_name} {self.change_type}: {self.record_key}"


class AssessorSyncReport(models.Model):
    run = models.ForeignKey(AssessorSyncRun, on_delete=models.DO_NOTHING, db_column="run_id", related_name="reports")
    report_text = models.TextField()
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "assessor_sync_reports"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Report for run {self.run_id}"


class AuditorRecording(models.Model):
    recording_number = models.TextField(unique=True)
    recorded_date = models.DateField(blank=True, null=True)
    document_type = models.TextField()
    signal_group = models.TextField()
    grantor = models.TextField(blank=True)
    grantee = models.TextField(blank=True)
    filer = models.TextField(blank=True)
    comment = models.TextField(blank=True)
    legal = models.TextField(blank=True)
    parcel_number = models.TextField(blank=True)
    parcel_text = models.TextField(blank=True)
    assessor_url = models.TextField(blank=True)
    pdf_url = models.TextField(blank=True)
    reference_url = models.TextField(blank=True)
    raw_row = models.JSONField(default=dict)
    first_seen_run = models.ForeignKey(
        AssessorSyncRun,
        on_delete=models.DO_NOTHING,
        db_column="first_seen_run_id",
        related_name="first_seen_auditor_recordings",
        blank=True,
        null=True,
    )
    last_seen_run = models.ForeignKey(
        AssessorSyncRun,
        on_delete=models.DO_NOTHING,
        db_column="last_seen_run_id",
        related_name="last_seen_auditor_recordings",
        blank=True,
        null=True,
    )
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "auditor_recordings"
        ordering = ["-recorded_date", "-id"]

    def __str__(self):
        return f"{self.recording_number} {self.document_type}"


class AuditorSyncQuery(models.Model):
    run = models.ForeignKey(AssessorSyncRun, on_delete=models.DO_NOTHING, db_column="run_id", related_name="auditor_queries")
    document_type = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField()
    result_count = models.IntegerField()
    parsed_count = models.IntegerField()
    page_count = models.IntegerField()
    inserted_count = models.IntegerField()
    updated_count = models.IntegerField()
    status = models.TextField()
    capped = models.BooleanField()
    error = models.TextField(blank=True)
    created_at = models.DateTimeField()
    finished_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "auditor_sync_queries"
        ordering = ["-created_at", "document_type"]

    def __str__(self):
        return f"{self.document_type} {self.start_date} to {self.end_date}"
