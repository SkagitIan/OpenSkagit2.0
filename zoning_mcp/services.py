from __future__ import annotations

import logging
import os
import re
from decimal import Decimal
from dataclasses import asdict
from difflib import SequenceMatcher
from typing import Any

from django.db import connection
from django.db.models import Q

from .models import Jurisdiction, ZoningCodeSection, ZoningSourceTable, ZoningUseRule
from .seed_data import JURISDICTIONS, SEED_RULES, USE_ALIASES, ZONE_NAMES
from .source_clients import CodePublishingClient

STATUS_LABELS = {
    "P": "Permitted",
    "AC": "Accessory",
    "AD": "Administrative review",
    "HE": "Hearing Examiner review",
    "C": "Conditional use",
    "CUP": "Conditional use permit",
    "X": "Prohibited or not listed as allowed",
    "UNKNOWN": "Unknown / not parsed",
}
logger = logging.getLogger(__name__)


def resolve_parcel(parcel_id: str | None = None, address: str | None = None) -> dict[str, Any]:
    if not parcel_id and not address:
        raise ValueError("Provide parcel_id or address.")
    params: list[Any] = []
    where = "p.inactive_date IS NULL"
    if parcel_id:
        where += " AND upper(p.parcel_number) = upper(%s)"
        params.append(parcel_id)
    else:
        for term in _address_terms(address or ""):
            where += " AND concat_ws(' ', p.situs_street_number, p.situs_street_name, p.situs_city_state_zip) ILIKE %s"
            params.append(f"%{term}%")
    rows = _dict_rows(
        f"""
        SELECT p.parcel_number, concat_ws(' ', p.situs_street_number, p.situs_street_name) AS address,
               p.situs_city_state_zip, COALESCE(z.jurisdiction, '') AS jurisdiction, z.zone_id,
               z.zone_name, z.reference_url, z.percent_of_parcel, g.citydistrict
        FROM skagit_parcels p
        LEFT JOIN parcel_primary_zoning z ON z.parcel_id = p.parcel_number
        LEFT JOIN gis_skagit_parcels g ON g.parcel_id = p.parcel_number
        WHERE {where}
        ORDER BY p.parcel_number
        LIMIT 5
        """,
        params,
    )
    if not rows:
        return {"found": False, "query": {"parcel_id": parcel_id, "address": address}, "source": "OpenSkagit parcel + jurisdiction GIS"}
    row = rows[0]
    jurisdiction = normalize_jurisdiction(row.get("jurisdiction") or row.get("citydistrict"))
    candidates = [_serialize_row(candidate) for candidate in rows]
    ambiguous = bool(address and not parcel_id and len(rows) > 1)
    return {
        "found": True,
        "ambiguous": ambiguous,
        "parcel_id": row["parcel_number"],
        "address": " ".join(value for value in [row.get("address"), row.get("situs_city_state_zip")] if value),
        "jurisdiction": jurisdiction,
        "jurisdiction_label": JURISDICTIONS.get(jurisdiction, {}).get("display_name", jurisdiction.replace("_", " ").title()),
        "zoning_code": normalize_zone_code(row.get("zone_id")),
        "zoning_name": row.get("zone_name") or "",
        "inside_city_limits": jurisdiction not in {"", "skagit_county", "unknown"},
        "inside_uga": None,
        "percent_of_parcel": row.get("percent_of_parcel"),
        "source": "OpenSkagit parcel_primary_zoning + GIS parcel tables",
        "source_url": row.get("reference_url") or "",
        "candidates": candidates,
        "notes": "Multiple parcel candidates matched this address; ask the user to disambiguate before feasibility analysis." if ambiguous else "",
    }


