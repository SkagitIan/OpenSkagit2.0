"""Cyclomedia Street Smart property-view proof of concept.

This module deliberately accepts only a caller-supplied, short-lived OAuth
bearer token or Cyclomedia Basic Auth credentials. It never reads Chrome
cookies, HAR secrets, or Street Smart browser storage.

Example:
    CYCLOMEDIA_BEARER_TOKEN=... python scripts/streetsmart_poc.py \
        --x -13616516.484 --y 6177192.734 --input-crs 3857 \
        --output output/streetsmart-property.jpg
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from PIL import Image


WFS_URL = os.getenv("CYCLOMEDIA_WFS_URL", "https://atlasapi.cyclomedia.com/api/recording/wfs")
TILE_BASE_URL = os.getenv("CYCLOMEDIA_TILE_BASE_URL", "https://atlasapi.cyclomedia.com/image/panorama/tiles/Tile")
DEFAULT_RADIUS_METERS = 250.0
TILE_ZOOM = 2
TILE_SIZE = 512
FACE_GRID_SIZE = 3
HORIZONTAL_FACES = ("F", "R", "B", "L")
ALL_FACES = HORIZONTAL_FACES + ("U", "D")


class StreetSmartAuthError(RuntimeError):
    pass


class StreetSmartDataError(RuntimeError):
    pass


def _auth_headers() -> dict[str, str]:
    token = os.getenv("CYCLOMEDIA_BEARER_TOKEN", "").strip()
    if token:
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    username = os.getenv("CYCLOMEDIA_USERNAME", "")
    password = os.getenv("CYCLOMEDIA_PASSWORD", "")
    if username or password:
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
        return {"Authorization": f"Basic {encoded}", "Accept": "application/json"}
    raise StreetSmartAuthError(
        "No supported Cyclomedia credential supplied. Set CYCLOMEDIA_BEARER_TOKEN "
        "or CYCLOMEDIA_USERNAME/CYCLOMEDIA_PASSWORD; browser cookies are not accepted."
    )


def _web_mercator(x: float, y: float, input_crs: int) -> tuple[float, float]:
    if input_crs == 3857:
        return float(x), float(y)
    if input_crs != 4326:
        raise ValueError("input_crs must be 4326 or 3857")
    lon, lat = float(x), max(-85.05112878, min(85.05112878, float(y)))
    radius = 6378137.0
    return radius * math.radians(lon), radius * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def _dwithin_filter(x: float, y: float, radius_meters: float) -> str:
    return f"""<ogc:Filter xmlns:ogc="http://www.opengis.net/ogc" xmlns:gml="http://www.opengis.net/gml">
  <ogc:DWithin>
    <ogc:PropertyName>location</ogc:PropertyName>
    <gml:Point srsName="EPSG:3857"><gml:coordinates>{x},{y}</gml:coordinates></gml:Point>
    <ogc:Distance units="m">{radius_meters}</ogc:Distance>
  </ogc:DWithin>
