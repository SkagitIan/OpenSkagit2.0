from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode

from django.db import connection
from django.urls import reverse


ASSESSOR_DETAIL_URL = "https://www.skagitcounty.net/search/property/default.aspx?id={parcel_number}"
AUDITOR_RECORDING_SEARCH_URL = "https://www.skagitcounty.net/Search/Recording/default.aspx"
AUDITOR_DOCUMENT_URL = "https://www.skagitcounty.net/AuditorRecording/Documents/RecordedDocuments/{year}/{month}/{day}/{recording_number}.pdf"
LATEST_AERIAL_IMAGE_URL = "https://gis.skagitcountywa.gov/arcgis/rest/services/Images/SkagitCounty2021_3inch/ImageServer/exportImage"
RECENT_RECORDING_DAYS = 90
SYNC_BRIEF_DISCLAIMER = (
    "Public-record screening signals only. Confirm documents, title, zoning, access, taxes, and site conditions "
    "before treating any parcel as an investment lead."
)
BRIEF_SIGNAL_LABELS = {
    "transfer": "Transfers",
    "financing": "Financing",
    "distress": "Distress",
    "lien_judgment": "Liens and judgments",
    "lease_option": "Leases and options",
    "land_division": "Land division",
    "land_status": "Land status",
    "rights_access": "Rights and access",
    "fresh_sale": "Fresh sales",
    "other": "Other recordings",
}
BRIEF_SIGNAL_WEIGHTS = {
    "land_division": 95,
    "land_status": 90,
    "distress": 88,
    "rights_access": 82,
    "lease_option": 78,
    "lien_judgment": 72,
    "transfer": 66,
    "fresh_sale": 62,
    "financing": 52,
    "other": 25,
}
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
INDUSTRIAL_ZONE_GROUPS = {"IND"}
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
    OpportunityTab("delinquent-tax-pressure", "Delinquent Tax Pressure", "Parcels where unpaid taxes may signal owner pressure or a need to resolve carrying costs.", "Signals show delinquent tax years and estimated past-due amount; sorted by tax pressure and redevelopment relevance."),
    OpportunityTab("vacant-buildable-lots", "Vacant Buildable Lots", "Residentially zoned parcels with little or no building value where a straightforward build may be possible.", "Signals show utility and frontage clues; sorted toward urban vacant lots with better service signals."),
    OpportunityTab("possible-lot-splits", "Possible Lot Splits", "Large residential lots that stand out against smaller nearby or same-zone lots and may have extra land capacity.", "Signals show theoretical capacity screens, not approved yield; sorted by oversize lots versus nearby median lots."),
    OpportunityTab("teardown-candidates", "Teardown Candidates", "Single-family parcels where the land value is high and the existing main dwelling appears low-value or obsolete.", "Signals show main dwelling condition/year and land-building ratio; manufactured homes, recent homes, and good-condition homes are excluded."),
]
TAB_LOOKUP = {tab.key: tab for tab in TABS}
DEFAULT_TAB = TABS[0].key
ROW_LIMIT = 100
FILTER_LABELS = {
    "min_years": ("Minimum delinquent years", "2"),
    "min_due": ("Minimum tax due", "5000"),
    "improved": ("Vacant/improved", ""),
    "place": ("Place", "Mount Vernon"),
    "min_land_ratio": ("Minimum land/building ratio", "3"),
    "min_acres": ("Minimum acres", "0.25"),
    "max_building": ("Maximum building value", "10000"),
    "min_land_value": ("Minimum land value", "150000"),
    "min_cluster": ("Minimum cluster size", "3"),
}
TAB_FILTER_KEYS = {
    "delinquent-tax-pressure": ["min_years", "min_due", "min_land_ratio", "improved", "place"],
    "vacant-buildable-lots": ["min_acres", "max_building", "place"],
    "possible-lot-splits": ["min_acres", "max_building", "place"],
    "teardown-candidates": ["min_land_value", "max_building", "place"],
    "generated-opportunity": ["min_acres", "min_land_value", "max_building", "improved", "place"],
}
DATA_SOURCES = [
    {
        "name": "Skagit County Assessor parcels",
        "category": "Parcel facts",
        "description": "Active parcel identity, situs location, ownership mailing fields, value fields, land use, utility tokens, acres, and assessor sale fields.",
        "cadence": "Nightly sync when source files change",
        "used_for": "Parcel summaries, watchlist cards, opportunity rows, valuation context, and basic parcel filtering.",
    },
    {
        "name": "Assessor improvements",
        "category": "Buildings",
        "description": "Improvement segments, class descriptions, condition descriptions, living area, value, and build-year fields.",
        "cadence": "Nightly sync when source files change",
        "used_for": "Teardown screens, dwelling evidence, AI search hydration, and saved parcel dossiers.",
    },
    {
        "name": "Assessor land segments",
        "category": "Land",
        "description": "Land type, appraisal method, market value, segment size, and frontage signals.",
        "cadence": "Nightly sync when source files change",
        "used_for": "Vacant lots, lot split screens, feature labels, and parcel dossiers.",
    },
    {
        "name": "Skagit GIS parcels and zoning",
        "category": "Map and zoning",
        "description": "Parcel geometry, map coordinates, primary zoning, jurisdiction, WAZA group labels, zoning overlaps, and source URLs.",
        "cadence": "Synced from local GIS-backed tables",
        "used_for": "Map buttons, zoning labels, opportunity filters, parcel detail maps, and feasibility screens.",
    },
    {
        "name": "Treasurer tax delinquency",
        "category": "Tax pressure",
        "description": "Current tax statement status, delinquent rows, unpaid installment signals, oldest due date, and total due.",
        "cadence": "Separate delinquency refresh",
        "used_for": "Delinquent Tax Pressure tab, tax flags, and watchlist alert context.",
    },
    {
        "name": "Auditor recorded documents",
        "category": "Recorded documents",
        "description": "Recording number, document type, signal group, recorded date, parcel number, and document link when a filing is attached to an active parcel.",
        "cadence": "Auditor lookup during assessor sync",
        "used_for": "Dashboard recorded documents, sync brief, watchlist notifications, and source-document links.",
    },
    {
        "name": "Assessor sales",
        "category": "Sales",
        "description": "Sale date, deed date, sale price, recording number, deed type, buyer, and seller fields attached to active parcels.",
        "cadence": "Nightly sync when source files change",
        "used_for": "Fresh sales, parcel detail sales, AI no-recent-sale filters, and sync brief counts.",
    },
]


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


def current_use_zoning_audit(row: dict[str, Any]) -> dict[str, str]:
    land_use = row.get("land_use") or row.get("current_use") or ""
    waza_general = (row.get("waza_general") or "").upper()
    zone_id = row.get("zone_id") or row.get("zoning") or ""
    zone_name = row.get("zone_name") or ""
    if is_residential_dwelling_land_use(land_use) and waza_general in INDUSTRIAL_ZONE_GROUPS:
        return {
            "status": "review",
            "label": "Residential use in industrial zoning",
            "description": (
                f"Current assessor land use is residential ({_land_use_label(land_use)}), "
                f"while primary zoning is {zone_id or zone_name}."
            ),
        }
    return {"status": "", "label": "", "description": ""}


def current_use_zoning_flags(row: dict[str, Any]) -> list[str]:
    audit = current_use_zoning_audit(row)
    return [audit["label"]] if audit.get("label") else []


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
    return rows[:limit]


def filter_specs_for_tab(tab_key: str) -> list[dict[str, str]]:
    specs = []
    for key in TAB_FILTER_KEYS.get(tab_key, TAB_FILTER_KEYS["generated-opportunity"]):
        label, placeholder = FILTER_LABELS[key]
        specs.append({"key": key, "label": label, "placeholder": placeholder})
    return specs


def tab_counts(filters: dict[str, str]) -> dict[str, str]:
    counts = {}
    for tab in TABS:
        try:
            counts[tab.key] = f"{len(fetch_tab_rows(tab.key, filters, limit=500)):,}+"
        except Exception:
            counts[tab.key] = ""
    return counts


