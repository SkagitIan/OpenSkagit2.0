"""
Models for the first SFR sales modeling dataset and baseline ratio-study tool.

These are all derived/cache tables, fully rebuilt from the source assessor,
land, improvement, geography, and zoning tables by
``build_sfr_sales_model_dataset``. Nothing here is a source of truth -- the
real assessor data lives in ``sales``, ``land``, ``improvements``,
``skagit_parcels``, etc. This app never writes to those tables.
"""

from __future__ import annotations

from django.db import models


class ModelLandSummary(models.Model):
    """One row per parcel, aggregated from the one-to-many ``land`` table."""

    parcel_number = models.TextField(unique=True)
    land_segment_count = models.IntegerField()
    total_land_acres = models.FloatField(null=True)
    total_land_market_value = models.FloatField(null=True)
    primary_land_type = models.TextField(null=True)
    primary_appr_method = models.TextField(null=True)
    has_open_space_value = models.BooleanField(default=False)
    max_land_segment_acres = models.FloatField(null=True)
    max_land_segment_value = models.FloatField(null=True)
    built_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "model_land_summary"
        ordering = ["parcel_number"]

    def __str__(self):
        return self.parcel_number


class ModelImprovementSummary(models.Model):
    """
    One row per parcel, aggregated from the one-to-many ``improvements`` table.

    The "primary" improvement is the row with the largest usable living area
    (falling back to largest improvement value when living area is missing on
    every row for that parcel). ``primary_imprv_id`` is kept so the selection
    can be audited against the source ``improvements`` row.
    """

    parcel_number = models.TextField(unique=True)
    improvement_row_count = models.IntegerField()
    building_count = models.IntegerField()
    total_improvement_value = models.FloatField(null=True)
    total_living_area = models.FloatField(null=True)

    primary_imprv_id = models.TextField(null=True)
    primary_living_area = models.FloatField(null=True)
    primary_building_style = models.TextField(null=True)
    primary_condition_cd = models.TextField(null=True)
    primary_condition_description = models.TextField(null=True)
    primary_imprv_det_type_cd = models.TextField(null=True)
    primary_imprv_det_class_cd = models.TextField(null=True)
    primary_imprv_det_type_description = models.TextField(null=True)
    primary_imprv_det_class_description = models.TextField(null=True)
    primary_actual_year_built = models.FloatField(null=True)
    primary_effective_year_built = models.FloatField(null=True)

    bedrooms = models.TextField(null=True)
    rooms = models.TextField(null=True)
    has_garage = models.BooleanField(default=False)
    has_fireplace = models.BooleanField(default=False)
    has_basement = models.BooleanField(default=False)

    built_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "model_improvement_summary"
        ordering = ["parcel_number"]

    def __str__(self):
        return self.parcel_number


class ModelSFRSalesExclusion(models.Model):
    """Every sale excluded from the SFR modeling dataset, with a stated reason."""

    saleid = models.TextField(null=True)
    parcel_number = models.TextField(null=True)
    sale_date_iso = models.TextField(null=True)
    sale_price_num = models.FloatField(null=True)
    exclusion_reason = models.TextField()
    details = models.TextField(blank=True)
    built_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "model_sfr_sales_exclusions"
        indexes = [models.Index(fields=["exclusion_reason"])]

    def __str__(self):
        return f"{self.saleid} excluded: {self.exclusion_reason}"


