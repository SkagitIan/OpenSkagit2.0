from django.db import models


class CurrentDraft(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        REJECTED = "rejected", "Rejected"
        ARCHIVED = "archived", "Archived"
        PUBLISHED = "published", "Published"

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    probe = models.TextField()
    model = models.TextField(blank=True)
    question = models.TextField()
    short_answer = models.TextField(blank=True)
    why_it_matters = models.TextField(blank=True)
    confidence = models.IntegerField(blank=True, null=True)
    publish_score = models.IntegerField(blank=True, null=True)
    source_data = models.TextField(blank=True)
    caveats = models.JSONField(default=list, blank=True)
    what_to_check_next = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    row_count = models.IntegerField(default=0)
    qa_flags = models.JSONField(default=list, blank=True)
    probe_metadata = models.JSONField(default=dict, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "core_currentdraft"
        ordering = ["-publish_score", "-created_at"]

    def __str__(self):
        return self.question[:120]
