"""Deterministic, SVG-first property visual assets for the public MCP."""

from __future__ import annotations

import hashlib
import html
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connection

from .cloudinary_service import CloudinaryError, upload_generated_asset, transformed_url

logger = logging.getLogger(__name__)

ASPECTS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080)}
MAP_MODES = {"subject", "neighborhood", "comparables", "sales", "land", "aerial", "context"}
CARD_MODES = {"subject", "sale", "assessment", "land", "improvements"}
INFOGRAPHIC_TYPES = {
    "big_number",
    "bar",
    "horizontal_bar",
    "range",
    "before_after",
    "value_breakdown",
    "timeline",
    "property_diagram",
}
STYLE_VERSION = "home-value-brief-v1"
BRAND_NAME = "HOME VALUE BRIEF"

COLORS = {
    "ink": "#102a43",
    "muted": "#627d98",
    "paper": "#f7f9fb",
    "accent": "#e76f51",
    "gold": "#e9c46a",
    "blue": "#2a9d8f",
    "line": "#d9e2ec",
    "white": "#ffffff",
}


def _esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(re.sub(r"[^0-9.-]", "", str(value)))
    except (TypeError, ValueError):
        return None


def _money(value: Any) -> str | None:
    number = _num(value)
    return f"${number:,.0f}" if number is not None else None


def _fmt(value: Any, field: str = "") -> str:
    if value is None or value == "":
        return ""
    if "price" in field or "value" in field:
        return _money(value) or str(value)
    if field in {"acres", "lot_size"}:
        number = _num(value)
        return f"{number:,.2f} ac" if number is not None else str(value)
    if field in {"living_area", "square_feet"}:
        number = _num(value)
        return f"{number:,.0f} sq ft" if number is not None else str(value)
    return f"{value:,}" if isinstance(value, (int, float)) else str(value)


def _text(
    x: float,
    y: float,
    value: Any,
    size: int = 28,
    *,
    fill: str | None = None,
    weight: str = "400",
    anchor: str = "start",
) -> str:
    return f'<text x="{x}" y="{y}" font-family="Inter,Arial,sans-serif" font-size="{size}px" font-weight="{weight}" fill="{fill or COLORS["ink"]}" text-anchor="{anchor}">{_esc(value)}</text>'


