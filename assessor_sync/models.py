from django.db import models


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