def get_zone_profile(jurisdiction: str, zone_code: str) -> dict[str, Any]:
    jurisdiction = normalize_jurisdiction(jurisdiction)
    zone_code = normalize_zone_code(zone_code)
    configured_name = ZONE_NAMES.get(jurisdiction, {}).get(zone_code, "")
    rows = _dict_rows(
        """
        SELECT zone_id, zone_name, waza_general, waza_specific, reference_url, count(*) AS feature_count
        FROM waza_zoning_zones
        WHERE lower(replace(jurisdiction, ' ', '_')) = lower(%s) AND upper(zone_id) = upper(%s)
        GROUP BY zone_id, zone_name, waza_general, waza_specific, reference_url
        ORDER BY feature_count DESC
        LIMIT 1
        """,
        [jurisdiction, zone_code],
        swallow_errors=True,
    )
    row = rows[0] if rows else {}
    return {
        "zone_code": zone_code,
        "zone_name": row.get("zone_name") or configured_name,
        "jurisdiction": jurisdiction,
        "jurisdiction_label": JURISDICTIONS.get(jurisdiction, {}).get("display_name", jurisdiction),
        "purpose": _zone_purpose(row, configured_name),
        "source_chapter": JURISDICTIONS.get(jurisdiction, {}).get("zoning_title", ""),
        "source_url": row.get("reference_url") or JURISDICTIONS.get(jurisdiction, {}).get("source_url", ""),
        "source": "OpenSkagit waza_zoning_zones plus zoning source registry",
    }


def lookup_use_status(jurisdiction: str, zone_code: str, proposed_use: str) -> dict[str, Any]:
    jurisdiction = normalize_jurisdiction(jurisdiction)
    zone_code = normalize_zone_code(zone_code)
    db_match = _best_db_rule_match(jurisdiction, zone_code, proposed_use)
    if db_match:
        rule, score = db_match
        return {
            "matched_use": rule.use_name,
            "normalized_use": rule.normalized_use_key,
            "match_score": round(score, 3),
            "status": rule.normalized_status,
            "status_label": STATUS_LABELS.get(rule.normalized_status, rule.normalized_status),
            "notes": rule.notes,
            "source_table": rule.source_table,
            "source_url": rule.source_url,
        }
    match = _best_rule_match(jurisdiction, proposed_use)
    if not match:
        return {"matched_use": "", "normalized_use": normalize_use_key(proposed_use), "status": "UNKNOWN", "status_label": STATUS_LABELS["UNKNOWN"], "notes": "No structured use row matched. Call search_zoning_code for a source-text fallback.", "source_table": "", "source_url": JURISDICTIONS.get(jurisdiction, {}).get("source_url", "")}
    rule, score = match
    status = rule.zones.get(zone_code, "UNKNOWN")
    return {"matched_use": rule.use_name, "normalized_use": rule.normalized_use_key, "match_score": round(score, 3), "status": status, "status_label": STATUS_LABELS.get(status, status), "notes": rule.notes, "source_table": rule.source_table, "source_url": rule.source_url}


def list_allowed_uses(jurisdiction: str, zone_code: str, status_filter: list[str] | None = None) -> dict[str, Any]:
    jurisdiction = normalize_jurisdiction(jurisdiction)
    zone_code = normalize_zone_code(zone_code)
    wanted = {status.upper() for status in status_filter} if status_filter else {"P", "AC", "AD", "HE", "C", "CUP"}
    db_uses = _db_allowed_uses(jurisdiction, zone_code, wanted)
    if db_uses:
        return {"jurisdiction": jurisdiction, "zone_code": zone_code, "allowed_uses": db_uses, "source": "zoning_mcp database use rules"}
    uses = []
    for rule in SEED_RULES:
        if rule.jurisdiction != jurisdiction:
            continue
        status = rule.zones.get(zone_code, "UNKNOWN")
        if status in wanted:
            uses.append({"use": rule.use_name, "normalized_use": rule.normalized_use_key, "status": status, "status_label": STATUS_LABELS.get(status, status), "category": rule.use_category, "source_table": rule.source_table, "source_url": rule.source_url})
    return {"jurisdiction": jurisdiction, "zone_code": zone_code, "allowed_uses": uses, "source": "structured zoning seed rules"}