def delinquent_tax_pressure(filters: dict[str, str], limit: int) -> list[dict[str, Any]]:
    min_years = _int_filter(filters.get("min_years"), 0)
    min_due = _decimal_filter(filters.get("min_due"), Decimal("0"))
    min_land_ratio = _decimal_filter(filters.get("min_land_ratio"), Decimal("0"))
    improved = filters.get("improved", "")
    place = filters.get("place", "")
    where = [
        "p.inactive_date IS NULL",
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
        "current_statement.parcel_number IS NOT NULL",
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
        WITH current_statement AS (
            SELECT t.parcel_number, t.tax_year, t.raw_data, t.total_due, t.lead_level, t.oldest_due_date
            FROM tax_delinquency_taxstatement t
            WHERE t.tax_year = EXTRACT(YEAR FROM CURRENT_DATE)::int
              AND (
                jsonb_array_length(COALESCE(t.raw_data->'delinquent_rows', '[]'::jsonb)) > 0
                OR t.delinquent_installment_count > 0
              )
        ),
        due AS (
            SELECT current_statement.parcel_number,
                   COUNT(*) FILTER (WHERE due_rows.tax_year < EXTRACT(YEAR FROM CURRENT_DATE)::int) AS years_delinquent,
                   COUNT(*) FILTER (WHERE due_rows.tax_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int) AS current_year_count,
                   array_agg(due_rows.tax_year ORDER BY due_rows.tax_year DESC) AS past_due_years,
                   SUM(due_rows.amount) AS total_due,
                   SUM(due_rows.amount) AS past_due_amount,
                   MAX(CASE current_statement.lead_level
                     WHEN 'severe' THEN 5 WHEN 'serious' THEN 4 WHEN 'behind' THEN 3
                     WHEN 'one_late' THEN 2 WHEN 'watch' THEN 1 ELSE 0 END) AS lead_score,
                   MIN(current_statement.oldest_due_date) AS oldest_due_date
            FROM current_statement
            JOIN skagit_parcels p ON p.parcel_number = current_statement.parcel_number
            LEFT JOIN parcel_primary_zoning z ON z.parcel_id = p.parcel_number
            JOIN LATERAL (
                SELECT (value->>'year')::int AS tax_year,
                       NULLIF(regexp_replace(value->>'total', '[^0-9.]', '', 'g'), '')::numeric AS amount
                FROM jsonb_array_elements(COALESCE(current_statement.raw_data->'delinquent_rows', '[]'::jsonb)) AS value
                UNION ALL
                SELECT current_statement.tax_year AS tax_year,
                       NULLIF(regexp_replace(value->>'amount', '[^0-9.]', '', 'g'), '')::numeric AS amount
                FROM jsonb_array_elements(COALESCE(current_statement.raw_data->'installments', '[]'::jsonb)) AS value
                WHERE jsonb_array_length(COALESCE(current_statement.raw_data->'delinquent_rows', '[]'::jsonb)) = 0
                  AND value->>'is_delinquent' = 'true'
                  AND COALESCE(value->>'is_unpaid', 'true') = 'true'
            ) due_rows ON true
            WHERE {" AND ".join(where)}
            GROUP BY current_statement.parcel_number
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
               due.years_delinquent, due.current_year_count, due.past_due_years, due.total_due, due.past_due_amount, due.oldest_due_date,
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
          AND due.past_due_amount >= %s
          AND (%s = 0 OR COALESCE(p.building_value, 0) = 0
               OR (COALESCE(p.impr_land_value, 0) + COALESCE(p.unimpr_land_value, 0)) / NULLIF(p.building_value, 0) >= %s)
        ORDER BY score DESC NULLS LAST, due.years_delinquent DESC, due.past_due_amount DESC NULLS LAST
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
                 + CASE WHEN lower(COALESCE(i.primary_condition, '')) = 'low' THEN 90000
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
              (lower(COALESCE(i.primary_condition, '')) IN ('fair', 'low')
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
    """Serve the assemblage tab from precomputed graph pattern results."""
    from graph.models import GraphOpportunityResult

    min_cluster = _int_filter(filters.get("min_cluster"), 2)
    candidates = list(GraphOpportunityResult.objects.filter(pattern_key="assemblage").order_by("rank")[: max(limit * 3, limit)])
    candidates = [candidate for candidate in candidates if int(candidate.detail.get("cluster_count") or 0) + 1 >= min_cluster][:limit]
    if not candidates:
        return []
    parcel_numbers = [candidate.parcel_number for candidate in candidates]
    base_rows = _fetch(
        """
        SELECT p.parcel_number, p.owner_name,
               concat_ws(' ', p.situs_street_number, p.situs_street_name) AS address,
               COALESCE(NULLIF(p.situs_city_state_zip, ''), NULLIF(z.citydistrict, ''), NULLIF(z.jurisdiction, '')) AS city,
               p.acres, p.assessed_value, p.building_value, p.land_use,
               COALESCE(NULLIF(ar.impr_land_value, '')::numeric, 0) AS impr_land_value,
               COALESCE(NULLIF(ar.unimpr_land_value, '')::numeric, 0) AS unimpr_land_value,
               z.zone_id, z.zone_name, z.waza_general, z.waza_specific, z.reference_url,
               geo.lat, geo.lon AS lng,
               split_part(ltrim(COALESCE(p.land_use, ''), '('), ')', 1) AS land_use_code
        FROM skagit_parcels p
        LEFT JOIN assessor_rollup ar ON ar.parcel_number = p.parcel_number
        LEFT JOIN parcel_primary_zoning z ON z.parcel_id = p.parcel_number
        LEFT JOIN parcel_geo_static_features geo ON geo.parcel_number = p.parcel_number
        WHERE p.parcel_number = ANY(%s)
        """,
        [parcel_numbers],
    )
    by_parcel = {row["parcel_number"]: row for row in base_rows}
    formatted = []
    for candidate in candidates:
        row = by_parcel.get(candidate.parcel_number)
        if not row:
            continue
        row.update(candidate.detail)
        row["score"] = candidate.score
        formatted.append(_format_assemblage(row))
    return formatted

def _assemblage_opportunities_sql_legacy(filters: dict[str, str], limit: int) -> list[dict[str, Any]]:
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


def _fetch(sql: str, params: list[Any]) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _base_row(row: dict[str, Any], opportunity_type: str) -> dict[str, Any]:
    lat = row.get("lat")
    lng = row.get("lng")
    map_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}" if lat is not None and lng is not None else ""
    map_embed_url = f"https://maps.google.com/maps?q={lat},{lng}&z=17&output=embed" if lat is not None and lng is not None else ""
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
        "building_value": row.get("building_value"),
        "land_value": land_value,
        "assessed_value_fmt": money(row.get("assessed_value")),
        "land_value_fmt": money(land_value),
        "building_value_fmt": money(row.get("building_value")),
        "score": int(row.get("score") or 0),
        "risk_flags": [],
        "current_use_zoning_audit": current_use_zoning_audit(row),
        "lat": lat,
        "lng": lng,
        "map_url": map_url,
        "map_embed_url": map_embed_url,
        "aerial_image_url": aerial_image_url(row),
        "aerial_image_source": "Skagit County 2021 3-inch aerial imagery",
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
    amount = _decimal(row.get("past_due_amount") or row.get("total_due"))
    if amount:
        item["signal_labels"] = [f"{money(amount)} past due"]
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
    ) + current_use_zoning_flags(row)
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
    ) + current_use_zoning_flags(row)
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
    ) + current_use_zoning_flags(row)
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
    ) + current_use_zoning_flags(row)
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
    ) + current_use_zoning_flags(row)
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


def _sync_window(run=None, summary: dict[str, Any] | None = None) -> tuple[date | None, date | None]:
    auditor = (summary or getattr(run, "summary", {}) or {}).get("auditor") or {}
    start = _date_value(auditor.get("start_date"))
    end = _date_value(auditor.get("end_date"))
    if start and end:
        return start, end
    stamp = getattr(run, "finished_at", None) or getattr(run, "started_at", None)
    fallback = _date_value(stamp)
    return fallback, fallback


def _date_in_window(value: Any, start: date | None, end: date | None) -> bool:
    parsed = _date_value(value)
    if not parsed or not start or not end:
        return False
    return start <= parsed <= end


def _sale_event_date(row: dict[str, Any]) -> date | None:
    return _date_value(
        row.get("sale_date")
        or row.get("sale_date_iso")
        or row.get("deed_date_iso")
        or row.get("deed_date")
    )


def _is_fresh_sale_row(row: dict[str, Any], start: date | None, end: date | None) -> bool:
    event_date = _sale_event_date(row)
    return bool(event_date and start and end and start <= event_date <= end)


def _brief_signal_label(signal_group: str | None) -> str:
    return BRIEF_SIGNAL_LABELS.get(signal_group or "other", "Other recordings")


def _brief_notability_score(row: dict[str, Any]) -> int:
    group = row.get("signal_group") or ("fresh_sale" if row.get("event_kind") == "sale" else "other")
    score = BRIEF_SIGNAL_WEIGHTS.get(group, BRIEF_SIGNAL_WEIGHTS["other"])
    document_type = (row.get("document_type") or row.get("deed_type") or "").lower()
    if "notice" in document_type or "trustee" in document_type or "foreclosure" in document_type:
        score += 12
    if "lot certification" in document_type or "survey" in document_type or "plat" in document_type:
        score += 10
    if row.get("parcel_number"):
        score += 4
    if row.get("document_url") or row.get("pdf_url"):
        score += 2
    amount = _decimal(row.get("sale_price_num"))
    if amount and amount >= Decimal("1000000"):
        score += 8
    return score


def _compact_date(value: Any) -> str:
    parsed = _date_value(value)
    if not parsed:
        return ""
    return f"{parsed:%b %-d, %Y}" if os.name != "nt" else f"{parsed:%b %#d, %Y}"


def _watchlist_alert_label(row: dict[str, Any]) -> str:
    table = row.get("table_name")
    change = row.get("change_type") or "changed"
    if table == "sales":
        return "New sale" if change == "insert" else "Sale changed"
    if table == "auditor_recordings":
        return "New recording" if change == "insert" else "Recording changed"
    if table == "improvements":
        return "Improvement changed"
    if table == "land":
        return "Land detail changed"
    return "Watchlist change"


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


def _chart_bounds(values: list[Decimal]) -> tuple[Decimal, Decimal]:
    low = min(values) if values else Decimal("0")
    high = max(values) if values else Decimal("0")
    if low == high:
        padding = max(abs(high) * Decimal("0.1"), Decimal("1"))
        return max(Decimal("0"), low - padding), high + padding
    padding = (high - low) * Decimal("0.12")
    return max(Decimal("0"), low - padding), high + padding


def _chart_y(value: Decimal, low: Decimal, high: Decimal, top_pad: Decimal, plot_height: Decimal) -> Decimal:
    if high == low:
        return top_pad + (plot_height / 2)
    return top_pad + plot_height - ((value - low) / (high - low) * plot_height)


def _svg_number(value: Decimal) -> str:
    return f"{value:.1f}"


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


def saved_parcel_numbers(user) -> set[str]:
    if not getattr(user, "is_authenticated", False):
        return set()
    from .models import OpportunitySavedParcel

    return set(OpportunitySavedParcel.objects.filter(user=user).values_list("parcel_number", flat=True))


def mark_saved(rows: list[dict[str, Any]], user) -> list[dict[str, Any]]:
    saved = saved_parcel_numbers(user)
    for row in rows:
        row["is_saved"] = row.get("parcel_number") in saved
    return rows


def latest_assessor_sync_summary(user=None, sales_sort: str = "") -> dict[str, Any]:
    try:
        from assessor_sync.models import AssessorSyncChange, AssessorSyncReport, AssessorSyncRun

        report = latest_nonempty_sync_report(AssessorSyncReport)
        run = report.run if report else AssessorSyncRun.objects.order_by("-started_at").first()
        if not run:
            return {"has_run": False, "metrics": [], "changes": []}
        tables = (run.summary or {}).get("tables", {})
        applied = sum(int((table or {}).get("applied_rows") or 0) for table in tables.values())
        inserted = sum(int((table or {}).get("inserted") or 0) for table in tables.values())
        updated = sum(int((table or {}).get("updated") or 0) for table in tables.values())
        warnings = sum(int((table or {}).get("warnings") or 0) for table in tables.values())
        window_start, window_end = _sync_window(run, run.summary or {})
        sync_counts = latest_sync_metric_counts(run, user)
        since_text = sync_since_text(run)
        changes = list(
            AssessorSyncChange.objects.filter(run=run)
            .values("table_name", "record_key", "change_type", "changed_fields", "created_at")
            .order_by("-created_at")[:6]
        )
        recent_sales = latest_sync_sales(run.pk, sort=sales_sort, window=(window_start, window_end))
        recorded_docs = latest_sync_recorded_docs(run.pk)
        watchlist_alerts = latest_watchlist_alerts(run.pk, user)
        return {
            "has_run": True,
            "run": run,
            "tables": tables,
            "since_text": since_text,
            "sales_sort": sales_sort if sales_sort in {"city", "price"} else "",
            "metrics": [
                {"label": "Parcel signals updated", "value": f"{sync_counts['parcel_signals']:,}", "accent": "teal", "note": since_text},
                {"label": "Fresh sales", "value": f"{sync_counts['new_sales']:,}", "accent": "gold", "note": since_text},
                {"label": "New filings", "value": f"{sync_counts['new_filings']:,}", "accent": "red", "note": since_text},
                {"label": "Watchlist changes", "value": f"{sync_counts['watchlist_changes']:,}", "accent": "blue", "note": since_text},
            ],
            "totals": {"applied": applied, "inserted": inserted, "updated": updated, "warnings": warnings},
            "narrative": sync_narrative_dict(report, report.run.summary or {}) if report else fallback_sync_narrative(run.summary or {}),
            "changes": changes,
            "activity": latest_sync_activity(run.pk),
            "recent_sales": recent_sales,
            "recorded_docs": recorded_docs,
            "watchlist_alerts": watchlist_alerts,
        }
    except Exception:
        return {"has_run": False, "metrics": [], "changes": [], "activity": [], "recent_sales": [], "recorded_docs": [], "watchlist_alerts": []}


