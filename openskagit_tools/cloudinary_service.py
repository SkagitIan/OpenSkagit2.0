"""Small, testable Cloudinary adapter used by the visual asset pipeline."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import requests

logger = logging.getLogger(__name__)

PRESETS = {
    "youtube_landscape": {"width": 1920, "height": 1080},
    "vertical_video": {"width": 1080, "height": 1920},
    "instagram_portrait": {"width": 1080, "height": 1350},
    "square_social": {"width": 1080, "height": 1080},
    "thumbnail": {"width": 1280, "height": 720},
}


class CloudinaryError(RuntimeError):
    """A safe, user-facing Cloudinary integration failure."""


@dataclass(frozen=True)
class CloudinaryConfig:
    cloud_name: str
    api_key: str
    api_secret: str

    @classmethod
    def from_environment(cls) -> "CloudinaryConfig":
        cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip()
        api_key = os.environ.get("CLOUDINARY_API_KEY", "").strip() or os.environ.get("CLOUDINARY_API", "").strip()
        api_secret = os.environ.get("CLOUDINARY_API_SECRET", "").strip() or os.environ.get("CLOUDINARY_SECRET", "").strip()
        cloudinary_url = os.environ.get("CLOUDINARY_URL", "").strip()
        if cloudinary_url:
            parsed = urlparse(cloudinary_url)
            cloud_name = cloud_name or parsed.hostname or ""
            api_key = api_key or parsed.username or ""
            api_secret = api_secret or (parsed.password or "")
            if not cloud_name and parse_qs(parsed.query).get("cloud_name"):
                cloud_name = parse_qs(parsed.query)["cloud_name"][0]
        missing = [name for name, value in (("cloud name", cloud_name), ("API key", api_key), ("API secret", api_secret)) if not value]
        if missing:
            raise CloudinaryError("Cloudinary configuration is missing: " + ", ".join(missing) + ".")
        return cls(cloud_name, api_key, api_secret)


def _signature(params: dict[str, str], secret: str) -> str:
    serialized = "&".join(f"{key}={params[key]}" for key in sorted(params) if params[key] not in (None, ""))
    return hashlib.sha1((serialized + secret).encode("utf-8")).hexdigest()


def _public_id(asset_type: str, digest: str, source_ids: list[str]) -> str:
    folder = {"map": "maps", "property_card": "property_cards", "comparison": "comparisons", "infographic": "infographics"}.get(asset_type, "other")
    subject = source_ids[0] if source_ids else "direct"
    return f"openskagit/visuals/{folder}/{subject}/{asset_type}_{digest}"


def _delivery_url(config: CloudinaryConfig, public_id: str, transformation: str = "") -> str:
    transform = f"{transformation}/" if transformation else ""
    return f"https://res.cloudinary.com/{config.cloud_name}/image/upload/{transform}{public_id}"


def transformed_url(public_id: str, preset: str, *, fmt: str = "auto") -> str:
    if preset not in PRESETS:
        raise CloudinaryError(f"Unknown Cloudinary transformation preset {preset!r}. Use one of: {', '.join(PRESETS)}.")
    config = CloudinaryConfig.from_environment()
    size = PRESETS[preset]
    format_part = "f_auto" if fmt == "auto" else f"f_{fmt}"
    transformation = f"c_pad,w_{size['width']},h_{size['height']},{format_part},q_auto"
    return _delivery_url(config, public_id, transformation)


def get_asset_metadata(public_id: str) -> dict:
    config = CloudinaryConfig.from_environment()
    url = f"https://api.cloudinary.com/v1_1/{config.cloud_name}/resources/image/upload/{public_id}"
    try:
        response = requests.get(url, auth=(config.api_key, config.api_secret), timeout=15)
    except requests.RequestException as exc:
        raise CloudinaryError("Cloudinary metadata lookup failed.") from exc
    if response.status_code == 404:
        return {}
    if response.status_code >= 400:
        raise CloudinaryError(f"Cloudinary metadata lookup failed with HTTP {response.status_code}.")
    return response.json()


def upload_generated_asset(content: bytes, *, asset_type: str, digest: str, source_property_ids: list[str], metadata: dict[str, str], content_type: str = "image/svg+xml") -> dict:
    config = CloudinaryConfig.from_environment()
    public_id = _public_id(asset_type, digest, source_property_ids)
    existing = get_asset_metadata(public_id)
    if existing:
        logger.info("cloudinary_asset_cache_hit", extra={"asset_type": asset_type, "public_id": public_id})
        secure_url = existing.get("secure_url") or _delivery_url(config, public_id)
        width, height = existing.get("width"), existing.get("height")
        return {"cloudinary_public_id": public_id, "secure_url": secure_url, "source_url": secure_url, "width": width, "height": height, "cached": True}

    timestamp = str(int(time.time()))
    sign_params = {"public_id": public_id, "timestamp": timestamp, "type": "upload"}
    signature = _signature(sign_params, config.api_secret)
    upload_url = f"https://api.cloudinary.com/v1_1/{config.cloud_name}/image/upload"
    data = {**sign_params, "api_key": config.api_key, "signature": signature, "context": "|".join(f"{key}={value}" for key, value in sorted(metadata.items()))}
    try:
        response = requests.post(upload_url, data=data, files={"file": (f"{public_id.rsplit('/', 1)[-1]}.svg", content, content_type)}, timeout=30)
    except requests.RequestException as exc:
        logger.exception("cloudinary_asset_upload_failed", extra={"asset_type": asset_type, "public_id": public_id})
        raise CloudinaryError("Cloudinary upload failed due to a network error.") from exc
    if response.status_code >= 400:
        logger.error("cloudinary_asset_upload_failed", extra={"asset_type": asset_type, "public_id": public_id, "status_code": response.status_code})
        raise CloudinaryError(f"Cloudinary upload failed with HTTP {response.status_code}.")
    result = response.json()
    logger.info("cloudinary_asset_uploaded", extra={"asset_type": asset_type, "public_id": public_id})
    return {"cloudinary_public_id": public_id, "secure_url": result.get("secure_url") or _delivery_url(config, public_id), "source_url": result.get("secure_url"), "width": result.get("width"), "height": result.get("height"), "cached": False}


def delete_asset(public_id: str) -> None:
    config = CloudinaryConfig.from_environment()
    timestamp = str(int(time.time()))
    signature = _signature({"public_id": public_id, "timestamp": timestamp}, config.api_secret)
    url = f"https://api.cloudinary.com/v1_1/{config.cloud_name}/image/destroy"
    try:
        response = requests.post(url, data={"public_id": public_id, "timestamp": timestamp, "api_key": config.api_key, "signature": signature}, timeout=15)
    except requests.RequestException as exc:
        raise CloudinaryError("Cloudinary delete failed due to a network error.") from exc
    if response.status_code >= 400:
        raise CloudinaryError(f"Cloudinary delete failed with HTTP {response.status_code}.")