def search_zoning_code(jurisdiction: str, query: str, limit: int = 8) -> dict[str, Any]:
    jurisdiction = normalize_jurisdiction(jurisdiction)
    db_matches = _db_code_matches(jurisdiction, query, limit)
    if db_matches:
        return {
            "jurisdiction": jurisdiction,
            "query": query,
            "matches": db_matches,
            "coverage_status": _coverage_status(jurisdiction),
            "source": "imported zoning_mcp code sections",
        }
    if os.environ.get("ZONING_MCP_ENABLE_LIVE_SEARCH", "").lower() not in {"1", "true", "yes"}:
        return {
            "jurisdiction": jurisdiction,
            "query": query,
            "matches": [],
            "coverage_status": _coverage_status(jurisdiction),
            "source": "imported zoning_mcp code sections",
            "notes": "No imported source-text matches found. Live web fallback is disabled; set ZONING_MCP_ENABLE_LIVE_SEARCH=1 to allow runtime source fetches.",
        }
    matches = CodePublishingClient().search(jurisdiction, query, limit=limit)
    serialized = [asdict(match) for match in matches]
    if not serialized:
        serialized = _seed_code_matches(jurisdiction, query, limit)
    return {
        "jurisdiction": jurisdiction,
        "query": query,
        "matches": serialized,
        "coverage_status": _coverage_status(jurisdiction),
        "source": "live Code Publishing search fallback",
    }


def get_overlays_and_constraints(parcel_id: str) -> dict[str, Any]:
    rows = _dict_rows(
        """
        SELECT zone_id, zone_name, jurisdiction, percent_of_parcel, reference_url
        FROM parcel_zoning
        WHERE upper(parcel_id) = upper(%s)
        ORDER BY is_primary DESC, percent_of_parcel DESC NULLS LAST
        LIMIT 20
        """,
        [parcel_id],
        swallow_errors=True,
    )
    notes = [
        "Local zoning overlaps are available from parcel_zoning.",
        "Environmental overlay GIS layers for shoreline, floodplain, wetlands, steep slopes, airport, and historic districts are not present in the current registered PostGIS schema, so those fields are reported as unknown rather than inferred.",
    ]
    if len(rows) > 1:
        notes.insert(0, "Parcel has multiple zoning overlaps; primary zone may not control every part of the parcel.")
    return {
        "parcel_id": parcel_id,
        "zoning_overlaps": rows,
        "multiple_zoning_overlaps": len(rows) > 1,
        "shoreline": "unknown",
        "floodplain": "unknown",
        "critical_area": "unknown",
        "historic_district": "unknown",
        "airport_overlay": "unknown",
        "notes": notes,
        "source": "OpenSkagit parcel_zoning; environmental overlay layers not loaded",
    }


def get_development_standards(jurisdiction: str, zone_code: str) -> dict[str, Any]:
    jurisdiction = normalize_jurisdiction(jurisdiction)
    zone_code = normalize_zone_code(zone_code)
    table_values = _development_standards_from_tables(jurisdiction, zone_code)
    matches = search_zoning_code(jurisdiction, f"{zone_code} setbacks height lot size density parking development standards dimensional standards", limit=5).get("matches", [])
    standards = {
        "jurisdiction": jurisdiction,
        "zone_code": zone_code,
        "minimum_lot_size": _first_standard_value(table_values, "lot_size"),
        "front_setback": _first_standard_value(table_values, "front_setback"),
        "side_setback": _first_standard_value(table_values, "side_setback"),
        "rear_setback": _first_standard_value(table_values, "rear_setback"),
        "max_height": _first_standard_value(table_values, "height"),
        "density": _first_standard_value(table_values, "density"),
        "lot_coverage": _first_standard_value(table_values, "coverage"),
        "parking_reference": _first_source_match(matches, "parking"),
        "table_values": table_values,
        "source_matches": matches,
        "coverage_status": _coverage_status(jurisdiction),
        "notes": "Structured values are extracted when imported standards tables have zone columns. Source matches are included for review, especially where standards are section/list based.",
    }
    return standards


def build_parcel_feasibility_report(parcel_id: str, proposed_use: str) -> dict[str, Any]:
    parcel = resolve_parcel(parcel_id=parcel_id)
    if not parcel.get("found"):
        return {
            "found": False,
            "parcel_id": parcel_id,
            "proposed_use": proposed_use,
            "summary": "Parcel was not found in the OpenSkagit parcel table.",
            "parcel": parcel,
            "citations": [],
        }
    if parcel.get("ambiguous"):
        return {
            "found": True,
            "needs_disambiguation": True,
            "parcel_id": parcel_id,
            "proposed_use": proposed_use,
            "summary": "Multiple parcel candidates matched. Select a parcel_id before generating a feasibility report.",
            "parcel": parcel,
            "citations": [],
        }
    jurisdiction = parcel.get("jurisdiction", "")
    zone_code = parcel.get("zoning_code", "")
    zone_profile = get_zone_profile(jurisdiction, zone_code)
    use_status = lookup_use_status(jurisdiction, zone_code, proposed_use)
    standards = get_development_standards(jurisdiction, zone_code)
    overlays = get_overlays_and_constraints(parcel_id)
    summary = _feasibility_summary(parcel, proposed_use, use_status)
    citations = _report_citations(zone_profile, use_status, standards)
    return {
        "found": True,
        "parcel_id": parcel_id,
        "proposed_use": proposed_use,
        "summary": summary,
        "parcel": parcel,
        "zone_profile": zone_profile,
        "use_status": use_status,
        "development_standards": standards,
        "overlays": overlays,
        "citations": citations,
    }