def latest_sync_sales(
    run_id: int,
    sort: str = "",
    limit: int | None = None,
    window: tuple[date | None, date | None] | None = None,
) -> list[dict[str, Any]]:
    limit_sql = "LIMIT %s" if limit else ""
    params = [run_id]
    if limit:
        params.append(limit)
    rows = _fetch(
        f"""
        WITH sales_changes AS (
          SELECT DISTINCT ON (c.record_key)
            c.record_key,
            c.created_at,
            COALESCE(NULLIF(c.new_row->>'parcel_number', ''), split_part(c.record_key, '|', 2)) AS parcel_number,
            COALESCE(NULLIF(c.new_row->>'recording_number', ''), split_part(c.record_key, '|', 3)) AS recording_number,
            NULLIF(c.new_row->>'deed_type', '') AS deed_type,
            COALESCE(NULLIF(c.new_row->>'sale_date_iso', ''), NULLIF(c.new_row->>'deed_date_iso', '')) AS sale_date,
            NULLIF(c.new_row->>'sale_price_num', '')::numeric AS sale_price_num
          FROM assessor_sync_changes c
          WHERE c.run_id = %s
            AND c.table_name = 'sales'
            AND c.change_type IN ('insert', 'update')
            AND COALESCE(NULLIF(c.new_row->>'parcel_number', ''), split_part(c.record_key, '|', 2), '') <> ''
          ORDER BY c.record_key, c.created_at DESC
        )
        SELECT
          c.parcel_number,
          c.recording_number,
          COALESCE(c.deed_type, s.deed_type, 'Sale') AS deed_type,
          COALESCE(c.sale_date, s.sale_date_iso, s.deed_date_iso) AS sale_date,
          COALESCE(c.sale_price_num, s.sale_price_num) AS sale_price_num,
          concat_ws(' ', p.situs_street_number, p.situs_street_name) AS address,
          COALESCE(NULLIF(p.situs_city_state_zip, ''), NULLIF(z.citydistrict, ''), NULLIF(z.jurisdiction, '')) AS city
        FROM sales_changes c
        LEFT JOIN LATERAL (
          SELECT s.deed_type, s.sale_date_iso, s.deed_date_iso, s.sale_price_num
          FROM sales s
          WHERE s.saleid = split_part(c.record_key, '|', 1)
            AND s.parcel_number = c.parcel_number
            AND COALESCE(s.recording_number, '') = COALESCE(c.recording_number, '')
          ORDER BY s.sale_date_iso DESC NULLS LAST
          LIMIT 1
        ) s ON true
        LEFT JOIN skagit_parcels p ON p.parcel_number = c.parcel_number
        LEFT JOIN parcel_primary_zoning z ON z.parcel_id = p.parcel_number
        ORDER BY c.created_at DESC
        {limit_sql}
        """,
        params,
    )
    for row in rows:
        row["city_label"] = _city_label(row.get("city"))
        row["location"] = _location_label((row.get("address") or "").strip(), row["city_label"])
        row["sale_price_fmt"] = money(row.get("sale_price_num"))
        row["date_label"] = _compact_date(row.get("sale_date"))
        row["document_url"] = _auditor_url(row.get("recording_number")) if row.get("recording_number") else ""
    if window:
        start, end = window
        rows = [row for row in rows if _is_fresh_sale_row(row, start, end)]
    if sort == "city":
        rows.sort(key=lambda row: ((row.get("city_label") or "zzzz").lower(), row.get("parcel_number") or ""))
    elif sort == "price":
        rows.sort(key=lambda row: (_decimal(row.get("sale_price_num")) or Decimal("0"), row.get("parcel_number") or ""), reverse=True)
    return rows


def latest_sync_recorded_docs(run_id: int, limit: int | None = None) -> list[dict[str, Any]]:
    limit_sql = "LIMIT %s" if limit else ""
    params = [run_id]
    if limit:
        params.append(limit)
    rows = _fetch(
        f"""
        WITH recording_changes AS (
          SELECT
            COALESCE(NULLIF(c.new_row->>'parcel_number', ''), NULLIF(c.old_row->>'parcel_number', '')) AS parcel_number,
            COALESCE(NULLIF(c.new_row->>'recording_number', ''), NULLIF(c.old_row->>'recording_number', ''), c.record_key) AS recording_number,
            COALESCE(NULLIF(c.new_row->>'recorded_date', ''), NULLIF(c.old_row->>'recorded_date', '')) AS recorded_date,
            COALESCE(NULLIF(c.new_row->>'document_type', ''), NULLIF(c.old_row->>'document_type', ''), 'Auditor filing') AS document_type,
            COALESCE(NULLIF(c.new_row->>'signal_group', ''), NULLIF(c.old_row->>'signal_group', '')) AS signal_group,
            COALESCE(NULLIF(c.new_row->>'pdf_url', ''), NULLIF(c.old_row->>'pdf_url', '')) AS pdf_url,
            c.created_at
          FROM assessor_sync_changes c
          WHERE c.run_id = %s
            AND c.table_name = 'auditor_recordings'
            AND c.change_type IN ('insert', 'update')
        )
        SELECT
          rc.parcel_number,
          rc.recording_number,
          rc.recorded_date,
          rc.document_type,
          rc.signal_group,
          rc.pdf_url,
          concat_ws(' ', p.situs_street_number, p.situs_street_name) AS address,
          COALESCE(NULLIF(p.situs_city_state_zip, ''), NULLIF(z.citydistrict, ''), NULLIF(z.jurisdiction, '')) AS city
        FROM recording_changes rc
        JOIN skagit_parcels p ON p.parcel_number = rc.parcel_number
        LEFT JOIN parcel_primary_zoning z ON z.parcel_id = p.parcel_number
        WHERE COALESCE(rc.parcel_number, '') <> ''
        ORDER BY rc.created_at DESC
        {limit_sql}
        """,
        params,
    )
    for row in rows:
        row["location"] = _location_label((row.get("address") or "").strip(), _city_label(row.get("city")))
        row["date_label"] = _compact_date(row.get("recorded_date"))
        row["document_url"] = row.get("pdf_url") or _auditor_url(row.get("recording_number"))
    return rows


def latest_watchlist_alerts(run_id: int, user=None, limit: int = 8) -> list[dict[str, Any]]:
    saved = saved_parcel_numbers(user)
    if not saved:
        return []
    rows = _fetch(
        """
        WITH events AS (
          SELECT
            CASE
              WHEN c.table_name IN ('land', 'improvements') THEN split_part(c.record_key, '|', 1)
              WHEN c.table_name = 'sales' THEN COALESCE(NULLIF(c.new_row->>'parcel_number', ''), split_part(c.record_key, '|', 2))
              WHEN c.table_name = 'auditor_recordings' THEN COALESCE(NULLIF(c.new_row->>'parcel_number', ''), NULLIF(c.old_row->>'parcel_number', ''))
              ELSE ''
            END AS parcel_number,
            c.table_name,
            c.change_type,
            c.changed_fields,
            c.created_at,
            COALESCE(NULLIF(c.new_row->>'recording_number', ''), NULLIF(c.old_row->>'recording_number', ''), '') AS recording_number
          FROM assessor_sync_changes c
          WHERE c.run_id = %s
            AND c.table_name IN ('land', 'improvements', 'sales', 'auditor_recordings')
        )
        SELECT
          e.*,
          concat_ws(' ', p.situs_street_number, p.situs_street_name) AS address,
          COALESCE(NULLIF(p.situs_city_state_zip, ''), NULLIF(z.citydistrict, ''), NULLIF(z.jurisdiction, '')) AS city,
          p.land_use
        FROM events e
        LEFT JOIN skagit_parcels p ON p.parcel_number = e.parcel_number
        LEFT JOIN parcel_primary_zoning z ON z.parcel_id = e.parcel_number
        WHERE e.parcel_number = ANY(%s)
        ORDER BY e.created_at DESC
        LIMIT %s
        """,
        [run_id, list(saved), limit],
    )
    for row in rows:
        row["location"] = _location_label((row.get("address") or "").strip(), _city_label(row.get("city")))
        row["current_use"] = _land_use_label(row.get("land_use"))
        row["alert_label"] = _watchlist_alert_label(row)
        row["date_label"] = _compact_date(row.get("created_at"))
        row["document_url"] = _auditor_url(row.get("recording_number")) if row.get("recording_number") else ""
    return rows


def latest_sync_activity(run_id: int, limit: int = 40) -> list[dict[str, Any]]:
    rows = _fetch(
        """
        WITH raw_events AS (
          SELECT
            'sale' AS event_kind,
            split_part(c.record_key, '|', 2) AS parcel_number,
            c.change_type,
            c.record_key,
            c.created_at,
            split_part(c.record_key, '|', 3) AS recording_number,
            s.sale_date_iso AS event_date,
            s.sale_price_num,
            s.deed_type,
            '' AS document_type,
            '' AS signal_group,
            '' AS pdf_url
          FROM assessor_sync_changes c
          LEFT JOIN sales s
            ON s.saleid = split_part(c.record_key, '|', 1)
           AND s.parcel_number = split_part(c.record_key, '|', 2)
           AND COALESCE(s.recording_number, '') = split_part(c.record_key, '|', 3)
          WHERE c.run_id = %s
            AND c.table_name = 'sales'
          UNION ALL
          SELECT
            'auditor' AS event_kind,
            COALESCE(NULLIF(c.new_row->>'parcel_number', ''), NULLIF(c.old_row->>'parcel_number', '')) AS parcel_number,
            c.change_type,
            c.record_key,
            c.created_at,
            COALESCE(NULLIF(c.new_row->>'recording_number', ''), NULLIF(c.old_row->>'recording_number', ''), c.record_key) AS recording_number,
            COALESCE(NULLIF(c.new_row->>'recorded_date', ''), NULLIF(c.old_row->>'recorded_date', '')) AS event_date,
            NULL::numeric AS sale_price_num,
            '' AS deed_type,
            COALESCE(NULLIF(c.new_row->>'document_type', ''), NULLIF(c.old_row->>'document_type', '')) AS document_type,
            COALESCE(NULLIF(c.new_row->>'signal_group', ''), NULLIF(c.old_row->>'signal_group', '')) AS signal_group,
            COALESCE(NULLIF(c.new_row->>'pdf_url', ''), NULLIF(c.old_row->>'pdf_url', '')) AS pdf_url
          FROM assessor_sync_changes c
          WHERE c.run_id = %s
            AND c.table_name = 'auditor_recordings'
        )
        SELECT
          e.*,
          concat_ws(' ', p.situs_street_number, p.situs_street_name) AS address,
          COALESCE(NULLIF(p.situs_city_state_zip, ''), NULLIF(z.citydistrict, ''), NULLIF(z.jurisdiction, '')) AS city,
          p.land_use,
          p.assessed_value
        FROM raw_events e
        JOIN skagit_parcels p ON p.parcel_number = e.parcel_number
        LEFT JOIN parcel_primary_zoning z ON z.parcel_id = e.parcel_number
        WHERE COALESCE(e.parcel_number, '') <> ''
        ORDER BY e.created_at DESC
        LIMIT %s
        """,
        [run_id, run_id, limit],
    )
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        parcel_number = row.get("parcel_number") or "Unknown"
        group = grouped.setdefault(
            parcel_number,
            {
                "parcel_number": parcel_number,
                "location": _location_label((row.get("address") or "").strip(), _city_label(row.get("city"))),
                "current_use": _land_use_label(row.get("land_use")),
                "assessed_value_fmt": money(row.get("assessed_value")),
                "sale_count": 0,
                "auditor_count": 0,
                "events": [],
            },
        )
        if row.get("event_kind") == "sale":
            group["sale_count"] += 1
            label = row.get("deed_type") or "Sale record"
            detail = money(row.get("sale_price_num")) if row.get("sale_price_num") else (row.get("recording_number") or "updated")
        else:
            group["auditor_count"] += 1
            label = row.get("document_type") or "Auditor filing"
            detail = row.get("recording_number") or row.get("signal_group") or "new filing"
        if len(group["events"]) < 3:
            group["events"].append(
                {
                    "kind": row.get("event_kind"),
                    "label": label,
                    "detail": detail,
                    "date": row.get("event_date") or row.get("created_at"),
                    "url": row.get("pdf_url") or "",
                }
            )
    return list(grouped.values())[:12]


