from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode

from django.db import connection


ASSESSOR_DETAIL_URL = "https://www.skagitcounty.net/search/property/default.aspx?id={parcel_number}"
AUDITOR_RECORDING_SEARCH_URL = "https://www.skagitcounty.net/Search/Recording/default.aspx"
AUDITOR_DOCUMENT_URL = "https://www.skagitcounty.net/AuditorRecording/Documents/RecordedDocuments/{year}/{month}/{day}/{recording_number}.pdf"
RECENT_RECORDING_DAYS = 90
SFR_OR_MOBILE_CODES = {"110", "111", "112", "113", "180", "185"}
SFR_TEARDOWN_CODES = {"110", "111", "112", "113"}
VACANT_BUILDABLE_CODES = {"910", "911", "912"}
VACANT_OR_DWELLING_CODES = VACANT_BUILDABLE_CODES | SFR_OR_MOBILE_CODES
PUBLIC_OR_CIVIC_CODES = {"0", "450", "480", "670", "680", "760", "930", "970"}
RESOURCE_CODES = {"810", "830", "840", "850", "880", "920", "940"}
EXEMPT_OR_COMMON_AREA_CODES = {"0", "140", "500", "970"}
NON_BUILDER_CODES = PUBLIC_OR_CIVIC_CODES | RESOURCE_CODES
URBAN_RESIDENTIAL_ZONE_GROUPS = {"LIR", "MR"}
MIXED_OR_COMMERCIAL_REDEVELOPMENT_ZONE_GROUPS = {"MXU", "COM"}
SORT_FIELDS = {"assessed", "zone", "risk", "location"}


BUILDER_ZONE_EXCLUSION_SQL = """
  COALESCE(z.zone_id, '') <> 'R-A'
  AND COALESCE(z.zone_id, '') NOT ILIKE 'RR%%'
  AND COALESCE(z.zone_id, '') NOT ILIKE 'RVR%%'
  AND COALESCE(z.zone_id, '') <> 'RI'
"""


RESIDENTIAL_ZONE_SQL = """
(
  z.waza_general ILIKE '%%residential%%'
  OR z.zone_id ILIKE 'R%%'
  OR z.zone_name ILIKE '%%residential%%'
)
"""


@dataclass(frozen=True)
class OpportunityTab:
    key: str
    label: str
    description: str
    note: str


TABS = [
    OpportunityTab("delinquent-tax-pressure", "Delinquent Tax Pressure", "Parcels where unpaid taxes may signal owner pressure or a need to resolve carrying costs.", "Signals show delinquent tax years and total amount due; sorted by tax pressure and redevelopment relevance."),
    OpportunityTab("vacant-buildable-lots", "Vacant Buildable Lots", "Residentially zoned parcels with little or no building value where a straightforward build may be possible.", "Signals show utility and frontage clues; sorted toward urban vacant lots with better service signals."),
    OpportunityTab("possible-lot-splits", "Possible Lot Splits", "Large residential lots that stand out against smaller nearby or same-zone lots and may have extra land capacity.", "Signals show theoretical capacity screens, not approved yield; sorted by oversize lots versus nearby median lots."),
    OpportunityTab("teardown-candidates", "Teardown Candidates", "Single-family parcels where the land value is high and the existing main dwelling appears low-value or obsolete.", "Signals show main dwelling condition/year and land-building ratio; manufactured homes, recent homes, and good-condition homes are excluded."),
]
TAB_LOOKUP = {tab.key: tab for tab in TABS}
DEFAULT_TAB = TABS[0].key
ROW_LIMIT = 100


def money(value: Any) -> str:
    amount = _decimal(value) or Decimal("0")
    return f"${amount:,.0f}"


def acres(value: Any) -> str:
    amount = _decimal(value)
    if amount is None:
        return "unknown acres"
    return f"{amount:.2f} acres"


def ratio(value: Any) -> str:
    amount = _decimal(value)
    if amount is None:
        return "unknown"
    return f"{amount:.1f}x"


def risk_flags(*flags: str | None) -> list[str]:
    return [flag for flag in flags if flag]