def compare_zones_for_use(proposed_use: str, jurisdictions: list[str] | None = None) -> dict[str, Any]:
    jurisdiction_set = {normalize_jurisdiction(item) for item in jurisdictions} if jurisdictions else None
    db_results = _db_compare_zones_for_use(proposed_use, jurisdiction_set)
    if db_results:
        return {"proposed_use": proposed_use, "matches": db_results}
    results = []
    for rule in SEED_RULES:
        if jurisdiction_set and rule.jurisdiction not in jurisdiction_set:
            continue
        score = _rule_match_score(rule.normalized_use_key, rule.use_name, proposed_use)
        if score < 0.7:
            continue
        for zone_code, status in rule.zones.items():
            if status in {"P", "AD", "HE", "C", "CUP", "AC"}:
                results.append({"jurisdiction": rule.jurisdiction, "zone_code": zone_code, "status": status, "status_label": STATUS_LABELS.get(status, status), "matched_use": rule.use_name, "match_score": round(score, 3), "source_table": rule.source_table, "source_url": rule.source_url})
    results.sort(key=lambda row: (row["status"] != "P", -row["match_score"], row["jurisdiction"], row["zone_code"]))
    return {"proposed_use": proposed_use, "matches": results}


def _feasibility_summary(parcel: dict[str, Any], proposed_use: str, use_status: dict[str, Any]) -> str:
    jurisdiction = parcel.get("jurisdiction_label") or parcel.get("jurisdiction", "")
    zone = " ".join(part for part in [parcel.get("zoning_code"), parcel.get("zoning_name")] if part)
    status = use_status.get("status")
    matched = use_status.get("matched_use") or proposed_use
    if status == "P":
        answer = f"{matched} appears to be permitted"
    elif status in {"AD", "HE", "C", "CUP", "AC"}:
        answer = f"{matched} appears possible but requires {use_status.get('status_label', status).lower()}"
    elif status == "X":
        answer = f"{matched} is not listed as allowed in the structured zoning rules"
    else:
        answer = f"{matched} could not be confirmed from structured zoning rules"
    return f"Parcel {parcel.get('parcel_id')} is in {jurisdiction} and appears zoned {zone}. For '{proposed_use}', {answer}. Check development standards and overlays before treating this as final feasibility."


def _report_citations(zone_profile: dict[str, Any], use_status: dict[str, Any], standards: dict[str, Any]) -> list[dict[str, str]]:
    citations = []
    if zone_profile.get("source_url"):
        citations.append({"label": "Zone profile", "url": zone_profile["source_url"]})
    if use_status.get("source_url"):
        citations.append({"label": use_status.get("source_table") or "Use status", "url": use_status["source_url"]})
    for match in standards.get("source_matches", [])[:3]:
        if match.get("source_url"):
            citations.append({"label": match.get("section") or "Development standards", "url": match["source_url"]})
    seen = set()
    unique = []
    for citation in citations:
        key = (citation["label"], citation["url"])
        if key not in seen:
            unique.append(citation)
            seen.add(key)
    return unique


def normalize_jurisdiction(value: str | None) -> str:
    text = normalize_use_key(value or "")
    return {"skagit": "skagit_county", "county": "skagit_county", "mt_vernon": "mount_vernon", "sedro_woolley_city": "sedro_woolley"}.get(text, text or "unknown")


def normalize_zone_code(value: str | None) -> str:
    return normalize_use_key(value or "").upper()