def latest_nonempty_sync_report(AssessorSyncReport):
    reports = (
        AssessorSyncReport.objects.select_related("run")
        .filter(run__status="success")
        .order_by("-run__started_at", "-created_at")[:30]
    )
    fallback = None
    for report in reports:
        fallback = fallback or report
        if sync_summary_has_activity(report.run.summary or {}):
            return report
    return fallback


def sync_summary_has_activity(summary: dict[str, Any] | None) -> bool:
    tables = (summary or {}).get("tables", {})
    if int((summary or {}).get("files_changed") or 0) > 0:
        return True
    auditor = (summary or {}).get("auditor") or {}
    for key in ("inserted", "updated", "errors"):
        if int(auditor.get(key) or 0) > 0:
            return True
    for table in tables.values():
        table = table or {}
        for key in ("applied_rows", "inserted", "updated", "deleted", "warnings"):
            if int(table.get(key) or 0) > 0:
                return True
    return False


def latest_sync_metric_counts(run, user=None) -> dict[str, int]:
    summary = run.summary or {}
    tables = summary.get("tables", {})
    auditor = summary.get("auditor", {}) or {}
    window_start, window_end = _sync_window(run, summary)
    sales_summary = tables.get("sales", {}) or {}
    new_sales = int(sales_summary.get("inserted") or 0) + int(sales_summary.get("updated") or 0)
    signal_tables = ("sales", "land", "improvements")
    parcel_signals = sum(int((tables.get(table) or {}).get("applied_rows") or 0) for table in signal_tables)
    new_filings = (
        int(auditor.get("inserted") or 0) + int(auditor.get("updated") or 0)
        if auditor.get("enabled")
        else new_sales
    )
    watchlist_changes = 0

    try:
        sales_rows = _fetch(
            """
            SELECT
              COUNT(*) FILTER (WHERE change_type IN ('insert', 'update')) AS new_sales,
              COUNT(*) FILTER (
                WHERE change_type IN ('insert', 'update')
                  AND COALESCE(NULLIF(new_row->>'recording_number', ''), NULLIF(new_row->>'excise_number', '')) IS NOT NULL
              ) AS new_filings
            FROM assessor_sync_changes
            WHERE run_id = %s
              AND table_name = 'sales'
            """,
            [run.pk],
        )
        if sales_rows:
            if new_sales <= 0:
                new_sales = int(sales_rows[0].get("new_sales") or new_sales)
            if not auditor.get("enabled"):
                new_filings = int(sales_rows[0].get("new_filings") or 0)

        if window_start and window_end:
            fresh_sales_rows = _fetch(
                """
                SELECT COUNT(*) AS fresh_sales
                FROM assessor_sync_changes
                WHERE run_id = %s
                  AND table_name = 'sales'
                  AND change_type IN ('insert', 'update')
                  AND COALESCE(
                    NULLIF(new_row->>'sale_date_iso', ''),
                    NULLIF(new_row->>'sale_date', ''),
                    NULLIF(new_row->>'deed_date_iso', ''),
                    NULLIF(new_row->>'deed_date', '')
                  ) ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                  AND LEFT(COALESCE(
                    NULLIF(new_row->>'sale_date_iso', ''),
                    NULLIF(new_row->>'sale_date', ''),
                    NULLIF(new_row->>'deed_date_iso', ''),
                    NULLIF(new_row->>'deed_date', '')
                  ), 10)::date BETWEEN %s AND %s
                """,
                [run.pk, window_start, window_end],
            )
            new_sales = int((fresh_sales_rows[0] or {}).get("fresh_sales") or 0) if fresh_sales_rows else 0

        auditor_rows = _fetch(
            """
            SELECT COUNT(*) AS new_filings
            FROM assessor_sync_changes c
            JOIN skagit_parcels p
              ON p.parcel_number = COALESCE(NULLIF(c.new_row->>'parcel_number', ''), NULLIF(c.old_row->>'parcel_number', ''))
            WHERE c.run_id = %s
              AND c.table_name = 'auditor_recordings'
              AND c.change_type IN ('insert', 'update')
            """,
            [run.pk],
        )
        if auditor_rows and int(auditor_rows[0].get("new_filings") or 0) > 0:
            new_filings = int(auditor_rows[0].get("new_filings") or 0)

        parcel_rows = _fetch(
            """
            WITH normalized AS (
              SELECT DISTINCT
                CASE
                  WHEN table_name IN ('land', 'improvements') THEN split_part(record_key, '|', 1)
                  WHEN table_name = 'sales' THEN split_part(record_key, '|', 2)
                  WHEN table_name = 'auditor_recordings' THEN COALESCE(NULLIF(new_row->>'parcel_number', ''), NULLIF(old_row->>'parcel_number', ''))
                  ELSE ''
                END AS parcel_number
              FROM assessor_sync_changes
              WHERE run_id = %s
                AND table_name IN ('land', 'improvements', 'sales', 'auditor_recordings')
            )
            SELECT COUNT(*) AS parcel_signals
            FROM normalized n
            JOIN skagit_parcels p ON p.parcel_number = n.parcel_number
            WHERE n.parcel_number <> ''
            """,
            [run.pk],
        )
        if parcel_rows:
            parcel_signals = int(parcel_rows[0].get("parcel_signals") or parcel_signals)

        saved = saved_parcel_numbers(user)
        if saved:
            watchlist_rows_count = _fetch(
                """
                WITH normalized AS (
                  SELECT DISTINCT
                    CASE
                      WHEN table_name IN ('land', 'improvements') THEN split_part(record_key, '|', 1)
                      WHEN table_name = 'sales' THEN split_part(record_key, '|', 2)
                      WHEN table_name = 'auditor_recordings' THEN COALESCE(NULLIF(new_row->>'parcel_number', ''), NULLIF(old_row->>'parcel_number', ''))
                      ELSE ''
                    END AS parcel_number
                  FROM assessor_sync_changes
                  WHERE run_id = %s
                    AND table_name IN ('land', 'improvements', 'sales', 'auditor_recordings')
                )
                SELECT COUNT(*) AS watchlist_changes
                FROM normalized n
                JOIN skagit_parcels p ON p.parcel_number = n.parcel_number
                WHERE n.parcel_number = ANY(%s)
                """,
                [run.pk, list(saved)],
            )
            if watchlist_rows_count:
                watchlist_changes = int(watchlist_rows_count[0].get("watchlist_changes") or 0)
    except Exception:
        pass

    return {
        "parcel_signals": parcel_signals,
        "new_sales": new_sales,
        "new_filings": new_filings,
        "watchlist_changes": watchlist_changes,
    }


def sync_since_text(run) -> str:
    stamp = run.finished_at or run.started_at
    if not stamp:
        return "latest sync"
    return f"since {stamp:%b %-d} sync" if os.name != "nt" else f"since {stamp:%b %#d} sync"


