"""Run internal Kuzu graph patterns and persist public-safe opportunity results.

This command does not serialize owner names, entity IDs, mailing addresses, or
entity membership. Legacy SQL comparison is a diagnostic only and is not the
serving source.
"""
from __future__ import annotations
import time
from uuid import uuid4
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from graph.models import GraphOpportunityResult
from graph.patterns import all_pattern_results

class Command(BaseCommand):
    help = "Precompute graph opportunity patterns into graph_opportunity_results."
    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=2500)
        parser.add_argument("--graph", help="Path to the Kuzu zip artifact.")
    def handle(self, *args, **options):
        started = time.monotonic()
        run_id = uuid4().hex
        try:
            results = all_pattern_results(options["graph"]) if options["graph"] else all_pattern_results()
            result_rows = []
            for pattern_key, rows in results.items():
                seen_parcels = set()
                rank = 0
                for row in rows:
                    if row["parcel_number"] in seen_parcels:
                        continue
                    seen_parcels.add(row["parcel_number"])
                    rank += 1
                    if rank > options["limit"]:
                        break
                    result_rows.append(GraphOpportunityResult(pattern_key=pattern_key, parcel_number=row["parcel_number"], score=row["score"], rank=rank, detail=row["detail"], run_id=run_id))
            with transaction.atomic():
                GraphOpportunityResult.objects.all().delete()
                GraphOpportunityResult.objects.bulk_create(result_rows, batch_size=1000)
            comparison = self._compare_legacy(results.get("assemblage", []), options["limit"])
            for parcel_number in comparison.get("legacy_only_ids", []):
                self.stdout.write(f"Legacy-only assemblage parcel {parcel_number}: SQL proximity/raw-owner heuristic not represented by shared-boundary/common-control graph pattern.")
            self.stdout.write(self.style.SUCCESS(f"Graph patterns complete: run_id={run_id} assemblage={len(results.get('assemblage', [])):,} infill={len(results.get('infill', [])):,} estate_signal={len(results.get('estate_signal', [])):,} stored={len(result_rows):,} overlap={comparison['overlap']:,} graph_only={comparison['graph_only']:,} legacy_only={comparison['legacy_only']:,} runtime={time.monotonic()-started:.1f}s"))
        except Exception as exc:  # noqa: BLE001 - command must fail nonzero
            raise CommandError(f"Graph patterns failed: {exc}") from exc
    def _compare_legacy(self, graph_rows: list[dict], limit: int) -> dict[str, int]:
        try:
            from opportunity.services import _assemblage_opportunities_sql_legacy
            legacy = _assemblage_opportunities_sql_legacy({"min_cluster": "2"}, limit)
            graph_ids = {row["parcel_number"] for row in graph_rows}
            legacy_ids = {row.get("parcel_number") for row in legacy}
            return {"overlap": len(graph_ids & legacy_ids), "graph_only": len(graph_ids - legacy_ids), "legacy_only": len(legacy_ids - graph_ids), "legacy_only_ids": sorted(legacy_ids - graph_ids)}
        except Exception as exc:  # comparison must not hide a successful graph build
            self.stdout.write(self.style.WARNING(f"Legacy comparison unavailable: {exc}"))
            return {"overlap": 0, "graph_only": 0, "legacy_only": 0, "legacy_only_ids": []}