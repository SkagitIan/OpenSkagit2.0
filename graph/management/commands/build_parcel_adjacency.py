"""Build graph parcel adjacency from the tracked assessor parcel shapefile.

This command does not download GIS data; ``sync_gis_sources`` owns downloads
and GISSource identifies the extracted parcel layer used here.
"""
from __future__ import annotations
from pathlib import Path
import geopandas as gpd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from assessor_sync.gis_sources import find_shapefile_members, sha256_file
from assessor_sync.models import GISSource
from assessor_sync import geo_features
from graph.adjacency import build_adjacency
from graph.models import GraphBuildState, GraphParcelAdjacency

STATE_KEY = "parcel_adjacency"

class Command(BaseCommand):
    help = "Build shared-boundary parcel adjacency from the tracked parcel shapefile."
    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Rebuild even when the tracked parcel hash is unchanged.")
    def handle(self, *args, **options):
        source = GISSource.objects.filter(layer_name="parcels", enabled=True).first()
        if not source or not source.extracted_path:
            raise CommandError("Tracked GISSource 'parcels' is missing an extracted_path; run sync_gis_sources first.")
        state = GraphBuildState.objects.filter(key=STATE_KEY).first()
        if not options["force"] and state and state.source_hash and state.source_hash == source.source_hash:
            self.stdout.write(f"Parcel adjacency skipped: source hash unchanged ({source.source_hash[:12]}...).")
            return
        shapefile = self._find_shapefile(Path(source.extracted_path))
        try:
            frame = geo_features.force_crs(gpd.read_file(shapefile))
            result = build_adjacency(frame)
        except Exception as exc:  # noqa: BLE001 - command must fail nonzero with readable context
            raise CommandError(f"Could not build parcel adjacency from {shapefile}: {exc}") from exc
        objects = [GraphParcelAdjacency(**row) for row in result.to_dict("records")]
        with transaction.atomic():
            GraphParcelAdjacency.objects.all().delete()
            GraphParcelAdjacency.objects.bulk_create(objects, batch_size=5000)
            GraphBuildState.objects.update_or_create(key=STATE_KEY, defaults={"source_hash": source.source_hash, "last_success_at": timezone.now(), "summary": {"rows": len(objects), "invalid_repaired": result.attrs.get("invalid_repaired", 0)}})
        self.stdout.write(self.style.SUCCESS(f"Parcel adjacency complete: rows={len(objects)} invalid_repaired={result.attrs.get('invalid_repaired', 0)} source_hash={source.source_hash[:12]}..."))
    def _find_shapefile(self, folder: Path) -> Path:
        members = find_shapefile_members(folder)
        paths = members.get(".shp", [])
        if not paths:
            raise CommandError(f"No parcel shapefile found under {folder}; run sync_gis_sources first.")
        return sorted(paths)[0]