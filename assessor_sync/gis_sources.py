"""
Helpers for the GIS source-management step.

This module keeps the *pure* logic of the ``sync_gis_sources`` command --
loading the YAML config, hashing a downloaded file, and extracting/validating a
shapefile ZIP -- separate from the database and network work in the command
itself. That split keeps the logic easy to read and easy to unit test without a
database or a live download.

Nothing here builds parcel features or touches PostGIS. It only manages local
copies of GIS source files.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import yaml

# The four sidecar files that together make up a usable shapefile. We require
# all four before we trust an extracted package enough to promote it.
REQUIRED_SHAPEFILE_SUFFIXES = (".shp", ".shx", ".dbf", ".prj")

CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class LayerConfig:
    """One configured GIS source layer from gis_sources.yaml."""

    layer_name: str
    display_name: str
    url: str
    enabled: bool
    expected_geometry_type: str
    refresh_frequency: str


class GISConfigError(Exception):
    """Raised when gis_sources.yaml is missing or malformed."""


def load_layer_configs(config_path: Path) -> list[LayerConfig]:
    """
    Read gis_sources.yaml and return one LayerConfig per configured layer.

    Layers are returned in the order they appear in the file (both enabled and
    disabled); callers decide which ones to act on.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise GISConfigError(f"GIS config file not found: {config_path}")

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise GISConfigError(f"Could not parse {config_path}: {exc}") from exc

    if not isinstance(raw, dict) or "layers" not in raw:
        raise GISConfigError(f"{config_path} must contain a top-level 'layers' mapping.")

    layers = raw["layers"]
    if not isinstance(layers, dict) or not layers:
        raise GISConfigError(f"{config_path} 'layers' must be a non-empty mapping.")

    configs: list[LayerConfig] = []
    for layer_name, entry in layers.items():
        if not isinstance(entry, dict):
            raise GISConfigError(f"Layer '{layer_name}' must be a mapping of settings.")
        url = str(entry.get("url", "")).strip()
        if not url:
            raise GISConfigError(f"Layer '{layer_name}' is missing a 'url'.")
        configs.append(
            LayerConfig(
                layer_name=str(layer_name).strip(),
                display_name=str(entry.get("display_name", layer_name)).strip(),
                url=url,
                enabled=bool(entry.get("enabled", True)),
                expected_geometry_type=str(entry.get("expected_geometry_type", "")).strip(),
                refresh_frequency=str(entry.get("refresh_frequency", "")).strip(),
            )
        )
    return configs


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file, read in chunks."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_shapefile_members(folder: Path) -> dict[str, list[Path]]:
    """
    Group the files in ``folder`` (recursively) by lowercased suffix.

    Used to confirm a shapefile package is complete without assuming the ``.shp``
    filename matches the layer name.
    """
    grouped: dict[str, list[Path]] = {}
    for path in sorted(Path(folder).rglob("*")):
        if path.is_file():
            grouped.setdefault(path.suffix.lower(), []).append(path)
    return grouped


def missing_shapefile_suffixes(folder: Path) -> list[str]:
    """Return required shapefile suffixes that are absent from ``folder``."""
    present = find_shapefile_members(folder)
    return [suffix for suffix in REQUIRED_SHAPEFILE_SUFFIXES if suffix not in present]


def extract_shapefile_zip(zip_path: Path, extracted_dir: Path) -> Path:
    """
    Safely extract a shapefile ZIP into ``extracted_dir``.

    Steps, in order, so a bad download never destroys the last good copy:

    1. Extract everything into a temporary sibling folder.
    2. Confirm the extracted files include at least one .shp/.shx/.dbf/.prj.
    3. Only after validation, replace ``extracted_dir`` with the new folder.

    Raises GISConfigError (with a readable message) if the ZIP is invalid or the
    extracted contents are not a complete shapefile. On failure ``extracted_dir``
    is left untouched.
    """
    zip_path = Path(zip_path)
    extracted_dir = Path(extracted_dir)
    extracted_dir.parent.mkdir(parents=True, exist_ok=True)

    # Stage the extraction next to the final location so the final move stays on
    # the same filesystem (fast, atomic-ish rename).
    staging = Path(tempfile.mkdtemp(prefix=f"{extracted_dir.name}_", dir=extracted_dir.parent))
    try:
        try:
            with zipfile.ZipFile(zip_path) as zf:
                _safe_extract_all(zf, staging)
        except zipfile.BadZipFile as exc:
            raise GISConfigError(f"{zip_path.name} is not a valid ZIP file: {exc}") from exc

        missing = missing_shapefile_suffixes(staging)
        if missing:
            raise GISConfigError(
                f"{zip_path.name} is missing required shapefile part(s): {', '.join(missing)}"
            )

        # Validation passed: swap the new folder in. Remove the old copy last,
        # and only once the replacement is ready to take its place.
        if extracted_dir.exists():
            shutil.rmtree(extracted_dir)
        staging.replace(extracted_dir)
        return extracted_dir
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _safe_extract_all(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract every member of ``zf`` into ``dest``, rejecting path traversal."""
    dest = dest.resolve()
    for member in zf.namelist():
        target = (dest / member).resolve()
        if not str(target).startswith(str(dest)):
            raise GISConfigError(f"Unsafe path in ZIP archive: {member}")
    zf.extractall(dest)
