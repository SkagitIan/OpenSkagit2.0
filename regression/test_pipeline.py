"""
Tests for the pure pandas logic in regression/pipeline.py.

classify_sales/build_dataset_frame/build_exclusion_frame take plain
DataFrames and need no database, so these run as ordinary SimpleTestCase
tests. The SQL aggregation functions (fetch_land_summary,
fetch_improvement_summary, fetch_sales_join) were verified live against the
real database while building this milestone -- this repo's test-database
bootstrap is blocked by a pre-existing, unrelated migration issue (a `core`
migration builds SQL views over the unmanaged `assessor_rollup` table, which
never exists in a fresh test database), the same blocker noted in the two
prior milestones.
"""

from __future__ import annotations

import pandas as pd
from django.test import SimpleTestCase

from regression import pipeline

# A complete, valid-SFR-sale row. Individual tests override just the field(s)
# under test so each test stays readable.
_BASE_ROW = {
    "saleid": "S1",
    "parcel_number": "P1",
    "sale_price_num": 300000.0,
    "sale_date_iso": "2022-05-01",
    "deed_type": "WARRANTY DEED",
    "sale_type": "VALID SALE",
    "reval_area": "101",
    "recording_number": "R1",
    "excise_number": "E1",
    "neighborhood_code": "100",
    "neighborhood_description": "Some Neighborhood",
    "land_use": "(111) HOUSEHOLD, SFR, INSIDE CITY",
    "land_use_description": "HOUSEHOLD SFR INSIDE CITY",
    "proptype": "R",
    "buildingstyle": "ONE STORY",
    "tax_year": "2023",
    "appraisal_year": "2023",
    "assessed_value": 280000.0,
    "total_market_value": 300000.0,
    "building_value": 150000.0,
    "acres": 0.25,
    "inactive_date": None,
    "exemptions": "",
    "land_segment_count": 1,
    "total_land_acres": 0.25,
    "total_land_market_value": 80000.0,
    "primary_land_type": "CLEARED",
    "has_open_space_value": False,
    "improvement_row_count": 5,
    "building_count": 1,
    "total_improvement_value": 150000.0,
    "total_living_area": 1800.0,
    "primary_living_area": 1800.0,
    "primary_building_style": "ONE STORY",
    "primary_condition_cd": "A",
    "primary_condition_description": "Average",
    "primary_actual_year_built": 1995.0,
    "primary_effective_year_built": 1995.0,
    "primary_imprv_det_type_cd": "MA",
    "primary_imprv_det_class_cd": "MSA",
    "bedrooms": "3",
    "rooms": None,
    "has_garage": True,
    "has_fireplace": False,
    "has_basement": False,
    "x": 1200000.0,
    "y": 500000.0,
    "lat": 48.4,
    "lon": -122.3,
    "point_source": "parcel_numbers_point",
    "city_name": "MOUNT VERNON",
    "comp_plan_designation": "CITY",
    "school_district": "MOUNT VERNON",
    "fire_district": "MV",
    "voting_precinct": "1",
    "historical_area_flag": False,
    "distance_to_nearest_road_miles": 0.05,
    "distance_to_mount_vernon_miles": 0.5,
    "distance_to_burlington_miles": 5.0,
    "distance_to_sedro_woolley_miles": 8.0,
    "distance_to_anacortes_miles": 15.0,
    "distance_to_la_conner_miles": 10.0,
    "distance_to_nearest_public_place_miles": 0.3,
    "distance_to_nearest_tide_gate_miles": 3.0,
    "feature_status": "ok",
    "primary_zoning_code": "R3",
    "primary_zoning_description": "Residential",
    "primary_zoning_overlap_percent": 1.0,
}


def _rows(*overrides: dict) -> pd.DataFrame:
    return pd.DataFrame([{**_BASE_ROW, **override} for override in overrides])


