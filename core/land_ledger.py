from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.db import connection
from django.utils import timezone


BUILDOUT_FACTOR = Decimal("0.5")
HORIZON_YEARS = 10
MIN_BENCHMARK_SAMPLE = 5


CITY_CONFIGS = {
    "sedro-woolley": {"name": "Sedro-Woolley", "district": "Sedro Woolley", "mcag": "0647"},
    "burlington": {"name": "Burlington", "district": "Burlington", "mcag": "0633"},
    "mount-vernon": {"name": "Mount Vernon", "district": "Mount Vernon", "mcag": "0644"},
    "anacortes": {"name": "Anacortes", "district": "Anacortes", "mcag": "0628"},
    "concrete": {"name": "Concrete", "district": "Concrete", "mcag": "0636"},
    "la-conner": {"name": "La Conner", "district": "La Conner", "mcag": "0640"},
    "hamilton": {"name": "Hamilton", "district": "Hamilton", "mcag": "0638"},
    "lyman": {"name": "Lyman", "district": "Lyman", "mcag": "0642"},
}


ZONE_SCENARIOS = {
    "R-1": ["small_infill"],
    "R-5": ["small_infill"],
    "R-7": ["small_infill", "townhomes"],
    "R-15": ["small_infill", "townhomes"],
    "CBD": ["small_multifamily", "mixed_use"],
    "MC": ["townhomes", "small_multifamily", "mixed_use"],
    "I": ["industrial_reuse"],
    "P": [],
    "OS": [],
}

POLICY_SCENARIOS_BY_GROUP = {
    "residential": ["small_multifamily"],
    "commercial": ["mixed_use"],
    "industrial": ["mixed_use"],
    "public": [],
    "other": [],
}

SCENARIOS = {
    "small_infill": {
        "label": "Add a Home",
        "description": "One new single-family home or ADU-scale infill.",
        "cohort": "sfr",
    },
    "townhomes": {
        "label": "Townhomes",
        "description": "Attached homes that use serviced land more efficiently.",
        "cohort": "multi",
    },
    "small_multifamily": {
        "label": "Small Apartment Building",
        "description": "A small multifamily building such as a fourplex or courtyard apartment.",
        "cohort": "multi",
    },
    "mixed_use": {
        "label": "Shops + Apartments",
        "description": "Ground-floor commercial space with homes above.",
        "cohort": "mixed",
    },
    "industrial_reuse": {
        "label": "Higher-Productivity Industrial",
        "description": "A more productive industrial or business-park use.",
        "cohort": "retail",
    },
}

ZONE_DESCRIPTIONS = {
    "R-1": {"label": "Residential 1", "description": "Low-density residential zoning with constrained development capacity."},
    "R-5": {"label": "Residential 5", "description": "Single-family residential areas with smaller urban lots."},
    "R-7": {"label": "Residential 7", "description": "Traditional grid neighborhoods where gentle infill is most plausible."},
    "R-15": {"label": "Residential 15", "description": "Larger-lot residential areas with a lower-intensity baseline."},
    "CBD": {"label": "Central Business District", "description": "Downtown mixed-use commercial and civic core."},
    "MC": {"label": "Mixed Commercial", "description": "Commercial corridors where housing and commercial activity can mix."},
    "I": {"label": "Industrial", "description": "Land reserved primarily for employment, manufacturing, warehousing, and business uses."},
    "P": {"label": "Public", "description": "Public, institutional, or civic land not modeled as private development opportunity."},
    "OS": {"label": "Open Space", "description": "Parks, natural areas, and protected open land."},
}

SFR_CODES = {"110", "111", "112", "113", "180", "181", "182", "185"}
MULTI_CODES = {"120", "130", "140", "150"}
RETAIL_CODES = {"510", "520", "530", "540", "550", "560", "580", "590", "610", "620", "640", "650", "660", "690"}
VACANT_CODES = {"910", "911", "912", "940", "941"}


def zone_group_for(zone_id: str | None) -> str:
    if not zone_id:
        return "other"
    zone = zone_id.upper().strip()
    if zone in {"R-1", "R-5", "R-7", "R-15"} or zone.startswith("R-"):
        return "residential"
    if zone in {"CBD", "MC"} or "COMMERCIAL" in zone or "BUSINESS" in zone:
        return "commercial"
    if zone == "I" or "INDUSTRIAL" in zone:
        return "industrial"
    if zone in {"P", "OS"} or "PUBLIC" in zone or "OPEN" in zone or "PARK" in zone:
        return "public"
    return "other"


def category_for(land_use: str | None) -> str:
    if not land_use:
        return "other"
    code = land_use.strip().lstrip("(").split(")")[0].strip()
    if code in SFR_CODES:
        return "sfr"
    if code in MULTI_CODES:
        return "multi"
    if code in RETAIL_CODES:
        return "retail"
    if code in VACANT_CODES:
        return "vacant"
    return "other"


