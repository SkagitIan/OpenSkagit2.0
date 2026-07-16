from __future__ import annotations

import json
import math
from decimal import Decimal

from django.contrib.auth.views import redirect_to_login
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET


MAX_BBOX_SPAN = 0.08
MAX_FEATURES = 1_000
SKAGIT_BOUNDS = {
    "west": -123.0,
    "south": 47.7,
    "east": -120.8,
    "north": 49.2,
}


def _is_staff(request) -> bool:
    user = request.user
    return bool(user.is_authenticated and user.is_active and user.is_staff)


@require_GET
def field_map(request):
    if not _is_staff(request):
        return redirect_to_login(request.get_full_path(), "/login/")
    return render(request, "field_map/map.html")


def _parse_bbox(raw_bbox: str | None) -> tuple[float, float, float, float]:
    if not raw_bbox:
        raise ValueError("A bbox query parameter is required.")
    parts = raw_bbox.split(",")
    if len(parts) != 4:
        raise ValueError("bbox must contain west,south,east,north.")
    try:
        west, south, east, north = (float(part) for part in parts)
    except (TypeError, ValueError) as exc:
        raise ValueError("bbox coordinates must be numbers.") from exc
    if not all(math.isfinite(value) for value in (west, south, east, north)):
        raise ValueError("bbox coordinates must be finite numbers.")
    if west >= east or south >= north:
        raise ValueError("bbox coordinates are reversed or empty.")
    if east - west > MAX_BBOX_SPAN or north - south > MAX_BBOX_SPAN:
        raise ValueError("The map area is too large. Zoom in to load parcels.")
    if (
        west < SKAGIT_BOUNDS["west"]
        or east > SKAGIT_BOUNDS["east"]
        or south < SKAGIT_BOUNDS["south"]
        or north > SKAGIT_BOUNDS["north"]
    ):
        raise ValueError("The requested map area is outside Skagit County.")
    return west, south, east, north


def _json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _query_parcels(bbox: tuple[float, float, float, float]):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            WITH viewport AS (
                SELECT ST_MakeEnvelope(%s, %s, %s, %s, 4326) AS geometry
            )
            SELECT
                p.parcel_number,
                p.owner_name,
                nullif(trim(concat_ws(' ', p.situs_street_number, p.situs_street_name)), '') AS situs_address,
                p.situs_city_state_zip,
                p.acres,
                p.land_use,
                ST_AsGeoJSON(g.geometry, 7)::json AS geometry
            FROM viewport v
            JOIN gis_skagit_parcels g
              ON g.geometry && v.geometry
             AND ST_Intersects(g.geometry, v.geometry)
            JOIN skagit_parcels p
              ON p.parcel_number = g.parcel_id
            WHERE p.inactive_date IS NULL
              AND g.geometry IS NOT NULL
            ORDER BY p.parcel_number
            LIMIT %s
            """,
            [*bbox, MAX_FEATURES + 1],
        )
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


@require_GET
def parcels_geojson(request):
    if not _is_staff(request):
        response = JsonResponse({"error": "Staff sign-in is required."}, status=403)
        response["Cache-Control"] = "private, no-store"
        return response
    try:
        bbox = _parse_bbox(request.GET.get("bbox"))
    except ValueError as exc:
        response = JsonResponse({"error": str(exc)}, status=400)
        response["Cache-Control"] = "private, no-store"
        return response

    rows = _query_parcels(bbox)
    truncated = len(rows) > MAX_FEATURES
    features = []
    for row in rows[:MAX_FEATURES]:
        geometry = row.pop("geometry")
        if isinstance(geometry, str):
            geometry = json.loads(geometry)
        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": {key: _json_value(value) for key, value in row.items()},
        })

    response = JsonResponse({
        "type": "FeatureCollection",
        "features": features,
        "truncated": truncated,
    })
    response["Cache-Control"] = "private, no-store"
    return response
