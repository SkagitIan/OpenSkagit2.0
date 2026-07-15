"""Pure GeoPandas parcel adjacency computation for the internal graph.

This module does not load shapefiles or access Django/database state. It only
repairs and compares parcel geometries supplied by the caller in EPSG:2926;
command-level source tracking lives elsewhere.
"""
from __future__ import annotations
import geopandas as gpd
import pandas as pd
from shapely.geometry.base import BaseGeometry
try:
    from shapely.validation import make_valid
except ImportError:  # pragma: no cover
    make_valid = None
from assessor_sync.geo_features import WORKING_EPSG, force_crs

def _parcel_column(frame: gpd.GeoDataFrame) -> str:
    for name in ("parcel_number", "PARCELID", "parcel_id", "PARCEL_ID"):
        if name in frame.columns:
            return name
    raise ValueError("Parcel GeoDataFrame must contain parcel_number or PARCELID")

def _repair(geometry: BaseGeometry) -> tuple[BaseGeometry, bool]:
    if geometry is None or geometry.is_empty or geometry.is_valid:
        return geometry, False
    repaired = make_valid(geometry) if make_valid is not None else geometry.buffer(0)
    if repaired is None or repaired.is_empty or repaired.geom_type == "GeometryCollection":
        repaired = geometry.buffer(0)
    return repaired, True

def build_adjacency(parcels_gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """Return each true shared-boundary parcel pair once, with feet of edge."""
    pid_col = _parcel_column(parcels_gdf)
    frame = force_crs(parcels_gdf[[pid_col, "geometry"]].dropna(subset=[pid_col, "geometry"]).copy(), WORKING_EPSG)
    repaired_count = 0
    repaired_geometries = []
    for geometry in frame.geometry:
        repaired, changed = _repair(geometry)
        repaired_count += int(changed)
        repaired_geometries.append(repaired)
    frame["geometry"] = repaired_geometries
    frame = frame[frame.geometry.apply(lambda geometry: isinstance(geometry, BaseGeometry) and not geometry.is_empty)].reset_index(drop=True)
    rows: list[dict] = []
    if not frame.empty:
        sindex = frame.sindex
        for index, geometry_a in enumerate(frame.geometry):
            for candidate in sindex.query(geometry_a, predicate="intersects"):
                candidate = int(candidate)
                if candidate <= index:
                    continue
                geometry_b = frame.geometry.iloc[candidate]
                if not geometry_a.relate_pattern(geometry_b, "****1****"):
                    continue
                boundary_a, boundary_b = geometry_a.boundary, geometry_b.boundary
                if boundary_a is None or boundary_b is None:
                    continue
                shared = boundary_a.intersection(boundary_b).length
                if shared <= 0:
                    continue
                pid_a, pid_b = str(frame.iloc[index][pid_col]), str(frame.iloc[candidate][pid_col])
                if pid_b < pid_a:
                    pid_a, pid_b = pid_b, pid_a
                rows.append({"pid_a": pid_a, "pid_b": pid_b, "shared_boundary_ft": float(shared)})
    result = pd.DataFrame(rows, columns=["pid_a", "pid_b", "shared_boundary_ft"])
    if not result.empty:
        result = result.sort_values(["pid_a", "pid_b"]).drop_duplicates(["pid_a", "pid_b"], keep="first").reset_index(drop=True)
    result.attrs["invalid_repaired"] = repaired_count
    result.attrs["working_epsg"] = WORKING_EPSG
    return result