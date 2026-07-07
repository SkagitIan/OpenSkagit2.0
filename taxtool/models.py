from django.conf import settings
from django.db import models


class TaxShiftSignup(models.Model):
    RESOLUTION_PENDING = "pending"
    RESOLUTION_RESOLVED = "resolved"
    RESOLUTION_UNRESOLVED = "unresolved"
    RESOLUTION_AMBIGUOUS = "ambiguous"
    RESOLUTION_CHOICES = [
        (RESOLUTION_PENDING, "Pending"),
        (RESOLUTION_RESOLVED, "Resolved"),
        (RESOLUTION_UNRESOLVED, "Unresolved"),
        (RESOLUTION_AMBIGUOUS, "Ambiguous"),
    ]

    email = models.EmailField(unique=True)
    address_or_parcel = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=80, default="taxshift_home")
    parcel_number = models.TextField(blank=True)
    resolution_status = models.CharField(max_length=16, choices=RESOLUTION_CHOICES, default=RESOLUTION_PENDING)
    snapshot_captured_at = models.DateTimeField(blank=True, null=True)
    recorded_docs_snapshot = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    unsubscribed_at = models.DateTimeField(blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(blank=True, null=True)
    verification_email_sent_at = models.DateTimeField(blank=True, null=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="taxshift_signups",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["parcel_number"], name="taxtool_signup_parcel_idx"),
            models.Index(fields=["resolution_status"], name="taxtool_signup_status_idx"),
        ]

    def __str__(self):
        return self.email


class TaxShiftNotification(models.Model):
    TRIGGER_ASSESSOR = "assessor_change"
    TRIGGER_AUDITOR = "auditor_recording"
    TRIGGER_CHOICES = [
        (TRIGGER_ASSESSOR, "Assessor data change"),
        (TRIGGER_AUDITOR, "Auditor recording"),
    ]

    signup = models.ForeignKey(TaxShiftSignup, on_delete=models.CASCADE, related_name="notifications")
    parcel_number = models.TextField()
    trigger_type = models.CharField(max_length=24, choices=TRIGGER_CHOICES)
    payload = models.JSONField(default=dict)
    run_id = models.BigIntegerField()
    sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["signup", "parcel_number", "trigger_type", "run_id"],
                name="uniq_taxshift_notification",
            ),
        ]
        indexes = [
            models.Index(fields=["signup", "sent_at", "-created_at"], name="taxtool_notif_signup_idx"),
            models.Index(fields=["trigger_type", "sent_at"], name="taxtool_notif_trigger_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.signup_id}: {self.parcel_number} {self.trigger_type}"


class TaxShiftEmailTemplate(models.Model):
    WATCHLIST_DIGEST = "taxshift_watchlist_digest"
    VERIFICATION = "taxshift_verification"
    NAME_CHOICES = [
        (WATCHLIST_DIGEST, "TaxShift watchlist digest"),
        (VERIFICATION, "TaxShift verification + snapshot summary"),
    ]

    name = models.CharField(max_length=32, unique=True, choices=NAME_CHOICES)
    subject = models.TextField()
    body_html = models.TextField(
        help_text=(
            "Django template syntax. Watchlist digest variables: {{ signup }}, {{ changes }}, "
            "{{ unsubscribe_url }}, {{ site_url }}. Verification variables: {{ signup }}, "
            "{{ snapshot }}, {{ verify_url }}, {{ unsubscribe_url }}, {{ parcel_url }}, {{ site_url }}."
        )
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.get_name_display()


class LevyAreaMap(models.Model):
    levy_code = models.TextField(primary_key=True)
    area_label = models.TextField()
    parcel_count = models.IntegerField()
    median_rate = models.DecimalField(max_digits=10, decimal_places=4, blank=True, null=True)
    geometry = models.TextField(blank=True, null=True)
    rebuilt_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "levy_area_map"

    def __str__(self):
        return f"{self.levy_code} ({self.area_label})"


class ParcelSearchCache(models.Model):
    parcel_number = models.CharField(max_length=32, unique=True)
    situs_street_number = models.CharField(max_length=32, blank=True)
    situs_street_name = models.CharField(max_length=160, blank=True)
    situs_city_state_zip = models.CharField(max_length=160, blank=True)
    last_query = models.CharField(max_length=255, blank=True)
    last_source = models.CharField(max_length=40, default="search_result")
    hit_count = models.PositiveIntegerField(default=0)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_seen_at"]
        indexes = [
            models.Index(fields=["parcel_number"], name="taxtool_par_parcel__ffba79_idx"),
            models.Index(fields=["last_seen_at"], name="taxtool_par_last_se_8f9ffd_idx"),
        ]

    @property
    def address(self):
        parts = [self.situs_street_number, self.situs_street_name]
        street = " ".join(part for part in parts if part).strip()
        return ", ".join(part for part in [street, self.situs_city_state_zip] if part)

    def __str__(self):
        return f"{self.parcel_number} {self.address}".strip()
