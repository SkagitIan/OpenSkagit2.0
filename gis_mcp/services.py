from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

from .layers import DEFAULT_BUNDLES, DEFAULT_OVERLAY_LAYERS, GIS_BUNDLES, GIS_LAYERS, GisLayerConfig

USER_AGENT = "OpenSkagit research tool"
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_WORKERS = 12
OVERLAY_RECORD_LIMIT = 25
QUERY_RECORD_LIMIT = 50


def gis_answer_rule() -> dict[str, Any]:
    return {
        "rule": "Use GIS MCP tools for live ArcGIS parcel geometry and overlay screening. Do not treat GIS overlays as final legal, permitting, engineering, environmental, or appraisal determinations.",
        "flow": "parcel -> parcel geometry -> selected bundles/layers -> intersecting overlay features -> limitations",
        "default_bundles": DEFAULT_BUNDLES,
    }


def list_gis_layers() -> dict[str, Any]:
    return {
        "default_bundles": DEFAULT_BUNDLES,
        "bundles": GIS_BUNDLES,
        "layers": [layer.to_dict() for layer in GIS_LAYERS.values()],
    }


def clean_parcel(value: str | None) -> str:
    text = (value or "").strip().upper()
    if re.fullmatch(r"\d{1,10}", text):
        text = f"P{text}"
    if not re.fullmatch(r"P\d{1,10}", text):
        raise ValueError("Parcel must look like P96023.")
    return text


def sql_literal(value: str) -> str:
    return value.replace("'", "''").upper()


def get_layer(key: str | None) -> GisLayerConfig:
    layer = GIS_LAYERS.get((key or "").strip())
    if not layer:
        raise ValueError(f"Unknown GIS layer. Use one of: {', '.join(GIS_LAYERS)}")
    return layer


def parse_layer_keys(layers: str | list[str] | None = None, bundles: str | list[str] | None = None) -> list[str]:
    keys: list[str] = []

    def add_key(key: str) -> None:
        layer = get_layer(key)
        if layer.key not in keys:
            keys.append(layer.key)

    for bundle in _coerce_csv(bundles):
        if bundle not in GIS_BUNDLES:
            raise ValueError(f"Unknown GIS bundle. Use one of: {', '.join(GIS_BUNDLES)}")
        for key in GIS_BUNDLES[bundle]:
            add_key(key)

    for key in _coerce_csv(layers):
        add_key(key)

    return keys or list(DEFAULT_OVERLAY_LAYERS)


def get_parcel_gis(parcel: str, include_geometry: bool = True) -> dict[str, Any]:
    parcel = clean_parcel(parcel)
    layer = GIS_LAYERS["parcel"]
    data = arcgis_request(
        layer,
        {
            "where": f"PARCELID = '{sql_literal(parcel)}'",
            "outFields": layer.out_fields,
            "returnGeometry": "true" if include_geometry else "false",
            "outSR": "4326",
            "resultRecordCount": "1",
        },
    )
    feature = data.get("features", [None])[0]
    if not feature:
        raise ValueError(f"No parcel geometry found for {parcel}")
    return trim_feature(feature, include_geometry)


def query_gis_layer(
    layer: str,
    where: str = "1=1",
    limit: int = 10,
    include_geometry: bool = False,
    arcgis_geometry: dict[str, Any] | str | None = None,
    geometry_type: str = "esriGeometryPolygon",
) -> dict[str, Any]:
    config = get_layer(layer)
    count = min(max(int(limit or 10), 1), QUERY_RECORD_LIMIT)
    params = {
        "where": where or "1=1",
        "outFields": config.out_fields,
        "returnGeometry": "true" if include_geometry else "false",
        "outSR": "4326",
        "resultRecordCount": str(count),
    }
    if arcgis_geometry:
        params.update(
            {
                "geometry": arcgis_geometry if isinstance(arcgis_geometry, str) else json.dumps(arcgis_geometry),
                "geometryType": geometry_type,
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
            }
        )
    data = arcgis_request(config, params)
    return {
        "layer": config.key,
        "label": config.label,
        "count": len(data.get("features", [])),
        "exceededTransferLimit": bool(data.get("exceededTransferLimit")),
        "features": [trim_feature(feature, include_geometry) for feature in data.get("features", [])],
    }


def get_gis_layer_metadata(layer: str) -> dict[str, Any]:
    config = get_layer(layer)
    metadata = fetch_layer_metadata(config)
    return {
        "layer": config.key,
        "label": config.label,
        "configured_url": config.url,
        "configured_outFields": config.out_fields,
        "metadata": compact_metadata(metadata),
    }


def get_parcel_overlays(
    parcel: str,
    bundles: str | list[str] | None = None,
    layers: str | list[str] | None = None,
    include_parcel_geometry: bool = True,
) -> dict[str, Any]:
    parcel = clean_parcel(parcel)
    layer_keys = parse_layer_keys(layers=layers, bundles=bundles)
    parcel_feature = get_parcel_gis(parcel, include_geometry=True)
    geometry = parcel_feature.get("geometry")
    if not geometry:
        raise ValueError(f"No parcel geometry returned for {parcel}")

    geometry_text = json.dumps({**geometry, "spatialReference": {"wkid": 4326}})
    workers = min(max_workers(), len(layer_keys)) or 1
    overlays: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(query_overlay_layer, GIS_LAYERS[key], geometry_text): key
            for key in layer_keys
        }
        results_by_key: dict[str, dict[str, Any]] = {}
        for future in as_completed(futures):
            key = futures[future]
            try:
                results_by_key[key] = future.result()
            except Exception as exc:
                layer = GIS_LAYERS[key]
                results_by_key[key] = {
                    "layer": layer.key,
                    "label": layer.label,
                    "status": "query_error",
                    "error": str(exc),
                    "features": [],
                }
        overlays = [results_by_key[key] for key in layer_keys]

    parcel_gis = {"attributes": parcel_feature.get("attributes", {})}
    if include_parcel_geometry:
        parcel_gis["geometry"] = geometry
    return {"parcel": parcel, "parcel_gis": parcel_gis, "overlays": overlays}


