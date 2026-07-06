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