def land_use_code(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().lstrip("(").split(")")[0].strip()


def is_resource_land_use(value: str | None) -> bool:
    return land_use_code(value) in RESOURCE_CODES


def is_public_or_civic_land_use(value: str | None) -> bool:
    return land_use_code(value) in PUBLIC_OR_CIVIC_CODES


def is_vacant_buildable_land_use(value: str | None) -> bool:
    return land_use_code(value) in VACANT_BUILDABLE_CODES


def is_residential_dwelling_land_use(value: str | None) -> bool:
    return land_use_code(value) in SFR_OR_MOBILE_CODES


def is_natural_resource_zone(zone_id: str | None = "", zone_name: str | None = "", waza_general: str | None = "") -> bool:
    zone_text = f"{zone_id or ''} {zone_name or ''}".upper()
    return (waza_general or "").upper() == "NRL" or "-NRL" in zone_text


def is_public_or_open_space_zone(waza_general: str | None = "") -> bool:
    return (waza_general or "").upper() in {"PUB", "OS"}


def is_urban_residential_zone(waza_general: str | None = "") -> bool:
    return (waza_general or "").upper() in URBAN_RESIDENTIAL_ZONE_GROUPS


def is_mixed_or_commercial_redevelopment_zone(waza_general: str | None = "") -> bool:
    return (waza_general or "").upper() in MIXED_OR_COMMERCIAL_REDEVELOPMENT_ZONE_GROUPS


def is_rural_residential_zone(waza_general: str | None = "") -> bool:
    return (waza_general or "").upper() == "RUR"


def utility_labels(value: str | None) -> list[str]:
    text = (value or "").upper()
    if not text.strip() or "NONE" in text:
        return []
    labels = []
    if "SEW" in text:
        labels.append("sewer")
    if "SEP" in text:
        labels.append("septic")
    if "PWR" in text:
        labels.append("power")
    if "WTR-P" in text:
        labels.append("public water")
    elif "WTR-W" in text:
        labels.append("well water")
    elif "WTR" in text:
        labels.append("water")
    return labels


def utility_phrase(value: str | None) -> str:
    labels = utility_labels(value)
    if not labels:
        return "no utility signal"
    if len(labels) == 1:
        return f"{labels[0]} indicated"
    return f"{', '.join(labels[:-1])} and {labels[-1]} indicated"


def feature_labels(row: dict[str, Any]) -> list[str]:
    labels = utility_labels(row.get("utilities"))
    frontage = _decimal(row.get("effective_frontage") or row.get("actual_frontage"))
    if frontage:
        labels.append(f"{frontage:.0f} ft frontage")
    return labels


def fetch_tab_rows(
    tab_key: str,
    filters: dict[str, str],
    limit: int = ROW_LIMIT,
    sort: str = "",
    direction: str = "desc",
) -> list[dict[str, Any]]:
    raw_limit = limit if limit >= 1000 else limit * 5
    if tab_key == "vacant-buildable-lots":
        rows = _dedupe_rows(vacant_buildable_lots(filters, raw_limit))
    elif tab_key == "possible-lot-splits":
        rows = _dedupe_rows(possible_lot_splits(filters, raw_limit))
    elif tab_key == "teardown-candidates":
        rows = _dedupe_rows(teardown_candidates(filters, raw_limit))
    else:
        rows = _dedupe_rows(delinquent_tax_pressure(filters, raw_limit))
    return _sort_rows(rows, sort, direction)[:limit]


def tab_counts(filters: dict[str, str]) -> dict[str, str]:
    return {tab.key: "" for tab in TABS}


def delinquent_tax_pressure(filters: dict[str, str], limit: int) -> list[dict[str, Any]]:
    min_years = _int_filter(filters.get("min_years"), 1)
    min_due = _decimal_filter(filters.get("min_due"), Decimal("0"))
    min_land_ratio = _decimal_filter(filters.get("min_land_ratio"), Decimal("0"))
    improved = filters.get("improved", "")
    place = filters.get("place", "")
    where = [
        "p.inactive_date IS NULL",
        "t.total_due > 0",
        "COALESCE(p.assessed_value, 0) > 0",
        "COALESCE(p.neighborhood_code, '') NOT ILIKE '%%COMAREA%%'",
        "COALESCE(p.exemptions, '') NOT ILIKE '%%COMAREA%%'",
        "split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) = ANY(%s)",
        "split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) <> ALL(%s)",
        "COALESCE(z.waza_general, '') IN ('LIR', 'MR', 'MXU', 'COM')",
        "COALESCE(z.waza_general, '') NOT IN ('NRL', 'PUB', 'OS')",
        "COALESCE(z.zone_id, '') NOT ILIKE '%%-NRL%%'",
        "COALESCE(z.zone_name, '') NOT ILIKE '%%Natural Resource%%'",
        BUILDER_ZONE_EXCLUSION_SQL,
        "t.tax_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 1",
    ]
    if improved == "vacant":
        where.append("COALESCE(p.building_value, 0) <= 10000")
    elif improved == "improved":
        where.append("COALESCE(p.building_value, 0) > 10000")
    if place == "city":
        where.append("COALESCE(z.jurisdiction, z.citydistrict, p.city_district, '') <> ''")
    elif place == "unincorporated":
        where.append("COALESCE(z.jurisdiction, z.citydistrict, p.city_district, '') = ''")

    sql = f"""
        WITH due AS (
            SELECT t.parcel_number,
                   COUNT(DISTINCT t.tax_year) FILTER (WHERE t.tax_year < EXTRACT(YEAR FROM CURRENT_DATE)::int) AS years_delinquent,
                   COUNT(DISTINCT t.tax_year) FILTER (WHERE t.tax_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int) AS current_year_count,
                   array_agg(DISTINCT t.tax_year ORDER BY t.tax_year DESC) AS past_due_years,
                   SUM(t.total_due) AS total_due,
                   MAX(CASE t.lead_level
                     WHEN 'severe' THEN 5 WHEN 'serious' THEN 4 WHEN 'behind' THEN 3
                     WHEN 'one_late' THEN 2 WHEN 'watch' THEN 1 ELSE 0 END) AS lead_score,
                   MIN(t.oldest_due_date) AS oldest_due_date
            FROM tax_delinquency_taxstatement t
            JOIN skagit_parcels p ON p.parcel_number = t.parcel_number
            LEFT JOIN parcel_primary_zoning z ON z.parcel_id = p.parcel_number
            WHERE {" AND ".join(where)}
            GROUP BY t.parcel_number
        )
        SELECT p.parcel_number,
               concat_ws(' ', p.situs_street_number, p.situs_street_name) AS address,
               COALESCE(NULLIF(p.situs_city_state_zip, ''), NULLIF(z.citydistrict, ''), NULLIF(z.jurisdiction, '')) AS city,
               p.owner_name, p.acres, z.zone_id, z.zone_name,
               z.waza_general, z.waza_specific, z.reference_url,
               p.assessed_value, p.impr_land_value, p.unimpr_land_value, p.building_value,
               COALESCE(p.impr_land_value, 0) + COALESCE(p.unimpr_land_value, 0) AS land_value,
               CASE WHEN COALESCE(p.assessed_value, 0) <= 0 THEN NULL
                    ELSE (COALESCE(p.impr_land_value, 0) + COALESCE(p.unimpr_land_value, 0)) / NULLIF(p.assessed_value, 0) * 100
               END AS land_value_pct,
               p.land_use, p.utilities, p.owner_city, p.owner_state, p.year_built,
               split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) AS land_use_code,
               due.years_delinquent, due.current_year_count, due.past_due_years, due.total_due, due.oldest_due_date,
               sale.recording_number, sale.deed_type, sale.deed_date_iso, sale.sale_date_iso, sale.sale_price_num,
               hist.value_5yr_growth_pct,
               CASE WHEN COALESCE(p.building_value, 0) <= 0 THEN NULL
                    ELSE (COALESCE(p.impr_land_value, 0) + COALESCE(p.unimpr_land_value, 0)) / NULLIF(p.building_value, 0)
               END AS land_building_ratio,
               ST_Y(ST_Centroid(g.geometry)) AS lat, ST_X(ST_Centroid(g.geometry)) AS lng,
               due.years_delinquent * 220
                 + due.current_year_count * 35
                 + due.lead_score * 25
                 + LEAST((COALESCE(p.impr_land_value, 0) + COALESCE(p.unimpr_land_value, 0)) / 10000, 100)
                 + CASE
                     WHEN COALESCE(p.building_value, 0) <= 0
                       AND (COALESCE(p.impr_land_value, 0) + COALESCE(p.unimpr_land_value, 0)) > 0 THEN 90
                     WHEN (COALESCE(p.impr_land_value, 0) + COALESCE(p.unimpr_land_value, 0)) / NULLIF(p.building_value, 0) >= 2 THEN 60
                     WHEN (COALESCE(p.impr_land_value, 0) + COALESCE(p.unimpr_land_value, 0)) / NULLIF(p.building_value, 0) >= 1 THEN 30
                     ELSE 0
                   END
                 + CASE WHEN p.utilities ILIKE '%%SEW%%' THEN 25 ELSE 0 END
                 + CASE WHEN p.utilities ILIKE '%%WTR-P%%' THEN 15 ELSE 0 END
                 + LEAST(COALESCE(hist.value_5yr_growth_pct, 0), 100) / 4
                 - CASE WHEN COALESCE(p.building_value, 0) > 500000 THEN 35 ELSE 0 END AS score
        FROM due
        JOIN skagit_parcels p ON p.parcel_number = due.parcel_number
        LEFT JOIN gis_skagit_parcels g ON g.parcel_id = p.parcel_number
        LEFT JOIN parcel_primary_zoning z ON z.parcel_id = p.parcel_number
        LEFT JOIN LATERAL (
            SELECT
                (
                    max(total_value) FILTER (WHERE tax_year = 2025)
                    - max(total_value) FILTER (WHERE tax_year = 2020)
                ) / NULLIF(max(total_value) FILTER (WHERE tax_year = 2020), 0) * 100 AS value_5yr_growth_pct
            FROM skagit_parcel_history h
            WHERE h.parcel_number = p.parcel_number
              AND h.tax_year IN (2020, 2025)
        ) hist ON true
        LEFT JOIN LATERAL (
            SELECT s.recording_number, s.deed_type, s.deed_date_iso, s.sale_date_iso, s.sale_price_num
            FROM sales s
            WHERE s.parcel_number = p.parcel_number
              AND (s.recording_number IS NOT NULL OR s.deed_date_iso IS NOT NULL OR s.sale_date_iso IS NOT NULL)
            ORDER BY COALESCE(s.deed_date_iso, s.sale_date_iso) DESC NULLS LAST
            LIMIT 1
        ) sale ON true
        WHERE due.years_delinquent >= %s
          AND due.total_due >= %s
          AND (%s = 0 OR COALESCE(p.building_value, 0) = 0
               OR (COALESCE(p.impr_land_value, 0) + COALESCE(p.unimpr_land_value, 0)) / NULLIF(p.building_value, 0) >= %s)
        ORDER BY score DESC NULLS LAST, due.years_delinquent DESC, due.total_due DESC NULLS LAST
        LIMIT %s
    """
    return [_format_delinquency(row) for row in _fetch(sql, [list(VACANT_OR_DWELLING_CODES), list(NON_BUILDER_CODES | EXEMPT_OR_COMMON_AREA_CODES), min_years, min_due, min_land_ratio, min_land_ratio, limit])]


def vacant_buildable_lots(filters: dict[str, str], limit: int) -> list[dict[str, Any]]:
    min_acres = _decimal_filter(filters.get("min_acres"), Decimal("0.10"))
    max_building = _decimal_filter(filters.get("max_building"), Decimal("10000"))
    sql = f"""
        SELECT p.parcel_number,
               concat_ws(' ', p.situs_street_number, p.situs_street_name) AS address,
               COALESCE(NULLIF(p.situs_city_state_zip, ''), NULLIF(z.citydistrict, ''), NULLIF(z.jurisdiction, '')) AS city,
               p.owner_name, p.acres, z.zone_id, z.zone_name,
               z.waza_general, z.waza_specific, z.reference_url,
               z.jurisdiction, p.assessed_value, p.impr_land_value, p.unimpr_land_value,
               p.building_value, p.land_use, p.utilities,
               split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) AS land_use_code,
               ls.effective_frontage, ls.actual_frontage, ls.primary_land_type,
               ST_Y(ST_Centroid(g.geometry)) AS lat, ST_X(ST_Centroid(g.geometry)) AS lng,
               COALESCE(p.acres, 0) * 20 + CASE WHEN {RESIDENTIAL_ZONE_SQL} THEN 80 ELSE 0 END
                 + CASE WHEN split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) = '911' THEN 45 ELSE 0 END
                 + CASE WHEN p.utilities ILIKE '%%SEW%%' THEN 35 ELSE 0 END
                 + CASE WHEN p.utilities ILIKE '%%PWR%%' THEN 20 ELSE 0 END
                 + CASE WHEN p.utilities ILIKE '%%WTR-P%%' THEN 20 ELSE 0 END
                 + CASE WHEN COALESCE(ls.effective_frontage, 0) > 30 THEN 20 ELSE 0 END
                 + CASE WHEN concat_ws(' ', p.situs_street_number, p.situs_street_name) <> '' THEN 20 ELSE 0 END
                 + CASE WHEN COALESCE(z.jurisdiction, z.citydistrict, p.city_district, '') <> '' THEN 20 ELSE 0 END
                 - COALESCE(p.building_value, 0) / 1000 AS score
        FROM skagit_parcels p
        LEFT JOIN gis_skagit_parcels g ON g.parcel_id = p.parcel_number
        LEFT JOIN parcel_primary_zoning z ON z.parcel_id = p.parcel_number
        LEFT JOIN LATERAL (
            SELECT
                max(NULLIF(regexp_replace(effective_front, '[^0-9.]', '', 'g'), '')::numeric) AS effective_frontage,
                max(NULLIF(regexp_replace(actual_front, '[^0-9.]', '', 'g'), '')::numeric) AS actual_frontage,
                (array_agg(NULLIF(land_type, '') ORDER BY market_value_num DESC NULLS LAST))[1] AS primary_land_type
            FROM land l
            WHERE l.parcelnumber = p.parcel_number
        ) ls ON true
        WHERE p.inactive_date IS NULL
          AND COALESCE(p.assessed_value, 0) > 0
          AND COALESCE(p.neighborhood_code, '') NOT ILIKE '%%COMAREA%%'
          AND COALESCE(p.exemptions, '') NOT ILIKE '%%COMAREA%%'
          AND p.acres >= %s
          AND p.acres <= 2
          AND COALESCE(p.building_value, 0) <= %s
          AND split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) = ANY(%s)
          AND split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) <> ALL(%s)
          AND COALESCE(z.waza_general, '') IN ('LIR', 'MR')
          AND COALESCE(z.waza_general, '') NOT IN ('NRL', 'PUB', 'OS')
          AND COALESCE(z.zone_id, '') NOT ILIKE '%%-NRL%%'
          AND COALESCE(z.zone_name, '') NOT ILIKE '%%Natural Resource%%'
          AND {BUILDER_ZONE_EXCLUSION_SQL}
          AND {RESIDENTIAL_ZONE_SQL}
        ORDER BY score DESC NULLS LAST, p.acres DESC NULLS LAST
        LIMIT %s
    """
    return [_format_vacant(row) for row in _fetch(sql, [min_acres, max_building, list(VACANT_BUILDABLE_CODES), list(NON_BUILDER_CODES), limit])]


def possible_lot_splits(filters: dict[str, str], limit: int) -> list[dict[str, Any]]:
    min_acres = _decimal_filter(filters.get("min_acres"), Decimal("0.35"))
    max_building = _decimal_filter(filters.get("max_building"), Decimal("250000"))
    sql = f"""
        WITH residential AS (
            SELECT p.parcel_number, p.acres, COALESCE(z.citydistrict, p.city_district, z.jurisdiction, 'UNKNOWN') AS place_key,
                   COALESCE(z.zone_id, 'UNKNOWN') AS zone_key
            FROM skagit_parcels p
            LEFT JOIN parcel_primary_zoning z ON z.parcel_id = p.parcel_number
            WHERE p.inactive_date IS NULL
              AND COALESCE(p.assessed_value, 0) > 0
              AND COALESCE(p.neighborhood_code, '') NOT ILIKE '%%COMAREA%%'
              AND COALESCE(p.exemptions, '') NOT ILIKE '%%COMAREA%%'
              AND p.acres BETWEEN 0.04 AND 1.5
              AND split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) = ANY(%s)
              AND split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) <> ALL(%s)
              AND COALESCE(z.waza_general, '') IN ('LIR', 'MR')
              AND COALESCE(z.waza_general, '') NOT IN ('NRL', 'PUB', 'OS')
              AND COALESCE(z.zone_id, '') NOT ILIKE '%%-NRL%%'
              AND COALESCE(z.zone_name, '') NOT ILIKE '%%Natural Resource%%'
              AND {BUILDER_ZONE_EXCLUSION_SQL}
              AND {RESIDENTIAL_ZONE_SQL}
        ),
        cohorts AS (
            SELECT place_key, zone_key,
                   COUNT(*) AS neighbor_count,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY acres) AS nearby_median_acres
            FROM residential
            GROUP BY place_key, zone_key
        )
        SELECT p.parcel_number,
               concat_ws(' ', p.situs_street_number, p.situs_street_name) AS address,
               COALESCE(NULLIF(p.situs_city_state_zip, ''), NULLIF(z.citydistrict, ''), NULLIF(z.jurisdiction, '')) AS city,
               p.owner_name, p.acres, z.zone_id, z.zone_name,
               z.waza_general, z.waza_specific, z.reference_url,
               z.jurisdiction, p.assessed_value, p.impr_land_value, p.unimpr_land_value,
               p.building_value, p.land_use, p.utilities, p.year_built,
               split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) AS land_use_code,
               c.neighbor_count, c.nearby_median_acres,
               floor(p.acres / NULLIF(c.nearby_median_acres, 0))::integer AS estimated_lot_count,
               ls.effective_frontage, ls.actual_frontage,
               ST_Y(ST_Centroid(g.geometry)) AS lat, ST_X(ST_Centroid(g.geometry)) AS lng,
               (p.acres / NULLIF(c.nearby_median_acres, 0)) * 35
                 + CASE WHEN COALESCE(p.building_value, 0) <= 100000 THEN 30 ELSE 0 END
                 + CASE WHEN COALESCE(z.jurisdiction, z.citydistrict, p.city_district, '') <> '' THEN 20 ELSE 0 END AS score
        FROM skagit_parcels p
        JOIN gis_skagit_parcels g ON g.parcel_id = p.parcel_number
        LEFT JOIN parcel_primary_zoning z ON z.parcel_id = p.parcel_number
        LEFT JOIN LATERAL (
            SELECT NULL::numeric AS effective_frontage, NULL::numeric AS actual_frontage
        ) ls ON true
        JOIN cohorts c
          ON c.place_key = COALESCE(z.citydistrict, p.city_district, z.jurisdiction, 'UNKNOWN')
         AND c.zone_key = COALESCE(z.zone_id, 'UNKNOWN')
        WHERE p.inactive_date IS NULL
          AND COALESCE(p.assessed_value, 0) > 0
          AND COALESCE(p.neighborhood_code, '') NOT ILIKE '%%COMAREA%%'
          AND COALESCE(p.exemptions, '') NOT ILIKE '%%COMAREA%%'
          AND p.acres >= %s
          AND p.acres <= 5
          AND COALESCE(p.building_value, 0) <= %s
          AND split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) = ANY(%s)
          AND split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) <> ALL(%s)
          AND COALESCE(z.waza_general, '') IN ('LIR', 'MR')
          AND COALESCE(z.waza_general, '') NOT IN ('NRL', 'PUB', 'OS')
          AND COALESCE(z.zone_id, '') NOT ILIKE '%%-NRL%%'
          AND COALESCE(z.zone_name, '') NOT ILIKE '%%Natural Resource%%'
          AND {BUILDER_ZONE_EXCLUSION_SQL}
          AND {RESIDENTIAL_ZONE_SQL}
          AND c.neighbor_count >= 5
          AND c.nearby_median_acres IS NOT NULL
          AND p.acres >= c.nearby_median_acres * 2.5
        ORDER BY score DESC NULLS LAST
        LIMIT %s
    """
    return [_format_lot_split(row) for row in _fetch(sql, [list(VACANT_OR_DWELLING_CODES), list(NON_BUILDER_CODES), min_acres, max_building, list(VACANT_OR_DWELLING_CODES), list(NON_BUILDER_CODES), limit])]


def teardown_candidates(filters: dict[str, str], limit: int) -> list[dict[str, Any]]:
    min_land_value = _decimal_filter(filters.get("min_land_value"), Decimal("150000"))
    max_building = _decimal_filter(filters.get("max_building"), Decimal("180000"))
    sql = f"""
        SELECT p.parcel_number,
               concat_ws(' ', p.situs_street_number, p.situs_street_name) AS address,
               COALESCE(NULLIF(p.situs_city_state_zip, ''), NULLIF(z.citydistrict, ''), NULLIF(z.jurisdiction, '')) AS city,
               p.owner_name, p.acres, z.zone_id, z.zone_name,
               z.waza_general, z.waza_specific, z.reference_url,
               p.assessed_value, p.impr_land_value, p.unimpr_land_value, p.building_value,
               p.land_use, p.year_built, p.eff_year_built,
               split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) AS land_use_code,
               i.improvement_count, i.primary_style, i.primary_condition, i.primary_quality,
               i.primary_effective_year, i.primary_actual_year, i.primary_living_area,
               (COALESCE(p.impr_land_value, 0) + COALESCE(p.unimpr_land_value, 0)) / NULLIF(p.building_value, 0) AS teardown_ratio,
               COALESCE(i.primary_effective_year, p.eff_year_built, p.year_built, 9999) AS teardown_year,
               lower(COALESCE(i.primary_condition, 'unknown')) AS teardown_condition,
               ST_Y(ST_Centroid(g.geometry)) AS lat, ST_X(ST_Centroid(g.geometry)) AS lng,
               (COALESCE(p.impr_land_value, 0) + COALESCE(p.unimpr_land_value, 0))
                 + LEAST(((COALESCE(p.impr_land_value, 0) + COALESCE(p.unimpr_land_value, 0)) / NULLIF(p.building_value, 0)) * 25000, 250000)
                 + CASE WHEN lower(COALESCE(i.primary_condition, '')) IN ('poor', 'low') THEN 90000
                        WHEN lower(COALESCE(i.primary_condition, '')) = 'fair' THEN 65000
                        ELSE 20000 END
                 + CASE WHEN COALESCE(i.primary_effective_year, p.eff_year_built, p.year_built, 9999) < 1960 THEN 80000
                        WHEN COALESCE(i.primary_effective_year, p.eff_year_built, p.year_built, 9999) < 1975 THEN 50000
                        ELSE 15000 END
                 - COALESCE(p.building_value, 0) AS score
        FROM skagit_parcels p
        LEFT JOIN gis_skagit_parcels g ON g.parcel_id = p.parcel_number
        LEFT JOIN parcel_primary_zoning z ON z.parcel_id = p.parcel_number
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) AS improvement_count,
                (array_agg(
                    COALESCE(NULLIF(trim(imprv_det_type_description), ''), NULLIF(trim(imprv_det_type_cd), ''), NULLIF(trim(building_style), ''))
                    ORDER BY imprv_val_num DESC NULLS LAST
                ))[1] AS primary_style,
                (array_agg(NULLIF(condition_description, '') ORDER BY imprv_val_num DESC NULLS LAST))[1] AS primary_condition,
                (array_agg(NULLIF(imprv_det_class_description, '') ORDER BY imprv_val_num DESC NULLS LAST))[1] AS primary_quality,
                (array_agg(NULLIF(effective_yr_blt, '')::numeric ORDER BY imprv_val_num DESC NULLS LAST))[1] AS primary_effective_year,
                (array_agg(NULLIF(actual_year_built, '')::numeric ORDER BY imprv_val_num DESC NULLS LAST))[1] AS primary_actual_year,
                (array_agg(living_area_num ORDER BY imprv_val_num DESC NULLS LAST))[1] AS primary_living_area
            FROM improvements i
            WHERE i.parcelnumber = p.parcel_number
              AND trim(COALESCE(i.imprv_det_type_cd, '')) IN (
                  'MA', 'MA2', 'MA1.5F', 'MA-SPLIT', 'UF2', 'UF1.5F',
                  'BMF', 'BMU', 'BMG'
              )
        ) i ON true
        WHERE p.inactive_date IS NULL
          AND COALESCE(p.assessed_value, 0) > 0
          AND COALESCE(p.neighborhood_code, '') NOT ILIKE '%%COMAREA%%'
          AND COALESCE(p.exemptions, '') NOT ILIKE '%%COMAREA%%'
          AND (COALESCE(p.impr_land_value, 0) + COALESCE(p.unimpr_land_value, 0)) >= %s
          AND COALESCE(p.building_value, 0) <= %s
          AND COALESCE(p.building_value, 0) > 0
          AND split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) = ANY(%s)
          AND split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) <> ALL(%s)
          AND COALESCE(z.waza_general, '') IN ('LIR', 'MR', 'MXU', 'COM')
          AND COALESCE(z.waza_general, '') NOT IN ('NRL', 'PUB', 'OS')
          AND COALESCE(z.zone_id, '') NOT ILIKE '%%-NRL%%'
          AND COALESCE(z.zone_name, '') NOT ILIKE '%%Natural Resource%%'
          AND {BUILDER_ZONE_EXCLUSION_SQL}
          AND {RESIDENTIAL_ZONE_SQL}
          AND COALESCE(i.improvement_count, 0) > 0
          AND (COALESCE(p.impr_land_value, 0) + COALESCE(p.unimpr_land_value, 0)) / NULLIF(p.building_value, 0) >= 3
          AND (
              (lower(COALESCE(i.primary_condition, '')) IN ('poor', 'fair', 'low')
               AND COALESCE(i.primary_effective_year, p.eff_year_built, p.year_built, 9999) <= 1989)
              OR
              (lower(COALESCE(i.primary_condition, '')) IN ('average', 'unknown', '')
               AND COALESCE(i.primary_effective_year, p.eff_year_built, p.year_built, 9999) <= 1975)
          )
        ORDER BY score DESC NULLS LAST
        LIMIT %s
    """
    return [_format_teardown(row) for row in _fetch(sql, [min_land_value, max_building, list(SFR_TEARDOWN_CODES), list(NON_BUILDER_CODES), limit])]


def assemblage_opportunities(filters: dict[str, str], limit: int) -> list[dict[str, Any]]:
    min_cluster = _int_filter(filters.get("min_cluster"), 2)
    sql = f"""
        WITH candidates AS (
            SELECT p.parcel_number, p.owner_name,
                   concat_ws(' ', p.situs_street_number, p.situs_street_name) AS address,
                   COALESCE(NULLIF(p.situs_city_state_zip, ''), NULLIF(z.citydistrict, ''), NULLIF(z.jurisdiction, '')) AS city,
                   p.acres, p.assessed_value, p.impr_land_value,
                   p.unimpr_land_value, p.building_value, p.land_use, z.zone_id, z.zone_name,
                   z.waza_general, z.waza_specific, z.reference_url, g.geometry,
                   split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) AS land_use_code,
                   regexp_replace(upper(COALESCE(p.owner_name, '')), '[^A-Z0-9]', '', 'g') AS owner_key,
                   COALESCE(z.zone_id, 'UNKNOWN') AS zone_key,
                   EXISTS (
                       SELECT 1 FROM tax_delinquency_taxstatement t
                       WHERE t.parcel_number = p.parcel_number AND t.total_due > 0
                   ) AS has_delinquency
            FROM skagit_parcels p
            JOIN gis_skagit_parcels g ON g.parcel_id = p.parcel_number
            LEFT JOIN parcel_primary_zoning z ON z.parcel_id = p.parcel_number
            WHERE p.inactive_date IS NULL
              AND COALESCE(p.assessed_value, 0) > 0
              AND COALESCE(p.neighborhood_code, '') NOT ILIKE '%%COMAREA%%'
              AND COALESCE(p.exemptions, '') NOT ILIKE '%%COMAREA%%'
              AND p.owner_name IS NOT NULL
              AND p.owner_name <> ''
              AND COALESCE(p.acres, 0) BETWEEN 0.03 AND 3
              AND split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) = ANY(%s)
              AND split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) <> ALL(%s)
              AND COALESCE(z.waza_general, '') NOT IN ('NRL', 'PUB', 'OS')
              AND COALESCE(z.waza_general, '') IN ('LIR', 'MR', 'MXU', 'COM')
              AND COALESCE(z.zone_id, '') NOT ILIKE '%%-NRL%%'
              AND COALESCE(z.zone_name, '') NOT ILIKE '%%Natural Resource%%'
              AND {BUILDER_ZONE_EXCLUSION_SQL}
              AND (COALESCE(p.building_value, 0) <= 50000 OR p.land_use ~ '^\\(?9')
            ORDER BY COALESCE(p.building_value, 0), COALESCE(p.acres, 0) DESC
            LIMIT 2500
        ),
        clusters AS (
            SELECT c.parcel_number, c.owner_name, c.address, c.city, c.acres, c.zone_id, c.zone_name,
                   c.waza_general, c.waza_specific, c.reference_url,
                   c.assessed_value, c.impr_land_value, c.unimpr_land_value, c.building_value, c.land_use, c.land_use_code,
                   ST_Y(ST_Centroid(c.geometry)) AS lat, ST_X(ST_Centroid(c.geometry)) AS lng,
                   COUNT(n.parcel_number) AS cluster_count, SUM(n.acres) AS cluster_acres,
                   SUM(CASE WHEN n.has_delinquency THEN 1 ELSE 0 END) AS delinquent_neighbors,
                   SUM(CASE WHEN COALESCE(n.building_value, 0) <= 10000 THEN 1 ELSE 0 END) AS vacant_like_count,
                   COUNT(DISTINCT n.zone_key) AS neighbor_zone_count
            FROM candidates c
            JOIN candidates n
              ON n.owner_key = c.owner_key
             AND n.parcel_number <> c.parcel_number
             AND ST_DWithin(c.geometry::geography, n.geometry::geography, 90)
            GROUP BY c.parcel_number, c.owner_name, c.address, c.city, c.acres, c.zone_id, c.zone_name,
                     c.waza_general, c.waza_specific, c.reference_url,
                     c.assessed_value, c.impr_land_value, c.unimpr_land_value, c.building_value, c.land_use, c.land_use_code, c.geometry
        )
        SELECT *, cluster_count * 50 + cluster_acres * 20 + delinquent_neighbors * 30 + vacant_like_count * 10
                  + CASE WHEN neighbor_zone_count = 1 THEN 25 ELSE 0 END AS score
        FROM clusters
        WHERE cluster_count + 1 >= %s
        ORDER BY score DESC NULLS LAST, cluster_count DESC, cluster_acres DESC
        LIMIT %s
    """
    return [_format_assemblage(row) for row in _fetch(sql, [list(VACANT_OR_DWELLING_CODES), list(NON_BUILDER_CODES), min_cluster, limit])]


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        parcel_number = row.get("parcel_number")
        if parcel_number in seen:
            continue
        seen.add(parcel_number)
        deduped.append(row)
    return deduped


def _sort_rows(rows: list[dict[str, Any]], sort: str, direction: str) -> list[dict[str, Any]]:
    if sort not in SORT_FIELDS:
        return rows
    reverse = direction != "asc"
    if sort == "assessed":
        return sorted(rows, key=lambda row: row.get("assessed_value") or Decimal("0"), reverse=reverse)
    if sort == "zone":
        return sorted(rows, key=lambda row: (row.get("zoning") or "").lower(), reverse=reverse)
    if sort == "risk":
        return sorted(rows, key=lambda row: ", ".join(row.get("risk_flags") or []).lower(), reverse=reverse)
    return sorted(rows, key=lambda row: (row.get("location") or "").lower(), reverse=reverse)


def _fetch(sql: str, params: list[Any]) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _base_row(row: dict[str, Any], opportunity_type: str) -> dict[str, Any]:
    lat = row.get("lat")
    lng = row.get("lng")
    map_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}" if lat is not None and lng is not None else ""
    land_value = (row.get("impr_land_value") or 0) + (row.get("unimpr_land_value") or 0)
    address = (row.get("address") or "").strip()
    city = _city_label(row.get("city"))
    return {
        "parcel_number": row.get("parcel_number"),
        "parcel_url": ASSESSOR_DETAIL_URL.format(parcel_number=row.get("parcel_number")),
        "location": _location_label(address, city),
        "city": city,
        "owner": row.get("owner_name") or "",
        "acres": row.get("acres"),
        "acres_fmt": acres(row.get("acres")),
        "land_use": row.get("land_use") or "",
        "land_use_code": row.get("land_use_code") or land_use_code(row.get("land_use")),
        "current_use": _land_use_label(row.get("land_use")),
        "utilities": row.get("utilities") or "",
        "feature_labels": feature_labels(row),
        "signal_labels": [],
        "past_due_years": row.get("past_due_years") or [],
        "effective_frontage": row.get("effective_frontage"),
        "actual_frontage": row.get("actual_frontage"),
        "zoning": row.get("zone_id") or row.get("zone_name") or "Unknown zoning",
        "zone_name": row.get("zone_name") or "",
        "waza_general": row.get("waza_general") or "",
        "zone_definition": _zone_definition(row),
        "zone_url": row.get("reference_url") or "",
        "assessed_value": row.get("assessed_value"),
        "assessed_value_fmt": money(row.get("assessed_value")),
        "land_value_fmt": money(land_value),
        "building_value_fmt": money(row.get("building_value")),
        "score": int(row.get("score") or 0),
        "risk_flags": [],
        "map_url": map_url,
        "auditor_url": "",
        "auditor_label": "",
        "auditor_note": "",
        "recent_document_url": "",
    }


