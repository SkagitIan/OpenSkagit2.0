from django.db import models


class Jurisdiction(models.Model):
    key = models.SlugField(max_length=80, unique=True)
    display_name = models.CharField(max_length=160)
    code_source = models.CharField(max_length=160, blank=True)
    zoning_title = models.CharField(max_length=240, blank=True)
    source_url = models.URLField(blank=True)
    extraction_status = models.CharField(max_length=120, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_name"]

    def __str__(self) -> str:
        return self.display_name


class Zone(models.Model):
    jurisdiction = models.ForeignKey(Jurisdiction, on_delete=models.CASCADE, related_name="zones")
    zone_code = models.CharField(max_length=40)
    zone_name = models.CharField(max_length=240, blank=True)
    source_url = models.URLField(blank=True)

    class Meta:
        unique_together = [("jurisdiction", "zone_code")]
        ordering = ["jurisdiction__display_name", "zone_code"]

    def __str__(self) -> str:
        return f"{self.jurisdiction.key}:{self.zone_code}"


class ZoningUseRule(models.Model):
    STATUS_CHOICES = [
        ("P", "Permitted"),
        ("AC", "Accessory"),
        ("AD", "Administrative Review"),
        ("HE", "Hearing Examiner"),
        ("C", "Conditional"),
        ("CUP", "Conditional Use Permit"),
        ("X", "Prohibited"),
        ("UNKNOWN", "Unknown / Not Parsed"),
    ]

    jurisdiction = models.ForeignKey(Jurisdiction, on_delete=models.CASCADE, related_name="use_rules")
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name="use_rules")
    use_category = models.CharField(max_length=160, blank=True)
    use_name = models.CharField(max_length=240)
    normalized_use_key = models.SlugField(max_length=180)
    local_status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    normalized_status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    source_table = models.CharField(max_length=240, blank=True)
    source_url = models.URLField(blank=True)
    notes = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["jurisdiction", "zone", "normalized_use_key"]),
            models.Index(fields=["jurisdiction", "normalized_use_key", "normalized_status"]),
        ]
        unique_together = [("jurisdiction", "zone", "normalized_use_key", "source_table")]
        ordering = ["jurisdiction__display_name", "zone__zone_code", "use_category", "use_name"]

    def __str__(self) -> str:
        return f"{self.jurisdiction.key}:{self.zone.zone_code}:{self.normalized_use_key}={self.normalized_status}"


class ZoningCodeDocument(models.Model):
    jurisdiction = models.ForeignKey(Jurisdiction, on_delete=models.CASCADE, related_name="code_documents")
    title = models.CharField(max_length=240)
    chapter = models.CharField(max_length=120, blank=True)
    source_url = models.URLField(unique=True)
    text = models.TextField(blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["jurisdiction__display_name", "chapter", "title"]

    def __str__(self) -> str:
        return f"{self.jurisdiction.key}:{self.chapter or self.title}"


class ZoningCodeSection(models.Model):
    jurisdiction = models.ForeignKey(Jurisdiction, on_delete=models.CASCADE, related_name="code_sections")
    title = models.CharField(max_length=240)
    chapter_ref = models.CharField(max_length=120)
    chapter_title = models.CharField(max_length=240)
    section = models.CharField(max_length=40)
    heading = models.CharField(max_length=300)
    text = models.TextField(blank=True)
    source_url = models.URLField(unique=True)
    order = models.PositiveIntegerField(default=0)
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["jurisdiction", "section"]),
            models.Index(fields=["jurisdiction", "chapter_ref", "order"]),
        ]
        ordering = ["jurisdiction__display_name", "chapter_ref", "order"]

    def __str__(self) -> str:
        return f"{self.jurisdiction.key}:{self.section}"


class ZoningSourceTable(models.Model):
    jurisdiction = models.ForeignKey(Jurisdiction, on_delete=models.CASCADE, related_name="source_tables")
    title = models.CharField(max_length=240)
    chapter_ref = models.CharField(max_length=120)
    chapter_title = models.CharField(max_length=240)
    table_index = models.PositiveIntegerField(default=0)
    caption = models.CharField(max_length=300, blank=True)
    nearest_heading = models.CharField(max_length=300, blank=True)
    source_url = models.URLField()
    rows = models.JSONField(default=list)
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("jurisdiction", "chapter_ref", "table_index")]
        indexes = [
            models.Index(fields=["jurisdiction", "caption"]),
            models.Index(fields=["jurisdiction", "chapter_ref", "table_index"]),
        ]
        ordering = ["jurisdiction__display_name", "chapter_ref", "table_index"]

    def __str__(self) -> str:
        return f"{self.jurisdiction.key}:{self.caption or self.chapter_ref}"