def sync_narrative_dict(report, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    from .models import ParcelBookSyncNarrative

    narrative = ParcelBookSyncNarrative.objects.filter(assessor_sync_report=report).first()
    current_context = build_sync_brief_context(report.run)
    stale_recording_scope = narrative and (narrative.brief_context or {}).get("recording_scope") != "active_parcel_attached_only"
    stale_incomplete_text = narrative and (narrative.narrative or "").strip() and (narrative.narrative or "").strip()[-1:] not in ".!?"
    if stale_recording_scope or stale_incomplete_text:
        narrative = generate_sync_narrative_for_report(report.pk, force=True)
    if not narrative:
        narrative = generate_sync_narrative_for_report(report.pk)
    if narrative:
        return {
            "headline": narrative.headline,
            "dek": narrative.dek,
            "narrative": narrative.narrative,
            "bullets": narrative.bullets or [],
            "notable_signals": narrative.notable_signals or [],
            "trend_line": narrative.trend_line,
            "disclaimer": narrative.disclaimer or SYNC_BRIEF_DISCLAIMER,
            "newsletter_subject": narrative.newsletter_subject,
            "preview_text": narrative.preview_text,
            "generated": narrative.generated_by_ai,
            "model": narrative.model,
        }
    return fallback_sync_narrative(summary or getattr(report.run, "summary", {}) or {}, current_context)


def build_sync_brief_context(run) -> dict[str, Any]:
    summary = run.summary or {}
    window_start, window_end = _sync_window(run, summary)
    sales = latest_sync_sales(run.pk, window=(window_start, window_end))
    docs = [
        row for row in latest_sync_recorded_docs(run.pk)
        if _date_in_window(row.get("recorded_date"), window_start, window_end)
    ]
    signal_counts: dict[str, int] = {}
    document_counts: dict[str, int] = {}
    city_counts: dict[str, int] = {}
    notable_rows: list[dict[str, Any]] = []

    for row in docs:
        group = row.get("signal_group") or "other"
        signal_counts[group] = signal_counts.get(group, 0) + 1
        doc_type = row.get("document_type") or "Auditor filing"
        document_counts[doc_type] = document_counts.get(doc_type, 0) + 1
        location = row.get("location") or ""
        city = location.rsplit(",", 1)[-1].strip() if "," in location else location
        if city and city != "n/a":
            city_counts[city] = city_counts.get(city, 0) + 1
        notable_rows.append({
            "event_kind": "recording",
            "parcel_number": row.get("parcel_number") or "",
            "location": row.get("location") or row.get("signal_group") or "n/a",
            "document_type": doc_type,
            "signal_group": group,
            "signal_label": _brief_signal_label(group),
            "recorded_date": str(row.get("recorded_date") or ""),
            "date_label": row.get("date_label") or _compact_date(row.get("recorded_date")),
            "recording_number": row.get("recording_number") or "",
            "document_url": row.get("document_url") or "",
        })

    for row in sales:
        notable_rows.append({
            "event_kind": "sale",
            "parcel_number": row.get("parcel_number") or "",
            "location": row.get("location") or "n/a",
            "document_type": row.get("deed_type") or "Sale",
            "signal_group": "fresh_sale",
            "signal_label": _brief_signal_label("fresh_sale"),
            "recorded_date": str(row.get("sale_date") or ""),
            "date_label": row.get("date_label") or _compact_date(row.get("sale_date")),
            "recording_number": row.get("recording_number") or "",
            "sale_price": row.get("sale_price_fmt") or "",
            "sale_price_num": str(row.get("sale_price_num") or ""),
            "document_url": row.get("document_url") or "",
        })

    notable_rows.sort(key=lambda row: (_brief_notability_score(row), row.get("recorded_date") or ""), reverse=True)
    stale_sales = int(((summary.get("tables") or {}).get("sales") or {}).get("updated") or 0) - len(sales)
    return {
        "run_id": run.pk,
        "window": {
            "start": window_start.isoformat() if window_start else "",
            "end": window_end.isoformat() if window_end else "",
            "label": (
                f"{_compact_date(window_start)} to {_compact_date(window_end)}"
                if window_start and window_end and window_start != window_end
                else _compact_date(window_end or window_start)
            ),
        },
        "counts": {
            "fresh_sales": len(sales),
            "fresh_recordings": len(docs),
            "notable_signals": len(notable_rows),
            "stale_sales_updates_ignored": max(0, stale_sales),
        },
        "signal_counts": dict(sorted(signal_counts.items(), key=lambda item: item[1], reverse=True)),
        "document_counts": dict(sorted(document_counts.items(), key=lambda item: item[1], reverse=True)[:12]),
        "city_counts": dict(sorted(city_counts.items(), key=lambda item: item[1], reverse=True)[:12]),
        "notable_signals": notable_rows[:12],
        "source_note": (
            "Fresh means the sale/deed date or auditor recorded date falls inside the reporting window. "
            "Historical sales rows updated by the assessor export are ignored. Auditor recordings without an active attached parcel are excluded."
        ),
        "recording_scope": "active_parcel_attached_only",
    }


def generate_sync_narrative_for_report(report_id: int, force: bool = False):
    from assessor_sync.models import AssessorSyncReport
    from .models import ParcelBookSyncNarrative

    report = AssessorSyncReport.objects.select_related("run").get(pk=report_id)
    existing = ParcelBookSyncNarrative.objects.filter(assessor_sync_report=report).first()
    if existing and not force:
        return existing

    summary = report.run.summary or {}
    brief_context = build_sync_brief_context(report.run)
    model = os.environ.get("OPENAI_SYNC_NARRATIVE_MODEL", os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"))
    fallback = fallback_sync_narrative(summary, brief_context)
    payload = fallback | {"model": "", "generated_by_ai": False, "error": ""}

    if not os.environ.get("OPENAI_API_KEY"):
        payload["error"] = "OPENAI_API_KEY is not set."
    else:
        try:
            from openai import OpenAI

            response = OpenAI().responses.create(
                model=model,
                input=build_sync_narrative_prompt(report.report_text or "", summary, brief_context),
                temperature=0.2,
                max_output_tokens=1800,
            )
            parsed = parse_sync_narrative_response(response.output_text)
            payload = {
                "headline": parsed["headline"],
                "dek": parsed["dek"],
                "narrative": parsed["narrative"],
                "bullets": parsed["bullets"],
                "notable_signals": parsed["notable_signals"],
                "trend_line": parsed["trend_line"],
                "disclaimer": parsed["disclaimer"],
                "newsletter_subject": parsed["newsletter_subject"],
                "preview_text": parsed["preview_text"],
                "model": model,
                "generated_by_ai": True,
                "error": "",
            }
        except Exception as exc:
            payload["error"] = str(exc)[:1000]

    narrative, _ = ParcelBookSyncNarrative.objects.update_or_create(
        assessor_sync_report=report,
        defaults={
            "model": payload.get("model", ""),
            "headline": payload["headline"],
            "dek": payload.get("dek", ""),
            "narrative": payload["narrative"],
            "bullets": payload["bullets"],
            "notable_signals": payload.get("notable_signals", []),
            "trend_line": payload.get("trend_line", ""),
            "disclaimer": payload.get("disclaimer", SYNC_BRIEF_DISCLAIMER),
            "newsletter_subject": payload.get("newsletter_subject", ""),
            "preview_text": payload.get("preview_text", ""),
            "summary_snapshot": summary,
            "brief_context": brief_context,
            "generated_by_ai": payload.get("generated_by_ai", False),
            "error": payload.get("error", ""),
        },
    )
    return narrative


def build_sync_narrative_prompt(
    report_text: str,
    summary: dict[str, Any],
    brief_context: dict[str, Any] | None = None,
) -> str:
    auditor = (summary or {}).get("auditor") or {}
    brief_context = brief_context or {}
    return (
        "You are writing the morning OpenSkagit Parcel Book field note for Skagit County real estate investors, "
        "brokers, builders, and land watchers. Sound local, precise, and useful: more field-note analyst than "
        "generic software summary. Focus only on fresh public-record signals inside the reporting window. "
        "The curated fresh-signal context is authoritative for every count that appears in the dashboard or newsletter. "
        "Raw sync and auditor summary totals are diagnostics only; do not quote them when they differ from curated context counts, "
        "because unmatched recordings and stale assessor sales updates are intentionally filtered out. "
        "Do not treat assessor sales rows that were merely updated as market activity. Mention them only if the "
        "curated context says there are current-window sale/deed dates. Auditor recordings are filing metadata "
        "and document links, not legal conclusions, approvals, title opinions, or investment advice.\n\n"
        "Return compact JSON with keys: headline, dek, narrative, bullets, notable_signals, trend_line, "
        "disclaimer, newsletter_subject, preview_text. bullets must be exactly 3 short strings. notable_signals "
        "must be 3 to 6 short strings based only on the notable_signals in the curated context. Return only the "
        "JSON object, with no markdown fences, no prose before it, and no prose after it.\n\n"
        f"Curated fresh-signal context JSON:\n{json.dumps(brief_context, default=str)[:14000]}\n\n"
        f"Assessor sync summary JSON:\n{json.dumps(summary, default=str)[:6000]}\n\n"
        f"Auditor sync summary JSON:\n{json.dumps(auditor, default=str)[:4000]}\n\n"
        f"Latest admin assessor sync report:\n{report_text[:12000]}"
    )


def parse_sync_narrative_response(text: str) -> dict[str, Any]:
    body = (text or "").strip()
    if body.startswith("```"):
        body = body.strip("`").strip()
        if body.lower().startswith("json"):
            body = body[4:].strip()
    start = body.find("{")
    end = body.rfind("}")
    if start >= 0 and end > start:
        body = body[start : end + 1]
    parsed = json.loads(body)
    fallback = fallback_sync_narrative({})
    bullets = [str(item)[:180] for item in (parsed.get("bullets") or [])[:3]]
    if len(bullets) != 3:
        bullets = fallback["bullets"]
    notable = [str(item)[:220] for item in (parsed.get("notable_signals") or [])[:6]]
    if not notable:
        notable = fallback.get("notable_signals", [])
    return {
        "headline": str(parsed.get("headline") or fallback["headline"])[:140],
        "dek": str(parsed.get("dek") or fallback.get("dek") or "")[:220],
        "narrative": _clean_text(str(parsed.get("narrative") or fallback["narrative"])),
        "bullets": bullets,
        "notable_signals": notable,
        "trend_line": str(parsed.get("trend_line") or fallback.get("trend_line") or "")[:300],
        "disclaimer": str(parsed.get("disclaimer") or fallback.get("disclaimer") or SYNC_BRIEF_DISCLAIMER)[:400],
        "newsletter_subject": str(parsed.get("newsletter_subject") or fallback.get("newsletter_subject") or "")[:140],
        "preview_text": str(parsed.get("preview_text") or fallback.get("preview_text") or "")[:220],
    }


def _clean_text(text: str) -> str:
    return " ".join((text or "").split())


def fallback_sync_narrative(summary: dict[str, Any], brief_context: dict[str, Any] | None = None) -> dict[str, Any]:
    if brief_context:
        counts = brief_context.get("counts") or {}
        signal_counts = brief_context.get("signal_counts") or {}
        window = (brief_context.get("window") or {}).get("label") or "the latest sync window"
        fresh_recordings = int(counts.get("fresh_recordings") or 0)
        fresh_sales = int(counts.get("fresh_sales") or 0)
        ignored_sales = int(counts.get("stale_sales_updates_ignored") or 0)
        top_groups = [
            f"{_brief_signal_label(group)}: {count:,}"
            for group, count in list(signal_counts.items())[:3]
        ]
        notable = []
        for item in (brief_context.get("notable_signals") or [])[:5]:
            label = item.get("signal_label") or item.get("document_type") or "Recording"
            parcel = item.get("parcel_number") or "unmatched parcel"
            place = item.get("location") or "Skagit County"
            notable.append(f"{label}: {parcel} at {place}")
        if not notable and not fresh_recordings and not fresh_sales:
            notable = ["No fresh investor-facing parcel signals were detected in this window."]
        if fresh_recordings or fresh_sales:
            headline = f"{fresh_recordings + fresh_sales:,} fresh Skagit record signal(s)"
            dek = f"{window}: auditor filings lead the read; stale assessor sales updates are filtered out."
            narrative = (
                f"Parcel Book found {fresh_recordings:,} current-window auditor recording(s)"
                f" and {fresh_sales:,} current-window sale record(s). "
                "The brief is using recorded dates and sale/deed dates, so historical assessor sales rows touched by the nightly file are not treated as market activity."
            )
        else:
            headline = "No fresh investor-facing parcel signals"
            dek = f"{window}: the sync did not surface current-window sales or notable recordings."
            narrative = (
                "The latest sync did not surface fresh sale/deed dates or auditor recordings that should be treated as investor-facing signals. "
                f"{ignored_sales:,} historical assessor sales update(s) were ignored as data maintenance."
            )
        bullets = (top_groups + [
            f"{fresh_sales:,} current-window sale/deed record(s)",
            f"{ignored_sales:,} historical assessor sales update(s) ignored",
            "Confirm source documents before acting",
        ])[:3]
        while len(bullets) < 3:
            bullets.append("Screening signal only, not a due-diligence conclusion")
        return {
            "headline": headline,
            "dek": dek,
            "narrative": narrative,
            "bullets": bullets,
            "notable_signals": notable,
            "trend_line": "; ".join(top_groups) if top_groups else "No fresh signal cluster stood out in this window.",
            "disclaimer": SYNC_BRIEF_DISCLAIMER,
            "newsletter_subject": f"Skagit parcel field note: {headline}",
            "preview_text": dek,
            "generated": False,
        }

    tables = (summary or {}).get("tables", {})
    auditor = (summary or {}).get("auditor") or {}
    files_changed = int((summary or {}).get("files_changed") or 0)
    updated = sum(int((table or {}).get("updated") or 0) for table in tables.values())
    inserted = sum(int((table or {}).get("inserted") or 0) for table in tables.values())
    applied = sum(int((table or {}).get("applied_rows") or 0) for table in tables.values())
    auditor_inserted = int(auditor.get("inserted") or 0)
    auditor_updated = int(auditor.get("updated") or 0)
    auditor_errors = int(auditor.get("errors") or 0)
    auditor_phrase = (
        f" Auditor recording checks found {auditor_inserted:,} new filing(s) and {auditor_updated:,} changed filing(s)."
        if auditor.get("enabled")
        else ""
    )
    return {
        "headline": "Latest assessor sync is ready",
        "dek": "Public-record data refreshed; review source documents before acting.",
        "narrative": (
            f"The latest assessor sync found {files_changed:,} changed source file(s) and applied "
            f"{applied:,} public-record updates.{auditor_phrase} Parcel Book is using those changes as screening signals only."
        ),
        "bullets": [
            f"{updated:,} existing records updated",
            f"{inserted + auditor_inserted:,} new records inserted",
            f"{auditor_errors:,} auditor query warning(s)" if auditor_errors else "Review high-signal parcels before relying on them for due diligence",
        ],
        "notable_signals": [],
        "trend_line": "",
        "disclaimer": SYNC_BRIEF_DISCLAIMER,
        "newsletter_subject": "Skagit parcel field note",
        "preview_text": "Fresh public-record data is ready for review.",
        "generated": False,
    }


def dashboard_context(user, sales_sort: str = "") -> dict[str, Any]:
    sync = latest_assessor_sync_summary(user, sales_sort=sales_sort)
    watchlist = dashboard_watchlist_rows(user, sync, limit=8)
    return {
        "watchlist": watchlist,
        "opportunity_cards": dashboard_opportunity_cards(user, limit=8),
        "sample_alert_row": sample_dashboard_alert_row(watchlist),
        "sync": sync,
        "tabs": TABS,
    }


def dashboard_opportunity_cards(user, limit: int = 8) -> list[dict[str, Any]]:
    from .models import OpportunitySearch

    counts = tab_counts({})
    cards = []
    accents = ["green", "blue", "purple", "orange"]
    for index, tab in enumerate(TABS):
        cards.append(
            {
                "title": tab.label,
                "location": "Skagit County, WA",
                "criteria": tab.note or tab.description,
                "count": counts.get(tab.key, ""),
                "match_label": f"{counts.get(tab.key, '')} Matches".strip(),
                "updated_at": None,
                "updated_label": "live county data",
                "url": f"{reverse('opportunity_explore')}?tab={tab.key}",
                "accent": accents[index % len(accents)],
            }
        )
    searches = OpportunitySearch.objects.filter(user=user, saved_at__isnull=False).order_by("-saved_at", "-updated_at")[: max(limit - len(cards), 0)]
    for search in searches:
        plan = search.search_plan or {}
        index = len(cards)
        cards.append(
            {
                "title": search.short_name or search.title or "Opportunity",
                "location": _opportunity_location(plan),
                "criteria": _opportunity_criteria(search, plan),
                "count": f"{search.result_count:,}",
                "match_label": f"{search.result_count:,} Match" if search.result_count == 1 else f"{search.result_count:,} Matches",
                "updated_at": search.saved_at or search.updated_at,
                "updated_label": "",
                "url": reverse("opportunity_detail", args=[search.pk]),
                "accent": accents[index % len(accents)],
            }
        )
    return cards[: max(limit, len(TABS))]


def _opportunity_location(plan: dict[str, Any]) -> str:
    value = plan.get("location") or plan.get("place") or ""
    if isinstance(value, dict):
        value = value.get("label") or value.get("name") or value.get("value") or ""
    if isinstance(value, list):
        value = ", ".join(str(item) for item in value[:2] if item)
    text = str(value or "").strip()
    return text or "Skagit County, WA"


def _opportunity_criteria(search, plan: dict[str, Any]) -> str:
    for key in ("hard_filters", "soft_rankers", "asset_intent"):
        value = plan.get(key)
        if isinstance(value, list):
            text = ", ".join(str(item) for item in value[:2] if item)
            if text:
                return text[:84]
        if isinstance(value, str) and value.strip():
            return value.strip()[:84]
    summary = (search.criteria_summary or search.prompt or "").strip()
    first_sentence = summary.split(".")[0].strip()
    return (first_sentence or "Saved parcel opportunity")[:84]


def dashboard_watchlist_rows(user, sync: dict[str, Any], limit: int | None = 8) -> list[dict[str, Any]]:
    rows = watchlist_rows(user)
    alerts = {
        (alert.get("parcel_number") or "").upper(): alert
        for alert in (sync.get("watchlist_alerts") or [])
        if alert.get("parcel_number")
    }
    for row in rows:
        alert = alerts.get((row.get("parcel_number") or "").upper())
        row["has_alert"] = bool(alert)
        row["alert_label"] = alert.get("alert_label", "") if alert else ""
        row["alert_date_label"] = alert.get("date_label", "") if alert else ""
        row["alert_document_url"] = alert.get("document_url", "") if alert else ""
        row["alert_created_at"] = alert.get("created_at") if alert else None
    rows.sort(key=lambda row: _timestamp(row.get("saved_at")), reverse=True)
    rows.sort(key=lambda row: not row.get("has_alert"))
    return rows[:limit] if limit else rows


def _timestamp(value: Any) -> float:
    if hasattr(value, "timestamp"):
        return float(value.timestamp())
    return 0.0


def sample_dashboard_alert_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if any(row.get("has_alert") for row in rows):
        return {}
    source = rows[0] if rows else {}
    return {
        "parcel_number": source.get("parcel_number") or "P77001",
        "location": source.get("location") or "906 MAPLE ST, SEDRO WOOLLEY",
        "current_use": source.get("current_use") or "HOUSEHOLD, SFR, INSIDE CITY",
        "zoning": source.get("zoning") or "I",
        "source_tab_label": source.get("source_tab_label") or "Saved Parcel",
        "assessed_value_fmt": source.get("assessed_value_fmt") or "$462,200",
        "acres_fmt": source.get("acres_fmt") or "1.47 acres",
        "aerial_image_url": source.get("aerial_image_url") or "",
        "alert_label": "Sample alert",
        "alert_date_label": "latest sync",
        "has_alert": True,
        "is_sample": True,
    }


def watchlist_rows(user, limit: int | None = None) -> list[dict[str, Any]]:
    from .models import OpportunitySavedParcel, OpportunitySearch

    qs = OpportunitySavedParcel.objects.filter(user=user).order_by("-updated_at")
    if limit:
        qs = qs[:limit]
    saved_items = list(qs)
    rows = []
    for saved in saved_items:
        detail = parcel_summary(saved.parcel_number)
        if detail:
            detail["source_tab"] = saved.source_tab
            opportunity_title = ""
            if saved.source_tab.startswith("opportunity:"):
                search_id = saved.source_tab.split(":", 1)[1]
                opportunity = OpportunitySearch.objects.filter(user=user, pk=search_id).first()
                opportunity_title = (opportunity.short_name or opportunity.title) if opportunity else ""
            detail["source_tab_label"] = opportunity_title or (TAB_LOOKUP.get(saved.source_tab, TABS[0]).label if saved.source_tab else "Saved Parcel")
            detail["watch_reason"] = watch_reason(detail)
            detail["saved_at"] = saved.updated_at
            detail["is_saved"] = True
            rows.append(detail)
    return rows


def watch_reason(row: dict[str, Any]) -> str:
    source = row.get("source_tab_label") or "Saved Parcel"
    signals = [signal for signal in (row.get("signal_labels") or [])[:2] if signal]
    flags = [flag for flag in (row.get("risk_flags") or [])[:1] if flag]
    details = signals + flags
    if details:
        return f"Saved from {source}: {', '.join(details)}."
    return f"Saved from {source} for repeat review."


def parcel_summary(parcel_number: str) -> dict[str, Any] | None:
    detail = parcel_detail(parcel_number, include_dossier=False)
    if not detail:
        return None
    return {
        "parcel_number": detail["parcel_number"],
        "parcel_url": detail["parcel_url"],
        "detail_url_name": "opportunity_parcel_detail",
        "location": detail["location"],
        "city": detail["city"],
        "zoning": detail["zoning"],
        "zone_definition": detail["zone_definition"],
        "current_use": detail["current_use"],
        "assessed_value": detail["assessed_value"],
        "assessed_value_fmt": detail["assessed_value_fmt"],
        "land_value_fmt": detail["land_value_fmt"],
        "building_value_fmt": detail["building_value_fmt"],
        "acres_fmt": detail["acres_fmt"],
        "map_url": detail["map_url"],
        "aerial_image_url": detail["aerial_image_url"],
        "signal_labels": detail["feature_labels"],
        "risk_flags": detail["risk_flags"],
    }


def parcel_detail(parcel_number: str, include_dossier: bool = True, use_ai_feasibility: bool = False) -> dict[str, Any] | None:
    sql = """
        SELECT p.parcel_number,
               concat_ws(' ', p.situs_street_number, p.situs_street_name) AS address,
               COALESCE(NULLIF(p.situs_city_state_zip, ''), NULLIF(z.citydistrict, ''), NULLIF(z.jurisdiction, '')) AS city,
               p.owner_name, p.owner_add_1, p.owner_add_2, p.owner_add_3, p.owner_city, p.owner_state, p.owner_zip,
               p.legal_description, p.neighborhood_code, p.exemptions, p.acres, p.land_use, p.utilities,
               p.assessed_value, p.impr_land_value, p.unimpr_land_value, p.building_value,
               p.taxable_value, p.total_market_value, p.total_taxes, p.sale_date, p.sale_price, p.sale_deed_type,
               p.year_built, p.living_area, p.levy_code,
               z.zone_id, z.zone_name, z.waza_general, z.waza_specific, z.reference_url,
               ST_Y(ST_Centroid(g.geometry)) AS lat, ST_X(ST_Centroid(g.geometry)) AS lng,
               ST_XMin(g.geometry::box3d) AS min_lng, ST_YMin(g.geometry::box3d) AS min_lat,
               ST_XMax(g.geometry::box3d) AS max_lng, ST_YMax(g.geometry::box3d) AS max_lat
        FROM skagit_parcels p
        LEFT JOIN parcel_primary_zoning z ON z.parcel_id = p.parcel_number
        LEFT JOIN gis_skagit_parcels g ON g.parcel_id = p.parcel_number
        WHERE p.parcel_number = %s
          AND p.inactive_date IS NULL
        LIMIT 1
    """
    rows = _fetch(sql, [parcel_number.upper()])
    if not rows:
        return None
    row = rows[0]
    item = _base_row(row, "Parcel")
    item.update(
        {
            "taxable_value_fmt": money(row.get("taxable_value")),
            "market_value_fmt": money(row.get("total_market_value")),
            "total_taxes_fmt": money(row.get("total_taxes")),
            "sale_price_fmt": money(row.get("sale_price")),
            "sale_date": row.get("sale_date"),
            "sale_deed_type": row.get("sale_deed_type") or "",
            "year_built": row.get("year_built") or "",
            "living_area": row.get("living_area") or "",
            "levy_code": row.get("levy_code") or "",
            "legal_description": row.get("legal_description") or "",
            "neighborhood_code": row.get("neighborhood_code") or "",
            "owner_lines": _owner_lines(row),
            "feature_labels": feature_labels(row),
            "risk_flags": risk_flags(
                "No parcel geometry" if not item["map_url"] else None,
                "Unknown zoning" if not row.get("zone_id") else None,
                "No utility signal" if not utility_labels(row.get("utilities")) else None,
                "Natural resource zoning" if is_natural_resource_zone(row.get("zone_id"), row.get("zone_name"), row.get("waza_general")) else None,
            ) + current_use_zoning_flags(row),
            "history": parcel_value_history(parcel_number),
            "history_chart": parcel_value_history_chart(parcel_number),
            "sales": parcel_recent_sales(parcel_number),
            "tax_pressure": parcel_tax_pressure(parcel_number),
            "sync_changes": parcel_sync_changes(parcel_number),
            "dossier": parcel_dossier(parcel_number) if include_dossier else {},
            "gis_context": parcel_gis_context(parcel_number) if include_dossier else {},
        }
    )
    item["feasibility"] = parcel_feasibility(item, use_ai=use_ai_feasibility) if include_dossier else {}
    return item


def _owner_lines(row: dict[str, Any]) -> list[str]:
    lines = []
    for key in ("owner_add_1", "owner_add_2", "owner_add_3"):
        value = (row.get(key) or "").strip()
        if value:
            lines.append(value)
    city_line = " ".join(str(row.get(key) or "").strip() for key in ("owner_city", "owner_state", "owner_zip") if row.get(key))
    if city_line:
        lines.append(city_line)
    return lines


def parcel_dossier(parcel_number: str) -> dict[str, Any]:
    parcel_number = parcel_number.upper()
    improvements = parcel_improvements(parcel_number)
    land_segments = parcel_land_segments(parcel_number)
    zoning_overlaps = parcel_zoning_overlaps(parcel_number)
    rollup = parcel_rollup_context(parcel_number)
    return {
        "summary_cards": [
            {"label": "Improvement records", "value": len(improvements), "note": _dossier_improvement_note(improvements)},
            {"label": "Land segments", "value": len(land_segments), "note": _dossier_land_note(land_segments)},
            {"label": "Zoning", "value": len(zoning_overlaps), "note": _dossier_zoning_note(zoning_overlaps)},
        ],
        "improvements": improvements,
        "land_segments": land_segments,
        "zoning_overlaps": zoning_overlaps,
        "rollup": rollup,
    }


def parcel_improvements(parcel_number: str) -> list[dict[str, Any]]:
    rows = _fetch(
        """
        SELECT
            i.imprv_id,
            i.segment_id,
            NULLIF(i.description, '') AS description,
            NULLIF(i.building_style, '') AS building_style,
            i.imprv_det_type_cd,
            COALESCE(i.imprv_det_type_description, type_map.description, NULLIF(i.imprv_det_type_cd, '')) AS type_description,
            i.imprv_det_class_cd,
            COALESCE(i.imprv_det_class_description, class_map.description, NULLIF(i.imprv_det_class_cd, '')) AS class_description,
            i.condition_cd,
            COALESCE(i.condition_description, condition_map.description, NULLIF(i.condition_cd, '')) AS condition_description,
            i.imprv_val_num,
            i.living_area_num,
            NULLIF(i.actual_year_built, '') AS actual_year_built,
            NULLIF(i.effective_yr_blt, '') AS effective_yr_blt,
            NULLIF(i.constructionstyle, '') AS constructionstyle,
            NULLIF(i.foundation, '') AS foundation,
            NULLIF(i.exteriorwall, '') AS exteriorwall,
            NULLIF(i.roofcovering, '') AS roofcovering,
            NULLIF(i.heatingcooling, '') AS heatingcooling,
            NULLIF(i.bedrooms, '') AS bedrooms
        FROM improvements i
        LEFT JOIN code_mappings type_map
          ON type_map.category = 'improvement_type'
         AND type_map.code = upper(trim(i.imprv_det_type_cd))
        LEFT JOIN code_mappings class_map
          ON class_map.category = 'improvement_class'
         AND class_map.code = upper(trim(i.imprv_det_class_cd))
        LEFT JOIN code_mappings condition_map
          ON condition_map.category = 'condition'
         AND condition_map.code = upper(trim(i.condition_cd))
        WHERE upper(i.parcelnumber) = upper(%s)
        ORDER BY i.imprv_id, i.segment_id
        LIMIT 12
        """,
        [parcel_number],
    )
    for row in rows:
        row["living_area_fmt"] = _area(row.get("living_area_num"))
        row["detail_line"] = _improvement_detail_line(row)
    return rows


def parcel_land_segments(parcel_number: str) -> list[dict[str, Any]]:
    rows = _fetch(
        """
        SELECT land_seg_id, land_type, appr_meth, size_acres_num, size_square_feet,
               effective_front, actual_front, market_value_num, open_space_val,
               open_space_use_code_desc, land_seg_comment
        FROM land
        WHERE upper(parcelnumber) = upper(%s)
        ORDER BY market_value_num DESC NULLS LAST, land_seg_id
        LIMIT 10
        """,
        [parcel_number],
    )
    for row in rows:
        row["size_fmt"] = acres(row.get("size_acres_num")) if row.get("size_acres_num") else _area(row.get("size_square_feet"), "sq ft")
        row["market_value_fmt"] = money(row.get("market_value_num"))
    return rows


def parcel_zoning_overlaps(parcel_number: str) -> list[dict[str, Any]]:
    rows = _fetch(
        """
        SELECT zone_id, zone_name, jurisdiction, waza_general, waza_specific,
               percent_of_parcel, overlap_area_sqft, reference_url, is_primary
        FROM parcel_zoning
        WHERE upper(parcel_id) = upper(%s)
        ORDER BY is_primary DESC, percent_of_parcel DESC NULLS LAST
        LIMIT 10
        """,
        [parcel_number],
    )
    material = []
    seen = set()
    for row in rows:
        percent = _decimal(row.get("percent_of_parcel")) or Decimal("0")
        is_primary = bool(row.get("is_primary"))
        key = (row.get("zone_id"), row.get("zone_name"), row.get("jurisdiction"))
        if key in seen:
            continue
        if not is_primary and percent < Decimal("5"):
            continue
        row["percent_of_parcel_fmt"] = f"{percent:.0f}%" if percent >= Decimal("5") else ""
        row["is_tiny_overlap"] = percent < Decimal("5") and not is_primary
        row.update(zoning_definition_context(row))
        material.append(row)
        seen.add(key)
    return material


def zoning_definition_context(row: dict[str, Any]) -> dict[str, str]:
    zone_code = row.get("zone_id") or ""
    jurisdiction = row.get("jurisdiction") or ""
    source_url = row.get("reference_url") or ""
    description = row.get("zone_name") or ""
    try:
        from zoning_mcp import services as zoning_services

        normalized_jurisdiction = zoning_services.normalize_jurisdiction(jurisdiction)
        normalized_zone = zoning_services.normalize_zone_code(zone_code)
        profile = zoning_services.get_zone_profile(normalized_jurisdiction, normalized_zone) if normalized_jurisdiction and normalized_zone else {}
        profile_name = profile.get("zone_name") or description
        purpose = profile.get("purpose") or ""
        if profile_name and purpose and purpose != profile_name:
            description = f"{profile_name}. {purpose}."
        elif profile_name:
            description = profile_name
        source_url = profile.get("source_url") or source_url
    except Exception:
        pass
    if not description:
        description = "No zoning definition is available from zoning_mcp."
    return {
        "definition": description[:500],
        "definition_source_url": source_url,
    }


def parcel_gis_context(parcel_number: str) -> dict[str, Any]:
    try:
        from gis_mcp import services as gis_services

        raw = gis_services.get_parcel_overlays(parcel_number, include_parcel_geometry=False)
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:220], "layers": [], "count": 0}

    layers = []
    for overlay in raw.get("overlays") or []:
        features = overlay.get("features") or []
        if not features:
            continue
        rows = [_gis_feature_summary(feature.get("attributes") or {}) for feature in features[:4]]
        rows = [row for row in rows if row.get("primary") or row.get("details")]
        if not rows:
            continue
        layers.append(
            {
                "key": overlay.get("layer") or "",
                "label": overlay.get("label") or overlay.get("layer") or "GIS layer",
                "count": overlay.get("count") or len(features),
                "exceeded": bool(overlay.get("exceededTransferLimit")),
                "rows": rows,
            }
        )
    return {"status": "ok", "layers": layers, "count": len(layers)}