def allowed_scenarios(zone_id: str | None) -> list[str]:
    if not zone_id:
        return []
    return ZONE_SCENARIOS.get(zone_id.upper().strip(), [])


def policy_scenarios(zone_group: str, allowed: list[str]) -> list[str]:
    return [key for key in POLICY_SCENARIOS_BY_GROUP.get(zone_group, []) if key not in allowed]


def _decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _median(values: list[Decimal]) -> Decimal | None:
    values = sorted(values)
    if not values:
        return None
    midpoint = len(values) // 2
    if len(values) % 2:
        return values[midpoint]
    return (values[midpoint - 1] + values[midpoint]) / Decimal("2")


def _benchmark_for(
    rows: list[dict[str, Any]],
    city_slug: str,
    zone_id: str | None,
    scenario_key: str,
) -> tuple[Decimal | None, dict[str, Any]]:
    scenario = SCENARIOS[scenario_key]
    cohort = scenario["cohort"]
    zone = (zone_id or "").upper().strip()

    def values_for(predicate):
        return [
            row["tax_per_acre"]
            for row in rows
            if row["city_slug"] == city_slug
            and row["tax_per_acre"] > 0
            and predicate(row)
        ]

    if cohort == "mixed":
        retail = values_for(lambda row: row["category"] == "retail")
        multi = values_for(lambda row: row["category"] == "multi")
        if len(retail) >= MIN_BENCHMARK_SAMPLE and len(multi) >= MIN_BENCHMARK_SAMPLE:
            value = (_median(retail) + _median(multi)) / Decimal("2")
            return value, {"source": "city_retail_multi_median", "sample_size": len(retail) + len(multi)}
    else:
        exact = values_for(lambda row: row["zone_id"] == zone and row["category"] == cohort)
        if len(exact) >= MIN_BENCHMARK_SAMPLE:
            return _median(exact), {"source": "zone_scenario_median", "sample_size": len(exact)}

        compatible = values_for(lambda row: row["zone_group"] == zone_group_for(zone) and row["category"] == cohort)
        if len(compatible) >= MIN_BENCHMARK_SAMPLE:
            return _median(compatible), {"source": "compatible_zone_group_median", "sample_size": len(compatible)}

        citywide = values_for(lambda row: row["category"] == cohort)
        if len(citywide) >= MIN_BENCHMARK_SAMPLE:
            return _median(citywide), {"source": "citywide_scenario_median", "sample_size": len(citywide)}

    return None, {"source": "insufficient_sample", "sample_size": 0}


def _scenario_result(row: dict[str, Any], scenario_key: str, benchmark: Decimal, source: dict[str, Any]) -> dict[str, Any]:
    annual_gain = (benchmark - row["tax_per_acre"]) * row["acres"]
    ten_year_gain = annual_gain * Decimal(HORIZON_YEARS) * BUILDOUT_FACTOR
    return {
        "key": scenario_key,
        "label": SCENARIOS[scenario_key]["label"],
        "description": SCENARIOS[scenario_key]["description"],
        "tax_per_acre": float(round(benchmark, 2)),
        "annual_gain": float(round(annual_gain, 2)),
        "ten_year_gain": float(round(ten_year_gain, 2)),
        "benchmark": source,
    }


@dataclass(frozen=True)
class RebuildResult:
    city_slug: str
    parcel_count: int
    zoned_count: int
    unknown_zone_count: int
    current_opportunity_10yr: Decimal
    policy_opportunity_10yr: Decimal