</ogc:Filter>"""


def find_recordings(session: requests.Session, x: float, y: float, radius_meters: float) -> list[dict[str, Any]]:
    params = {
        "service": "WFS",
        "version": "1.1.0",
        "request": "GetFeature",
        "typename": "atlas:Recording",
        "srsname": "EPSG:3857",
        "outputformat": "application/json",
        "filter": _dwithin_filter(x, y, radius_meters),
    }
    response = session.get(WFS_URL, params=params, timeout=30)
    if response.status_code in (401, 403):
        raise StreetSmartAuthError(f"Cyclomedia WFS rejected credentials with HTTP {response.status_code}")
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("exception"):
        raise StreetSmartDataError(str(payload["exception"]))
    features = payload.get("features", []) if isinstance(payload, dict) else []
    return [feature for feature in features if isinstance(feature, dict)]


def _feature_recording(feature: dict[str, Any], subject_x: float, subject_y: float) -> dict[str, Any]:
    props = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    coords = geometry.get("coordinates") or props.get("location") or [None, None]
    if isinstance(coords, dict):
        coords = coords.get("coordinates") or [None, None]
    x, y = float(coords[0]), float(coords[1])
    return {
        "image_id": props.get("imageId") or props.get("image_id"),
        "recorded_at": props.get("recordedAt") or props.get("recorded_at"),
        "x": x,
        "y": y,
        "distance_m": math.hypot(x - subject_x, y - subject_y),
        "orientation": props.get("orientation"),
        "recorder_direction": props.get("recorderDirection"),
        "product_type": props.get("productType"),
        "is_authorized": props.get("isAuthorized"),
        "panorama_tile_schema": props.get("panoramaTileSchema"),
        "tile_schema": props.get("tileSchema"),
        "raw": props,
    }


def _date_score(value: Any) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def choose_recording(features: list[dict[str, Any]], subject_x: float, subject_y: float) -> dict[str, Any]:
    recordings = [_feature_recording(feature, subject_x, subject_y) for feature in features]
    recordings = [item for item in recordings if item.get("image_id")]
    if not recordings:
        raise StreetSmartDataError("No Street Smart recordings were found near the parcel")
    cycloramas = [item for item in recordings if str(item.get("product_type") or "").lower() == "cyclorama"]
    authorized = [item for item in cycloramas if item.get("is_authorized") is not False]
    pool = authorized or cycloramas or recordings
    return max(pool, key=lambda item: (_date_score(item.get("recorded_at")), -item["distance_m"]))


def _bearing_degrees(camera_x: float, camera_y: float, subject_x: float, subject_y: float) -> float:
    return (math.degrees(math.atan2(subject_x - camera_x, subject_y - camera_y)) + 360.0) % 360.0


def _face_for_relative_bearing(relative_degrees: float) -> str:
    normalized = relative_degrees % 360.0
    return HORIZONTAL_FACES[int((normalized + 45.0) // 90.0) % 4]


def _tile_url(image_id: str, face: str, x: int, y: int, zoom: int = TILE_ZOOM) -> str:
    return f"{TILE_BASE_URL}/{image_id}/{zoom}/{face}/{x}/{y}"


def _download_face(session: requests.Session, image_id: str, face: str, zoom: int = TILE_ZOOM) -> Image.Image:
    canvas = Image.new("RGB", (TILE_SIZE * FACE_GRID_SIZE, TILE_SIZE * FACE_GRID_SIZE), "black")
    for y in range(FACE_GRID_SIZE):
        for x in range(FACE_GRID_SIZE):
            response = session.get(_tile_url(image_id, face, x, y, zoom), timeout=30)
            if response.status_code in (401, 403):
                raise StreetSmartAuthError(f"Cyclomedia tile request rejected with HTTP {response.status_code}")
            response.raise_for_status()
            from io import BytesIO
            tile = Image.open(BytesIO(response.content)).convert("RGB")
            canvas.paste(tile.resize((TILE_SIZE, TILE_SIZE)), (x * TILE_SIZE, y * TILE_SIZE))
    return canvas


def _project_face(face: Image.Image, output_size: tuple[int, int], fov_degrees: float) -> Image.Image:
    """Project a cube face into a normal, rectangular perspective view.

    The face is assumed to be the view direction. The face-label mapping is
    intentionally explicit and documented because the HAR was unavailable to
    verify whether Cyclomedia's F face is always recorder-forward.
    """
    width, height = output_size
    output = Image.new("RGB", output_size, "black")
    source = face.load()
    half_fov = math.radians(fov_degrees / 2)
    focal = (width / 2) / math.tan(half_fov)
    for py in range(height):
        for px in range(width):
            ray_x = (px - width / 2) / focal
            ray_y = 1.0
            ray_z = -(py - height / 2) / focal
            scale = max(abs(ray_x), abs(ray_y), abs(ray_z))
            u = 0.5 + (ray_x / scale) * 0.5
            v = 0.5 - (ray_z / scale) * 0.5
            sx = min(face.width - 1, max(0, int(u * face.width)))
            sy = min(face.height - 1, max(0, int(v * face.height)))
            output.putpixel((px, py), source[sx, sy])
    return output


def get_streetsmart_property_image(
    parcel_x: float,
    parcel_y: float,
    *,
    input_crs: int = 4326,
    radius_meters: float = DEFAULT_RADIUS_METERS,
    output_path: str | Path = "streetsmart-property.jpg",
    output_size: tuple[int, int] = (1024, 768),
) -> dict[str, Any]:
    subject_x, subject_y = _web_mercator(parcel_x, parcel_y, input_crs)
    headers = _auth_headers()
    with requests.Session() as session:
        session.headers.update(headers)
        features = find_recordings(session, subject_x, subject_y, radius_meters)
        recording = choose_recording(features, subject_x, subject_y)
        camera_heading = recording.get("recorder_direction")
        if camera_heading is None:
            camera_heading = recording.get("orientation")
        if camera_heading is None:
            raise StreetSmartDataError("Selected recording has no orientation/recorderDirection")
        bearing = _bearing_degrees(recording["x"], recording["y"], subject_x, subject_y)
        relative = (bearing - float(camera_heading)) % 360.0
        face = _face_for_relative_bearing(relative)
        face_image = _download_face(session, str(recording["image_id"]), face)
        result_image = _project_face(face_image, output_size, 90.0)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    result_image.save(output, "JPEG", quality=90, optimize=True)
    result = {
        "output": str(output),
        "image_id": recording["image_id"],
        "recorded_at": recording.get("recorded_at"),
        "recording_distance_m": round(recording["distance_m"], 2),
        "parcel_bearing": round(bearing, 2),
        "camera_heading": round(float(camera_heading), 2),
        "relative_bearing": round(relative, 2),
        "selected_face": face,
        "warning": "Face orientation is provisional until the supplied HAR is available for verification.",
    }
    print(json.dumps(result, indent=2))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--x", type=float, required=True, help="Parcel longitude (4326) or X (3857)")
    parser.add_argument("--y", type=float, required=True, help="Parcel latitude (4326) or Y (3857)")
    parser.add_argument("--input-crs", type=int, default=4326, choices=(4326, 3857))
    parser.add_argument("--radius-meters", type=float, default=DEFAULT_RADIUS_METERS)
    parser.add_argument("--output", default="output/streetsmart-property.jpg")
    args = parser.parse_args()
    get_streetsmart_property_image(args.x, args.y, input_crs=args.input_crs, radius_meters=args.radius_meters, output_path=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
