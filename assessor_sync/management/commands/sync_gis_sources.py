"""
sync_gis_sources -- download, hash, and track Skagit County GIS source files.

This is the first GIS foundation step. It keeps clean local copies of GIS
source shapefiles and records whether each one changed since the last run. It
deliberately does NOT build parcel features, import anything into PostGIS, or
run any analysis -- later commands do that using the files this one manages.

For each configured layer the command:
  1. Downloads the source file to data/gis/raw/<layer>/source.zip
  2. Computes a SHA-256 hash of the raw download
  3. Compares the hash to the previously stored hash in the GISSource table
  4. Re-extracts the shapefile into data/gis/extracted/<layer>/ only if changed
  5. Records status/metadata and prints a summary

One failing layer never stops the others.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from assessor_sync.gis_sources import (
    GISConfigError,
    LayerConfig,
    extract_shapefile_zip,
    load_layer_configs,
    sha256_file,
)
from assessor_sync.models import GISSource


def default_config_path() -> Path:
    return Path(settings.BASE_DIR) / "data" / "gis" / "sources" / "gis_sources.yaml"


def raw_dir_for(layer_name: str) -> Path:
    return Path(settings.BASE_DIR) / "data" / "gis" / "raw" / layer_name


def extracted_dir_for(layer_name: str) -> Path:
    return Path(settings.BASE_DIR) / "data" / "gis" / "extracted" / layer_name


class Command(BaseCommand):
    help = "Download, hash, and track Skagit County GIS source shapefiles (no feature building)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--config",
            default=str(default_config_path()),
            help="Path to gis_sources.yaml.",
        )
        parser.add_argument("--layer", help="Sync only this single configured layer.")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-download and re-extract even if the hash looks unchanged.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would happen without downloading, writing files, or touching the database.",
        )

    def handle(self, *args, **options):
        config_path = Path(options["config"])
        try:
            configs = load_layer_configs(config_path)
        except GISConfigError as exc:
            raise CommandError(str(exc)) from exc

        if options["layer"]:
            configs = [c for c in configs if c.layer_name == options["layer"]]
            if not configs:
                raise CommandError(
                    f"Layer '{options['layer']}' is not in {config_path}."
                )

        dry_run = options["dry_run"]
        force = options["force"]

        results = []
        for config in configs:
            if dry_run:
                results.append(self._plan_layer(config))
            else:
                results.append(self._sync_layer(config, force=force))

        self._print_summary(results, dry_run=dry_run)
        return None

    # ------------------------------------------------------------------
    # Dry run
    # ------------------------------------------------------------------
    def _plan_layer(self, config: LayerConfig) -> dict:
        """Report what a real run would do for this layer, writing nothing."""
        existing = GISSource.objects.filter(layer_name=config.layer_name).first()
        current_status = existing.last_status if existing else "never_synced"
        if not config.enabled:
            action = "skip (disabled)"
            status = GISSource.STATUS_DISABLED
        else:
            action = "download, hash, and extract if changed"
            status = current_status
        return {
            "layer_name": config.layer_name,
            "status": status,
            "action": action,
            "raw_path": str(raw_dir_for(config.layer_name) / "source.zip"),
            "extracted_path": str(extracted_dir_for(config.layer_name)),
            "error": "",
        }

    # ------------------------------------------------------------------
    # Real sync
    # ------------------------------------------------------------------
    def _sync_layer(self, config: LayerConfig, *, force: bool) -> dict:
        raw_dir = raw_dir_for(config.layer_name)
        extracted_dir = extracted_dir_for(config.layer_name)
        raw_zip = raw_dir / "source.zip"

        source, _ = GISSource.objects.get_or_create(layer_name=config.layer_name)
        self._apply_config_fields(source, config)
        source.raw_file_path = str(raw_zip)
        source.extracted_path = str(extracted_dir)

        if not config.enabled:
            source.enabled = False
            source.last_status = GISSource.STATUS_DISABLED
            source.last_error = ""
            source.save()
            self.stdout.write(f"{config.layer_name}: disabled, skipping.")
            return self._result(config.layer_name, source.last_status, raw_zip, extracted_dir)

        previous_hash = source.source_hash or ""

        # 1. Download to a temp file first so a failed download never clobbers
        #    the previous good source.zip.
        raw_dir.mkdir(parents=True, exist_ok=True)
        try:
            new_zip = self._download(config.url, raw_dir)
        except Exception as exc:  # noqa: BLE001 -- one layer must not crash the run
            source.last_status = GISSource.STATUS_DOWNLOAD_FAILED
            source.last_error = f"download failed: {exc}"
            source.save()
            self.stdout.write(self.style.WARNING(f"{config.layer_name}: {source.last_error}"))
            return self._result(config.layer_name, source.last_status, raw_zip, extracted_dir, error=str(exc))

        new_hash = sha256_file(new_zip)
        changed = new_hash != previous_hash
        retry_after_failure = source.last_status == GISSource.STATUS_EXTRACT_FAILED
        need_extract = force or changed or retry_after_failure

        # Promote the freshly downloaded file into place and record its hash.
        new_zip.replace(raw_zip)
        (raw_dir / "source_hash.txt").write_text(new_hash + "\n", encoding="utf-8")
        now = timezone.now()
        (raw_dir / "downloaded_at.txt").write_text(now.isoformat() + "\n", encoding="utf-8")

        source.previous_source_hash = previous_hash
        source.source_hash = new_hash
        source.last_downloaded_at = now
        source.last_error = ""

        if need_extract:
            try:
                extract_shapefile_zip(raw_zip, extracted_dir)
            except GISConfigError as exc:
                # Extraction failed: the previous extracted folder is left intact.
                source.last_status = GISSource.STATUS_EXTRACT_FAILED
                source.last_error = f"extract failed: {exc}"
                source.save()
                self.stdout.write(self.style.WARNING(f"{config.layer_name}: {source.last_error}"))
                return self._result(config.layer_name, source.last_status, raw_zip, extracted_dir, error=str(exc))

        if changed:
            source.last_status = GISSource.STATUS_CHANGED
            source.last_changed_at = now
            message = "changed" + (" (re-extracted)" if need_extract else "")
        else:
            source.last_status = GISSource.STATUS_UNCHANGED
            message = "unchanged" + (" (force re-extracted)" if need_extract and force else "")
        source.save()

        self.stdout.write(f"{config.layer_name}: {message}.")
        return self._result(config.layer_name, source.last_status, raw_zip, extracted_dir)

    def _apply_config_fields(self, source: GISSource, config: LayerConfig) -> None:
        source.display_name = config.display_name
        source.url = config.url
        source.enabled = config.enabled
        source.expected_geometry_type = config.expected_geometry_type
        source.refresh_frequency = config.refresh_frequency

    def _download(self, url: str, dest_dir: Path) -> Path:
        """Download ``url`` into a temp file inside ``dest_dir`` and return its path."""
        fd, tmp_name = tempfile.mkstemp(prefix="download_", suffix=".zip", dir=dest_dir)
        os.close(fd)  # we only want mkstemp's unique path; open it ourselves below
        tmp_path = Path(tmp_name)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "OpenSkagit-GIS-Sync/1.0"})
            with urllib.request.urlopen(request, timeout=120) as response, tmp_path.open("wb") as handle:
                shutil.copyfileobj(response, handle)
        except (urllib.error.URLError, OSError):
            tmp_path.unlink(missing_ok=True)
            raise
        return tmp_path

    def _result(self, layer_name, status, raw_zip, extracted_dir, error="") -> dict:
        return {
            "layer_name": layer_name,
            "status": status,
            "raw_path": str(raw_zip),
            "extracted_path": str(extracted_dir),
            "error": error,
        }

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def _print_summary(self, results: list[dict], *, dry_run: bool) -> None:
        out = self.stdout
        out.write("")
        if dry_run:
            out.write("GIS source sync DRY RUN -- no files or database rows were changed.")
        else:
            out.write("GIS source sync complete.")
        out.write("")

        changed = [r for r in results if r["status"] == GISSource.STATUS_CHANGED]
        unchanged = [r for r in results if r["status"] == GISSource.STATUS_UNCHANGED]
        disabled = [r for r in results if r["status"] == GISSource.STATUS_DISABLED]
        failed = [
            r for r in results
            if r["status"] in (GISSource.STATUS_DOWNLOAD_FAILED, GISSource.STATUS_EXTRACT_FAILED)
        ]

        out.write(f"Layers checked: {len(results)}")
        out.write(f"Changed: {len(changed)}")
        out.write(f"Unchanged: {len(unchanged)}")
        out.write(f"Failed: {len(failed)}")
        out.write(f"Disabled: {len(disabled)}")

        if changed:
            out.write("")
            out.write("Changed layers:")
            for r in changed:
                out.write(f"- {r['layer_name']}")

        if failed:
            out.write("")
            out.write("Failed layers:")
            for r in failed:
                out.write(f"- {r['layer_name']}: {r['status']}: {r['error']}")

        out.write("")
        out.write("Paths:")
        for r in results:
            out.write(f"- {r['layer_name']}")
            out.write(f"    raw:       {r['raw_path']}")
            out.write(f"    extracted: {r['extracted_path']}")