def _format_delinquency(row: dict[str, Any]) -> dict[str, Any]:
    item = _base_row(row, "Delinquent Tax Pressure")
    growth = _decimal(row.get("value_5yr_growth_pct"))
    growth_phrase = _value_history_phrase(growth)
    years_phrase = _delinquent_years_phrase(row.get("years_delinquent"), row.get("current_year_count"))
    zoning = row.get("zone_id") or row.get("zone_name") or "unknown zoning"
    use = _land_use_label(row.get("land_use"))
    item["why_it_ranks"] = (
        f"{years_phrase}. {use} in {zoning}{growth_phrase}."
    )
    amount = _decimal(row.get("total_due"))
    if amount:
        item["signal_labels"] = [f"{money(amount)} due"]
    item["recent_document_url"] = _recent_document_url(row)
    item["risk_flags"] = risk_flags(
        "No parcel geometry" if not item["map_url"] else None,
        "Unknown zoning" if not row.get("zone_id") else None,
        "Natural resource zoning" if is_natural_resource_zone(row.get("zone_id"), row.get("zone_name"), row.get("waza_general")) else None,
        "Public/open-space zoning" if is_public_or_open_space_zone(row.get("waza_general")) else None,
        "Public/civic or moorage use" if is_public_or_civic_land_use(row.get("land_use")) else None,
        "Resource land" if is_resource_land_use(row.get("land_use")) else None,
        "Improved parcel" if (row.get("building_value") or 0) > 10000 else None,
        "Septic/well only" if "sewer" not in utility_labels(row.get("utilities")) and any(label in utility_labels(row.get("utilities")) for label in {"septic", "well water"}) else None,
        "No utility signal" if not utility_labels(row.get("utilities")) else None,
    )
    return item


