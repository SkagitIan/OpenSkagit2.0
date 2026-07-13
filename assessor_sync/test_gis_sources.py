"""
Tests for the GIS source-management step (sync_gis_sources).

Pure helpers (config loading, hashing, extraction) are tested with
SimpleTestCase so they need no database. The management command is tested with
TestCase; downloads use local ``file://`` URLs so the tests never touch the
network, and BASE_DIR is redirected to a temp folder so nothing is written into
the real data/gis tree.
"""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from assessor_sync.gis_sources import (
    GISConfigError,
    extract_shapefile_zip,
    load_layer_configs,
    missing_shapefile_suffixes,
    sha256_file,
)
from assessor_sync.models import GISSource

SHAPEFILE_PARTS = (".shp", ".shx", ".dbf", ".prj")


def write_shapefile_zip(path: Path, *, parts=SHAPEFILE_PARTS, name="layer", salt="") -> Path:
    """Write a tiny fake shapefile ZIP containing the requested sidecar files."""
    path = Path(path)
    with zipfile.ZipFile(path, "w") as zf:
        for suffix in parts:
            zf.writestr(f"{name}{suffix}", f"dummy {suffix} content {salt}")
    return path


def write_config(path: Path, layers: dict) -> Path:
    """Write a minimal gis_sources.yaml from a dict of {layer_name: settings}."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["layers:"]
    for layer_name, entry in layers.items():
        lines.append(f"  {layer_name}:")
        for key, value in entry.items():
            if isinstance(value, bool):
                lines.append(f"    {key}: {str(value).lower()}")
            else:
                lines.append(f'    {key}: "{value}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class ConfigLoadingTests(SimpleTestCase):
    def test_loads_all_layers_with_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = write_config(
                Path(tmp) / "gis_sources.yaml",
                {
                    "city_limits": {
                        "display_name": "City Limits",
                        "url": "https://example.com/city_limits.zip",
                        "enabled": True,
                        "expected_geometry_type": "Polygon",
                        "refresh_frequency": "weekly",
                    },
                    "roads": {
                        "display_name": "Roads",
                        "url": "https://example.com/roads.zip",
                        "enabled": False,
                        "expected_geometry_type": "LineString",
                        "refresh_frequency": "weekly",
                    },
                },
            )
            configs = load_layer_configs(config)

        self.assertEqual([c.layer_name for c in configs], ["city_limits", "roads"])
        self.assertEqual(configs[0].display_name, "City Limits")
        self.assertEqual(configs[0].expected_geometry_type, "Polygon")
        self.assertTrue(configs[0].enabled)
        self.assertFalse(configs[1].enabled)

    def test_missing_file_raises(self):
        with self.assertRaises(GISConfigError):
            load_layer_configs(Path("does-not-exist.yaml"))

    def test_layer_without_url_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = write_config(Path(tmp) / "gis_sources.yaml", {"zoning": {"enabled": True}})
            with self.assertRaises(GISConfigError):
                load_layer_configs(config)


class HashingTests(SimpleTestCase):
    def test_sha256_of_known_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f.bin"
            path.write_bytes(b"hello world")
            # Known SHA-256 of b"hello world".
            self.assertEqual(
                sha256_file(path),
                "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
            )

    def test_unchanged_and_changed_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = write_shapefile_zip(Path(tmp) / "a.zip", salt="one")
            b = write_shapefile_zip(Path(tmp) / "b.zip", salt="one")
            c = write_shapefile_zip(Path(tmp) / "c.zip", salt="two")
            # Same content -> same hash (unchanged); different content -> changed.
            self.assertEqual(sha256_file(a), sha256_file(b))
            self.assertNotEqual(sha256_file(a), sha256_file(c))


class ExtractionTests(SimpleTestCase):
    def test_extracts_valid_shapefile_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            zip_path = write_shapefile_zip(tmp / "source.zip")
            extracted = tmp / "extracted" / "roads"
            extract_shapefile_zip(zip_path, extracted)

            self.assertEqual(missing_shapefile_suffixes(extracted), [])
            names = {p.name for p in extracted.iterdir()}
            self.assertEqual(names, {f"layer{s}" for s in SHAPEFILE_PARTS})

    def test_missing_parts_raises_and_preserves_previous(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            extracted = tmp / "extracted" / "roads"

            good = write_shapefile_zip(tmp / "good.zip")
            extract_shapefile_zip(good, extracted)
            self.assertEqual(missing_shapefile_suffixes(extracted), [])

            # A bad ZIP missing the .prj must not destroy the good extract.
            bad = write_shapefile_zip(tmp / "bad.zip", parts=(".shp", ".shx", ".dbf"))
            with self.assertRaises(GISConfigError):
                extract_shapefile_zip(bad, extracted)

            self.assertEqual(missing_shapefile_suffixes(extracted), [])
            names = {p.name for p in extracted.iterdir()}
            self.assertEqual(names, {f"layer{s}" for s in SHAPEFILE_PARTS})


class SyncCommandTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.config_path = self.base / "data" / "gis" / "sources" / "gis_sources.yaml"
        self.downloads = self.base / "downloads"
        self.downloads.mkdir(parents=True, exist_ok=True)
        self.addCleanup(self._tmp.cleanup)

    def _url_for(self, zip_path: Path) -> str:
        return Path(zip_path).resolve().as_uri()

    def _run(self, **kwargs):
        with override_settings(BASE_DIR=str(self.base)):
            call_command("sync_gis_sources", config=str(self.config_path), **kwargs)

    def raw_zip(self, layer):
        return self.base / "data" / "gis" / "raw" / layer / "source.zip"

    def extracted(self, layer):
        return self.base / "data" / "gis" / "extracted" / layer

    def test_creates_record_and_extracts(self):
        src = write_shapefile_zip(self.downloads / "roads.zip", salt="v1")
        write_config(self.config_path, {"roads": {"display_name": "Roads", "url": self._url_for(src)}})

        self._run()

        source = GISSource.objects.get(layer_name="roads")
        self.assertEqual(source.last_status, GISSource.STATUS_CHANGED)
        self.assertEqual(source.source_hash, sha256_file(src))
        self.assertIsNotNone(source.last_changed_at)
        self.assertTrue(self.raw_zip("roads").exists())
        self.assertEqual(missing_shapefile_suffixes(self.extracted("roads")), [])

    def test_second_run_unchanged(self):
        src = write_shapefile_zip(self.downloads / "roads.zip", salt="v1")
        write_config(self.config_path, {"roads": {"display_name": "Roads", "url": self._url_for(src)}})

        self._run()
        self._run()

        source = GISSource.objects.get(layer_name="roads")
        self.assertEqual(source.last_status, GISSource.STATUS_UNCHANGED)

    def test_changed_when_source_bytes_change(self):
        src = write_shapefile_zip(self.downloads / "roads.zip", salt="v1")
        write_config(self.config_path, {"roads": {"display_name": "Roads", "url": self._url_for(src)}})
        self._run()

        write_shapefile_zip(src, salt="v2")  # same URL, new bytes
        self._run()

        source = GISSource.objects.get(layer_name="roads")
        self.assertEqual(source.last_status, GISSource.STATUS_CHANGED)
        self.assertEqual(source.source_hash, sha256_file(src))
        self.assertNotEqual(source.previous_source_hash, source.source_hash)

    def test_layer_flag_syncs_only_one(self):
        roads = write_shapefile_zip(self.downloads / "roads.zip", salt="r")
        zoning = write_shapefile_zip(self.downloads / "zoning.zip", salt="z")
        write_config(
            self.config_path,
            {
                "roads": {"display_name": "Roads", "url": self._url_for(roads)},
                "zoning": {"display_name": "Zoning", "url": self._url_for(zoning)},
            },
        )

        self._run(layer="roads")

        self.assertEqual(list(GISSource.objects.values_list("layer_name", flat=True)), ["roads"])
        self.assertFalse(self.raw_zip("zoning").exists())

    def test_unknown_layer_flag_errors(self):
        src = write_shapefile_zip(self.downloads / "roads.zip", salt="r")
        write_config(self.config_path, {"roads": {"display_name": "Roads", "url": self._url_for(src)}})
        with self.assertRaises(CommandError):
            self._run(layer="nope")

    def test_dry_run_writes_nothing(self):
        src = write_shapefile_zip(self.downloads / "roads.zip", salt="r")
        write_config(self.config_path, {"roads": {"display_name": "Roads", "url": self._url_for(src)}})

        self._run(dry_run=True)

        self.assertEqual(GISSource.objects.count(), 0)
        self.assertFalse(self.raw_zip("roads").exists())
        self.assertFalse(self.extracted("roads").exists())

    def test_one_layer_failure_does_not_stop_others(self):
        good = write_shapefile_zip(self.downloads / "roads.zip", salt="r")
        missing = self.downloads / "missing.zip"  # never created -> download fails
        write_config(
            self.config_path,
            {
                "roads": {"display_name": "Roads", "url": self._url_for(good)},
                "flood_zones": {"display_name": "Flood", "url": self._url_for(missing)},
            },
        )

        self._run()

        self.assertEqual(GISSource.objects.get(layer_name="roads").last_status, GISSource.STATUS_CHANGED)
        failed = GISSource.objects.get(layer_name="flood_zones")
        self.assertEqual(failed.last_status, GISSource.STATUS_DOWNLOAD_FAILED)
        self.assertIn("download failed", failed.last_error)

    def test_extract_failure_preserves_previous_extract(self):
        src = write_shapefile_zip(self.downloads / "roads.zip", salt="v1")
        write_config(self.config_path, {"roads": {"display_name": "Roads", "url": self._url_for(src)}})
        self._run()
        self.assertEqual(missing_shapefile_suffixes(self.extracted("roads")), [])

        # New bytes (so it re-extracts) but missing the .prj part -> extract fails.
        write_shapefile_zip(src, parts=(".shp", ".shx", ".dbf"), salt="v2")
        self._run()

        source = GISSource.objects.get(layer_name="roads")
        self.assertEqual(source.last_status, GISSource.STATUS_EXTRACT_FAILED)
        self.assertIn("extract failed", source.last_error)
        # Previous good extract is still intact.
        self.assertEqual(missing_shapefile_suffixes(self.extracted("roads")), [])

    def test_disabled_layer_recorded_not_downloaded(self):
        src = write_shapefile_zip(self.downloads / "roads.zip", salt="r")
        write_config(
            self.config_path,
            {"roads": {"display_name": "Roads", "url": self._url_for(src), "enabled": False}},
        )

        self._run()

        source = GISSource.objects.get(layer_name="roads")
        self.assertEqual(source.last_status, GISSource.STATUS_DISABLED)
        self.assertFalse(self.raw_zip("roads").exists())