def normalize_use_key(value: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", value.lower())).strip("_")


def _address_terms(address: str) -> list[str]:
    return [term for term in re.findall(r"[A-Za-z0-9]+", address) if len(term) >= 2][:6]


def _dict_rows(sql: str, params: list[Any] | None = None, swallow_errors: bool = False) -> list[dict[str, Any]]:
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or [])
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception:
        if swallow_errors:
            logger.warning("Database query failed with swallow_errors=True", exc_info=True)
            return []
        raise


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    serialized = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            serialized[key] = float(value)
        elif hasattr(value, "isoformat"):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized


def _development_standards_from_tables(jurisdiction: str, zone_code: str) -> list[dict[str, str]]:
    try:
        tables = (
            ZoningSourceTable.objects.filter(jurisdiction__key=jurisdiction)
            .only("chapter_title", "caption", "nearest_heading", "source_url", "rows")
            .order_by("chapter_ref", "table_index")[:500]
        )
    except Exception:
        logger.warning("Failed to load zoning source tables for development standards", exc_info=True)
        return []

    matches: list[dict[str, str]] = []
    for table in tables:
        source_label = table.caption or table.nearest_heading or table.chapter_title
        context = f"{source_label} {table.chapter_title}".lower()
        if not _looks_like_standards_table(context):
            continue

        rows = _coerce_table_rows(table.rows)
        header_index, zone_index = _find_zone_column(rows, zone_code)
        if zone_index is None:
            continue

        category = ""
        for row in rows[header_index + 1 :]:
            row_label = str(row[0]).strip() if row else ""
            value = row[zone_index] if zone_index < len(row) else ""
            value = str(value).strip()
            if row_label and not value and _looks_like_category_row(row):
                category = row_label.title()
                continue
            label = f"{category} - {row_label}" if category and row_label else row_label
            if not label or not value or value in {"-", "--", "N/A", "n/a"}:
                continue
            kind = _classify_standard_label(label)
            if kind == "other" and len(matches) > 40:
                continue
            matches.append(
                {
                    "kind": kind,
                    "label": label,
                    "value": value,
                    "source_table": source_label,
                    "source_url": table.source_url,
                }
            )
            if len(matches) >= 60:
                return matches
    return matches


def _looks_like_standards_table(context: str) -> bool:
    terms = [
        "standard",
        "development",
        "dimensional",
        "bulk",
        "area",
        "lot",
        "setback",
        "yard",
        "height",
        "density",
        "coverage",
        "intensity",
    ]
    return any(term in context for term in terms)


def _coerce_table_rows(rows: Any) -> list[list[str]]:
    if not isinstance(rows, list):
        return []
    normalized = []
    for row in rows:
        if isinstance(row, dict):
            values = list(row.values())
        elif isinstance(row, list):
            values = row
        else:
            continue
        normalized.append(["" if value is None else str(value).strip() for value in values])
    return normalized


def _find_zone_column(rows: list[list[str]], zone_code: str) -> tuple[int, int | None]:
    zone = normalize_zone_code(zone_code)
    for row_index, row in enumerate(rows[:8]):
        for col_index, cell in enumerate(row):
            if normalize_zone_code(cell) == zone:
                return row_index, col_index
    return 0, None


def _looks_like_category_row(row: list[str]) -> bool:
    populated = [cell for cell in row if str(cell).strip()]
    first = str(row[0]).strip()
    text = normalize_use_key(first).replace("_", " ")
    if "note" in text:
        return False
    category_terms = {"minimum", "maximum", "setback", "setbacks", "coverage", "height", "density", "lot size", "lot width", "lot depth", "yard"}
    if len(populated) == 1:
        return any(term in text for term in category_terms)
    return bool(first and first.upper() == first and len(first.split()) <= 8)


def _classify_standard_label(label: str) -> str:
    text = normalize_use_key(label).replace("_", " ")
    if "coverage" in text or "impervious" in text or "open space" in text:
        return "coverage"
    if "height" in text:
        return "height"
    if ("side" in text and "setback" in text) or "side yard" in text or "interior side" in text:
        return "side_setback"
    if ("front" in text and "setback" in text) or "front yard" in text or ("street setback" in text and "side street" not in text):
        return "front_setback"
    if ("rear" in text and "setback" in text) or "rear yard" in text:
        return "rear_setback"
    if "lot width" in text or "lot depth" in text or "lot with alley" in text or "lot without alley" in text or "landscaped" in text:
        return "other"
    if "lot size" in text or "minimum lot" in text or "min lot" in text or "lot area" in text:
        return "lot_size"
    if "density" in text or "units per acre" in text:
        return "density"
    if "parking" in text:
        return "parking"
    return "other"


