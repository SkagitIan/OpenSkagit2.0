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
MIN_BENCHMARK_ACRES = Decimal("0.10")
MAX_BENCHMARK_ACRES = Decimal("10")
ASSUMPTION_VERSION = "scenario-value-v1"
DEFAULT_TOTAL_LEVY_RATE = Decimal("9.50")


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
        "added_value_per_unit": 450000,
        "units": 1,
        "min_acres": 0.12,
        "max_acres": 2.5,
        "eligible_categories": ["vacant", "sfr"],
        "allowed_zones": ["R-1", "R-5", "R-7", "R-15"],
    },
    "townhomes": {
        "label": "Townhomes",
        "description": "Attached homes that use serviced land more efficiently.",
        "cohort": "multi",
        "added_value_per_unit": 425000,
        "units_per_acre": 8,
        "max_units": 12,
        "min_acres": 0.25,
        "max_acres": 3,
        "eligible_categories": ["vacant", "sfr", "other"],
        "allowed_zones": ["R-7", "R-15", "MC"],
    },
    "small_multifamily": {
        "label": "Small Apartment Building",
        "description": "A small multifamily building such as a fourplex or courtyard apartment.",
        "cohort": "multi",
        "added_value_per_unit": 375000,
        "units": 6,
        "min_acres": 0.35,
        "max_acres": 2.5,
        "eligible_categories": ["vacant", "sfr", "other"],
        "allowed_zones": ["CBD", "MC"],
        "policy_zones": ["R-5", "R-7", "R-15"],
    },
    "mixed_use": {
        "label": "Shops + Apartments",
        "description": "Ground-floor commercial space with homes above.",
        "cohort": "mixed",
        "added_value_per_unit": 400000,
        "units_per_acre": 10,
        "commercial_value_per_acre": 600000,
        "max_units": 18,
        "min_acres": 0.25,
        "max_acres": 2.5,
        "eligible_categories": ["vacant", "sfr", "retail", "other"],
        "allowed_zones": ["CBD", "MC"],
        "policy_zones": ["I"],
    },
    "industrial_reuse": {
        "label": "Higher-Productivity Industrial",
        "description": "A more productive industrial or business-park use.",
        "cohort": "retail",
        "added_value_per_acre": 550000,
        "min_acres": 0.5,
        "max_acres": 5,
        "eligible_categories": ["vacant", "retail", "other"],
        "allowed_zones": ["I"],
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


def productivity_label(percentile: Decimal | None) -> str:
    if percentile is None:
        return "unavailable"
    if percentile < Decimal("0.25"):
        return "low"
    if percentile < Decimal("0.50"):
        return "below_median"
    if percentile < Decimal("0.75"):
        return "above_median"
    return "high"


def add_productivity_percentiles(rows: list[dict[str, Any]]) -> None:
    by_city: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_city.setdefault(row["city_slug"], []).append(row)
    for city_rows in by_city.values():
        ranked = sorted(
            [row for row in city_rows if row["tax_per_acre"] > 0],
            key=lambda row: row["tax_per_acre"],
        )
        denominator = max(len(ranked) - 1, 1)
        for index, row in enumerate(ranked):
            row["productivity_percentile"] = Decimal(index) / Decimal(denominator)
        for row in city_rows:
            row.setdefault("productivity_percentile", None)
            row["productivity_label"] = productivity_label(row["productivity_percentile"])


def _trimmed_median(values: list[Decimal]) -> Decimal | None:
    values = sorted(values)
    if len(values) < MIN_BENCHMARK_SAMPLE:
        return None
    trim_count = max(0, int(len(values) * 0.10))
    if trim_count and len(values) - (trim_count * 2) >= MIN_BENCHMARK_SAMPLE:
        values = values[trim_count:-trim_count]
    return _median(values)


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
            and row["acres"] >= MIN_BENCHMARK_ACRES
            and row["acres"] <= MAX_BENCHMARK_ACRES
            and predicate(row)
        ]

    if cohort == "mixed":
        retail = values_for(lambda row: row["category"] == "retail")
        multi = values_for(lambda row: row["category"] == "multi")
        if len(retail) >= MIN_BENCHMARK_SAMPLE and len(multi) >= MIN_BENCHMARK_SAMPLE:
            value = (_trimmed_median(retail) + _trimmed_median(multi)) / Decimal("2")
            return value, {"source": "city_retail_multi_median", "sample_size": len(retail) + len(multi)}
    else:
        exact = values_for(lambda row: row["zone_id"] == zone and row["category"] == cohort)
        if len(exact) >= MIN_BENCHMARK_SAMPLE:
            return _trimmed_median(exact), {"source": "zone_scenario_median", "sample_size": len(exact)}

        compatible = values_for(lambda row: row["zone_group"] == zone_group_for(zone) and row["category"] == cohort)
        if len(compatible) >= MIN_BENCHMARK_SAMPLE:
            return _trimmed_median(compatible), {"source": "compatible_zone_group_median", "sample_size": len(compatible)}

        citywide = values_for(lambda row: row["category"] == cohort)
        if len(citywide) >= MIN_BENCHMARK_SAMPLE:
            return _trimmed_median(citywide), {"source": "citywide_scenario_median", "sample_size": len(citywide)}

    return None, {"source": "insufficient_sample", "sample_size": 0}