def _svg(width: int, height: int, title: str, body: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{_esc(title)}"><rect width="100%" height="100%" fill="{COLORS["paper"]}"/>{body}</svg>'


def _header(width: int, height: int, title: str, subtitle: str = "") -> str:
    portrait = height > width
    title_fill = COLORS["white"] if portrait else COLORS["ink"]
    subtitle_fill = "#c7d7e3" if portrait else COLORS["muted"]
    line_color = "#b9cddd" if portrait else COLORS["line"]
    title_lines = [title]
    if portrait:
        title_lines = []
        current = ""
        for word in title.split():
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > 24:
                title_lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            title_lines.append(current)
    title_size = 60 if portrait else 52
    title_nodes = "".join(_text(72, 158 + index * 64, line, title_size, fill=title_fill, weight="800") for index, line in enumerate(title_lines))
    subtitle_y = 202 if not portrait else 158 + len(title_lines) * 64 + 28
    rule_y = subtitle_y + 28
    return (
        f'<rect x="72" y="54" width="34" height="34" rx="10" fill="{COLORS["accent"]}"/>'
        + _text(89, 79, "H", 21, fill=COLORS["white"], weight="700", anchor="middle")
        + _text(122, 79, BRAND_NAME, 20, fill=COLORS["accent"] if not portrait else COLORS["white"], weight="700")
        + title_nodes
        + (_text(72, subtitle_y, subtitle, 25, fill=subtitle_fill) if subtitle else "")
        + f'<path d="M72 {rule_y} H{width - 72}" stroke="{line_color}" stroke-width="3" opacity=".9"/>'
    )


def _vertical_infographic_backdrop(width: int, height: int) -> str:
    """Create a full-bleed editorial field behind portrait graphics."""
    if height <= width:
        return ""
    lines = "".join(
        f'<path d="M72 {y} H{width - 72}" stroke="#dbe7e5" stroke-width="2" opacity=".7"/>'
        for y in range(300, height - 150, 150)
    )
    return (
        f'<rect width="100%" height="100%" fill="#eef5f3"/>'
        f'<path d="M0 0 H{width} V255 C{width * .72} 350 {width * .45} 210 0 330 Z" fill="#102a43"/>'
        f'<circle cx="{width - 95}" cy="170" r="170" fill="#2a9d8f" opacity=".75"/>'
        f'<circle cx="{width - 180}" cy="95" r="62" fill="#e9c46a" opacity=".9"/>'
        f'<path d="M0 {height - 380} C260 {height - 500} 700 {height - 250} {width} {height - 420} V{height} H0 Z" fill="#102a43"/>'
        f'<circle cx="120" cy="{height - 110}" r="190" fill="#2a9d8f" opacity=".55"/>'
        f'<circle cx="{width - 75}" cy="{height - 150}" r="105" fill="#e76f51" opacity=".75"/>'
        f'<rect x="72" y="{height - 104}" width="34" height="34" rx="10" fill="#e76f51"/>'
        + _text(89, height - 79, "H", 21, fill=COLORS["white"], weight="700", anchor="middle")
        + _text(122, height - 79, BRAND_NAME, 20, fill=COLORS["white"], weight="700")
        + lines
    )


def _property_rows(row: dict[str, Any]) -> list[tuple[str, str, str]]:
    fields = [
        ("Address", "address"),
        ("Sale price", "sale_price"),
        ("Sale date", "sale_date"),
        ("Assessed value", "assessed_value"),
        ("Living area", "living_area"),
        ("Lot", "acres"),
        ("Year built", "year_built"),
        ("Bedrooms", "bedrooms"),
        ("Bathrooms", "bathrooms"),
        ("Garage", "garage"),
        ("Shop / outbuilding", "shop"),
    ]
    return [
        (label, _fmt(row.get(field), field), field) for label, field in fields if row.get(field) not in (None, "", [])
    ]


def _source_snapshot(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _query_properties(ids: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    if not ids:
        return [], []
    placeholders = ",".join(["%s"] * len(ids))
    sql = f"""
        SELECT p.parcel_number, concat_ws(' ', p.situs_street_number, p.situs_street_name) AS address,
               p.situs_city_state_zip, p.assessed_value, p.total_market_value, p.acres,
               p.sale_date, p.sale_price, ST_X(ST_PointOnSurface(g.geometry)) AS longitude,
               ST_Y(ST_PointOnSurface(g.geometry)) AS latitude,
               COALESCE((SELECT json_agg(json_build_object('type', i.imprv_det_type_description,
                 'class', i.imprv_det_class_description, 'living_area', i.living_area_num))
                 FROM improvements i WHERE i.parcelnumber = p.parcel_number), '[]') AS improvements
        FROM skagit_parcels p LEFT JOIN gis_skagit_parcels g ON g.parcel_id = p.parcel_number
        WHERE p.parcel_number IN ({placeholders}) AND p.inactive_date IS NULL
        ORDER BY array_position(ARRAY[{placeholders}], p.parcel_number)
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [*ids, *ids])
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    unique_rows: list[dict[str, Any]] = []
    found: set[str] = set()
    for row in rows:
        if row["parcel_number"] not in found:
            unique_rows.append(row)
            found.add(row["parcel_number"])
    return unique_rows, [
        f"Property {parcel_id} was not found in the active parcel store." for parcel_id in ids if parcel_id not in found
    ]


def _store(
    tool: str, payload: dict[str, Any], svg: str, width: int, height: int, source_ids: list[str], warnings: list[str]
) -> dict[str, Any]:
    digest = hashlib.sha256(
        json.dumps({"tool": tool, "payload": payload, "style": STYLE_VERSION}, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    relative = f"visual_assets/{tool}_{digest}_{width}x{height}.svg"
    if not default_storage.exists(relative):
        default_storage.save(relative, ContentFile(svg.encode("utf-8")))
    asset_type = tool.removeprefix("generate_")
    aspect_ratio = next((key for key, size in ASPECTS.items() if size == (width, height)), None)
    result = {
        "success": True,
        "tool_name": tool,
        "asset_id": f"visual_{digest}",
        "asset_url": default_storage.url(relative),
        "asset_type": asset_type,
        "format": "svg",
        "width": width,
        "height": height,
        "aspect_ratio": aspect_ratio,
        "generated_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_property_ids": source_ids,
        "source_dataset": "openskagit_postgis",
        "fields_used": payload.get("fields_used", []),
        "warnings": list(warnings),
        "summary": payload.get("summary", "Generated editorial visual asset."),
        "storage_reference": relative,
        "visual_style_version": STYLE_VERSION,
        "source_hash": digest,
    }
    metadata = {
        "asset_type": asset_type,
        "source_property_ids": ",".join(source_ids),
        "aspect_ratio": aspect_ratio or "",
        "width": str(width),
        "height": str(height),
        "visual_style_version": STYLE_VERSION,
        "source_hash": digest,
    }
    try:
        cloud = upload_generated_asset(
            svg.encode("utf-8"), asset_type=asset_type, digest=digest, source_property_ids=source_ids, metadata=metadata
        )
        result.update(
            {
                "cloudinary_public_id": cloud["cloudinary_public_id"],
                "secure_url": cloud["secure_url"],
                "source_url": cloud.get("source_url"),
                "svg_url": cloud["secure_url"],
                "cached": cloud["cached"],
            }
        )
        preset = {
            "16:9": "youtube_landscape",
            "9:16": "vertical_video",
            "4:5": "instagram_portrait",
            "1:1": "square_social",
        }[aspect_ratio]
        result["png_url"] = transformed_url(cloud["cloudinary_public_id"], preset, fmt="png")
    except CloudinaryError as exc:
        result["success"] = False
        result["cloudinary_error"] = str(exc)
        result["warnings"].append("Local visual was generated, but Cloudinary storage failed.")
    logger.info(
        "visual_asset_generated",
        extra={
            "asset_type": asset_type,
            "asset_id": result["asset_id"],
            "cached": result.get("cached", False),
            "cloudinary_public_id": result.get("cloudinary_public_id"),
        },
    )
    return result


def generate_property_card(
    property_id: str,
    mode: str = "subject",
    aspect_ratio: str = "16:9",
    title: str = "",
    subtitle: str = "",
    highlight_fields: list[str] | None = None,
    requested_fields: list[str] | None = None,
    identity_mode: str = "subject",
    presentation_mode: str = "standalone_social",
) -> dict[str, Any]:
    if presentation_mode not in {"standalone_social", "video_scene"}:
        raise ValueError("presentation_mode must be 'standalone_social' or 'video_scene'.")
    if identity_mode not in {"subject", "anonymized"}:
        raise ValueError("identity_mode must be 'subject' or 'anonymized'.")
    if mode not in CARD_MODES:
        raise ValueError(f"Unsupported card mode {mode!r}. Use one of: {', '.join(sorted(CARD_MODES))}.")
    width, height = ASPECTS.get(aspect_ratio, (0, 0))
    if not width:
        raise ValueError(f"Unsupported aspect ratio {aspect_ratio!r}. Use one of: {', '.join(ASPECTS)}.")
    rows, warnings = _query_properties([property_id.upper()])
    if not rows:
        raise ValueError(f"Property {property_id!r} could not be resolved.")
    row = rows[0]
    fields = _property_rows(row)
    if identity_mode == "anonymized":
        fields = [item for item in fields if item[2] not in {"address", "situs_city_state_zip"}]
    if requested_fields:
        fields = [item for item in fields if item[2] in requested_fields]
    title = title or ("Sale snapshot" if mode == "sale" else "Property snapshot")
    display_name = "Generalized residential example" if identity_mode == "anonymized" else (row.get("address") or row["parcel_number"])
    body = _header(width, height, title, subtitle) + _text(72, 280, display_name, 34, weight="700")
    if identity_mode != "anonymized" and row.get("situs_city_state_zip"):
        body += _text(72, 318, row["situs_city_state_zip"], 22, fill=COLORS["muted"])
    top = 390
    cols = 1 if height > width else 2
    for idx, (label, value, field) in enumerate(fields):
        col, line = idx % cols, idx // cols
        x = 72 + col * (width // cols)
        y = top + line * 105
        if highlight_fields and field in highlight_fields:
            body += f'<rect x="{x - 18}" y="{y - 48}" width="{width // cols - 45}" height="82" rx="12" fill="{COLORS["gold"]}" opacity=".35"/>'
        body += _text(x, y, label.upper(), 17, fill=COLORS["muted"], weight="700") + _text(
            x, y + 38, value, 31, weight="700"
        )
    payload = {
        "fields_used": [field for _, _, field in fields],
        "summary": f"{title} for a generalized residential example." if identity_mode == "anonymized" else f"{title} for {row['parcel_number']}.",
        "row": {key: value for key, value in row.items() if key not in {"parcel_number", "address", "situs_city_state_zip"}} if identity_mode == "anonymized" else row,
        "identity_mode": identity_mode,
    }
    return _store(
        "generate_property_card",
        payload,
        _svg(width, height, title, body),
        width,
        height,
        [row["parcel_number"]],
        warnings,
    )


def generate_comparison(
    subject_property_id: str,
    comparison_property_ids: list[str],
    requested_fields: list[str] | None = None,
    aspect_ratio: str = "16:9",
    title: str = "Property comparison",
    subtitle: str = "",
    highlight_fields: list[str] | None = None,
    custom_labels: list[str] | None = None,
    presentation_mode: str = "standalone_social",
) -> dict[str, Any]:
    if presentation_mode not in {"standalone_social", "video_scene"}:
        raise ValueError("presentation_mode must be 'standalone_social' or 'video_scene'.")
    ids = [subject_property_id, *(comparison_property_ids or [])]
    if not 2 <= len(ids) <= 4:
        raise ValueError("Comparison requires 2 to 4 properties.")
    if aspect_ratio not in ASPECTS:
        raise ValueError(f"Unsupported aspect ratio {aspect_ratio!r}. Use one of: {', '.join(ASPECTS)}.")
    width, height = ASPECTS[aspect_ratio]
    rows, warnings = _query_properties([x.upper() for x in ids])
    if not rows or rows[0]["parcel_number"] != ids[0].upper():
        raise ValueError("The subject property could not be resolved.")
    by_id = {row["parcel_number"]: row for row in rows}
    ordered = [by_id[x.upper()] for x in ids if x.upper() in by_id]
    if len(ordered) < 2:
        raise ValueError("Fewer than two supplied properties could be resolved.")
    available = {field for row in ordered for _, _, field in _property_rows(row)}
    fields = requested_fields or ["sale_price", "sale_date", "living_area", "acres", "year_built", "garage", "shop"]
    fields = [field for field in fields if field in available]
    if requested_fields and len(fields) < len(requested_fields):
        warnings.append("Unavailable requested fields were omitted from the comparison.")
    cols = len(ordered)
    colw = (width - 144) // cols
    body = _header(width, height, title, subtitle)
    for idx, row in enumerate(ordered):
        x = 72 + idx * colw
        label = (
            custom_labels[idx]
            if custom_labels and idx < len(custom_labels)
            else ("SUBJECT" if idx == 0 else f"COMP {idx}")
        )
        body += (
            f'<rect x="{x}" y="270" width="{colw - 16}" height="{height - 330}" rx="16" fill="{COLORS["white"]}" stroke="{COLORS["accent"] if idx == 0 else COLORS["line"]}" stroke-width="{4 if idx == 0 else 2}"/>'
            + _text(x + 22, 315, label, 18, fill=COLORS["accent"] if idx == 0 else COLORS["muted"], weight="700")
            + _text(x + 22, 360, row["parcel_number"], 23, weight="700")
        )
        for n, field in enumerate(fields):
            value = next((v for _, v, f in _property_rows(row) if f == field), "Unavailable")
            y = 425 + n * 82
            if highlight_fields and field in highlight_fields:
                body += f'<rect x="{x + 12}" y="{y - 30}" width="{colw - 40}" height="65" rx="8" fill="{COLORS["gold"]}" opacity=".5"/>'
            body += _text(x + 22, y, field.replace("_", " ").upper(), 14, fill=COLORS["muted"], weight="700") + _text(
                x + 22, y + 28, value, 24, weight="700"
            )
    payload = {
        "fields_used": fields,
        "summary": f"Comparison of {len(ordered)} properties.",
        "ids": [r["parcel_number"] for r in ordered],
        "source_snapshot": _source_snapshot(ordered),
    }
    return _store(
        "generate_comparison", payload, _svg(width, height, title, body), width, height, payload["ids"], warnings
    )


def generate_infographic(
    infographic_type: str,
    title: str,
    values: list[Any] | None = None,
    labels: list[str] | None = None,
    subtitle: str = "",
    units: str = "",
    aspect_ratio: str = "16:9",
    highlighted_items: list[str] | None = None,
    annotation: str = "",
    property_ids: list[str] | None = None,
    source_references: list[str] | None = None,
    presentation_mode: str = "standalone_social",
) -> dict[str, Any]:
    if presentation_mode not in {"standalone_social", "video_scene"}:
        raise ValueError("presentation_mode must be 'standalone_social' or 'video_scene'.")
    if infographic_type not in INFOGRAPHIC_TYPES:
        raise ValueError(f"Unsupported infographic type {infographic_type!r}.")
    if aspect_ratio not in ASPECTS:
        raise ValueError(f"Unsupported aspect ratio {aspect_ratio!r}. Use one of: {', '.join(ASPECTS)}.")
    if not title.strip():
        raise ValueError("Infographic title is required.")
    values, labels = list(values or []), list(labels or [])
    if infographic_type != "property_diagram" and not values:
        raise ValueError("Values are required for this infographic type.")
    if labels and len(labels) != len(values):
        raise ValueError("labels and values must have the same length.")
    if len(values) > 12:
        raise ValueError("At most 12 values can be displayed clearly.")
    width, height = ASPECTS[aspect_ratio]
    body = _vertical_infographic_backdrop(width, height) + _header(width, height, title, subtitle)
    labels = labels or [str(i + 1) for i in range(len(values))]
    if infographic_type == "big_number":
        body += _text(
            width / 2,
            height / 2 + 30,
            _fmt(values[0]),
            104 if width >= height else 82,
            fill=COLORS["accent"],
            weight="700",
            anchor="middle",
        ) + (_text(width / 2, height / 2 + 82, units, 28, fill=COLORS["muted"], anchor="middle") if units else "")
    elif infographic_type in {"bar", "horizontal_bar", "value_breakdown"}:
        maxv = max((_num(v) or 0 for v in values), default=1) or 1
        horizontal = infographic_type == "horizontal_bar" or height > width
        for i, (label, value) in enumerate(zip(labels, values)):
            n = _num(value) or 0
            selected = label in (highlighted_items or [])
            color = COLORS["accent"] if selected else COLORS["blue"]
            if horizontal:
                y = 390 + i * 125 if height > width else 300 + i * 75
                # Keep the bar and its value label inside the composition's
                # right inset. The old portrait calculation let the maximum
                # bar run to x=1200 on a 1080px canvas.
                bar_right = width - (210 if height > width else 430)
                bar_width = bar_right - 330
                bar = max(8, int(bar_width * n / maxv))
                label_x, bar_x = (90, 330) if height <= width else (90, 330)
                body += (
                    _text(label_x, y + 28, label, 24 if height > width else 22, weight="700")
                    + f'<rect x="{bar_x}" y="{y}" width="{bar}" height="54" rx="16" fill="{color}"/>'
                    + _text(min(bar_x + bar + 24, width - 160), y + 35, _fmt(value), 22, weight="700")
                )
            else:
                x = 100 + i * ((width - 200) // max(1, len(values)))
                bar = max(8, int((height - 500) * n / maxv))
                body += (
                    f'<rect x="{x}" y="{height - 250 - bar}" width="{min(100, (width - 250) // max(1, len(values)) - 20)}" height="{bar}" rx="8" fill="{color}"/>'
                    + _text(x, height - 210, label, 18, anchor="middle", weight="700")
                    + _text(x, height - 280 - bar, _fmt(value), 18, anchor="middle", weight="700")
                )
    elif infographic_type == "range" and len(values) >= 2:
        body += _text(
            width / 2, height / 2, f"{_fmt(values[0])} — {_fmt(values[-1])}", 64, anchor="middle", weight="700"
        )
    elif infographic_type in {"before_after", "timeline"}:
        for i, (label, value) in enumerate(zip(labels, values)):
            x = 140 + i * ((width - 280) // max(1, len(values)))
            body += _text(x, height / 2 - 30, label, 22, anchor="middle", weight="700") + _text(
                x, height / 2 + 35, _fmt(value), 34, anchor="middle", fill=COLORS["accent"], weight="700"
            )
    else:
        body += (
            _text(width / 2, height / 2 - 40, "SCHEMATIC", 20, anchor="middle", fill=COLORS["muted"], weight="700")
            + f'<rect x="{width * 0.25}" y="{height * 0.42}" width="{width * 0.5}" height="{height * 0.22}" rx="18" fill="{COLORS["gold"]}" stroke="{COLORS["ink"]}" stroke-width="4"/>'
            + _text(width / 2, height * 0.55, "Property components", 28, anchor="middle", weight="700")
        )
    if height > width and presentation_mode == "standalone_social":
        body += (
            f'<rect x="72" y="1060" width="{width - 144}" height="250" rx="28" fill="#ffffff" opacity=".92"/>'
            + _text(108, 1130, "READ THE RECORD IN PARTS", 22, fill=COLORS["accent"], weight="700")
            + _text(108, 1190, "SITE", 28, fill=COLORS["ink"], weight="700")
            + _text(108, 1235, "land component", 22, fill=COLORS["muted"])
            + _text(width / 2, 1190, "+", 34, fill=COLORS["accent"], weight="700", anchor="middle")
            + _text(width - 270, 1190, "STRUCTURES", 28, fill=COLORS["ink"], weight="700")
            + _text(width - 270, 1235, "building component", 22, fill=COLORS["muted"])
            + f'<path d="M108 1270 H{width - 108}" stroke="{COLORS["line"]}" stroke-width="3"/>'
            + _text(width / 2, 1305, "together, they form the assessment", 22, fill=COLORS["muted"], anchor="middle")
        )
    if annotation:
        body += _text(72, height - 70, annotation, 19, fill=COLORS["white"] if height > width else COLORS["muted"])
    payload = {
        "fields_used": source_references or [],
        "summary": f"{infographic_type.replace('_', ' ').title()} infographic.",
        "values": values,
        "labels": labels,
        "presentation_mode": presentation_mode,
    }
    return _store(
        "generate_infographic", payload, _svg(width, height, title, body), width, height, property_ids or [], []
    )


def generate_map(
    property_ids: list[str] | None = None,
    subject_property_id: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    mode: str = "subject",
    aspect_ratio: str = "16:9",
    title: str = "Property map",
    subtitle: str = "",
    highlighted_properties: list[str] | None = None,
    annotation: str = "",
    presentation_mode: str = "standalone_social",
) -> dict[str, Any]:
    if presentation_mode not in {"standalone_social", "video_scene"}:
        raise ValueError("presentation_mode must be 'standalone_social' or 'video_scene'.")
    if mode not in MAP_MODES:
        raise ValueError(f"Unsupported map mode {mode!r}. Use one of: {', '.join(sorted(MAP_MODES))}.")
    if aspect_ratio not in ASPECTS:
        raise ValueError(f"Unsupported aspect ratio {aspect_ratio!r}. Use one of: {', '.join(ASPECTS)}.")
    ids = list(
        dict.fromkeys(
            [x.upper() for x in ([subject_property_id] if subject_property_id else []) + (property_ids or []) if x]
        )
    )
    rows, warnings = _query_properties(ids)
    subject = (
        rows[0] if subject_property_id and rows and rows[0]["parcel_number"] == subject_property_id.upper() else None
    )
    if subject_property_id and not subject:
        raise ValueError("The subject property could not be located.")
    points = [
        (r["longitude"], r["latitude"], r["parcel_number"])
        for r in rows
        if r.get("longitude") is not None and r.get("latitude") is not None
    ]
    if latitude is not None and longitude is not None:
        points.insert(0, (float(longitude), float(latitude), subject["parcel_number"] if subject else "COORDINATE"))
    if not points and latitude is None:
        raise ValueError("Map requires a resolvable property geometry or latitude/longitude.")
    if mode == "aerial":
        warnings.append("No authorized aerial basemap is configured; generated a parcel-location schematic.")
    width, height = ASPECTS[aspect_ratio]
    body = _header(width, height, title, subtitle)
    body += f'<rect x="72" y="270" width="{width - 144}" height="{height - 350}" rx="18" fill="#e5eef0" stroke="{COLORS["line"]}"/>'
    minx, maxx = (
        min((p[0] for p in points), default=longitude or 0),
        max((p[0] for p in points), default=longitude or 0),
    )
    miny, maxy = min((p[1] for p in points), default=latitude or 0), max((p[1] for p in points), default=latitude or 0)
    dx = max(maxx - minx, 0.01)
    dy = max(maxy - miny, 0.01)
    for idx, (x, y, pid) in enumerate(points):
        px = 120 + (x - minx) / dx * (width - 240)
        py = 320 + (maxy - y) / dy * (height - 500)
        selected = pid in (highlighted_properties or []) or pid == (subject["parcel_number"] if subject else "")
        body += (
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{22 if selected else 14}" fill="{COLORS["accent"] if selected else COLORS["blue"]}" stroke="white" stroke-width="5"/>'
            + _text(
                px + 28,
                py + 8,
                "SUBJECT" if selected and subject and pid == subject["parcel_number"] else str(idx + 1),
                18,
                weight="700",
            )
        )
    if annotation:
        body += _text(72, height - 45, annotation, 19, fill=COLORS["muted"])
    payload = {
        "fields_used": ["longitude", "latitude"],
        "summary": f"{mode.title()} map with {len(points)} located properties.",
        "ids": [p[2] for p in points],
        "mode": mode,
        "source_snapshot": _source_snapshot(points),
    }
    return _store("generate_map", payload, _svg(width, height, title, body), width, height, payload["ids"], warnings)