def _first_standard_value(table_values: list[dict[str, str]], kind: str) -> str | None:
    if kind == "side_setback":
        for row in table_values:
            if row.get("kind") == kind and "interior side" in row.get("label", "").lower():
                return row.get("value") or None
    for row in table_values:
        if row.get("kind") == kind:
            return row.get("value") or None
    return None


def _first_source_match(matches: list[dict[str, str]], term: str) -> dict[str, str] | None:
    term = term.lower()
    for match in matches:
        if term in f"{match.get('section', '')} {match.get('text', '')}".lower():
            return match
    return matches[0] if matches else None


def _coverage_status(jurisdiction: str) -> dict[str, Any]:
    try:
        record = Jurisdiction.objects.filter(key=jurisdiction).values(
            "display_name", "code_source", "zoning_title", "source_url", "extraction_status"
        ).first()
    except Exception:
        logger.warning("Failed to load jurisdiction coverage status", exc_info=True)
        record = None
    configured = JURISDICTIONS.get(jurisdiction, {})
    status = record or configured
    return {
        "jurisdiction": jurisdiction,
        "display_name": status.get("display_name", jurisdiction),
        "code_source": status.get("code_source", ""),
        "zoning_title": status.get("zoning_title", ""),
        "source_url": status.get("source_url", ""),
        "extraction_status": status.get("extraction_status", "Coverage status is not registered."),
    }


def _zone_purpose(row: dict[str, Any], fallback_name: str) -> str:
    pieces = [row.get("waza_general"), row.get("waza_specific"), fallback_name]
    return " / ".join(str(piece) for piece in pieces if piece) or "Purpose not extracted yet; consult source chapter."


def _best_rule_match(jurisdiction: str, proposed_use: str):
    scored = [(rule, _rule_match_score(rule.normalized_use_key, rule.use_name, proposed_use)) for rule in SEED_RULES if rule.jurisdiction == jurisdiction]
    scored = [item for item in scored if item[1] >= 0.35]
    return max(scored, key=lambda item: item[1]) if scored else None


def _best_db_rule_match(jurisdiction: str, zone_code: str, proposed_use: str):
    try:
        rules = list(
            ZoningUseRule.objects.select_related("jurisdiction", "zone")
            .filter(jurisdiction__key=jurisdiction, zone__zone_code=zone_code)
        )
    except Exception:
        return None
    scored = [(rule, _rule_match_score(rule.normalized_use_key, rule.use_name, proposed_use)) for rule in rules]
    scored = [item for item in scored if item[1] >= 0.35]
    return max(scored, key=lambda item: (item[1], _status_rank(item[0].normalized_status))) if scored else None


def _db_allowed_uses(jurisdiction: str, zone_code: str, wanted: set[str]) -> list[dict[str, Any]]:
    try:
        rules = (
            ZoningUseRule.objects.select_related("zone")
            .filter(jurisdiction__key=jurisdiction, zone__zone_code=zone_code, normalized_status__in=wanted)
            .order_by("use_category", "use_name")
        )
        return [
            {
                "use": rule.use_name,
                "normalized_use": rule.normalized_use_key,
                "status": rule.normalized_status,
                "status_label": STATUS_LABELS.get(rule.normalized_status, rule.normalized_status),
                "category": rule.use_category,
                "source_table": rule.source_table,
                "source_url": rule.source_url,
            }
            for rule in rules
        ]
    except Exception:
        return []


def _db_code_matches(jurisdiction: str, query: str, limit: int) -> list[dict[str, str]]:
    terms = [term for term in re.findall(r"[a-z0-9]+", query.lower()) if len(term) >= 3]
    if not terms:
        return []
    try:
        filters = Q()
        for term in terms:
            filters |= Q(section__icontains=term) | Q(heading__icontains=term) | Q(text__icontains=term)
        section_rows = list(
            ZoningCodeSection.objects.filter(jurisdiction__key=jurisdiction)
            .filter(filters)
            .only("chapter_title", "section", "heading", "text", "source_url")[:5000]
        )
    except Exception:
        logger.warning("Failed to search imported zoning code sections", exc_info=True)
        return []
    scored = []
    for section in section_rows:
        haystack = f"{section.section} {section.heading} {section.text}".lower()
        score = sum(3 if term in section.heading.lower() else 1 for term in terms if term in haystack)
        if not score:
            continue
        snippet = _snippet_for_terms(section.text, terms)
        scored.append(
            (
                score,
                {
                    "chapter": section.chapter_title,
                    "section": section.section,
                    "text": f"{section.heading}\n{snippet}".strip(),
                    "source_url": section.source_url,
                },
            )
        )
    scored.sort(key=lambda item: (-item[0], item[1]["section"]))
    return [row for _, row in scored[:limit]]