def parcel_rollup_context(parcel_number: str) -> dict[str, Any]:
    rows = _fetch(
        """
        SELECT land_use_code, land_use_description, neighborhood_code_id,
               neighborhood_description, utilities_codes, utilities_description
        FROM assessor_rollup
        WHERE upper(parcel_number) = upper(%s)
        LIMIT 1
        """,
        [parcel_number],
    )
    return rows[0] if rows else {}


def parcel_feasibility(parcel: dict[str, Any], use_ai: bool = False) -> dict[str, Any]:
    zoning = _structured_zoning_context(parcel)
    fallback = fallback_feasibility(parcel, zoning)
    if not use_ai:
        fallback["status"] = "structured"
        fallback["note"] = "Showing zoning context from local source data."
        return fallback
    if not os.environ.get("OPENAI_API_KEY"):
        fallback["status"] = "structured"
        fallback["note"] = "OpenAI API key is not configured; showing zoning context from local source data."
        return fallback
    try:
        from openai import OpenAI

        model = os.environ.get("OPENAI_FEASIBILITY_MODEL", os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"))
        response = OpenAI().responses.create(
            model=model,
            input=build_feasibility_prompt(parcel, zoning),
            temperature=0.1,
            max_output_tokens=650,
        )
        parsed = parse_feasibility_response(response.output_text)
        parsed["status"] = "ai"
        parsed["model"] = model
        parsed["zoning_source"] = zoning.get("source", "")
        return parsed
    except Exception as exc:
        fallback["status"] = "error"
        fallback["note"] = f"AI feasibility summary unavailable: {str(exc)[:180]}"
        return fallback


def _structured_zoning_context(parcel: dict[str, Any]) -> dict[str, Any]:
    try:
        from zoning_mcp import services as zoning_services

        resolved = zoning_services.resolve_parcel(parcel_id=parcel.get("parcel_number"))
        jurisdiction = resolved.get("jurisdiction") or ""
        zone_code = resolved.get("zoning_code") or parcel.get("zoning") or ""
        profile = zoning_services.get_zone_profile(jurisdiction, zone_code) if jurisdiction and zone_code else {}
        allowed = zoning_services.list_allowed_uses(jurisdiction, zone_code) if jurisdiction and zone_code else {}
        constraints = zoning_services.get_overlays_and_constraints(parcel.get("parcel_number") or "")
        standards = zoning_services.get_development_standards(jurisdiction, zone_code) if jurisdiction and zone_code else {}
        return {
            "resolved": resolved,
            "profile": profile,
            "allowed_uses": (allowed.get("allowed_uses") or [])[:24],
            "constraints": constraints,
            "standards": standards,
            "source": "zoning_mcp",
        }
    except Exception as exc:
        return {"source": "zoning_mcp", "error": str(exc)[:300], "allowed_uses": []}


def fallback_feasibility(parcel: dict[str, Any], zoning: dict[str, Any]) -> dict[str, Any]:
    allowed = zoning.get("allowed_uses") or []
    top_uses = [row.get("use") for row in allowed[:8] if row.get("use")]
    zone = zoning.get("resolved", {}).get("zoning_code") or parcel.get("zoning")
    jurisdiction = zoning.get("resolved", {}).get("jurisdiction_label") or "local jurisdiction"
    summary = f"{zone} in {jurisdiction}. Review listed uses and source code before relying on this screen."
    if top_uses:
        summary = f"{zone} in {jurisdiction}. Zoning data lists {', '.join(top_uses[:4])} among allowed or reviewable uses."
    return {
        "headline": "Zoning screen ready for review",
        "summary": summary,
        "likely_uses": top_uses[:8],
        "constraints": [note for note in (zoning.get("constraints") or {}).get("notes", [])[:4]],
        "next_steps": ["Confirm setbacks, density, parking, critical areas, and utility capacity with the source code or planner."],
        "sources": _feasibility_sources(zoning),
        "note": "",
    }


def build_feasibility_prompt(parcel: dict[str, Any], zoning: dict[str, Any]) -> str:
    payload = {
        "parcel": {
            "parcel_number": parcel.get("parcel_number"),
            "location": parcel.get("location"),
            "owner": parcel.get("owner"),
            "acres": parcel.get("acres"),
            "current_use": parcel.get("current_use"),
            "utilities": parcel.get("utilities"),
            "assessed_value": parcel.get("assessed_value_fmt"),
            "land_value": parcel.get("land_value_fmt"),
            "building_value": parcel.get("building_value_fmt"),
            "legal_description": parcel.get("legal_description"),
        },
        "dossier": parcel.get("dossier"),
        "zoning_mcp": zoning,
    }
    return (
        "You are preparing a compact feasibility screen for an OpenSkagit parcel detail page. "
        "Use the supplied parcel dossier and zoning_mcp context. Determine what can plausibly be built or pursued, "
        "but do not state legal entitlements as certain. Be conservative and plain-English. "
        "Return only compact JSON with keys: headline, summary, likely_uses, constraints, next_steps, sources. "
        "likely_uses, constraints, next_steps, and sources must be arrays of short strings. "
        "Mention source-code or planner confirmation in next_steps.\n\n"
        f"{json.dumps(payload, default=str)[:14000]}"
    )


def parse_feasibility_response(text: str) -> dict[str, Any]:
    fallback = {
        "headline": "Feasibility needs review",
        "summary": "The AI response could not be parsed. Use the structured zoning context and source links.",
        "likely_uses": [],
        "constraints": [],
        "next_steps": ["Review source zoning code and planner guidance."],
        "sources": [],
    }
    try:
        body = (text or "").strip()
        if body.startswith("```"):
            body = body.strip("`").strip()
            if body.lower().startswith("json"):
                body = body[4:].strip()
        start = body.find("{")
        end = body.rfind("}")
        if start >= 0 and end > start:
            body = body[start : end + 1]
        parsed = json.loads(body)
    except Exception:
        return fallback
    return {
        "headline": str(parsed.get("headline") or fallback["headline"])[:140],
        "summary": str(parsed.get("summary") or fallback["summary"])[:900],
        "likely_uses": _short_list(parsed.get("likely_uses"), 8),
        "constraints": _short_list(parsed.get("constraints"), 8),
        "next_steps": _short_list(parsed.get("next_steps"), 5) or fallback["next_steps"],
        "sources": _short_list(parsed.get("sources"), 5),
    }


def _feasibility_sources(zoning: dict[str, Any]) -> list[str]:
    sources = []
    for obj in (zoning.get("profile"), zoning.get("resolved")):
        url = (obj or {}).get("source_url")
        if url and url not in sources:
            sources.append(url)
    for use in zoning.get("allowed_uses") or []:
        url = use.get("source_url")
        if url and url not in sources:
            sources.append(url)
        if len(sources) >= 4:
            break
    return sources


def _short_list(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item)[:220] for item in value if str(item).strip()][:limit]


