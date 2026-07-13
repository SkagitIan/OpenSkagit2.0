"""
Tests for the static parcel geography feature builder (build_geo_features).

Pure spatial algorithms (point resolution, rebuild detection, containment,
nearest-distance, anchor distance) are tested with SimpleTestCase using tiny
in-memory GeoDataFrames -- no database, no real shapefiles. The command's
upsert, per-parcel failure handling, and Parquet export need the database and
are tested with TestCase.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from shapely.geometry import LineString, Point, Polygon

from assessor_sync import geo_features as gf
from assessor_sync.management.commands.build_geo_features import Command
from assessor_sync.models import ParcelGeoStaticFeature

CRS = "EPSG:2926"


class RebuildDetectionTests(SimpleTestCase):
    def test_missing_feature_row_detected(self):
        resolved = pd.DataFrame(
            {"parcel_number": ["P1", "P2"], "x": [100.0, 200.0], "y": [50.0, 60.0], "point_source": ["parcel_numbers_point"] * 2}
        )
        existing = pd.DataFrame(
            {
                "parcel_number": ["P1"],
                "x": [100.0],
                "y": [50.0],
                "point_source": ["parcel_numbers_point"],
                "feature_status": ["ok"],
                "feature_version": [1],
            }
        )
        targets = gf.determine_rebuild_targets(resolved, existing, full=False, feature_version=1)
        self.assertEqual(targets, ["P2"])

    def test_changed_coordinate_detected_and_unchanged_skipped(self):
        existing = pd.DataFrame(
            {
                "parcel_number": ["P1"],
                "x": [100.0],
                "y": [50.0],
                "point_source": ["parcel_numbers_point"],
                "feature_status": ["ok"],
                "feature_version": [1],
            }
        )
        changed = pd.DataFrame({"parcel_number": ["P1"], "x": [105.0], "y": [50.0], "point_source": ["parcel_numbers_point"]})
        self.assertEqual(gf.determine_rebuild_targets(changed, existing, full=False, feature_version=1), ["P1"])

        unchanged = pd.DataFrame({"parcel_number": ["P1"], "x": [100.1], "y": [50.0], "point_source": ["parcel_numbers_point"]})
        self.assertEqual(
            gf.determine_rebuild_targets(unchanged, existing, full=False, feature_version=1, coordinate_tolerance_feet=0.5), []
        )

    def test_prior_failed_row_is_rebuilt(self):
        resolved = pd.DataFrame({"parcel_number": ["P1"], "x": [100.0], "y": [50.0], "point_source": ["parcel_numbers_point"]})
        existing = pd.DataFrame(
            {
                "parcel_number": ["P1"],
                "x": [100.0],
                "y": [50.0],
                "point_source": ["parcel_numbers_point"],
                "feature_status": ["failed"],
                "feature_version": [1],
            }
        )
        self.assertEqual(gf.determine_rebuild_targets(resolved, existing, full=False, feature_version=1), ["P1"])

    def test_full_mode_rebuilds_everything_regardless_of_existing(self):
        resolved = pd.DataFrame({"parcel_number": ["P1", "P2"], "x": [1.0, 2.0], "y": [1.0, 2.0], "point_source": ["a", "a"]})
        existing = pd.DataFrame(
            {
                "parcel_number": ["P1", "P2"],
                "x": [1.0, 2.0],
                "y": [1.0, 2.0],
                "point_source": ["a", "a"],
                "feature_status": ["ok", "ok"],
                "feature_version": [1, 1],
            }
        )
        self.assertEqual(sorted(gf.determine_rebuild_targets(resolved, existing, full=True)), ["P1", "P2"])


class PointResolutionTests(SimpleTestCase):
    def test_point_created_from_parcel_numbers_xy(self):
        parcel_numbers_gdf = gpd.GeoDataFrame({"PNUMBER": ["P1", "P2"]}, geometry=[Point(100, 50), Point(200, 60)], crs=CRS)
        parcels_gdf = gpd.GeoDataFrame({"PARCELID": []}, geometry=[], crs=CRS)

        resolved = gf.resolve_parcel_points(pd.Series(["P1", "P2"], name="parcel_number"), None, parcel_numbers_gdf, parcels_gdf)

        row = resolved[resolved["parcel_number"] == "P1"].iloc[0]
        self.assertEqual(row["x"], 100.0)
        self.assertEqual(row["y"], 50.0)
        self.assertEqual(row["point_source"], gf.SOURCE_PARCEL_NUMBERS_POINT)

    def test_point_falls_back_to_parcel_centroid(self):
        parcel_numbers_gdf = gpd.GeoDataFrame({"PNUMBER": []}, geometry=[], crs=CRS)
        square = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        parcels_gdf = gpd.GeoDataFrame({"PARCELID": ["P3"]}, geometry=[square], crs=CRS)

        resolved = gf.resolve_parcel_points(pd.Series(["P3"], name="parcel_number"), None, parcel_numbers_gdf, parcels_gdf)

        row = resolved.iloc[0]
        self.assertAlmostEqual(row["x"], 5.0)
        self.assertAlmostEqual(row["y"], 5.0)
        self.assertEqual(row["point_source"], gf.SOURCE_PARCEL_CENTROID)

    def test_point_missing_when_no_source_available(self):
        empty_points = gpd.GeoDataFrame({"PNUMBER": []}, geometry=[], crs=CRS)
        empty_polygons = gpd.GeoDataFrame({"PARCELID": []}, geometry=[], crs=CRS)

        resolved = gf.resolve_parcel_points(pd.Series(["P9"], name="parcel_number"), None, empty_points, empty_polygons)

        row = resolved.iloc[0]
        self.assertTrue(pd.isna(row["x"]))
        self.assertIsNone(row["point_source"])


class ContainmentTests(SimpleTestCase):
    def test_polygon_containment(self):
        square = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        polygons_gdf = gpd.GeoDataFrame({"NAME": ["CITY_A"]}, geometry=[square], crs=CRS)
        points_gdf = gpd.GeoDataFrame({"parcel_number": ["P1", "P2"]}, geometry=[Point(5, 5), Point(50, 50)], crs=CRS)

        result = gf.containment_lookup(points_gdf, polygons_gdf, "NAME")

        self.assertEqual(result["P1"], "CITY_A")
        self.assertTrue(pd.isna(result["P2"]))

    def test_containment_prefers_non_null_on_overlap(self):
        # A large background polygon with no designation overlapping a real
        # zoning polygon -- mirrors comp_plan.shp's water-body overlay.
        background = Polygon([(-100, -100), (100, -100), (100, 100), (-100, 100)])
        real_zone = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        polygons_gdf = gpd.GeoDataFrame({"NAME": [None, "ZONE_X"]}, geometry=[background, real_zone], crs=CRS)
        points_gdf = gpd.GeoDataFrame({"parcel_number": ["P1"]}, geometry=[Point(5, 5)], crs=CRS)

        result = gf.containment_lookup(points_gdf, polygons_gdf, "NAME")

        self.assertEqual(result["P1"], "ZONE_X")

    def test_historical_flag_from_parcel_polygon_containment(self):
        parcel_polygons = gpd.GeoDataFrame(
            {"parcel_number": ["P1", "P2"]},
            geometry=[Polygon([(0, 0), (10, 0), (10, 10), (0, 10)]), Polygon([(100, 100), (110, 100), (110, 110), (100, 110)])],
            crs=CRS,
        )
        historical_points = gpd.GeoDataFrame({"Name": ["Old Barn"]}, geometry=[Point(5, 5)], crs=CRS)

        flags = gf.historical_containment_flags(parcel_polygons, historical_points)

        self.assertEqual(flags, {"P1"})


class NearestDistanceTests(SimpleTestCase):
    def test_nearest_road_distance(self):
        road_a = LineString([(0, 0), (0, 100)])
        road_b = LineString([(50, 0), (50, 100)])
        roads_gdf = gpd.GeoDataFrame({"ROAD_LABEL": ["Road A", "Road B"]}, geometry=[road_a, road_b], crs=CRS)
        points_gdf = gpd.GeoDataFrame({"parcel_number": ["P1"]}, geometry=[Point(10, 50)], crs=CRS)

        result = gf.nearest_lookup(points_gdf, roads_gdf, name_col="ROAD_LABEL")

        row = result.loc["P1"]
        self.assertEqual(row["ROAD_LABEL"], "Road A")
        self.assertAlmostEqual(row["distance_feet"], 10.0)

    def test_anchor_distance_in_miles(self):
        points_gdf = gpd.GeoDataFrame({"parcel_number": ["P1"]}, geometry=[Point(0, 0)], crs=CRS)
        anchors = {"distance_to_mount_vernon_miles": Point(gf.FEET_PER_MILE, 0)}

        result = gf.anchor_distances_miles(points_gdf, anchors)

        self.assertAlmostEqual(result.loc["P1", "distance_to_mount_vernon_miles"], 1.0)


def _tiny_layers() -> dict:
    """A minimal but complete set of extracted-layer GeoDataFrames covering (0,0)-(20,20)."""
    square = Polygon([(0, 0), (20, 0), (20, 20), (0, 20)])
    return {
        "parcels": gpd.GeoDataFrame({"PARCELID": ["P_GOOD", "P_BAD"]}, geometry=[square, square], crs=CRS),
        "city_limits": gpd.GeoDataFrame({"NAME": ["TESTVILLE"]}, geometry=[square], crs=CRS),
        "comp_plan": gpd.GeoDataFrame({"LUD": ["A"], "LUD_ZONING": ["Ag-NRL"]}, geometry=[square], crs=CRS),
        "school_districts": gpd.GeoDataFrame({"NAME": ["TEST SCHOOL"]}, geometry=[square], crs=CRS),
        "fire_districts": gpd.GeoDataFrame({"DISTRICT": ["1"]}, geometry=[square], crs=CRS),
        "voting_precincts": gpd.GeoDataFrame({"PRECINCT": ["1"]}, geometry=[square], crs=CRS),
        "historical": gpd.GeoDataFrame({"Name": []}, geometry=[], crs=CRS),
        "roads": gpd.GeoDataFrame(
            {"ROAD_NM": ["MAIN"], "ROAD_DES": ["Street"]}, geometry=[LineString([(0, 0), (0, 20)])], crs=CRS
        ),
        "public_places": gpd.GeoDataFrame({"NAME": ["TOWN HALL"]}, geometry=[Point(1, 1)], crs=CRS),
        "tide_gates": gpd.GeoDataFrame({"NAME": []}, geometry=[], crs=CRS),
    }


class UpsertAndFailureHandlingTests(TestCase):
    def setUp(self):
        self.command = Command()
        # build_geo_features derives comp_plan/roads helper columns during
        # _load_layers(); tiny fixture layers bypass that method, so add them here.
        self.layers = _tiny_layers()
        self.layers["comp_plan"]["DESIGNATION"] = self.layers["comp_plan"]["LUD_ZONING"]
        self.layers["roads"]["ROAD_LABEL"] = self.layers["roads"]["ROAD_NM"] + " " + self.layers["roads"]["ROAD_DES"]

    def _target_points(self, parcel_numbers):
        return pd.DataFrame(
            {
                "parcel_number": parcel_numbers,
                "x": [5.0] * len(parcel_numbers),
                "y": [5.0] * len(parcel_numbers),
                "point_source": [gf.SOURCE_PARCEL_NUMBERS_POINT] * len(parcel_numbers),
            }
        )

    def test_upsert_without_duplicates(self):
        rows = [
            {
                "parcel_number": "P1",
                "feature_status": ParcelGeoStaticFeature.STATUS_OK,
                "feature_version": gf.FEATURE_VERSION,
                "city_name": "FIRST",
                "historical_area_flag": False,
                "missing_coordinate_flag": False,
            }
        ]
        self.command._upsert(rows)
        self.command._upsert(rows)  # same parcel_number again -- must update, not duplicate

        self.assertEqual(ParcelGeoStaticFeature.objects.filter(parcel_number="P1").count(), 1)

        rows[0]["city_name"] = "UPDATED"
        self.command._upsert(rows)
        feature = ParcelGeoStaticFeature.objects.get(parcel_number="P1")
        self.assertEqual(feature.city_name, "UPDATED")
        self.assertEqual(ParcelGeoStaticFeature.objects.filter(parcel_number="P1").count(), 1)

    def test_failed_parcel_does_not_stop_other_parcels(self):
        original_ok_row = self.command._ok_row

        def flaky_ok_row(point_row, computed):
            if point_row["parcel_number"] == "P_BAD":
                raise ValueError("simulated failure")
            return original_ok_row(point_row, computed)

        self.command._ok_row = flaky_ok_row

        target_points = self._target_points(["P_GOOD", "P_BAD"])
        rows, counts = self.command._build_rows(target_points, self.layers)

        self.assertEqual(counts["failed"], 1)
        self.assertEqual(counts["updated"], 1)
        by_parcel = {row["parcel_number"]: row for row in rows}
        self.assertEqual(by_parcel["P_BAD"]["feature_status"], ParcelGeoStaticFeature.STATUS_FAILED)
        self.assertEqual(by_parcel["P_GOOD"]["feature_status"], ParcelGeoStaticFeature.STATUS_OK)

        self.command._upsert(rows)
        self.assertEqual(ParcelGeoStaticFeature.objects.get(parcel_number="P_BAD").feature_status, ParcelGeoStaticFeature.STATUS_FAILED)
        self.assertEqual(ParcelGeoStaticFeature.objects.get(parcel_number="P_GOOD").feature_status, ParcelGeoStaticFeature.STATUS_OK)

    def test_missing_coordinates_marks_status_and_flag(self):
        target_points = pd.DataFrame({"parcel_number": ["P_NONE"], "x": [np.nan], "y": [np.nan], "point_source": [None]})
        rows, counts = self.command._build_rows(target_points, self.layers)

        self.assertEqual(counts["missing"], 1)
        self.assertEqual(rows[0]["feature_status"], ParcelGeoStaticFeature.STATUS_MISSING_COORDINATES)
        self.assertTrue(rows[0]["missing_coordinate_flag"])


class ParquetExportTests(TestCase):
    def test_export_writes_parquet_with_expected_rows(self):
        ParcelGeoStaticFeature.objects.create(parcel_number="P1", feature_status="ok", city_name="ANACORTES")
        ParcelGeoStaticFeature.objects.create(parcel_number="P2", feature_status="missing_coordinates")

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "parcel_geo_static_features.parquet"
            call_command("export_geo_features_parquet", output=str(output_path))

            self.assertTrue(output_path.exists())
            frame = pd.read_parquet(output_path)
            self.assertEqual(len(frame), 2)
            self.assertEqual(set(frame["parcel_number"]), {"P1", "P2"})
            self.assertEqual(frame.set_index("parcel_number").loc["P1", "city_name"], "ANACORTES")
