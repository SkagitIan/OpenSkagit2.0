"""Build the internal Kuzu parcel relationship graph and zip its artifact.

This command reads existing Postgres tables and graph adjacency/entity tables;
it does not download GIS data, expose owner data, or upload credentials to a
new service.
"""
from __future__ import annotations
import shutil
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from assessor_sync.models import AuditorRecording, ParcelGeoStaticFeature
from core.models import AssessorRollup, ParcelPrimaryZoning, SkagitParcel
from tax_delinquency.models import TaxStatement
from graph.models import GraphBuildState, GraphEntity, GraphEntityParcel, GraphOwnershipGroup, GraphParcelAdjacency
from graph.kuzu_build import GraphTables, build_kuzu_database, is_vacant_buildable


def number(value, default=0.0):
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def integer(value, default=0):
    try:
        return int(float(value)) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default

def clean_text(value) -> str:
    return "" if value is None else str(value)

class Command(BaseCommand):
    help = "Build data/processed/skagit_graph.kuzu.zip from Postgres and graph tables. Uploading is intentionally omitted; no object-storage pattern exists in this branch."
    def add_arguments(self, parser):
        parser.add_argument("--output", default=str(Path(settings.BASE_DIR) / "data" / "processed" / "skagit_graph.kuzu.zip"))
        parser.add_argument("--keep-intermediate", action="store_true", help="Keep CSV intermediates for inspection.")
    def handle(self, *args, **options):
        started = time.monotonic()
        output_zip = Path(options["output"]).resolve()
        if not output_zip.is_relative_to(Path(settings.BASE_DIR).resolve()):
            raise CommandError("Output must be inside the project directory.")
        work_root = output_zip.parent / f"{output_zip.stem}.build"
        artifact_dir = work_root / "artifact"
        database_dir = artifact_dir / "skagit_graph.kuzu"
        csv_dir = work_root / "csv"
        try:
            tables = self._load_tables()
            counts = build_kuzu_database(database_dir, tables, csv_dir)
            output_zip.parent.mkdir(parents=True, exist_ok=True)
            output_zip.unlink(missing_ok=True)
            archive_base = output_zip.with_suffix("")
            archive = Path(shutil.make_archive(str(archive_base), "zip", root_dir=artifact_dir))
            if archive != output_zip:
                archive.replace(output_zip)
            with transaction.atomic():
                GraphBuildState.objects.update_or_create(key="parcel_graph", defaults={"last_success_at": timezone.now(), "summary": counts})
            self.stdout.write(self.style.SUCCESS(f"Parcel graph complete: {counts} zip_bytes={output_zip.stat().st_size:,} runtime={time.monotonic()-started:.1f}s output={output_zip}"))
        except Exception as exc:  # noqa: BLE001 - management command must exit nonzero
            raise CommandError(f"Parcel graph failed: {exc}") from exc
        finally:
            if not options["keep_intermediate"]:
                shutil.rmtree(work_root, ignore_errors=True)

    def _load_tables(self) -> GraphTables:
        parcels = list({row["parcel_number"]: row for row in SkagitParcel.objects.filter(inactive_date__isnull=True).values("parcel_number", "acres", "land_use", "assessed_value", "building_value", "utilities", "year_built", "city_district") if row["parcel_number"]}.values())
        active = {row["parcel_number"] for row in parcels if row["parcel_number"]}
        zoning = {row["parcel_id"]: row for row in ParcelPrimaryZoning.objects.filter(parcel_id__in=active).values("parcel_id", "zone_id", "waza_general")}
        rollup = {row["parcel_number"]: row for row in AssessorRollup.objects.filter(parcel_number__in=active).values("parcel_number", "impr_land_value", "unimpr_land_value", "year_built")}
        geo = {row["parcel_number"]: row for row in ParcelGeoStaticFeature.objects.filter(parcel_number__in=active).values("parcel_number", "city_name")}
        delinquent = {}
        for row in TaxStatement.objects.filter(parcel_number__in=active, total_due__gt=0).values("parcel_number", "tax_year"):
            delinquent.setdefault(row["parcel_number"], set()).add(row["tax_year"])
        parcel_rows = []
        for row in parcels:
            pid = row["parcel_number"]
            zone = zoning.get(pid, {})
            assessor = rollup.get(pid, {})
            land_value = number(assessor.get("impr_land_value")) + number(assessor.get("unimpr_land_value"))
            parcel_rows.append({"pid": pid, "acres": number(row["acres"]), "land_use": clean_text(row["land_use"]), "zone_id": clean_text(zone.get("zone_id")), "city_name": clean_text((geo.get(pid) or {}).get("city_name") or row.get("city_district")), "assessed_value": number(row["assessed_value"]), "building_value": number(row["building_value"]), "land_value": land_value, "year_built": integer(row["year_built"] or assessor.get("year_built")), "utilities": clean_text(row["utilities"]), "is_vacant_buildable": is_vacant_buildable(row["land_use"], zone.get("waza_general"), zone.get("zone_id")), "delinquent_years": len(delinquent.get(pid, set()))})
        entity_rows = [{"entity_id": row.entity_id, "canonical_name": row.canonical_name, "kind": row.kind} for row in GraphEntity.objects.all()]
        entity_ids = {row["entity_id"] for row in entity_rows}
        parcel_ids = active
        owns = [{"FROM": row["entity_id"], "TO": row["parcel_number"]} for row in GraphEntityParcel.objects.filter(parcel_number__in=parcel_ids, entity_id__in=entity_ids).values("entity_id", "parcel_number")]
        group_rows = [{"group_id": row.group_id} for row in GraphOwnershipGroup.objects.all()]
        member_of = []
        for group in GraphOwnershipGroup.objects.all().only("group_id", "member_entity_ids"):
            member_of.extend({"FROM": entity_id, "TO": group.group_id} for entity_id in group.member_entity_ids if entity_id in entity_ids)
        adjacency = [{"FROM": row["pid_a"], "TO": row["pid_b"], "shared_boundary_ft": row["shared_boundary_ft"]} for row in GraphParcelAdjacency.objects.filter(pid_a__in=parcel_ids, pid_b__in=parcel_ids).values("pid_a", "pid_b", "shared_boundary_ft")]
        recording_rows, affects = [], []
        for row in AuditorRecording.objects.exclude(recording_number="").values("recording_number", "document_type", "signal_group", "recorded_date", "parcel_number"):
            recording_rows.append({"recording_number": row["recording_number"], "document_type": clean_text(row["document_type"]), "signal_group": clean_text(row["signal_group"]), "recorded_date": row["recorded_date"].isoformat() if row["recorded_date"] else ""})
            for pid in clean_text(row["parcel_number"]).replace(";", ",").split(","):
                pid = pid.strip()
                if pid in parcel_ids:
                    affects.append({"FROM": row["recording_number"], "TO": pid})
        return GraphTables(parcel_rows, entity_rows, group_rows, recording_rows, owns, member_of, adjacency, affects)