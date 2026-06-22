from django.db import models


class LandLedgerCitySummary(models.Model):
    city_slug = models.TextField(primary_key=True)
    city_name = models.TextField()
    parcel_count = models.IntegerField()
    zoned_count = models.IntegerField()
    unknown_zone_count = models.IntegerField()
    current_opportunity_10yr = models.DecimalField(max_digits=20, decimal_places=4)
    policy_opportunity_10yr = models.DecimalField(max_digits=20, decimal_places=4)
    diagnostics = models.JSONField(default=dict)
    scenario_definitions = models.JSONField(default=dict)
    zone_descriptions = models.JSONField(default=dict)
    buildout_factor = models.DecimalField(max_digits=10, decimal_places=4)
    horizon_years = models.IntegerField()
    rebuilt_at = models.DateTimeField()
    city_current_opportunity_10yr = models.DecimalField(max_digits=20, decimal_places=4)
    city_policy_opportunity_10yr = models.DecimalField(max_digits=20, decimal_places=4)
    eligible_parcel_count = models.IntegerField()
    excluded_parcel_count = models.IntegerField()
    scenario_totals = models.JSONField(default=dict)
    exclusion_counts = models.JSONField(default=dict)
    assumption_version = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "land_ledger_city_summary"

    def __str__(self):
        return self.city_name


class LandLedgerParcel(models.Model):
    city_slug = models.TextField()
    city_name = models.TextField()
    parcel_number = models.TextField(primary_key=True)
    address = models.TextField(blank=True, null=True)
    acres = models.DecimalField(max_digits=20, decimal_places=6, blank=True, null=True)
    land_use = models.TextField(blank=True, null=True)
    category = models.TextField(blank=True, null=True)
    zone_id = models.TextField(blank=True, null=True)
    zone_name = models.TextField(blank=True, null=True)
    zone_group = models.TextField(blank=True, null=True)
    current_tax = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True)
    tax_per_acre = models.DecimalField(max_digits=20, decimal_places=4, blank=True, null=True)
    city_tax_pct = models.DecimalField(max_digits=20, decimal_places=8, blank=True, null=True)
    allowed_scenarios = models.JSONField(default=list)
    policy_scenarios = models.JSONField(default=list)
    scenario_results = models.JSONField(default=dict)
    current_opportunity_10yr = models.DecimalField(max_digits=20, decimal_places=4)
    policy_opportunity_10yr = models.DecimalField(max_digits=20, decimal_places=4)
    benchmark_source = models.JSONField(default=dict)
    geometry = models.TextField(blank=True, null=True)
    rebuilt_at = models.DateTimeField()
    productivity_percentile = models.DecimalField(max_digits=20, decimal_places=8, blank=True, null=True)
    productivity_label = models.TextField(blank=True, null=True)
    city_current_opportunity_10yr = models.DecimalField(max_digits=20, decimal_places=4)
    city_policy_opportunity_10yr = models.DecimalField(max_digits=20, decimal_places=4)
    exclusion_reasons = models.JSONField(default=list)
    model_flags = models.JSONField(default=dict)
    assumption_version = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "land_ledger_parcels"

    def __str__(self):
        return self.parcel_number