def _format_vacant(row: dict[str, Any]) -> dict[str, Any]:
    item = _base_row(row, "Vacant Buildable Lot")
    frontage = _decimal(row.get("effective_frontage") or row.get("actual_frontage"))
    frontage_phrase = f", {frontage:.0f} ft frontage" if frontage else ""
    item["signal_labels"] = feature_labels(row)
    item["why_it_ranks"] = (
        f"{acres(row.get('acres'))} {row.get('land_use') or 'vacant parcel'} with "
        f"{utility_phrase(row.get('utilities'))}{frontage_phrase}, residential zoning, "
        f"and {money(row.get('building_value'))} in building value."
    )
    item["risk_flags"] = risk_flags(
        "Very small lot" if (row.get("acres") or 0) < Decimal("0.12") else None,
        "No situs address" if not row.get("address") else None,
        "No parcel geometry" if not item["map_url"] else None,
        "Septic/well only" if "sewer" not in utility_labels(row.get("utilities")) and any(label in utility_labels(row.get("utilities")) for label in {"septic", "well water"}) else None,
        "No utility signal" if not utility_labels(row.get("utilities")) else None,
        "No frontage signal" if not frontage else None,
        "Resource land" if is_resource_land_use(row.get("land_use")) else None,
        "Public/civic use" if is_public_or_civic_land_use(row.get("land_use")) else None,
    )
    return item