def land_use_code(row: dict[str, Any]) -> str:
    land_use = row.get("land_use")
    if not land_use:
        return ""
    return land_use.strip().lstrip("(").split(")")[0].strip()


def baseline_exclusions(row: dict[str, Any]) -> list[str]:
    reasons = []
    zone_id = row["zone_id"]
    code = land_use_code(row)
    if not zone_id:
        reasons.append("zoning_unavailable")
    if row["zone_group"] == "public" or zone_id in {"P", "OS"}:
        reasons.append("public_or_open_space_zone")
    if code == "830":
        reasons.append("current_use_farm_or_ag")
    if code in {"680", "770"}:
        reasons.append("civic_school_or_cemetery_use")
    if row["current_tax"] <= 0 and row["taxable_value"] <= 0:
        reasons.append("no_taxable_baseline")
    return reasons


def scenario_exclusions(row: dict[str, Any], scenario_key: str) -> list[str]:
    scenario = SCENARIOS[scenario_key]
    reasons = baseline_exclusions(row)
    zone_id = row["zone_id"]
    category = row["category"]
    acres = row["acres"]
    if zone_id and zone_id not in scenario.get("allowed_zones", []) and zone_id not in scenario.get("policy_zones", []):
        reasons.append("zone_not_eligible")
    if category not in scenario.get("eligible_categories", []):
        reasons.append("current_use_not_eligible")
    if acres < _decimal(scenario.get("min_acres", 0)):
        reasons.append("parcel_too_small")
    if acres > _decimal(scenario.get("max_acres", 999999)):
        reasons.append("parcel_too_large_for_scenario")
    if scenario_key == "small_infill" and category == "sfr" and acres < Decimal("0.35"):
        reasons.append("already_small_sfr_lot")
    if scenario_key in {"townhomes", "small_multifamily"} and category == "multi":
        reasons.append("already_multifamily")
    return reasons


def is_policy_scenario(row: dict[str, Any], scenario_key: str) -> bool:
    return row["zone_id"] in SCENARIOS[scenario_key].get("policy_zones", [])


def scenario_added_value(row: dict[str, Any], scenario_key: str) -> tuple[Decimal, dict[str, Any]]:
    scenario = SCENARIOS[scenario_key]
    acres = min(row["acres"], _decimal(scenario.get("max_acres", row["acres"])))
    if "units" in scenario:
        units = _decimal(scenario["units"])
    elif "units_per_acre" in scenario:
        units = acres * _decimal(scenario["units_per_acre"])
        units = min(units, _decimal(scenario.get("max_units", units)))
    else:
        units = Decimal("0")

    value = Decimal("0")
    if units:
        value += units * _decimal(scenario.get("added_value_per_unit", 0))
    if "added_value_per_acre" in scenario:
        value += acres * _decimal(scenario["added_value_per_acre"])
    if "commercial_value_per_acre" in scenario:
        value += acres * _decimal(scenario["commercial_value_per_acre"])

    return value, {
        "modeled_acres": float(round(acres, 2)),
        "modeled_units": float(round(units, 2)),
    }