class ModelSFRSalesDataset(models.Model):
    """
    One row = one valid SFR sale. The first working modeling dataset.

    Labeled ``dataset_version = 'prototype_current_characteristics'`` --
    current parcel/improvement characteristics are joined to historical
    sales, which can contain temporal leakage. See docs/sfr_modeling_dataset_plan.md.
    """

    DATASET_VERSION = "prototype_current_characteristics"

    # Sale fields
    # saleid is NOT unique in the source `sales` table (~1,760 exact-duplicate
    # row groups even among valid, priced sales -- an import artifact, not a
    # multi-parcel-sale pattern). The pipeline drops exact-duplicate raw sale
    # rows before classification, but saleid still isn't a safe unique key on
    # its own, so this table uses the default auto id and indexes saleid instead.
    saleid = models.TextField()
    parcel_number = models.TextField()
    sale_date = models.DateField(null=True)
    sale_year = models.IntegerField(null=True)
    sale_month = models.IntegerField(null=True)
    sale_price = models.FloatField()
    log_sale_price = models.FloatField()
    deed_type = models.TextField(null=True)
    sale_type = models.TextField(null=True)
    reval_area = models.TextField(null=True)
    recording_number = models.TextField(null=True)
    excise_number = models.TextField(null=True)

    # Parcel fields
    neighborhood_code = models.TextField(null=True)
    neighborhood_description = models.TextField(null=True)
    land_use_code = models.TextField(null=True)
    land_use_description = models.TextField(null=True)
    proptype = models.TextField(null=True)
    tax_year = models.TextField(null=True)
    appraisal_year = models.TextField(null=True)
    assessed_value = models.FloatField(null=True)
    total_market_value = models.FloatField(null=True)
    building_value = models.FloatField(null=True)
    acres = models.FloatField(null=True)

    # Land summary fields
    land_segment_count = models.IntegerField(null=True)
    total_land_acres = models.FloatField(null=True)
    total_land_market_value = models.FloatField(null=True)
    primary_land_type = models.TextField(null=True)
    has_open_space_value = models.BooleanField(null=True)

    # Improvement summary fields
    improvement_row_count = models.IntegerField(null=True)
    building_count = models.IntegerField(null=True)
    total_improvement_value = models.FloatField(null=True)
    total_living_area = models.FloatField(null=True)
    primary_living_area = models.FloatField(null=True)
    primary_building_style = models.TextField(null=True)
    primary_condition_cd = models.TextField(null=True)
    primary_condition_description = models.TextField(null=True)
    primary_actual_year_built = models.FloatField(null=True)
    primary_effective_year_built = models.FloatField(null=True)
    primary_imprv_det_type_cd = models.TextField(null=True)
    primary_imprv_det_class_cd = models.TextField(null=True)
    bedrooms = models.TextField(null=True)
    rooms = models.TextField(null=True)
    has_garage = models.BooleanField(null=True)
    has_fireplace = models.BooleanField(null=True)
    has_basement = models.BooleanField(null=True)

    # Geo feature fields
    x = models.FloatField(null=True)
    y = models.FloatField(null=True)
    lat = models.FloatField(null=True)
    lon = models.FloatField(null=True)
    point_source = models.TextField(null=True)
    city_name = models.TextField(null=True)
    comp_plan_designation = models.TextField(null=True)
    school_district = models.TextField(null=True)
    fire_district = models.TextField(null=True)
    voting_precinct = models.TextField(null=True)
    historical_area_flag = models.BooleanField(null=True)
    distance_to_nearest_road_miles = models.FloatField(null=True)
    distance_to_mount_vernon_miles = models.FloatField(null=True)
    distance_to_burlington_miles = models.FloatField(null=True)
    distance_to_sedro_woolley_miles = models.FloatField(null=True)
    distance_to_anacortes_miles = models.FloatField(null=True)
    distance_to_la_conner_miles = models.FloatField(null=True)
    distance_to_nearest_public_place_miles = models.FloatField(null=True)
    distance_to_nearest_tide_gate_miles = models.FloatField(null=True)
    feature_status = models.TextField(null=True)

    # Zoning fields
    primary_zoning_code = models.TextField(null=True)
    primary_zoning_description = models.TextField(null=True)
    primary_zoning_overlap_percent = models.FloatField(null=True)
    zoning_general_category = models.TextField(null=True)

    dataset_version = models.TextField(default=DATASET_VERSION)
    built_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "model_sfr_sales_dataset"
        indexes = [
            models.Index(fields=["saleid"]),
            models.Index(fields=["parcel_number"]),
            models.Index(fields=["sale_year"]),
            models.Index(fields=["neighborhood_code"]),
        ]

    def __str__(self):
        return f"{self.saleid} ({self.parcel_number})"


class SFRDatasetBuildRun(models.Model):
    """
    One row per run of ``build_sfr_sales_model_dataset``.

    Persisted (not just written to data/reports/) so a UI/dashboard can show
    build history without depending on local files -- Railway's filesystem is
    ephemeral between deploys and data/reports/ is gitignored.
    """

    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"

    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True)
    status = models.TextField(default=STATUS_SUCCESS)
    error = models.TextField(blank=True)

    dataset_version = models.TextField(default=ModelSFRSalesDataset.DATASET_VERSION)
    total_sales_loaded = models.IntegerField(null=True)
    retained_sfr_sales = models.IntegerField(null=True)
    excluded_by_reason = models.JSONField(default=list)

    class Meta:
        db_table = "sfr_dataset_build_runs"
        ordering = ["-started_at"]

    def __str__(self):
        return f"Build {self.pk} ({self.status}, {self.retained_sfr_sales} retained)"