def _format_lot_split(row: dict[str, Any]) -> dict[str, Any]:
    item = _base_row(row, "Possible Lot Split")
    estimated_lots = row.get("estimated_lot_count") or 0
    frontage = _decimal(row.get("effective_frontage") or row.get("actual_frontage"))
    frontage_phrase = f", {frontage:.0f} ft frontage" if frontage else ""
    item["signal_labels"] = feature_labels(row) + [
        f"~{estimated_lots} theoretical max",
        f"{acres(row.get('nearby_median_acres'))} nearby median",
    ]
    item["why_it_ranks"] = (
        f"{acres(row.get('acres'))} in residential zoning; nearby lots average "
        f"{acres(row.get('nearby_median_acres'))}; estimated capacity is about {estimated_lots} median-size lots"
        f"{frontage_phrase}; existing improvement value is {money(row.get('building_value'))}."
    )
    item["risk_flags"] = risk_flags(
        "Few nearby comps" if (row.get("neighbor_count") or 0) < 10 else None,
        "Improvement value not trivial" if (row.get("building_value") or 0) > 100000 else None,
        "Unknown zoning" if not row.get("zone_id") else None,
        "No frontage signal" if not frontage else None,
        "Rural split risk" if is_rural_residential_zone(row.get("waza_general")) else None,
        "Natural resource zoning" if is_natural_resource_zone(row.get("zone_id"), row.get("zone_name"), row.get("waza_general")) else None,
        "Resource land" if is_resource_land_use(row.get("land_use")) else None,
    )
    return item