def _improvement_detail_line(row: dict[str, Any]) -> str:
    parts = []
    for key in ("class_description", "condition_description"):
        value = (row.get(key) or "").strip()
        if value:
            parts.append(value)
    if row.get("actual_year_built"):
        parts.append(f"built {row['actual_year_built']}")
    if row.get("effective_yr_blt"):
        parts.append(f"effective {row['effective_yr_blt']}")
    return " / ".join(parts)


def _gis_feature_summary(attributes: dict[str, Any]) -> dict[str, Any]:
    cleaned = {
        _humanize_field_name(key): value
        for key, value in attributes.items()
        if _meaningful_gis_value(key, value)
    }
    if not cleaned:
        return {}
    priority_terms = ("name", "district", "zone", "type", "code", "water", "flood", "school", "parcel", "basin", "system")
    primary_key = next((key for key in cleaned if any(term in key.lower() for term in priority_terms)), next(iter(cleaned)))
    primary = cleaned.pop(primary_key)
    details = [f"{key}: {value}" for key, value in list(cleaned.items())[:5]]
    return {"primary": str(primary)[:160], "details": details}


def _meaningful_gis_value(key: str, value: Any) -> bool:
    if value in (None, "", " ", "Null", "NULL"):
        return False
    key_upper = str(key).upper()
    if key_upper in {"OBJECTID", "GLOBALID", "SHAPE", "SHAPE_AREA", "SHAPE_LENGTH"}:
        return False
    text = str(value).strip()
    return bool(text and text not in {"0", "0.0"})