class SFRRatioStudyRun(models.Model):
    """
    One row per run of ``run_sfr_baseline_ratio_study``, with the full model
    comparison table stored as JSON so a UI can render it without re-running
    the models or reading data/reports/ files.
    """

    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"

    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True)
    status = models.TextField(default=STATUS_SUCCESS)
    error = models.TextField(blank=True)

    recent_years = models.IntegerField(null=True)
    window_start_year = models.IntegerField(null=True)
    window_end_year = models.IntegerField(null=True)
    train_count = models.IntegerField(null=True)
    test_count = models.IntegerField(null=True)
    primary_model = models.TextField(blank=True)

    model_comparison = models.JSONField(default=list)

    class Meta:
        db_table = "sfr_ratio_study_runs"
        ordering = ["-started_at"]

    def __str__(self):
        return f"Ratio study {self.pk} ({self.status}, {self.test_count} test sales)"


class SFRSegmentExperiment(models.Model):
    """
    One row per (neighborhood, attempt) made by ``run_neighborhood_compliance_loop``.

    Every attempt is logged, pass or fail, mechanical or AI-guided -- nothing
    is silently discarded, matching the ``model_sfr_sales_exclusions`` pattern.
    """

    ATTEMPT_MECHANICAL_RIDGE = "mechanical_ridge"
    ATTEMPT_MECHANICAL_RIDGE_GRID = "mechanical_ridge_grid"
    ATTEMPT_MECHANICAL_LASSO = "mechanical_lasso"
    ATTEMPT_AI_GUIDED = "ai_guided"

    segment_value = models.TextField()
    attempt_kind = models.TextField()
    attempt_number = models.IntegerField()
    train_count = models.IntegerField(null=True)
    test_count = models.IntegerField(null=True)
    metrics = models.JSONField(default=dict)
    passed = models.BooleanField(default=False)
    coefficients = models.JSONField(null=True, blank=True)
    ai_rationale = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sfr_segment_experiments"
        indexes = [
            models.Index(fields=["segment_value"]),
            models.Index(fields=["attempt_kind"]),
        ]
        ordering = ["segment_value", "attempt_number"]

    def __str__(self):
        return f"{self.segment_value} attempt {self.attempt_number} ({self.attempt_kind}, passed={self.passed})"


class SFRSegmentModel(models.Model):
    """
    One row per neighborhood -- the current best result of the compliance
    loop. Holds everything needed to reproduce a price prediction without
    re-fitting: coefficients, intercept, feature list (implicit in
    ``coefficients``' keys), and the imputation values used.
    """

    STATUS_COMPLIANT = "compliant"
    STATUS_PROVISIONAL = "provisional"
    STATUS_DROPPED = "dropped"
    STATUS_CHOICES = [
        (STATUS_COMPLIANT, "Compliant"),
        (STATUS_PROVISIONAL, "Provisional"),
        (STATUS_DROPPED, "Dropped"),
    ]

    segment_value = models.TextField(unique=True)
    model_name = models.TextField(blank=True)
    coefficients = models.JSONField(null=True, blank=True)
    feature_medians = models.JSONField(null=True, blank=True)
    metrics = models.JSONField(default=dict)
    sample_count = models.IntegerField(null=True)
    status = models.TextField(choices=STATUS_CHOICES)
    recommendation = models.TextField(blank=True)
    attempts_made = models.IntegerField(default=0)
    trained_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sfr_segment_models"
        indexes = [models.Index(fields=["status"])]
        ordering = ["segment_value"]

    def __str__(self):
        return f"{self.segment_value} ({self.status})"


class SFRComplianceLoopRun(models.Model):
    """
    One row per run of ``run_neighborhood_compliance_loop``, same run-log
    pattern as ``SFRDatasetBuildRun`` / ``SFRRatioStudyRun``.
    """

    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"

    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True)
    status = models.TextField(default=STATUS_SUCCESS)
    error = models.TextField(blank=True)

    segments_attempted = models.IntegerField(null=True)
    segments_compliant = models.IntegerField(null=True)
    segments_provisional = models.IntegerField(null=True)
    segments_dropped = models.IntegerField(null=True)
    ai_calls_made = models.IntegerField(null=True)

    class Meta:
        db_table = "sfr_compliance_loop_runs"
        ordering = ["-started_at"]

    def __str__(self):
        return f"Compliance loop {self.pk} ({self.status}, {self.segments_compliant} compliant)"