def _format_teardown(row: dict[str, Any]) -> dict[str, Any]:
    item = _base_row(row, "Teardown Candidate")
    year = row.get("primary_effective_year") or row.get("eff_year_built") or row.get("year_built") or "unknown year"
    land_value = (row.get("impr_land_value") or 0) + (row.get("unimpr_land_value") or 0)
    condition = row.get("primary_condition") or "unknown condition"
    style = _improvement_label(row.get("primary_style"))
    land_building_ratio = None
    if row.get("building_value"):
        land_building_ratio = ((row.get("impr_land_value") or 0) + (row.get("unimpr_land_value") or 0)) / row.get("building_value")
    ratio_phrase = f", land is {ratio(land_building_ratio)} building value" if land_building_ratio is not None else ""
    item["signal_labels"] = [
        str(style),
        str(condition).lower(),
        f"year {year}",
    ]
    if land_building_ratio is not None:
        item["signal_labels"].append(f"{ratio(land_building_ratio)} land/building")
    item["why_it_ranks"] = (
        f"{money(land_value)} in land value, {money(row.get('building_value'))} in building value, "
        f"{style} in {condition.lower()}, built/effective year {year}{ratio_phrase}."
    )
    item["risk_flags"] = risk_flags(
        "Missing build year" if not row.get("year_built") and not row.get("eff_year_built") and not row.get("primary_effective_year") else None,
        "Large structure" if (row.get("primary_living_area") or 0) > 2500 else None,
        "No improvement detail" if not row.get("improvement_count") else None,
        "Natural resource zoning" if is_natural_resource_zone(row.get("zone_id"), row.get("zone_name"), row.get("waza_general")) else None,
        "No parcel geometry" if not item["map_url"] else None,
    )
    return item