def _db_compare_zones_for_use(proposed_use: str, jurisdiction_set: set[str] | None) -> list[dict[str, Any]]:
    try:
        rules = ZoningUseRule.objects.select_related("jurisdiction", "zone").filter(
            normalized_status__in=["P", "AD", "HE", "C", "CUP", "AC"]
        )
        if jurisdiction_set:
            rules = rules.filter(jurisdiction__key__in=jurisdiction_set)
        rules = list(rules.order_by("jurisdiction__key", "zone__zone_code", "normalized_use_key")[:5000])
    except Exception:
        logger.warning("Failed to compare zones for use from zoning rules", exc_info=True)
        return []
    results = []
    for rule in rules:
        score = _rule_match_score(rule.normalized_use_key, rule.use_name, proposed_use)
        if score < 0.7:
            continue
        results.append(
            {
                "jurisdiction": rule.jurisdiction.key,
                "zone_code": rule.zone.zone_code,
                "status": rule.normalized_status,
                "status_label": STATUS_LABELS.get(rule.normalized_status, rule.normalized_status),
                "matched_use": rule.use_name,
                "match_score": round(score, 3),
                "source_table": rule.source_table,
                "source_url": rule.source_url,
            }
        )
    results.sort(key=lambda row: (row["status"] != "P", -row["match_score"], row["jurisdiction"], row["zone_code"]))
    return results


def _snippet_for_terms(text: str, terms: list[str], width: int = 900) -> str:
    lowered = text.lower()
    first = min((lowered.find(term) for term in terms if term in lowered), default=0)
    start = max(first - 180, 0)
    return text[start : start + width].strip()


def _seed_code_matches(jurisdiction: str, query: str, limit: int) -> list[dict[str, str]]:
    terms = {term for term in re.findall(r"[a-z0-9]+", query.lower()) if len(term) >= 3}
    rows = []
    for rule in SEED_RULES:
        if rule.jurisdiction != jurisdiction:
            continue
        haystack = f"{rule.use_category} {rule.use_name} {rule.normalized_use_key} {rule.source_table}".lower()
        score = sum(1 for term in terms if term in haystack)
        if not score:
            continue
        statuses = ", ".join(f"{zone}: {status}" for zone, status in rule.zones.items())
        rows.append(
            (
                score,
                {
                    "chapter": JURISDICTIONS.get(jurisdiction, {}).get("zoning_title", ""),
                    "section": rule.source_table,
                    "text": f"{rule.use_name}. {statuses}",
                    "source_url": rule.source_url,
                },
            )
        )
    rows.sort(key=lambda item: (-item[0], item[1]["text"]))
    return [row for _, row in rows[:limit]]


def _rule_match_score(key: str, name: str, proposed_use: str) -> float:
    proposed_key = normalize_use_key(proposed_use)
    proposed = proposed_key.replace("_", " ")
    key_text = key.replace("_", " ")
    name_text = normalize_use_key(name).replace("_", " ")
    candidates = [key_text, name_text, *USE_ALIASES.get(key, [])]
    if proposed in candidates or proposed == key_text:
        return 1.0
    if proposed in key_text or proposed in name_text:
        return 0.9
    if any(proposed in alias or alias in proposed for alias in USE_ALIASES.get(key, [])):
        return 0.86
    if any(alias in key_text or alias in name_text for alias in USE_ALIASES.get(proposed_key, [])):
        return 0.86
    return max(SequenceMatcher(None, proposed, candidate).ratio() for candidate in candidates)


def _status_rank(status: str) -> int:
    return {"P": 6, "AC": 5, "AD": 4, "HE": 4, "C": 3, "CUP": 3, "UNKNOWN": 1, "X": 0}.get(status, 0)
