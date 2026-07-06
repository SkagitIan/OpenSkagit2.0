from django.db import models


class TaxShiftSignup(models.Model):
    email = models.EmailField(unique=True)
    address_or_parcel = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=80, default="taxshift_home")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email

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