def _format_assemblage(row: dict[str, Any]) -> dict[str, Any]:
    item = _base_row(row, "Assemblage Opportunity")
    total_count = (row.get("cluster_count") or 0) + 1
    item["why_it_ranks"] = (
        f"{total_count} nearby same-owner parcels totaling {acres(row.get('cluster_acres'))}; "
        f"{row.get('vacant_like_count') or 0} look vacant or low-improvement; "
        f"{row.get('neighbor_zone_count') or 1} zoning pattern(s) in the cluster."
    )
    item["risk_flags"] = risk_flags(
        "Delinquency in cluster" if (row.get("delinquent_neighbors") or 0) > 0 else None,
        "Small cluster" if total_count <= 2 else None,
        "Unknown zoning" if not row.get("zone_id") else None,
        "Mixed zoning" if (row.get("neighbor_zone_count") or 1) > 1 else None,
        "Natural resource zoning" if is_natural_resource_zone(row.get("zone_id"), row.get("zone_name"), row.get("waza_general")) else None,
        "Resource land" if is_resource_land_use(row.get("land_use")) else None,
    )
    return item


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _decimal_filter(value: str | None, default: Decimal) -> Decimal:
    return _decimal(value) or default


def _int_filter(value: str | None, default: int) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _land_use_code(value: str | None) -> str:
    return land_use_code(value)


