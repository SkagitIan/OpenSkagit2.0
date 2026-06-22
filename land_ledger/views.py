import json

from django.db import connection
from django.http import Http404, JsonResponse

from .services import CITY_CONFIGS


LAND_LEDGER_JSON_FIELDS = {
    "allowed_scenarios",
    "policy_scenarios",
    "scenario_results",
    "benchmark_source",
    "exclusion_reasons",
    "model_flags",
    "diagnostics",
    "scenario_definitions",
    "zone_descriptions",
    "scenario_totals",
    "exclusion_counts",
}


def _json_value(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (int, float, str, bool, list, dict)):
        return value
    return float(value)


def _land_ledger_value(key, value):
    if key in LAND_LEDGER_JSON_FIELDS and isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return _json_value(value)


def land_ledger_summary(request, city_slug):
    if city_slug not in CITY_CONFIGS:
        raise Http404("City not found")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT city_slug, city_name, parcel_count, zoned_count,
                   unknown_zone_count, current_opportunity_10yr,
                   policy_opportunity_10yr, city_current_opportunity_10yr,
                   city_policy_opportunity_10yr, eligible_parcel_count,
                   excluded_parcel_count, scenario_totals, exclusion_counts,
                   assumption_version, diagnostics, scenario_definitions,
                   zone_descriptions, buildout_factor, horizon_years, rebuilt_at
            FROM land_ledger_city_summary
            WHERE city_slug = %s
            """,
            [city_slug],
        )
        row = cursor.fetchone()
        if row is None:
            return JsonResponse({
                "city_slug": city_slug,
                "city_name": CITY_CONFIGS[city_slug]["name"],
                "ready": False,
                "message": "Land Ledger has not been rebuilt for this city yet.",
            }, status=404)
        cols = [col[0] for col in cursor.description]
    payload = {key: _land_ledger_value(key, value) for key, value in zip(cols, row)}
    payload["ready"] = True
    return JsonResponse(payload)


def land_ledger_parcels(request, city_slug):
    if city_slug not in CITY_CONFIGS:
        raise Http404("City not found")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                parcel_number, address, acres, land_use, category, zone_id,
                zone_name, zone_group, current_tax, tax_per_acre, city_tax_pct,
                productivity_percentile, productivity_label, allowed_scenarios,
                policy_scenarios, scenario_results, current_opportunity_10yr,
                policy_opportunity_10yr, city_current_opportunity_10yr,
                city_policy_opportunity_10yr, exclusion_reasons, model_flags,
                assumption_version,
                benchmark_source, ST_AsGeoJSON(geometry, 7)::json AS geometry
            FROM land_ledger_parcels
            WHERE city_slug = %s
              AND geometry IS NOT NULL
            """,
            [city_slug],
        )
        cols = [col[0] for col in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]

    features = []
    for row in rows:
        geometry = row.pop("geometry")
        properties = {key: _land_ledger_value(key, value) for key, value in row.items()}
        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": properties,
        })
    return JsonResponse({
        "type": "FeatureCollection",
        "features": features,
    })
