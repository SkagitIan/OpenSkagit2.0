from django.conf import settings
from django.db import models
from django.utils import timezone


class OpportunitySavedParcel(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="opportunity_saved_parcels")
    parcel_number = models.TextField()
    source_tab = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "parcel_number"], name="uniq_opportunity_saved_user_parcel"),
        ]
        indexes = [
            models.Index(fields=["user", "-updated_at"]),
            models.Index(fields=["parcel_number"]),
        ]
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user_id}: {self.parcel_number}"


class OpportunitySearch(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_READY = "ready"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_READY, "Ready"),
        (STATUS_ERROR, "Error"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="opportunity_searches")
    prompt = models.TextField()
    title = models.TextField(blank=True)
    criteria_summary = models.TextField(blank=True)
    assumptions = models.JSONField(default=list)
    search_plan = models.JSONField(default=dict)
    plan_review = models.JSONField(default=dict)
    result_diagnostics = models.JSONField(default=dict)
    generated_sql = models.TextField(blank=True)
    generated_params = models.JSONField(default=list)
    model = models.TextField(blank=True)
    result_rows = models.JSONField(default=list)
    result_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    error = models.TextField(blank=True)
    saved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-updated_at"], name="opp_search_user_updated_idx"),
            models.Index(fields=["user", "-saved_at"], name="opp_search_user_saved_idx"),
            models.Index(fields=["status", "-updated_at"], name="opp_search_status_upd_idx"),
        ]
        ordering = ["-updated_at"]

    @property
    def is_saved(self):
        return self.saved_at is not None

    def mark_saved(self):
        if not self.saved_at:
            self.saved_at = timezone.now()
            self.save(update_fields=["saved_at", "updated_at"])

    def __str__(self):
        return self.title or self.prompt[:80]


class OpportunitySearchFeedback(models.Model):
    RATING_GOOD = "good"
    RATING_BAD = "bad"
    RATING_CHOICES = [
        (RATING_GOOD, "Good match"),
        (RATING_BAD, "Bad match"),
    ]

    REASON_CHOICES = [
        ("too_broad", "Too broad"),
        ("too_narrow", "Too narrow"),
        ("wrong_location", "Wrong location"),
        ("wrong_parcel_type", "Wrong parcel type"),
        ("missing_utilities", "Missing utilities"),
        ("already_improved", "Already improved"),
        ("bad_data", "Bad data"),
        ("other", "Other"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="opportunity_search_feedback")
    search = models.ForeignKey(OpportunitySearch, on_delete=models.CASCADE, related_name="feedback")
    rating = models.CharField(max_length=12, choices=RATING_CHOICES)
    parcel_number = models.TextField(blank=True)
    reason_code = models.CharField(max_length=32, choices=REASON_CHOICES, blank=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "search", "parcel_number"], name="uniq_opportunity_search_feedback_scope"),
        ]
        indexes = [
            models.Index(fields=["user", "-updated_at"], name="opp_fb_user_updated_idx"),
            models.Index(fields=["search", "rating"], name="opp_fb_search_rating_idx"),
            models.Index(fields=["parcel_number"], name="opp_fb_parcel_idx"),
        ]
        ordering = ["-updated_at"]

    def __str__(self):
        scope = self.parcel_number or "search"
        return f"{self.user_id}: {self.search_id} {scope} {self.rating}"


class UserNotificationPreference(models.Model):
    CADENCE_DAILY = "daily"
    CADENCE_WEEKLY = "weekly"
    CADENCE_CHOICES = [
        (CADENCE_DAILY, "Daily digest"),
        (CADENCE_WEEKLY, "Weekly digest"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_pref"
    )
    notify_watchlist = models.BooleanField(default=False)
    digest_cadence = models.CharField(max_length=8, choices=CADENCE_CHOICES, default=CADENCE_DAILY)
    notify_brief = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Notification prefs for {self.user_id}"


class ParcelWatchNotification(models.Model):
    TRIGGER_ASSESSOR = "assessor_change"
    TRIGGER_AUDITOR = "auditor_recording"
    TRIGGER_BRIEF = "brief"
    TRIGGER_CHOICES = [
        (TRIGGER_ASSESSOR, "Assessor data change"),
        (TRIGGER_AUDITOR, "Auditor recording"),
        (TRIGGER_BRIEF, "Daily brief"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="parcel_watch_notifications"
    )
    parcel_number = models.TextField(blank=True)
    trigger_type = models.CharField(max_length=24, choices=TRIGGER_CHOICES)
    payload = models.JSONField(default=dict)
    run_id = models.BigIntegerField()
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "parcel_number", "trigger_type", "run_id"],
                name="uniq_parcel_watch_notification",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "sent_at", "-created_at"]),
            models.Index(fields=["trigger_type", "sent_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id}: {self.parcel_number} {self.trigger_type}"


class EmailTemplate(models.Model):
    WATCHLIST_DIGEST = "watchlist_digest"
    DAILY_BRIEF = "daily_brief"
    NAME_CHOICES = [
        (WATCHLIST_DIGEST, "Watchlist change digest"),
        (DAILY_BRIEF, "Daily brief / newsletter"),
    ]

    name = models.CharField(max_length=32, unique=True, choices=NAME_CHOICES)
    subject = models.TextField()
    body_html = models.TextField(help_text="Django template syntax. Variables: {{ user }}, {{ changes }}, {{ site_url }} for digest; {{ user }}, {{ narrative }}, {{ site_url }} for brief.")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.get_name_display()


class ParcelBookSyncNarrative(models.Model):
    assessor_sync_report = models.OneToOneField(
        "assessor_sync.AssessorSyncReport",
        on_delete=models.CASCADE,
        related_name="parcel_book_narrative",
    )
    model = models.TextField(blank=True)
    headline = models.TextField()
    dek = models.TextField(blank=True)
    narrative = models.TextField()
    bullets = models.JSONField(default=list)
    notable_signals = models.JSONField(default=list)
    trend_line = models.TextField(blank=True)
    disclaimer = models.TextField(blank=True)
    newsletter_subject = models.TextField(blank=True)
    preview_text = models.TextField(blank=True)
    summary_snapshot = models.JSONField(default=dict)
    brief_context = models.JSONField(default=dict)
    generated_by_ai = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["generated_by_ai", "-created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Parcel Book narrative for report {self.assessor_sync_report_id}"
