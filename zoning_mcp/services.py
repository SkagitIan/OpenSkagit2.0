from __future__ import annotations

import re
from dataclasses import asdict
from difflib import SequenceMatcher
from typing import Any

from django.db import connection

from .models import Jurisdiction, ZoningCodeSection, ZoningUseRule
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
    return {
        "found": True,
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
        "candidates": rows,
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
        return {"jurisdiction": jurisdiction, "query": query, "matches": db_matches}
    matches = CodePublishingClient().search(jurisdiction, query, limit=limit)
    serialized = [asdict(match) for match in matches]
    if not serialized:
        serialized = _seed_code_matches(jurisdiction, query, limit)
    return {"jurisdiction": jurisdiction, "query": query, "matches": serialized}


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
    notes = ["Only local zoning overlaps are available in this V1 tool; use GIS MCP overlay tools for flood, shoreline, wetland, slope, and service-district screening."]
    if len(rows) > 1:
        notes.insert(0, "Parcel has multiple zoning overlaps; primary zone may not control every part of the parcel.")
    return {"parcel_id": parcel_id, "zoning_overlaps": rows, "shoreline": None, "floodplain": None, "critical_area": None, "historic_district": None, "airport_overlay": None, "notes": notes, "source": "OpenSkagit parcel_zoning"}


def get_development_standards(jurisdiction: str, zone_code: str) -> dict[str, Any]:
    jurisdiction = normalize_jurisdiction(jurisdiction)
    zone_code = normalize_zone_code(zone_code)
    matches = search_zoning_code(jurisdiction, f"{zone_code} setbacks height lot size density parking", limit=5)["matches"]
    return {"jurisdiction": jurisdiction, "zone_code": zone_code, "minimum_lot_size": None, "front_setback": None, "side_setback": None, "rear_setback": None, "max_height": None, "density": None, "parking_reference": None, "source_matches": matches, "notes": "Structured development-standard extraction is not complete; source matches are provided for grounded review."}


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
            return []
        raise


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
    return max(scored, key=lambda item: item[1]) if scored else None


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
        section_rows = list(
            ZoningCodeSection.objects.filter(jurisdiction__key=jurisdiction)
            .only("chapter_title", "section", "heading", "text", "source_url")[:5000]
        )
    except Exception:
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
        rules = list(rules)
    except Exception:
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
