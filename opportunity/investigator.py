"""Bounded, deterministic investigation of existing opportunity-search rows.

This module deliberately does not generate SQL or run an open-ended agent loop.
It turns a normal OpportunitySearch result set into a small, sourced research
shortlist using fixed hypotheses and optional parcel-detail enrichment.
"""

from __future__ import annotations

import re
import math
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable


MAX_POOL = 50
DEFAULT_DEEP_LIMIT = 10
DEFAULT_RESULT_LIMIT = 8

HYPOTHESES = {
    "solvable_constraint": "Solvable constraint",
    "underutilized_improvement": "Underutilized improvement",
    "additional_use_potential": "Additional land-use or subdivision potential",
    "long_held_property": "Long-held or infrequently transferred property",
    "distress_or_complexity": "Distress or property complexity",
    "low_capital_structure": "Low-capital structure candidate",
}

PUBLIC_OR_CIVIC_CODES = {"0", "450", "480", "670", "680", "760", "930", "970"}
EXEMPT_OR_COMMON_AREA_CODES = {"0", "140", "500", "970"}
PUBLIC_SCREENING_TERMS = (
    "PARKS",
    "PUBLIC",
    "SCHOOL",
    "CHURCH",
    "CEMETERY",
    "MOORAGE",
    "COMMON AREA",
    "RIGHT OF WAY",
    "COUNTY",
    "STATE LAND",
    "PORT OF",
)


