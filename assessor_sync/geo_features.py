"""
Spatial helpers for the static parcel geography feature builder
(``build_geo_features``).

This module holds the vectorized GeoPandas logic -- point resolution,
polygon containment, nearest-feature distance, rebuild detection -- separate
from the Django/DB glue in the management command. Every function here takes
plain pandas/GeoPandas objects, so it can be unit tested with tiny fake
geometries and no database.

Nothing here builds a regression model, nearby-sales features, or a GIS
warehouse. It only computes static geography for one row per parcel.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

WORKING_EPSG = 2926
FEET_PER_MILE = 5280.0
FEATURE_VERSION = 1

STATUS_OK = "ok"
STATUS_MISSING_COORDINATES = "missing_coordinates"
STATUS_FAILED = "failed"

SOURCE_ASSESSOR_XY = "assessor_xy"
SOURCE_PARCEL_NUMBERS_POINT = "parcel_numbers_point"
SOURCE_PARCEL_CENTROID = "parcel_centroid"

# Skagit County's shapefile .prj is ESRI-style WKT for "NAD83 / Washington
# North (ftUS)" and does not auto-match the canonical EPSG:2926 definition
# via to_epsg(), even though its projection parameters (central meridian
# -120.833333, standard parallels 47.5/48.7333, false easting 1640416.667 ft)
# are exactly EPSG:2926. Every loaded layer's CRS is forced to EPSG:2926
# rather than trusted from auto-detection.

# Real, county-published city names in city_limits.shp -- used to derive
# each fixed market anchor as that city's own city-limits centroid, rather
# than a hardcoded lat/lon guess.
MARKET_ANCHOR_CITIES = {
    "distance_to_mount_vernon_miles": "MOUNT VERNON",
    "distance_to_burlington_miles": "BURLINGTON",
    "distance_to_sedro_woolley_miles": "SEDRO-WOOLLEY",
    "distance_to_anacortes_miles": "ANACORTES",
    "distance_to_la_conner_miles": "LA CONNER",
}


def force_crs(gdf, epsg: int = WORKING_EPSG):
    """Return ``gdf`` with its CRS declared as ``epsg``, without reprojecting."""
    return gdf.set_crs(epsg=epsg, allow_override=True)


def market_anchor_points(city_limits_gdf) -> dict[str, object]:
    """
    Derive the 5 fixed market anchor points as each city's own city-limits
    centroid (dissolving multi-polygon cities like Sedro-Woolley into one).

    Returns {feature_column_name: shapely Point or None (city not found)}.
    """
    names = city_limits_gdf["NAME"].astype(str).str.strip().str.upper()
    anchors: dict[str, object] = {}
    for column, city_name in MARKET_ANCHOR_CITIES.items():
        subset = city_limits_gdf[names == city_name]
        anchors[column] = subset.union_all().centroid if not subset.empty else None
    return anchors


def resolve_parcel_points(
    parcel_numbers: pd.Series,
    assessor_xy: pd.DataFrame | None,
    parcel_numbers_gdf,
    parcels_gdf,
) -> pd.DataFrame:
    """
    Resolve one (x, y, point_source) per parcel_number using, in order:

    1. assessor_xy -- a DataFrame with columns parcel_number/x/y, for a future
       assessor export that carries its own coordinates. The current Skagit
       assessor_rollup export has no such columns, so callers pass None; the
       tier is implemented for forward compatibility, not fabricated.
    2. parcel_numbers_gdf -- the county's PNumbers point layer (PNUMBER, geometry).
    3. parcels_gdf -- centroid of the matching parcel polygon (PARCELID, geometry).

    Returns a DataFrame with columns: parcel_number, x, y, point_source (source
    is None and x/y are NaN when no tier resolves a point).
    """
    result = pd.DataFrame({"parcel_number": parcel_numbers})
    result["x"] = np.nan
    result["y"] = np.nan
    result["point_source"] = None

    if assessor_xy is not None and not assessor_xy.empty:
        merged = result.merge(
            assessor_xy[["parcel_number", "x", "y"]].dropna(subset=["x", "y"]),
            on="parcel_number",
            how="left",
            suffixes=("", "_assessor"),
        )
        has_assessor = merged["x_assessor"].notna()
        result.loc[has_assessor, "x"] = merged.loc[has_assessor, "x_assessor"]
        result.loc[has_assessor, "y"] = merged.loc[has_assessor, "y_assessor"]
        result.loc[has_assessor, "point_source"] = SOURCE_ASSESSOR_XY

    still_missing = result["x"].isna()
    if still_missing.any() and parcel_numbers_gdf is not None and not parcel_numbers_gdf.empty:
        points = parcel_numbers_gdf[["PNUMBER", "geometry"]].drop_duplicates(subset="PNUMBER", keep="first")
        points = points.assign(px=points.geometry.x, py=points.geometry.y)
        merged = result.merge(
            points[["PNUMBER", "px", "py"]],
            left_on="parcel_number",
            right_on="PNUMBER",
            how="left",
        )
        use = still_missing.values & merged["px"].notna().values
        result.loc[use, "x"] = merged.loc[use, "px"].values
        result.loc[use, "y"] = merged.loc[use, "py"].values
        result.loc[use, "point_source"] = SOURCE_PARCEL_NUMBERS_POINT

    still_missing = result["x"].isna()
    if still_missing.any() and parcels_gdf is not None and not parcels_gdf.empty:
        polygons = parcels_gdf[["PARCELID", "geometry"]].drop_duplicates(subset="PARCELID", keep="first")
        centroids = polygons.geometry.centroid
        polygons = polygons.assign(cx=centroids.x, cy=centroids.y)
        merged = result.merge(
            polygons[["PARCELID", "cx", "cy"]],
            left_on="parcel_number",
            right_on="PARCELID",
            how="left",
        )
        use = still_missing.values & merged["cx"].notna().values
        result.loc[use, "x"] = merged.loc[use, "cx"].values
        result.loc[use, "y"] = merged.loc[use, "cy"].values
        result.loc[use, "point_source"] = SOURCE_PARCEL_CENTROID

    return result[["parcel_number", "x", "y", "point_source"]]


def _series_changed(a: pd.Series, b: pd.Series, tolerance: float = 0.0) -> pd.Series:
    """Elementwise 'did this value change', treating NaN==NaN as unchanged."""
    a_null = a.isna()
    b_null = b.isna()
    either_null = a_null ^ b_null
    both_present_and_different = (~a_null) & (~b_null) & ((a - b).abs() > tolerance)
    return either_null | both_present_and_different


def determine_rebuild_targets(
    resolved: pd.DataFrame,
    existing: pd.DataFrame,
    *,
    full: bool,
    feature_version: int = FEATURE_VERSION,
    coordinate_tolerance_feet: float = 0.5,
) -> list[str]:
    """
    Return the parcel_numbers that need a (re)build.

    ``resolved`` has columns parcel_number/x/y/point_source for every active
    parcel being considered. ``existing`` has the same columns plus
    feature_status/feature_version for parcels with a prior feature row (can
    be empty). Ignored entirely when ``full`` is True.
    """
    if full:
        return resolved["parcel_number"].tolist()

    prior = existing.rename(
        columns={
            "x": "prior_x",
            "y": "prior_y",
            "point_source": "prior_point_source",
            "feature_status": "prior_feature_status",
            "feature_version": "prior_feature_version",
        }
    )
    merged = resolved.merge(prior, on="parcel_number", how="left")

    is_new = merged["prior_feature_status"].isna()
    failed_before = merged["prior_feature_status"] == STATUS_FAILED
    version_changed = merged["prior_feature_version"].fillna(-1) != feature_version
    source_changed = merged["point_source"].fillna("") != merged["prior_point_source"].fillna("")
    x_changed = _series_changed(merged["x"], merged["prior_x"], coordinate_tolerance_feet)
    y_changed = _series_changed(merged["y"], merged["prior_y"], coordinate_tolerance_feet)

    needs_rebuild = is_new | failed_before | version_changed | source_changed | x_changed | y_changed
    return merged.loc[needs_rebuild, "parcel_number"].tolist()


def containment_lookup(points_gdf, polygons_gdf, attr_col: str) -> pd.Series:
    """
    For each point in ``points_gdf`` (must have a parcel_number column and
    Point geometry), return the ``attr_col`` value of the polygon in
    ``polygons_gdf`` that contains it (NaN if none contain it).

    Some county layers have overlapping polygons at the same location (e.g.
    comp_plan's county-wide water-body overlay sits on top of the actual
    zoning polygons near shorelines). When a point falls inside more than one
    polygon, a match with a non-null ``attr_col`` is preferred over a null one.

    Returns a Series indexed by parcel_number.
    """
    if points_gdf.empty or polygons_gdf.empty:
        return pd.Series(dtype=object, name=attr_col)

    joined = gpd.sjoin(
        points_gdf[["parcel_number", "geometry"]],
        polygons_gdf[[attr_col, "geometry"]],
        how="left",
        predicate="within",
    )
    joined = joined.sort_values(by=attr_col, na_position="last")
    joined = joined.drop_duplicates(subset="parcel_number", keep="first")
    return joined.set_index("parcel_number")[attr_col]


def historical_containment_flags(parcel_polygons_gdf, historical_points_gdf) -> set:
    """
    Return the set of parcel_numbers whose polygon contains at least one
    historical-site marker.

    The historical layer is points (site markers), not areas, so this checks
    "does this parcel's polygon contain a historical marker" rather than the
    point-in-polygon containment used for city/comp-plan/district layers.
    """
    if parcel_polygons_gdf.empty or historical_points_gdf.empty:
        return set()

    joined = gpd.sjoin(
        parcel_polygons_gdf[["parcel_number", "geometry"]],
        historical_points_gdf[["geometry"]],
        how="inner",
        predicate="contains",
    )
    return set(joined["parcel_number"].unique())


def nearest_lookup(points_gdf, target_gdf, name_col: str | None = None) -> pd.DataFrame:
    """
    For each point in ``points_gdf``, find the nearest feature in
    ``target_gdf`` (vectorized via GeoPandas' STRtree-backed sjoin_nearest).

    Returns a DataFrame indexed by parcel_number with column
    distance_feet, and ``name_col`` if given.
    """
    columns = ["geometry"] + ([name_col] if name_col else [])
    if points_gdf.empty or target_gdf.empty:
        empty_cols = ["distance_feet"] + ([name_col] if name_col else [])
        return pd.DataFrame(columns=empty_cols)

    joined = gpd.sjoin_nearest(
        points_gdf[["parcel_number", "geometry"]],
        target_gdf[columns],
        how="left",
        distance_col="distance_feet",
    )
    joined = joined.drop_duplicates(subset="parcel_number", keep="first")
    result_cols = ["distance_feet"] + ([name_col] if name_col else [])
    return joined.set_index("parcel_number")[result_cols]


def anchor_distances_miles(points_gdf, anchors: dict[str, object]) -> pd.DataFrame:
    """
    Distance in miles from each point to each fixed market anchor point.

    Returns a DataFrame indexed by parcel_number, one column per anchor key.
    """
    result = pd.DataFrame(index=points_gdf["parcel_number"].values)
    for column, anchor_point in anchors.items():
        if anchor_point is None:
            result[column] = np.nan
        else:
            result[column] = points_gdf.geometry.distance(anchor_point).values / FEET_PER_MILE
    result.index.name = "parcel_number"
    return result