class ClassifySalesTests(SimpleTestCase):
    def test_valid_sfr_sale_is_included(self):
        included, excluded = pipeline.classify_sales(_rows({}))
        self.assertEqual(len(included), 1)
        self.assertEqual(len(excluded), 0)

    def test_non_positive_price_excluded(self):
        included, excluded = pipeline.classify_sales(_rows({"sale_price_num": 0.0}))
        self.assertEqual(len(included), 0)
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "non_positive_sale_price")

    def test_missing_price_excluded(self):
        included, excluded = pipeline.classify_sales(_rows({"sale_price_num": None}))
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "missing_sale_price")

    def test_missing_sale_date_excluded(self):
        included, excluded = pipeline.classify_sales(_rows({"sale_date_iso": ""}))
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "missing_sale_date")

    def test_missing_parcel_match_excluded(self):
        included, excluded = pipeline.classify_sales(_rows({"land_use": None}))
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "missing_parcel_match")

    def test_non_arms_length_sale_type_excluded(self):
        included, excluded = pipeline.classify_sales(_rows({"sale_type": "FAMILY"}))
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "non_arms_length_sale_type")

    def test_mobile_home_excluded(self):
        included, excluded = pipeline.classify_sales(_rows({"land_use": "(180) MANUFACTURED HOMES"}))
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "mobile_or_manufactured_home")

    def test_wrong_proptype_excluded_even_with_core_sfr_land_use(self):
        # proptype is checked before the land-use rules, so it can exclude a
        # sale on its own even when the land_use code looks like core SFR.
        included, excluded = pipeline.classify_sales(_rows({"proptype": "M"}))
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "wrong_proptype")

    def test_condo_excluded(self):
        included, excluded = pipeline.classify_sales(_rows({"land_use": "(140) CONDO RESIDENTIAL"}))
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "condo")

    def test_multifamily_excluded(self):
        included, excluded = pipeline.classify_sales(_rows({"land_use": "(120) HOUSEHOLD, 2-4 UNITS"}))
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "multifamily_or_duplex_plus")

    def test_secondary_detached_unit_tracked_separately(self):
        included, excluded = pipeline.classify_sales(
            _rows({"land_use": "(112) HOUSEHOLD SFR, WITH A SECONDARY DETACHED UNIT"})
        )
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "secondary_detached_unit_present")

    def test_vacation_cabin_tracked_separately(self):
        included, excluded = pipeline.classify_sales(_rows({"land_use": "(190) VACATION AND CABIN"}))
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "vacation_cabin_use")

    def test_vacant_land_excluded(self):
        included, excluded = pipeline.classify_sales(_rows({"land_use": "(910) UNIMPROVED LAND"}))
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "vacant_or_undeveloped_land")

    def test_commercial_excluded(self):
        included, excluded = pipeline.classify_sales(_rows({"land_use": "(520) RETAIL TRADE"}))
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "commercial_or_industrial")

    def test_agricultural_excluded(self):
        included, excluded = pipeline.classify_sales(_rows({"land_use": "(830) CURRENT USE FARM AND AG"}))
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "agricultural_or_recreation_only")

    def test_attached_buildingstyle_excluded_despite_core_sfr_land_use(self):
        included, excluded = pipeline.classify_sales(
            _rows({"primary_building_style": "TOWNHOUSE - ATTACHED SFR UNITS"})
        )
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "attached_or_condo_buildingstyle")

    def test_no_usable_living_area_excluded(self):
        included, excluded = pipeline.classify_sales(_rows({"primary_living_area": None}))
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "no_usable_living_area")

    def test_no_usable_year_built_excluded(self):
        included, excluded = pipeline.classify_sales(
            _rows({"primary_actual_year_built": None, "primary_effective_year_built": None})
        )
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "no_usable_year_built")

    def test_no_usable_improvement_summary_excluded(self):
        row = dict(_BASE_ROW)
        for col in [
            "improvement_row_count", "building_count", "total_improvement_value", "total_living_area",
            "primary_living_area", "primary_building_style", "primary_condition_cd",
            "primary_condition_description", "primary_actual_year_built", "primary_effective_year_built",
            "primary_imprv_det_type_cd", "primary_imprv_det_class_cd", "bedrooms", "rooms",
            "has_garage", "has_fireplace", "has_basement",
        ]:
            row[col] = None
        included, excluded = pipeline.classify_sales(pd.DataFrame([row]))
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "no_usable_improvement_summary")

    def test_exempt_parcel_only_flagged_for_otherwise_valid_sfr(self):
        # A commercial parcel with an exemption should be excluded as commercial,
        # not "exempt" -- exempt_parcel is checked only after asset-class rules.
        included, excluded = pipeline.classify_sales(
            _rows({"land_use": "(520) RETAIL TRADE", "exemptions": "EX.CITY"})
        )
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "commercial_or_industrial")

        # A genuine core-SFR parcel with an exemption IS flagged as exempt_parcel.
        included, excluded = pipeline.classify_sales(_rows({"exemptions": "EX.CITY"}))
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "exempt_parcel")

    def test_first_applicable_rule_wins_not_multiple(self):
        # Non-positive price AND mobile home code both apply -- price check
        # (checked first) must win, so the mobile-home reason never fires.
        included, excluded = pipeline.classify_sales(
            _rows({"sale_price_num": 0.0, "land_use": "(180) MANUFACTURED HOMES", "proptype": "M"})
        )
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded.iloc[0]["exclusion_reason"], "non_positive_sale_price")

    def test_mixed_batch_partitions_correctly(self):
        df = _rows({"saleid": "GOOD"}, {"saleid": "BAD", "sale_price_num": 0.0})
        included, excluded = pipeline.classify_sales(df)
        self.assertEqual(list(included["saleid"]), ["GOOD"])
        self.assertEqual(list(excluded["saleid"]), ["BAD"])


class BuildDatasetFrameTests(SimpleTestCase):
    def test_dataset_frame_has_log_price_and_sale_year_month(self):
        included, _ = pipeline.classify_sales(_rows({}))
        dataset = pipeline.build_dataset_frame(included)
        row = dataset.iloc[0]
        self.assertEqual(row["sale_price"], 300000.0)
        self.assertAlmostEqual(row["log_sale_price"], 12.611538, places=4)
        self.assertEqual(row["sale_year"], 2022)
        self.assertEqual(row["sale_month"], 5)

    def test_exclusion_frame_carries_reason_and_detail(self):
        _, excluded = pipeline.classify_sales(_rows({"sale_type": "FAMILY"}))
        exclusion_frame = pipeline.build_exclusion_frame(excluded)
        row = exclusion_frame.iloc[0]
        self.assertEqual(row["exclusion_reason"], "non_arms_length_sale_type")
        self.assertEqual(row["details"], "FAMILY")


class RecordsHelperTests(SimpleTestCase):
    def test_nan_becomes_none_and_numpy_scalars_become_native(self):
        df = pd.DataFrame([{"a": 1, "b": float("nan"), "c": "x"}])
        df["a"] = df["a"].astype("Int64")
        rows = pipeline.records(df)
        self.assertEqual(rows, [{"a": 1, "b": None, "c": "x"}])
        self.assertIsInstance(rows[0]["a"], int)