def run_investigation(
    prompt: str,
    rows: list[dict[str, Any]],
    *,
    options: dict[str, Any] | None = None,
    deep_lookup: Callable[[str], dict[str, Any] | None] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate a bounded candidate pool and return a JSON-safe report."""

    options = _normalize_options(options)
    now = now or datetime.now(timezone.utc)
    candidates = _dedupe_rows(rows)[:MAX_POOL]
    deep_limit = options["max_candidates"]
    investigated: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    lookup_errors: list[str] = []

    for row in candidates[:deep_limit]:
        parcel_number = str(row.get("parcel_number") or "").strip().upper()
        detail: dict[str, Any] = {}
        if deep_lookup and parcel_number:
            try:
                lookup_result = deep_lookup(parcel_number)
                if lookup_result is None:
                    detail = {}
                elif isinstance(lookup_result, dict):
                    detail = lookup_result
                else:
                    lookup_errors.append(f"{parcel_number}: invalid parcel detail payload ({type(lookup_result).__name__})")
            except Exception as exc:  # one stale/bad parcel must not stop the pass
                lookup_errors.append(f"{parcel_number}: {type(exc).__name__}: {str(exc)[:180]}")
                detail = {}
        result = _evaluate_candidate(row, detail, options, prompt)
        if result["verdict"] == "worth_human_review":
            investigated.append(result)
        else:
            rejected.append(result)

    investigated.sort(key=lambda item: (-item["final_score"], -item.get("source_score", 0), item["parcel_number"]))
    for rank, item in enumerate(investigated[:DEFAULT_RESULT_LIMIT], start=1):
        item["rank"] = rank
    rejected.sort(key=lambda item: (-item["risk_score"], item["parcel_number"]))

    source_ids = {source.get("source_id") for item in investigated + rejected for source in item.get("sources", [])}
    warnings = [
        "This is a screening report, not a permit, appraisal, legal, financing, or entitlement determination.",
        f"The broad search supplied {len(candidates)} deduplicated candidates; only {min(len(candidates), deep_limit)} received deep review.",
    ]
    if lookup_errors:
        warnings.append(f"{len(lookup_errors)} parcel detail lookups failed; affected candidates may have incomplete evidence.")
    if not candidates:
        warnings.append("The existing broad search returned no candidates to investigate.")

    return _json_safe({
        "goal": str(prompt or "").strip(),
        "options": options,
        "hypotheses": [{"key": key, "label": HYPOTHESES[key]} for key in options["hypotheses"]],
        "candidate_count": len(candidates),
        "investigated_count": min(len(candidates), deep_limit),
        "result_count": len(investigated[:DEFAULT_RESULT_LIMIT]),
        "ranked_candidates": investigated[:DEFAULT_RESULT_LIMIT],
        "rejected_candidates": rejected[:20],
        "global_warnings": warnings,
        "lookup_errors": lookup_errors[:20],
        "sources": [{"source_id": source_id} for source_id in sorted(source_ids) if source_id],
        "generated_at": now.isoformat(),
    })


def screening_rejection(data: dict[str, Any]) -> str:
    """Return a hard screening reason for parcels unsuitable for this MVP."""

    land_use = str(data.get("land_use") or data.get("current_use") or "")
    code = str(data.get("land_use_code") or _land_use_code(land_use)).strip()
    text = " ".join(
        str(data.get(key) or "")
        for key in ("land_use", "current_use", "exemptions", "neighborhood_code", "zoning", "zone_name", "waza_general")
    ).upper()
    exemptions = str(data.get("exemptions") or "").strip().upper()
    if exemptions and exemptions not in {"NONE", "NO", "N/A", "NA", "NULL"}:
        return f"Assessor exemption signal: {exemptions}."
    if code in PUBLIC_OR_CIVIC_CODES or code in EXEMPT_OR_COMMON_AREA_CODES:
        return f"Land-use code {code} is public, civic, exempt, or common-area use."
    if any(term in text for term in PUBLIC_SCREENING_TERMS) or "COMAREA" in text or "EXEMPT" in text:
        return "The parcel record describes public, civic, common-area, or otherwise exempt land."
    values = [_number(data.get(key)) for key in ("assessed_value", "land_value", "building_value")]
    if all(value is not None for value in values) and all(value <= 0 for value in values):
        return "The parcel has no positive assessed, land, or building value in the available record."
    return ""


def _normalize_options(options: dict[str, Any] | None) -> dict[str, Any]:
    options = options if isinstance(options, dict) else {}
    try:
        max_candidates = int(options.get("max_candidates") or DEFAULT_DEEP_LIMIT)
    except (TypeError, ValueError):
        max_candidates = DEFAULT_DEEP_LIMIT
    max_candidates = max(5, min(max_candidates, 20))
    capital = str(options.get("capital_preference") or "not_specified").strip().lower()
    if capital not in {"very_limited", "moderate", "not_specified"}:
        capital = "not_specified"
    strategies = str(options.get("preferred_strategies") or "").strip()[:500]
    hypotheses = options.get("hypotheses")
    if not isinstance(hypotheses, list) or not hypotheses:
        hypotheses = list(HYPOTHESES)
    hypotheses = [key for key in hypotheses if key in HYPOTHESES]
    if not hypotheses:
        hypotheses = list(HYPOTHESES)
    return {
        "max_candidates": max_candidates,
        "capital_preference": capital,
        "preferred_strategies": strategies,
        "hypotheses": hypotheses[:6],
    }


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        parcel = str(row.get("parcel_number") or "").strip().upper()
        if not parcel or parcel in seen:
            continue
        seen.add(parcel)
        result.append(row)
    return sorted(result, key=lambda row: (-(_number(row.get("score")) or 0), str(row.get("parcel_number") or "")))


def _evaluate_candidate(row: dict[str, Any], detail: dict[str, Any], options: dict[str, Any], prompt: str) -> dict[str, Any]:
    data = _combined_data(row, detail)
    parcel_number = str(data.get("parcel_number") or row.get("parcel_number") or "").strip().upper()
    screening_reason = screening_rejection(data)
    hypotheses = []
    for key in options["hypotheses"]:
        hypotheses.append(_evaluate_hypothesis(key, data, detail, options))

    supported = [item for item in hypotheses if item["status"] == "supported"]
    weak = [item for item in hypotheses if item["status"] == "weakly_supported"]
    contradictions = [item for item in hypotheses if item["status"] == "contradicted"]
    evidence_count = sum(len(item["evidence"]) for item in hypotheses)
    risk_flags = _list_values(data.get("risk_flags"))
    risk_score = min(4, len(contradictions) + min(2, len(risk_flags)))
    if screening_reason:
        risk_score = 4
    information_edge = min(4, len(supported) + (1 if any(item["next_checks"] for item in hypotheses) else 0))
    low_capital_fit = min(4, len([item for item in hypotheses if item["key"] in {"long_held_property", "distress_or_complexity", "low_capital_structure"} and item["status"] in {"supported", "weakly_supported"}]) + (1 if options["capital_preference"] == "very_limited" else 0))
    upside = min(4, len([item for item in hypotheses if item["key"] in {"underutilized_improvement", "additional_use_potential", "low_capital_structure"} and item["status"] in {"supported", "weakly_supported"}]))
    evidence_quality = min(4, len({source.get("source_id") for item in hypotheses for source in item.get("sources", [])}))
    final_score = information_edge + low_capital_fit + upside + evidence_quality - risk_score
    if screening_reason:
        verdict = "rejected"
    elif contradictions and not supported and final_score <= 1:
        verdict = "rejected"
    elif supported or weak:
        verdict = "worth_human_review"
    else:
        verdict = "insufficient_evidence"

    structures = _possible_structures(hypotheses, options)
    why_survived = _dedupe_text([evidence for item in hypotheses for evidence in item["evidence"]])[:5]
    why_might_fail = _dedupe_text([reason for item in hypotheses for reason in item["contradictions"] + item["next_checks"]])[:5]
    if screening_reason:
        why_might_fail.insert(0, screening_reason)
        why_might_fail = _dedupe_text(why_might_fail)
    if not why_might_fail:
        why_might_fail = ["Key feasibility and deal terms still require human verification."]

    return {
        "parcel_number": parcel_number,
        "rank": None,
        "verdict": verdict,
        "final_score": final_score,
        "source_score": _number(row.get("score")) or 0,
        "risk_score": risk_score,
        "scores": {
            "information_edge": information_edge,
            "low_capital_fit": low_capital_fit,
            "upside": upside,
            "evidence_quality": evidence_quality,
            "risk": risk_score,
        },
        "property": _property_snapshot(data),
        "hypotheses": hypotheses,
        "why_it_survived": why_survived,
        "why_it_might_fail": why_might_fail,
        "possible_structures": structures,
        "next_human_action": "Verify the highest-risk unknown before spending money or making an offer.",
        "sources": _sources(row, detail),
        "prompt_context": str(prompt or "")[:300],
    }


def _evaluate_hypothesis(key: str, data: dict[str, Any], detail: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    evidence: list[str] = []
    contradictions: list[str] = []
    next_checks: list[str] = []
    sources = _sources(data, detail)
    acres = _number(data.get("acres"))
    building = _number(data.get("building_value")) or _number(data.get("assessor_building_value")) or 0
    land = _number(data.get("land_value")) or _number(data.get("improved_land_value")) or 0
    year = _number(data.get("primary_actual_year_built")) or _number(data.get("oldest_actual_year_built")) or _number(data.get("year_built"))
    years_since_sale = _number(data.get("years_since_last_valid_sale"))
    land_use = str(data.get("land_use") or data.get("current_use") or "")
    code = str(data.get("land_use_code") or _land_use_code(land_use))
    zoning = " ".join(str(data.get(key) or "") for key in ("zoning", "zone_name", "waza_general", "waza_specific")).lower()
    risk_flags = " ".join(_list_values(data.get("risk_flags"))).lower()
    publicish = code in {"140", "500", "680", "970"} or any(term in land_use.lower() for term in ("public", "school", "church", "cemetery", "moorage", "condo"))
    gis_context = detail.get("gis_context") if isinstance(detail.get("gis_context"), dict) else {}
    dossier = detail.get("dossier") if isinstance(detail.get("dossier"), dict) else {}

    if key == "solvable_constraint":
        if any(term in risk_flags for term in ("utility", "zoning", "geometry", "resource", "frontage")):
            evidence.append("The current record contains a constraint or missing-evidence signal worth verifying.")
        if gis_context:
            evidence.append("Parcel-level GIS context is available for a targeted constraint review.")
        if publicish:
            contradictions.append("The current use appears public, civic, condominium, or moorage-related.")
        next_checks.extend(["Confirm access, utility service, and the controlling zoning profile.", "Check whether mapped environmental constraints materially affect the usable area."])
    elif key == "underutilized_improvement":
        ratio = land / building if building > 0 else 0
        if building > 0 and (ratio >= 2.5 or building <= 100000):
            evidence.append(f"Land value is approximately {ratio:.1f}x building value." if ratio else "Building value is low relative to the parcel context.")
        if year and year <= 1980:
            evidence.append(f"The primary improvement appears to date from about {int(year)}.")
        if any(term in risk_flags for term in ("low", "fair", "improvement")):
            evidence.append("The record includes an older, lower-condition, or otherwise notable improvement signal.")
        if building <= 10000 and not dossier:
            contradictions.append("The parcel appears vacant or has little improvement evidence, so this is not an improvement-reuse lead.")
        next_checks.extend(["Inspect improvement records and current physical condition.", "Compare land value, replacement cost, and plausible reuse before treating this as a teardown or conversion idea."])
    elif key == "additional_use_potential":
        if acres and acres >= 0.5:
            evidence.append(f"The parcel is {acres:g} acres, large enough to justify a land-use or layout review.")
        if any(term in zoning for term in ("residential", "lir", "mr", "rur", "rvr", "city")):
            evidence.append("The zoning context contains a residential or incorporated-area signal.")
        if data.get("nearby_median_acres") and acres and acres >= _number(data.get("nearby_median_acres")) * 2.5:
            evidence.append("Acreage is materially larger than the nearby median signal.")
        if data.get("estimated_lot_count"):
            evidence.append(f"The existing search supplied a theoretical comparison of about {data['estimated_lot_count']} median-size lots.")
        if publicish:
            contradictions.append("Current use appears outside the intended private development screen.")
        next_checks.extend(["Verify frontage, access, utilities, minimum lot rules, and critical-area constraints.", "Use the zoning profile or planning source before discussing subdivision or additional use."])
    elif key == "long_held_property":
        if years_since_sale is not None and years_since_sale >= 20:
            evidence.append(f"No valid sale has been recorded for approximately {int(years_since_sale)} years.")
        elif years_since_sale is not None and years_since_sale >= 10:
            evidence.append(f"The parcel appears to have gone at least {int(years_since_sale)} years without a valid sale.")
        elif detail.get("sales") and len(detail["sales"]) <= 1:
            evidence.append("Only limited transfer history is visible in the available record.")
        else:
            contradictions.append("The available sale history does not show a strong long-hold signal.")
        next_checks.append("Verify transfer history and treat long ownership only as a possible conversation signal, not seller motivation.")
    elif key == "distress_or_complexity":
        tax_pressure = detail.get("tax_pressure") or data.get("tax_pressure")
        if tax_pressure:
            evidence.append("Tax-pressure information is present in the parcel record.")
        if len(dossier.get("land_segments", detail.get("land_segments", [])) or []) > 1:
            evidence.append("The parcel has multiple land segments requiring interpretation.")
        if len(dossier.get("improvements", detail.get("improvements", [])) or []) > 1:
            evidence.append("The parcel has multiple improvement records requiring interpretation.")
        if not evidence:
            contradictions.append("No clear distress or unusual-record signal was found in the available evidence.")
        next_checks.append("Confirm the source date, payment status, and whether the complexity is actionable rather than merely administrative.")
    elif key == "low_capital_structure":
        if options["capital_preference"] == "very_limited":
            evidence.append("The stated capital preference favors time, information, or deal structure over immediate cash deployment.")
        if any(item in zoning for item in ("residential", "lir", "mr", "rur", "rvr")) or acres and acres >= 0.5:
            evidence.append("The parcel has enough land-use or physical context to justify a feasibility conversation.")
        if publicish:
            contradictions.append("The current use may make the suggested private deal structures inappropriate.")
        next_checks.append("Treat any option, seller-financing, partnership, or feasibility-period idea as a conversation hypothesis requiring owner and professional review.")

    if len(evidence) >= 2 and not contradictions:
        status = "supported"
    elif evidence:
        status = "weakly_supported"
    elif contradictions:
        status = "contradicted"
    else:
        status = "insufficient_evidence"
    return {
        "key": key,
        "name": HYPOTHESES[key],
        "status": status,
        "evidence": _dedupe_text(evidence),
        "contradictions": _dedupe_text(contradictions),
        "next_checks": _dedupe_text(next_checks),
        "sources": sources,
    }


def _combined_data(row: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    parcel_data = row.get("parcel_data") if isinstance(row.get("parcel_data"), dict) else {}
    data = {**parcel_data, **row}
    if isinstance(detail, dict) and detail:
        data.update({key: value for key, value in detail.items() if value not in (None, "")})
        for key in ("parcel_number", "acres", "land_use", "land_use_code", "zoning", "zone_name", "waza_general", "assessed_value", "building_value", "land_value", "risk_flags", "utilities"):
            if detail.get(key) not in (None, ""):
                data[key] = detail[key]
    return data


def _property_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    return {key: data.get(key) for key in ("location", "city", "acres", "assessed_value", "building_value", "land_value", "land_use_code", "land_use", "current_use", "exemptions", "neighborhood_code", "zoning", "zone_name", "waza_general", "utilities") if data.get(key) not in (None, "")}


def _possible_structures(hypotheses: list[dict[str, Any]], options: dict[str, Any]) -> list[str]:
    keys = {item["key"] for item in hypotheses if item["status"] in {"supported", "weakly_supported"}}
    structures = []
    if keys & {"additional_use_potential", "solvable_constraint"}:
        structures.append("Long feasibility period tied to zoning, access, utility, and environmental verification.")
    if keys & {"underutilized_improvement", "long_held_property"}:
        structures.append("Option agreement or seller-financing discussion, subject to owner willingness and professional review.")
    if keys & {"additional_use_potential", "underutilized_improvement"}:
        structures.append("Partnership or entitlement-work contribution where time and execution substitute for part of the cash requirement.")
    if not structures and options["capital_preference"] == "very_limited":
        structures.append("Information-first approach: verify the constraint before proposing a transaction structure.")
    return structures[:3]


def _sources(row: dict[str, Any], detail: dict[str, Any]) -> list[dict[str, str]]:
    sources = [{
        "source_id": "opportunity_search",
        "source_name": "Existing /opportunity broad search",
        "scope": "broad_candidate_screen",
    }]
    if detail:
        sources.append({
            "source_id": "openskagit_postgis",
            "source_name": "OpenSkagit PostGIS parcel and assessor records",
            "scope": "parcel_detail",
        })
        local_gis = detail.get("gis_context") if isinstance(detail.get("gis_context"), dict) else {}
        if local_gis:
            sources.append({
                "source_id": "openskagit_postgis",
                "source_name": "OpenSkagit PostGIS parcel GIS context",
                "scope": "parcel_gis_context",
            })
        live_gis = detail.get("live_gis_context") if isinstance(detail.get("live_gis_context"), dict) else {}
        if live_gis:
            sources.append({
                "source_id": "openskagit_gis_registry",
                "source_name": "OpenSkagit GIS registry / live ArcGIS overlays",
                "scope": "live_parcel_gis_context",
            })
    return sources


def _land_use_code(value: Any) -> str:
    match = re.search(r"\((\d+)\)", str(value or ""))
    return match.group(1) if match else ""


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _list_values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if value not in (None, "") else []


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        value = str(value or "").strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _json_safe(value: Any) -> Any:
    """Convert report values to types accepted by strict JSON encoders."""

    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