def fetch_land_ledger_source(city_slugs: list[str]) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT city_slug, city_name, parcel_number, address, acres, land_use,
                   total_taxes, city_tax_pct, zone_id, zone_name, zone_group,
                   ST_AsGeoJSON(geometry, 7)::json AS geometry
            FROM v_land_ledger_source
            WHERE city_slug = ANY(%s)
              AND geometry IS NOT NULL
              AND acres > 0
              AND total_taxes IS NOT NULL
            """,
            [city_slugs],
        )
        cols = [col[0] for col in cursor.description]
        source_rows = [dict(zip(cols, row)) for row in cursor.fetchall()]

    rows = []
    for row in source_rows:
        acres = _decimal(row["acres"])
        total_taxes = _decimal(row["total_taxes"])
        row["acres"] = acres
        row["current_tax"] = total_taxes
        row["tax_per_acre"] = total_taxes / acres if acres else Decimal("0")
        row["city_tax_pct"] = _decimal(row["city_tax_pct"])
        row["zone_id"] = (row["zone_id"] or "").upper().strip() or None
        row["zone_group"] = row["zone_group"] or zone_group_for(row["zone_id"])
        row["category"] = category_for(row["land_use"])
        rows.append(row)
    return rows


def rebuild_land_ledger(city_slugs: list[str]) -> list[RebuildResult]:
    unknown = [slug for slug in city_slugs if slug not in CITY_CONFIGS]
    if unknown:
        raise ValueError(f"Unknown city slug(s): {', '.join(unknown)}")

    rows = fetch_land_ledger_source(city_slugs)
    now = timezone.now()
    results: list[RebuildResult] = []

    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM land_ledger_parcels WHERE city_slug = ANY(%s)", [city_slugs])
        cursor.execute("DELETE FROM land_ledger_city_summary WHERE city_slug = ANY(%s)", [city_slugs])

        for city_slug in city_slugs:
            city_rows = [row for row in rows if row["city_slug"] == city_slug]
            summary = {
                "parcel_count": len(city_rows),
                "zoned_count": sum(1 for row in city_rows if row["zone_id"]),
                "unknown_zone_count": sum(1 for row in city_rows if not row["zone_id"]),
                "zone_counts": {},
                "zone_group_counts": {},
                "scenario_counts": {},
            }
            current_total = Decimal("0")
            policy_total = Decimal("0")

            for row in city_rows:
                zone_id = row["zone_id"]
                zone_group = row["zone_group"]
                allowed = allowed_scenarios(zone_id)
                policy = policy_scenarios(zone_group, allowed) if zone_id else []
                scenario_results: dict[str, dict[str, Any]] = {}
                best_current = Decimal("0")
                best_policy = Decimal("0")
                benchmark_meta = {}

                for key in allowed + policy:
                    benchmark, source = _benchmark_for(rows, city_slug, zone_id, key)
                    benchmark_meta[key] = source
                    if benchmark is None:
                        continue
                    result = _scenario_result(row, key, benchmark, source)
                    scenario_results[key] = result
                    gain = _decimal(result["ten_year_gain"])
                    if key in allowed:
                        best_current = max(best_current, gain)
                    else:
                        best_policy = max(best_policy, gain)

                best_current = max(best_current, Decimal("0"))
                best_policy = max(best_policy, Decimal("0"))
                current_total += best_current
                policy_total += best_policy
                summary["zone_counts"][zone_id or "UNKNOWN"] = summary["zone_counts"].get(zone_id or "UNKNOWN", 0) + 1
                summary["zone_group_counts"][zone_group] = summary["zone_group_counts"].get(zone_group, 0) + 1
                for key in allowed:
                    summary["scenario_counts"][key] = summary["scenario_counts"].get(key, 0) + 1

                cursor.execute(
                    """
                    INSERT INTO land_ledger_parcels (
                        city_slug, city_name, parcel_number, address, acres, land_use,
                        category, zone_id, zone_name, zone_group, current_tax,
                        tax_per_acre, city_tax_pct, allowed_scenarios, policy_scenarios,
                        scenario_results, current_opportunity_10yr,
                        policy_opportunity_10yr, benchmark_source, geometry, rebuilt_at
                    )
                    VALUES (
                        %(city_slug)s, %(city_name)s, %(parcel_number)s, %(address)s,
                        %(acres)s, %(land_use)s, %(category)s, %(zone_id)s,
                        %(zone_name)s, %(zone_group)s, %(current_tax)s,
                        %(tax_per_acre)s, %(city_tax_pct)s, %(allowed_scenarios)s::jsonb,
                        %(policy_scenarios)s::jsonb, %(scenario_results)s::jsonb,
                        %(current_opportunity_10yr)s, %(policy_opportunity_10yr)s,
                        %(benchmark_source)s::jsonb,
                        ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON(%(geometry)s)), 4326),
                        %(rebuilt_at)s
                    )
                    """,
                    {
                        **row,
                        "allowed_scenarios": json.dumps(allowed),
                        "policy_scenarios": json.dumps(policy),
                        "scenario_results": json.dumps(scenario_results),
                        "current_opportunity_10yr": best_current,
                        "policy_opportunity_10yr": best_policy,
                        "benchmark_source": json.dumps(benchmark_meta),
                        "geometry": json.dumps(row["geometry"]),
                        "rebuilt_at": now,
                    },
                )

            cursor.execute(
                """
                INSERT INTO land_ledger_city_summary (
                    city_slug, city_name, parcel_count, zoned_count,
                    unknown_zone_count, current_opportunity_10yr,
                    policy_opportunity_10yr, diagnostics, scenario_definitions,
                    zone_descriptions, buildout_factor, horizon_years, rebuilt_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s)
                """,
                [
                    city_slug,
                    CITY_CONFIGS[city_slug]["name"],
                    summary["parcel_count"],
                    summary["zoned_count"],
                    summary["unknown_zone_count"],
                    current_total,
                    policy_total,
                    json.dumps(summary),
                    json.dumps(SCENARIOS),
                    json.dumps(ZONE_DESCRIPTIONS),
                    BUILDOUT_FACTOR,
                    HORIZON_YEARS,
                    now,
                ],
            )
            results.append(RebuildResult(city_slug, summary["parcel_count"], summary["zoned_count"], summary["unknown_zone_count"], current_total, policy_total))
    return results