def _zone_definition(row: dict[str, Any]) -> str:
    parts = []
    if row.get("zone_name"):
        parts.append(row["zone_name"])
    if row.get("waza_general"):
        parts.append(f"General category: {row['waza_general']}")
    if row.get("waza_specific"):
        parts.append(f"Specific category: {row['waza_specific']}")
    return ". ".join(parts) or "No zoning definition is available for this parcel."


def _auditor_url(recording_number: str | None) -> str:
    value = str(recording_number or "").strip()
    if len(value) >= 8 and value[:8].isdigit():
        return AUDITOR_DOCUMENT_URL.format(year=value[:4], month=value[4:6], day=value[6:8], recording_number=value)
    return AUDITOR_RECORDING_SEARCH_URL


def _recent_document_url(row: dict[str, Any], today: date | None = None) -> str:
    recorded = _date_value(row.get("deed_date_iso") or row.get("sale_date_iso"))
    if not recorded:
        return ""
    today = today or date.today()
    if recorded < today - timedelta(days=RECENT_RECORDING_DAYS) or recorded > today:
        return ""
    return _auditor_url(row.get("recording_number")) if row.get("recording_number") else AUDITOR_RECORDING_SEARCH_URL


def _date_value(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _delinquent_years_phrase(years_delinquent: Any, current_year_count: Any) -> str:
    prior_years = int(years_delinquent or 0)
    has_current = bool(current_year_count or 0)
    if prior_years and has_current:
        unit = "year" if prior_years == 1 else "years"
        return f"{prior_years} prior delinquent tax {unit} plus current-year balance"
    if prior_years:
        unit = "year" if prior_years == 1 else "years"
        return f"{prior_years} prior delinquent tax {unit}"
    if has_current:
        return "current-year delinquent balance"
    return "tax delinquency signal"


def _land_building_signal(row: dict[str, Any]) -> str:
    land_value = _decimal(row.get("land_value"))
    if land_value is None:
        land_value = (_decimal(row.get("impr_land_value")) or Decimal("0")) + (_decimal(row.get("unimpr_land_value")) or Decimal("0"))
    building_value = _decimal(row.get("building_value")) or Decimal("0")
    land_pct = _decimal(row.get("land_value_pct"))
    pct_phrase = f", {_percent(land_pct)} of assessed value" if land_pct is not None else ""
    if land_value > 0 and building_value <= 0:
        return f"land-only value of {money(land_value)}{pct_phrase}"
    if building_value <= 0:
        return "no building value reported"
    return f"{money(land_value)} land vs {money(building_value)} building ({ratio(land_value / building_value)} land/building{pct_phrase})"


def _land_use_label(value: str | None) -> str:
    text = value or ""
    if ")" in text:
        return text.split(")", 1)[1].strip() or text
    return text or "unknown use"


def _improvement_label(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return "main dwelling area"
    key = text.upper()
    labels = {
        "MA": "main dwelling area",
        "MAIN AREA": "main dwelling area",
        "MA2": "two-story main dwelling",
        "MA1.5F": "one-and-a-half-story dwelling",
        "MA-SPLIT": "split-level dwelling",
        "UF2": "upper-floor living area",
        "UF1.5F": "upper-floor living area",
        "BMF": "finished basement area",
        "BMU": "unfinished basement area",
        "BMG": "basement garage area",
    }
    return labels.get(key, text.lower())


def _percent(value: Any) -> str:
    amount = _decimal(value)
    if amount is None:
        return "unknown"
    return f"{amount:.0f}%"


def _city_label(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    first = text.split(",", 1)[0].strip()
    return first or text


def _location_label(address: str, city: str) -> str:
    if address and city:
        return f"{address}, {city}"
    if address:
        return address
    if city:
        return city
    return "n/a"


def _value_history_phrase(growth: Any) -> str:
    amount = _decimal(growth)
    if amount is None:
        return ""
    if amount >= 5:
        return f"; assessed value up {amount:.0f}% since 2020"
    if amount <= -5:
        return f"; assessed value down {abs(amount):.0f}% since 2020"
    return "; assessed value roughly flat since 2020"


def filter_query(filters: dict[str, str]) -> str:
    return urlencode({key: value for key, value in filters.items() if value})