def query_overlay_layer(layer: GisLayerConfig, geometry_text: str) -> dict[str, Any]:
    metadata = fetch_layer_metadata(layer)
    metadata_debug = compact_metadata(metadata)
    if metadata.get("error"):
        return {
            "layer": layer.key,
            "label": layer.label,
            "status": "metadata_error",
            "error": metadata["error"],
            "metadata_debug": metadata_debug,
            "features": [],
        }
    if not metadata.get("geometryType"):
        return {
            "layer": layer.key,
            "label": layer.label,
            "status": "skipped_non_spatial",
            "reason": "Layer has no geometryType and cannot be intersected with a parcel polygon.",
            "metadata_debug": metadata_debug,
            "features": [],
        }

    base_params = {
        "geometry": geometry_text,
        "geometryType": "esriGeometryPolygon",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "returnGeometry": "false",
        "resultRecordCount": str(OVERLAY_RECORD_LIMIT),
    }
    safe_out_fields = existing_out_fields(layer, metadata)
    retried_with_all_fields = False
    try:
        data = arcgis_request(layer, {**base_params, "outFields": safe_out_fields})
    except ArcGisError:
        retried_with_all_fields = True
        try:
            data = arcgis_request(layer, {**base_params, "outFields": "*"})
        except ArcGisError as exc:
            return {
                "layer": layer.key,
                "label": layer.label,
                "status": "query_error",
                "error": exc.payload or str(exc),
                "configured_outFields": layer.out_fields,
                "attempted_outFields": safe_out_fields,
                "retried_with_all_fields": retried_with_all_fields,
                "metadata_debug": metadata_debug,
                "features": [],
            }

    return {
        "layer": layer.key,
        "label": layer.label,
        "status": "ok",
        "count": len(data.get("features", [])),
        "exceededTransferLimit": bool(data.get("exceededTransferLimit")),
        "outFields_used": safe_out_fields,
        "retried_with_all_fields": retried_with_all_fields,
        "metadata": {"name": metadata.get("name"), "geometryType": metadata.get("geometryType")},
        "features": [trim_feature(feature, False) for feature in data.get("features", [])],
    }


def arcgis_request(layer: GisLayerConfig, params: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(
        f"{layer.url}/query",
        data={"f": "json", **params},
        headers={
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
            "user-agent": USER_AGENT,
        },
        timeout=timeout_seconds(),
    )
    return _response_json_or_error(response, layer.key)


def fetch_layer_metadata(layer: GisLayerConfig) -> dict[str, Any]:
    response = requests.get(
        layer.url,
        params={"f": "json"},
        headers={"accept": "application/json", "user-agent": USER_AGENT},
        timeout=timeout_seconds(),
    )
    try:
        return _response_json_or_error(response, layer.key)
    except ArcGisError as exc:
        return {"error": exc.payload or str(exc)}


def existing_out_fields(layer: GisLayerConfig, metadata: dict[str, Any]) -> str:
    requested = [field.strip() for field in layer.out_fields.split(",") if field.strip()]
    if "*" in requested:
        return "*"
    field_names = {str(field.get("name", "")).upper() for field in metadata.get("fields", [])}
    valid = [field for field in requested if field.upper() in field_names]
    if valid:
        return ",".join(valid)
    if "OBJECTID" in field_names:
        return "OBJECTID"
    fields = metadata.get("fields") or []
    if fields and fields[0].get("name"):
        return str(fields[0]["name"])
    return "*"


def compact_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": metadata.get("id"),
        "name": metadata.get("name"),
        "type": metadata.get("type"),
        "geometryType": metadata.get("geometryType"),
        "capabilities": metadata.get("capabilities"),
        "maxRecordCount": metadata.get("maxRecordCount"),
        "fields": [
            {"name": field.get("name"), "type": field.get("type"), "alias": field.get("alias")}
            for field in metadata.get("fields", [])
        ],
        **({"error": metadata["error"]} if metadata.get("error") else {}),
    }


def trim_feature(feature: dict[str, Any], include_geometry: bool = False) -> dict[str, Any]:
    trimmed = {"attributes": feature.get("attributes", {})}
    if include_geometry:
        trimmed["geometry"] = feature.get("geometry")
    return trimmed


class ArcGisError(RuntimeError):
    def __init__(self, message: str, payload: Any = None):
        super().__init__(message)
        self.payload = payload


def _response_json_or_error(response: requests.Response, layer_key: str) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise ArcGisError(f"{layer_key} returned non-JSON response: {response.status_code}", response.text[:1200]) from exc
    if not response.ok or data.get("error"):
        raise ArcGisError(f"ArcGIS request failed for {layer_key}: {response.status_code}", data.get("error") or data)
    return data


def _coerce_csv(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.split(",")
    else:
        raw_items = value
    return [str(item).strip() for item in raw_items if str(item).strip()]


def timeout_seconds() -> float:
    return float(os.environ.get("GIS_MCP_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))


def max_workers() -> int:
    return max(1, int(os.environ.get("GIS_MCP_MAX_WORKERS", DEFAULT_MAX_WORKERS)))
