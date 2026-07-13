"""
build_geo_features -- build the static parcel geography feature table.

Reads active parcels from the assessor database, resolves one point per
parcel, and computes precomputed geography (containing city/district/
precinct, nearest road/public place/tide gate, distance to fixed city
anchors) using the shapefiles ``sync_gis_sources`` already downloaded and
extracted. Results are upserted into ``parcel_geo_static_features``.

No regression modeling, no nearby-sales features, no GIS warehouse -- this
is the first static geography feature builder only.
"""

from __future__ import annotations

import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from pyproj import Transformer

from assessor_sync import geo_features as gf
from assessor_sync.models import ParcelGeoStaticFeature

# Layers this command needs from data/gis/extracted/<name>/, and the field
# each one contributes. Field names come from Skagit County's actual shapefile
# attribute tables (confirmed against the real downloaded files).
CONTAINMENT_LAYERS = {
    "city_limits": ("NAME", "city_name"),
    "school_districts": ("NAME", "school_district"),
    "fire_districts": ("DISTRICT", "fire_district"),
    "voting_precincts": ("PRECINCT", "voting_precinct"),
}


class Command(BaseCommand):
    help = "Build data/gis-derived static geography features for active parcels."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--full", action="store_true", help="Rebuild all active parcels.")
        mode.add_argument(
            "--missing-or-changed",
            action="store_true",
            help="Rebuild only parcels with a missing/failed/stale feature row (default).",
        )
        parser.add_argument("--parcel", metavar="PARCEL_NUMBER", help="Rebuild one parcel by number.")
        parser.add_argument("--limit", type=int, help="Only process this many parcels needing rebuild (for testing).")

    def handle(self, *args, **options):
        started = time.monotonic()
        extracted_root = Path(settings.BASE_DIR) / "data" / "gis" / "extracted"

        active_parcel_numbers = self._load_active_parcel_numbers(options["parcel"])
        if options["parcel"] and not active_parcel_numbers:
            raise CommandError(f"Parcel '{options['parcel']}' was not found in assessor_rollup.")

        layers = self._load_layers(extracted_root)
        resolved = gf.resolve_parcel_points(
            pd.Series(active_parcel_numbers, name="parcel_number"),
            assessor_xy=None,  # no X/Y columns exist on assessor_rollup today
            parcel_numbers_gdf=layers["parcel_numbers"],
            parcels_gdf=layers["parcels"],
        )

        full = bool(options["full"] or options["parcel"])
        existing = self._load_existing_features()
        if options["parcel"]:
            targets = active_parcel_numbers
        else:
            targets = gf.determine_rebuild_targets(resolved, existing, full=full)
            if options["limit"]:
                targets = sorted(targets)[: options["limit"]]

        target_set = set(targets)
        target_points = resolved[resolved["parcel_number"].isin(target_set)].copy()

        rows, counts = self._build_rows(target_points, layers)
        self._upsert(rows)

        runtime = time.monotonic() - started
        self._print_summary(len(active_parcel_numbers), len(targets), counts, runtime)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def _load_active_parcel_numbers(self, single_parcel: str | None) -> list[str]:
        with connection.cursor() as cursor:
            if single_parcel:
                cursor.execute("SELECT DISTINCT parcel_number FROM assessor_rollup WHERE parcel_number = %s", (single_parcel,))
            else:
                cursor.execute(
                    "SELECT DISTINCT parcel_number FROM assessor_rollup "
                    "WHERE inactive_date IS NULL OR inactive_date = '' "
                    "ORDER BY parcel_number"
                )
            return [row[0] for row in cursor.fetchall()]

    def _load_existing_features(self) -> pd.DataFrame:
        rows = list(
            ParcelGeoStaticFeature.objects.values(
                "parcel_number", "x", "y", "point_source", "feature_status", "feature_version"
            )
        )
        if not rows:
            return pd.DataFrame(columns=["parcel_number", "x", "y", "point_source", "feature_status", "feature_version"])
        return pd.DataFrame(rows)

    def _load_layer(self, extracted_root: Path, layer_name: str) -> gpd.GeoDataFrame:
        layer_dir = extracted_root / layer_name
        if not any(layer_dir.glob("*.shp")):
            raise CommandError(
                f"No extracted shapefile for '{layer_name}' in {layer_dir}. "
                f"Run 'python manage.py sync_gis_sources' first."
            )
        gdf = gpd.read_file(layer_dir)
        return gf.force_crs(gdf)

    def _load_layers(self, extracted_root: Path) -> dict[str, gpd.GeoDataFrame]:
        names = [
            "parcels",
            "parcel_numbers",
            "city_limits",
            "comp_plan",
            "school_districts",
            "fire_districts",
            "voting_precincts",
            "historical",
            "roads",
            "public_places",
            "tide_gates",
        ]
        layers = {name: self._load_layer(extracted_root, name) for name in names}

        # comp_plan_designation prefers the human-readable zoning label
        # (LUD_ZONING); a handful of rows only carry the coarser LUD code.
        comp_plan = layers["comp_plan"]
        comp_plan["DESIGNATION"] = comp_plan["LUD_ZONING"].where(
            comp_plan["LUD_ZONING"].notna() & (comp_plan["LUD_ZONING"].astype(str).str.strip() != ""),
            comp_plan["LUD"],
        )
        layers["comp_plan"] = comp_plan

        roads = layers["roads"]
        roads["ROAD_LABEL"] = (roads["ROAD_NM"].fillna("").astype(str).str.strip() + " " + roads["ROAD_DES"].fillna("").astype(str).str.strip()).str.strip()
        layers["roads"] = roads

        return layers

    # ------------------------------------------------------------------
    # Computation
    # ------------------------------------------------------------------
    def _build_rows(self, target_points: pd.DataFrame, layers: dict) -> tuple[list[dict], dict]:
        missing_mask = target_points["x"].isna()
        missing = target_points.loc[missing_mask, "parcel_number"].tolist()
        present = target_points.loc[~missing_mask].copy()

        computed_by_parcel: dict[str, dict] = {}
        if not present.empty:
            computed_by_parcel = self._compute_geography(present, layers)

        rows = []
        failed = 0
        for parcel_number in missing:
            rows.append(self._missing_row(parcel_number))

        for _, point_row in present.iterrows():
            parcel_number = point_row["parcel_number"]
            try:
                rows.append(self._ok_row(point_row, computed_by_parcel.get(parcel_number, {})))
            except Exception as exc:  # noqa: BLE001 -- one bad parcel must not stop the run
                failed += 1
                rows.append(self._failed_row(parcel_number, str(exc)))

        counts = {
            "updated": sum(1 for r in rows if r["feature_status"] == ParcelGeoStaticFeature.STATUS_OK),
            "missing": len(missing),
            "failed": failed,
        }
        return rows, counts

    def _compute_geography(self, present: pd.DataFrame, layers: dict) -> dict[str, dict]:
        points_gdf = gpd.GeoDataFrame(
            present[["parcel_number"]],
            geometry=gpd.points_from_xy(present["x"], present["y"]),
            crs=f"EPSG:{gf.WORKING_EPSG}",
        )

        result: dict[str, dict] = {pn: {} for pn in present["parcel_number"]}

        for layer_name, (attr_col, feature_field) in CONTAINMENT_LAYERS.items():
            values = gf.containment_lookup(points_gdf, layers[layer_name], attr_col)
            for parcel_number, value in values.items():
                if pd.notna(value):
                    result[parcel_number][feature_field] = value

        comp_plan_values = gf.containment_lookup(points_gdf, layers["comp_plan"], "DESIGNATION")
        for parcel_number, value in comp_plan_values.items():
            if pd.notna(value):
                result[parcel_number]["comp_plan_designation"] = value

        parcel_polygons = gpd.GeoDataFrame(
            layers["parcels"][["PARCELID", "geometry"]].rename(columns={"PARCELID": "parcel_number"})
        )
        parcel_polygons = parcel_polygons[parcel_polygons["parcel_number"].isin(present["parcel_number"])]
        historical_flags = gf.historical_containment_flags(parcel_polygons, layers["historical"])
        for parcel_number in historical_flags:
            if parcel_number in result:
                result[parcel_number]["historical_area_flag"] = True

        nearest_roads = gf.nearest_lookup(points_gdf, layers["roads"], name_col="ROAD_LABEL")
        for parcel_number, row in nearest_roads.iterrows():
            result[parcel_number]["nearest_road_name"] = row["ROAD_LABEL"]
            result[parcel_number]["distance_to_nearest_road_feet"] = row["distance_feet"]
            result[parcel_number]["distance_to_nearest_road_miles"] = row["distance_feet"] / gf.FEET_PER_MILE

        nearest_places = gf.nearest_lookup(points_gdf, layers["public_places"], name_col="NAME")
        for parcel_number, row in nearest_places.iterrows():
            result[parcel_number]["nearest_public_place_name"] = row["NAME"]
            result[parcel_number]["distance_to_nearest_public_place_miles"] = row["distance_feet"] / gf.FEET_PER_MILE

        nearest_tide_gates = gf.nearest_lookup(points_gdf, layers["tide_gates"], name_col=None)
        for parcel_number, row in nearest_tide_gates.iterrows():
            result[parcel_number]["distance_to_nearest_tide_gate_miles"] = row["distance_feet"] / gf.FEET_PER_MILE

        anchors = gf.market_anchor_points(layers["city_limits"])
        anchor_df = gf.anchor_distances_miles(points_gdf, anchors)
        for parcel_number, row in anchor_df.iterrows():
            for column in anchors:
                result[parcel_number][column] = row[column]

        transformer = Transformer.from_crs(f"EPSG:{gf.WORKING_EPSG}", "EPSG:4326", always_xy=True)
        lons, lats = transformer.transform(present["x"].values, present["y"].values)
        for parcel_number, lon, lat in zip(present["parcel_number"], lons, lats):
            result[parcel_number]["lon"] = float(lon)
            result[parcel_number]["lat"] = float(lat)

        return result

    # ------------------------------------------------------------------
    # Row assembly
    # ------------------------------------------------------------------
    def _missing_row(self, parcel_number: str) -> dict:
        return {
            "parcel_number": parcel_number,
            "prop_id": None,
            "x": None,
            "y": None,
            "lat": None,
            "lon": None,
            "point_source": None,
            "historical_area_flag": False,
            "missing_coordinate_flag": True,
            "feature_status": ParcelGeoStaticFeature.STATUS_MISSING_COORDINATES,
            "feature_version": gf.FEATURE_VERSION,
        }

    def _ok_row(self, point_row: pd.Series, computed: dict) -> dict:
        return {
            "parcel_number": point_row["parcel_number"],
            "prop_id": None,
            "x": float(point_row["x"]),
            "y": float(point_row["y"]),
            "lat": computed.get("lat"),
            "lon": computed.get("lon"),
            "point_source": point_row["point_source"],
            "city_name": computed.get("city_name"),
            "comp_plan_designation": computed.get("comp_plan_designation"),
            "school_district": computed.get("school_district"),
            "fire_district": computed.get("fire_district"),
            "voting_precinct": computed.get("voting_precinct"),
            "historical_area_flag": bool(computed.get("historical_area_flag", False)),
            "nearest_road_name": computed.get("nearest_road_name"),
            "distance_to_nearest_road_feet": computed.get("distance_to_nearest_road_feet"),
            "distance_to_nearest_road_miles": computed.get("distance_to_nearest_road_miles"),
            "distance_to_mount_vernon_miles": computed.get("distance_to_mount_vernon_miles"),
            "distance_to_burlington_miles": computed.get("distance_to_burlington_miles"),
            "distance_to_sedro_woolley_miles": computed.get("distance_to_sedro_woolley_miles"),
            "distance_to_anacortes_miles": computed.get("distance_to_anacortes_miles"),
            "distance_to_la_conner_miles": computed.get("distance_to_la_conner_miles"),
            "nearest_public_place_name": computed.get("nearest_public_place_name"),
            "distance_to_nearest_public_place_miles": computed.get("distance_to_nearest_public_place_miles"),
            "distance_to_nearest_tide_gate_miles": computed.get("distance_to_nearest_tide_gate_miles"),
            "missing_coordinate_flag": False,
            "feature_status": ParcelGeoStaticFeature.STATUS_OK,
            "feature_version": gf.FEATURE_VERSION,
        }

    def _failed_row(self, parcel_number: str, error: str) -> dict:
        self.stdout.write(self.style.WARNING(f"{parcel_number}: failed: {error}"))
        return {
            "parcel_number": parcel_number,
            "prop_id": None,
            "x": None,
            "y": None,
            "lat": None,
            "lon": None,
            "point_source": None,
            "historical_area_flag": False,
            "missing_coordinate_flag": False,
            "feature_status": ParcelGeoStaticFeature.STATUS_FAILED,
            "feature_version": gf.FEATURE_VERSION,
        }

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------
    def _upsert(self, rows: list[dict]) -> None:
        if not rows:
            return
        # updated_at (auto_now) is deliberately left off the constructed objects
        # -- pre_save() stamps it automatically -- but it must still be listed
        # in update_fields, otherwise ON CONFLICT DO UPDATE never touches it.
        field_names = [f.name for f in ParcelGeoStaticFeature._meta.get_fields() if f.name not in ("id", "created_at")]
        objs = [
            ParcelGeoStaticFeature(**{name: row.get(name) for name in field_names if name != "updated_at"})
            for row in rows
        ]
        ParcelGeoStaticFeature.objects.bulk_create(
            objs,
            update_conflicts=True,
            unique_fields=["parcel_number"],
            update_fields=[name for name in field_names if name != "parcel_number"],
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def _print_summary(self, active_count: int, target_count: int, counts: dict, runtime: float) -> None:
        out = self.stdout
        out.write("")
        out.write("Static parcel geography build complete.")
        out.write("")
        out.write(f"Active parcels checked: {active_count:,}")
        out.write(f"Parcels needing rebuild: {target_count:,}")
        out.write(f"Parcels successfully updated: {counts['updated']:,}")
        out.write(f"Parcels missing coordinates: {counts['missing']:,}")
        out.write(f"Parcels failed: {counts['failed']:,}")
        out.write(f"Runtime: {runtime:.1f}s")
