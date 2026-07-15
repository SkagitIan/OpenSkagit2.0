"""Build internal graph entity and ownership-group tables from assessor data.

This command does not expose owner identities or mailing addresses publicly.
"""
from __future__ import annotations
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import AssessorRollup, SkagitParcel
from graph.entities import cluster_entities
from graph.models import GraphEntity, GraphEntityParcel, GraphOwnershipGroup

class Command(BaseCommand):
    help = "Resolve assessor owner rows into internal graph entities and groups."
    def add_arguments(self, parser):
        parser.add_argument("--mailing-threshold", type=int, default=25)
    def handle(self, *args, **options):
        rows = list(AssessorRollup.objects.values("parcel_number", "owner_name", "owner_add_1", "owner_add_2", "owner_add_3", "owner_city", "owner_state", "owner_zip"))
        seen = {row["parcel_number"] for row in rows if row["parcel_number"]}
        fallback = SkagitParcel.objects.exclude(parcel_number__in=seen).values("parcel_number", "owner_name", "owner_city", "owner_state", "owner_zip")
        rows.extend({**row, "owner_add_1": None, "owner_add_2": None, "owner_add_3": None} for row in fallback)
        resolution = cluster_entities(rows, mailing_threshold=options["mailing_threshold"])
        with transaction.atomic():
            GraphOwnershipGroup.objects.all().delete()
            GraphEntityParcel.objects.all().delete()
            GraphEntity.objects.all().delete()
            GraphEntity.objects.bulk_create([GraphEntity(entity_id=e.entity_id, canonical_name=e.canonical_name, kind=e.kind, raw_name_count=len(e.raw_names)) for e in resolution.entities])
            GraphEntityParcel.objects.bulk_create([GraphEntityParcel(entity_id=entity_id, parcel_number=parcel) for entity_id, parcel in resolution.entity_parcels], ignore_conflicts=True)
            GraphOwnershipGroup.objects.bulk_create([GraphOwnershipGroup(group_id=g.group_id, member_entity_ids=list(g.member_entity_ids), link_reason=g.link_reason, mailing_key=g.mailing_key) for g in resolution.groups])
        self.stdout.write(self.style.SUCCESS(f"Graph entities complete: entities={len(resolution.entities)} parcels={len(resolution.entity_parcels)} groups={len(resolution.groups)} junk_keys_skipped={len(resolution.junk_mailing_keys)} unresolved_rows={resolution.unresolved_rows}"))