def _humanize_field_name(value: str) -> str:
    text = str(value or "").replace("_", " ").strip()
    return " ".join(part.capitalize() for part in text.split())


def _area(value: Any, unit: str = "sq ft") -> str:
    amount = _decimal(value)
    if amount is None:
        return "n/a"
    return f"{amount:,.0f} {unit}"


def _dossier_improvement_note(rows: list[dict[str, Any]]) -> str:
    main = next((row for row in rows if (row.get("imprv_det_type_cd") or "").upper().startswith("MA")), None)
    if main:
        return f"{main.get('type_description') or 'Main area'} / {main.get('condition_description') or 'condition n/a'}"
    return "No main-area improvement found" if not rows else "Accessory or other segments found"


def _dossier_land_note(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No land detail segments found"
    first = rows[0]
    return " / ".join(str(value) for value in [first.get("land_type"), first.get("size_fmt")] if value)


def _dossier_zoning_note(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No zoning overlay rows found"
    first = rows[0]
    pct_text = first.get("percent_of_parcel_fmt") or ""
    primary_text = "primary" if first.get("is_primary") else ""
    return " / ".join(str(value) for value in [first.get("zone_id"), primary_text or pct_text] if value)


def parcel_value_history(parcel_number: str) -> list[dict[str, Any]]:
    rows = _fetch(
        """
        SELECT tax_year, total_value, land_value, building_value, tax_amount
        FROM skagit_parcel_history
        WHERE parcel_number = %s
        ORDER BY tax_year DESC
        LIMIT 6
        """,
        [parcel_number.upper()],
    )
    for row in rows:
        row["total_value_fmt"] = money(row.get("total_value"))
        row["tax_amount_fmt"] = money(row.get("tax_amount"))
    return rows


def parcel_value_history_chart(parcel_number: str) -> dict[str, Any]:
    rows = list(reversed(parcel_value_history(parcel_number)))
    if not rows:
        return {"points": [], "value_polyline": "", "tax_polyline": "", "has_data": False}

    chart_width = Decimal("720")
    chart_height = Decimal("280")
    left_pad = Decimal("70")
    right_pad = Decimal("76")
    top_pad = Decimal("24")
    bottom_pad = Decimal("42")
    plot_width = chart_width - left_pad - right_pad
    plot_height = chart_height - top_pad - bottom_pad

    value_values = [_decimal(row.get("total_value")) or Decimal("0") for row in rows]
    tax_values = [_decimal(row.get("tax_amount")) or Decimal("0") for row in rows]
    value_min, value_max = _chart_bounds(value_values)
    tax_min, tax_max = _chart_bounds(tax_values)

    points = []
    value_polyline = []
    tax_polyline = []
    count = len(rows)
    for index, row in enumerate(rows):
        x = left_pad + (plot_width * Decimal(index) / Decimal(max(count - 1, 1)))
        value = _decimal(row.get("total_value")) or Decimal("0")
        tax = _decimal(row.get("tax_amount")) or Decimal("0")
        value_y = _chart_y(value, value_min, value_max, top_pad, plot_height)
        tax_y = _chart_y(tax, tax_min, tax_max, top_pad, plot_height)
        point = {
            "tax_year": row.get("tax_year"),
            "x": _svg_number(x),
            "value_y": _svg_number(value_y),
            "tax_y": _svg_number(tax_y),
            "total_value": int(value),
            "tax_amount": int(tax),
            "total_value_fmt": money(value),
            "tax_amount_fmt": money(tax),
        }
        points.append(point)
        value_polyline.append(f"{point['x']},{point['value_y']}")
        tax_polyline.append(f"{point['x']},{point['tax_y']}")

    return {
        "points": points,
        "value_polyline": " ".join(value_polyline),
        "tax_polyline": " ".join(tax_polyline),
        "has_data": True,
        "value_min_fmt": money(value_min),
        "value_max_fmt": money(value_max),
        "tax_min_fmt": money(tax_min),
        "tax_max_fmt": money(tax_max),
        "labels_json": json.dumps([str(point["tax_year"]) for point in points]),
        "value_values_json": json.dumps([point["total_value"] for point in points]),
        "tax_values_json": json.dumps([point["tax_amount"] for point in points]),
    }


def aerial_image_url(row: dict[str, Any]) -> str:
    bounds = [
        _decimal(row.get("min_lng")),
        _decimal(row.get("min_lat")),
        _decimal(row.get("max_lng")),
        _decimal(row.get("max_lat")),
    ]
    if any(value is None for value in bounds):
        lat = _decimal(row.get("lat"))
        lng = _decimal(row.get("lng"))
        if lat is None or lng is None:
            return ""
        bounds = [lng - Decimal("0.0015"), lat - Decimal("0.0012"), lng + Decimal("0.0015"), lat + Decimal("0.0012")]

    min_lng, min_lat, max_lng, max_lat = bounds
    width = max(max_lng - min_lng, Decimal("0.0012"))
    height = max(max_lat - min_lat, Decimal("0.0010"))
    pad = max(width, height) * Decimal("0.85")
    bbox = [
        min_lng - pad,
        min_lat - pad,
        max_lng + pad,
        max_lat + pad,
    ]
    params = {
        "bbox": ",".join(f"{value:.7f}" for value in bbox),
        "bboxSR": "4326",
        "imageSR": "4326",
        "size": "900,620",
        "format": "jpgpng",
        "f": "image",
    }
    return f"{LATEST_AERIAL_IMAGE_URL}?{urlencode(params)}"


def parcel_recent_sales(parcel_number: str) -> list[dict[str, Any]]:
    rows = _fetch(
        """
        SELECT sale_date_iso, sale_price_num, deed_type, buyer_name, seller_name
        FROM sales
        WHERE parcel_number = %s
        ORDER BY sale_date_iso DESC NULLS LAST
        LIMIT 5
        """,
        [parcel_number.upper()],
    )
    for row in rows:
        row["sale_price_fmt"] = money(row.get("sale_price_num"))
    return rows


def parcel_tax_pressure(parcel_number: str) -> dict[str, Any] | None:
    rows = _fetch(
        """
        SELECT raw_data->'delinquent_rows' AS delinquent_rows, total_due, source_fetched_at
        FROM tax_delinquency_taxstatement
        WHERE parcel_number = %s
        ORDER BY tax_year DESC
        LIMIT 1
        """,
        [parcel_number.upper()],
    )
    if not rows:
        return None
    row = rows[0]
    delinquent_rows = row.get("delinquent_rows") or []
    total = Decimal("0")
    if isinstance(delinquent_rows, list):
        for due in delinquent_rows:
            total += _decimal(due.get("total")) or Decimal("0")
    return {"rows": delinquent_rows, "total_fmt": money(total or row.get("total_due")), "source_fetched_at": row.get("source_fetched_at")}


def parcel_sync_changes(parcel_number: str) -> list[dict[str, Any]]:
    try:
        from assessor_sync.models import AssessorSyncChange

        return list(
            AssessorSyncChange.objects.filter(record_key=parcel_number.upper())
            .values("table_name", "change_type", "changed_fields", "created_at")
            .order_by("-created_at")[:8]
        )
    except Exception:
        return []


def filter_query(filters: dict[str, str]) -> str:
    return urlencode({key: value for key, value in filters.items() if value})