def _scenario_result(row: dict[str, Any], scenario_key: str, benchmark: Decimal | None, source: dict[str, Any]) -> dict[str, Any]:
    added_value, modeled = scenario_added_value(row, scenario_key)
    total_levy_rate = row["effective_total_levy_rate"] or DEFAULT_TOTAL_LEVY_RATE
    city_levy_rate = total_levy_rate * row["city_tax_pct"] / Decimal("100")
    annual_gain = added_value / Decimal("1000") * total_levy_rate
    city_annual_gain = added_value / Decimal("1000") * city_levy_rate
    ten_year_gain = annual_gain * Decimal(HORIZON_YEARS) * BUILDOUT_FACTOR
    city_ten_year_gain = city_annual_gain * Decimal(HORIZON_YEARS) * BUILDOUT_FACTOR
    scenario_tax_per_acre = row["tax_per_acre"]
    if row["acres"]:
        scenario_tax_per_acre += annual_gain / row["acres"]
    return {
        "key": scenario_key,
        "label": SCENARIOS[scenario_key]["label"],
        "description": SCENARIOS[scenario_key]["description"],
        "tax_per_acre": float(round(scenario_tax_per_acre, 2)),
        "added_assessed_value": float(round(added_value, 2)),
        "total_levy_rate": float(round(total_levy_rate, 4)),
        "city_levy_rate": float(round(city_levy_rate, 4)),
        **modeled,
        "annual_gain": float(round(annual_gain, 2)),
        "city_annual_gain": float(round(city_annual_gain, 2)),
        "ten_year_gain": float(round(ten_year_gain, 2)),
        "city_ten_year_gain": float(round(city_ten_year_gain, 2)),
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
                   assessed_value, taxable_value, total_taxes, city_tax_pct,
                   zone_id, zone_name, zone_group,
                   ST_AsGeoJSON(geometry, 7)::json AS geometry
            FROM v_land_ledger_source
            WHERE city_slug = ANY(%s)
              AND geometry IS NOT NULL
              AND acres > 0
              AND total_taxes IS NOT NULL
            ORDER BY city_slug, parcel_number,
                     (zone_id IS NOT NULL) DESC,
                     total_taxes DESC NULLS LAST
            """,
            [city_slugs],
        )
        cols = [col[0] for col in cursor.description]
        source_rows = [dict(zip(cols, row)) for row in cursor.fetchall()]

    deduped_source_rows = {}
    for row in source_rows:
        key = (row["city_slug"], row["parcel_number"])
        if key not in deduped_source_rows:
            deduped_source_rows[key] = row
    source_rows = list(deduped_source_rows.values())

    rows = []
    for row in source_rows:
        acres = _decimal(row["acres"])
        total_taxes = _decimal(row["total_taxes"])
        row["acres"] = acres
        row["assessed_value"] = _decimal(row["assessed_value"])
        row["taxable_value"] = _decimal(row["taxable_value"])
        row["current_tax"] = total_taxes
        row["tax_per_acre"] = total_taxes / acres if acres else Decimal("0")
        row["effective_total_levy_rate"] = (
            total_taxes / row["taxable_value"] * Decimal("1000")
            if row["taxable_value"] > 0
            else DEFAULT_TOTAL_LEVY_RATE
        )
        row["city_tax_pct"] = _decimal(row["city_tax_pct"])
        row["zone_id"] = (row["zone_id"] or "").upper().strip() or None
        row["zone_group"] = row["zone_group"] or zone_group_for(row["zone_id"])
        row["category"] = category_for(row["land_use"])
        rows.append(row)
    add_productivity_percentiles(rows)
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
                "eligible_parcel_count": 0,
                "excluded_parcel_count": 0,
                "exclusion_counts": {},
                "scenario_totals": {},
                "model_limits": {
                    "assumption_version": ASSUMPTION_VERSION,
                    "min_benchmark_acres": float(MIN_BENCHMARK_ACRES),
                    "max_benchmark_acres": float(MAX_BENCHMARK_ACRES),
                    "benchmark_trim": "10% tails when sample size permits",
                },
            }
            current_total = Decimal("0")
            policy_total = Decimal("0")
            city_current_total = Decimal("0")
            city_policy_total = Decimal("0")

            for row in city_rows:
                zone_id = row["zone_id"]
                zone_group = row["zone_group"]
                current_candidates = allowed_scenarios(zone_id)
                policy_candidates = policy_scenarios(zone_group, current_candidates) if zone_id else []
                allowed = []
                policy = []
                scenario_results: dict[str, dict[str, Any]] = {}
                best_current = Decimal("0")
                best_policy = Decimal("0")
                best_city_current = Decimal("0")
                best_city_policy = Decimal("0")
                benchmark_meta = {}
                exclusion_reasons = set(baseline_exclusions(row))

                for key in current_candidates + policy_candidates:
                    reasons = scenario_exclusions(row, key)
                    if reasons:
                        for reason in reasons:
                            exclusion_reasons.add(reason)
                        continue
                    benchmark, source = _benchmark_for(rows, city_slug, zone_id, key)
                    source = {
                        **source,
                        "model": "scenario_added_assessed_value",
                        "assumption_version": ASSUMPTION_VERSION,
                    }
                    result = _scenario_result(row, key, benchmark, source)
                    scenario_results[key] = result
                    gain = _decimal(result["ten_year_gain"])
                    city_gain = _decimal(result["city_ten_year_gain"])
                    benchmark_meta[key] = source
                    if is_policy_scenario(row, key) or key in policy_candidates:
                        policy.append(key)
                        best_policy = max(best_policy, gain)
                        best_city_policy = max(best_city_policy, city_gain)
                    else:
                        allowed.append(key)
                        best_current = max(best_current, gain)
                        best_city_current = max(best_city_current, city_gain)

                best_current = max(best_current, Decimal("0"))
                best_policy = max(best_policy, Decimal("0"))
                best_city_current = max(best_city_current, Decimal("0"))
                best_city_policy = max(best_city_policy, Decimal("0"))
                current_total += best_current
                policy_total += best_policy
                city_current_total += best_city_current
                city_policy_total += best_city_policy
                if allowed or policy:
                    summary["eligible_parcel_count"] += 1
                else:
                    summary["excluded_parcel_count"] += 1
                summary["zone_counts"][zone_id or "UNKNOWN"] = summary["zone_counts"].get(zone_id or "UNKNOWN", 0) + 1
                summary["zone_group_counts"][zone_group] = summary["zone_group_counts"].get(zone_group, 0) + 1
                for reason in sorted(exclusion_reasons):
                    summary["exclusion_counts"][reason] = summary["exclusion_counts"].get(reason, 0) + 1
                for key in allowed + policy:
                    summary["scenario_counts"][key] = summary["scenario_counts"].get(key, 0) + 1
                    value = _decimal(scenario_results[key]["ten_year_gain"])
                    summary["scenario_totals"][key] = float(_decimal(summary["scenario_totals"].get(key, 0)) + value)

                cursor.execute(
                    """
                    INSERT INTO land_ledger_parcels (
                        city_slug, city_name, parcel_number, address, acres, land_use,
                        category, zone_id, zone_name, zone_group, current_tax,
                        tax_per_acre, city_tax_pct, productivity_percentile,
                        productivity_label, allowed_scenarios, policy_scenarios,
                        scenario_results, current_opportunity_10yr,
                        policy_opportunity_10yr, city_current_opportunity_10yr,
                        city_policy_opportunity_10yr, exclusion_reasons, model_flags,
                        assumption_version, benchmark_source, geometry, rebuilt_at
                    )
                    VALUES (
                        %(city_slug)s, %(city_name)s, %(parcel_number)s, %(address)s,
                        %(acres)s, %(land_use)s, %(category)s, %(zone_id)s,
                        %(zone_name)s, %(zone_group)s, %(current_tax)s,
                        %(tax_per_acre)s, %(city_tax_pct)s,
                        %(productivity_percentile)s, %(productivity_label)s,
                        %(allowed_scenarios)s::jsonb, %(policy_scenarios)s::jsonb,
                        %(scenario_results)s::jsonb,
                        %(current_opportunity_10yr)s, %(policy_opportunity_10yr)s,
                        %(city_current_opportunity_10yr)s, %(city_policy_opportunity_10yr)s,
                        %(exclusion_reasons)s::jsonb, %(model_flags)s::jsonb,
                        %(assumption_version)s,
                        %(benchmark_source)s::jsonb,
                        ST_SetSRID(ST_Multi(ST_GeomFromGeoJSON(%(geometry)s)), 4326),
                        %(rebuilt_at)s
                    )
                    ON CONFLICT (city_slug, parcel_number) DO UPDATE SET
                        city_name = EXCLUDED.city_name,
                        address = EXCLUDED.address,
                        acres = EXCLUDED.acres,
                        land_use = EXCLUDED.land_use,
                        category = EXCLUDED.category,
                        zone_id = EXCLUDED.zone_id,
                        zone_name = EXCLUDED.zone_name,
                        zone_group = EXCLUDED.zone_group,
                        current_tax = EXCLUDED.current_tax,
                        tax_per_acre = EXCLUDED.tax_per_acre,
                        city_tax_pct = EXCLUDED.city_tax_pct,
                        productivity_percentile = EXCLUDED.productivity_percentile,
                        productivity_label = EXCLUDED.productivity_label,
                        allowed_scenarios = EXCLUDED.allowed_scenarios,
                        policy_scenarios = EXCLUDED.policy_scenarios,
                        scenario_results = EXCLUDED.scenario_results,
                        current_opportunity_10yr = EXCLUDED.current_opportunity_10yr,
                        policy_opportunity_10yr = EXCLUDED.policy_opportunity_10yr,
                        city_current_opportunity_10yr = EXCLUDED.city_current_opportunity_10yr,
                        city_policy_opportunity_10yr = EXCLUDED.city_policy_opportunity_10yr,
                        exclusion_reasons = EXCLUDED.exclusion_reasons,
                        model_flags = EXCLUDED.model_flags,
                        assumption_version = EXCLUDED.assumption_version,
                        benchmark_source = EXCLUDED.benchmark_source,
                        geometry = EXCLUDED.geometry,
                        rebuilt_at = EXCLUDED.rebuilt_at
                    """,
                    {
                        **row,
                        "allowed_scenarios": json.dumps(allowed),
                        "policy_scenarios": json.dumps(policy),
                        "scenario_results": json.dumps(scenario_results),
                        "current_opportunity_10yr": best_current,
                        "policy_opportunity_10yr": best_policy,
                        "city_current_opportunity_10yr": best_city_current,
                        "city_policy_opportunity_10yr": best_city_policy,
                        "exclusion_reasons": json.dumps(sorted(exclusion_reasons)),
                        "model_flags": json.dumps({
                            "eligible": bool(allowed or policy),
                            "current_model_eligible": bool(allowed),
                            "policy_model_eligible": bool(policy),
                            "productivity_label": row["productivity_label"],
                        }),
                        "assumption_version": ASSUMPTION_VERSION,
                        "benchmark_source": json.dumps({
                            **benchmark_meta,
                            "exclusion_reasons": sorted(exclusion_reasons),
                            "assumption_version": ASSUMPTION_VERSION,
                        }),
                        "geometry": json.dumps(row["geometry"]),
                        "rebuilt_at": now,
                    },
                )

            cursor.execute(
                """
                INSERT INTO land_ledger_city_summary (
                    city_slug, city_name, parcel_count, zoned_count,
                    unknown_zone_count, current_opportunity_10yr,
                    policy_opportunity_10yr, city_current_opportunity_10yr,
                    city_policy_opportunity_10yr, eligible_parcel_count,
                    excluded_parcel_count, scenario_totals, exclusion_counts,
                    assumption_version, diagnostics, scenario_definitions,
                    zone_descriptions, buildout_factor, horizon_years, rebuilt_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s)
                ON CONFLICT (city_slug) DO UPDATE SET
                    city_name = EXCLUDED.city_name,
                    parcel_count = EXCLUDED.parcel_count,
                    zoned_count = EXCLUDED.zoned_count,
                    unknown_zone_count = EXCLUDED.unknown_zone_count,
                    current_opportunity_10yr = EXCLUDED.current_opportunity_10yr,
                    policy_opportunity_10yr = EXCLUDED.policy_opportunity_10yr,
                    city_current_opportunity_10yr = EXCLUDED.city_current_opportunity_10yr,
                    city_policy_opportunity_10yr = EXCLUDED.city_policy_opportunity_10yr,
                    eligible_parcel_count = EXCLUDED.eligible_parcel_count,
                    excluded_parcel_count = EXCLUDED.excluded_parcel_count,
                    scenario_totals = EXCLUDED.scenario_totals,
                    exclusion_counts = EXCLUDED.exclusion_counts,
                    assumption_version = EXCLUDED.assumption_version,
                    diagnostics = EXCLUDED.diagnostics,
                    scenario_definitions = EXCLUDED.scenario_definitions,
                    zone_descriptions = EXCLUDED.zone_descriptions,
                    buildout_factor = EXCLUDED.buildout_factor,
                    horizon_years = EXCLUDED.horizon_years,
                    rebuilt_at = EXCLUDED.rebuilt_at
                """,
                [
                    city_slug,
                    CITY_CONFIGS[city_slug]["name"],
                    summary["parcel_count"],
                    summary["zoned_count"],
                    summary["unknown_zone_count"],
                    current_total,
                    policy_total,
                    city_current_total,
                    city_policy_total,
                    summary["eligible_parcel_count"],
                    summary["excluded_parcel_count"],
                    json.dumps(summary["scenario_totals"]),
                    json.dumps(summary["exclusion_counts"]),
                    ASSUMPTION_VERSION,
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
