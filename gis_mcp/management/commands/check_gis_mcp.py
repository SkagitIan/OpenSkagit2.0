from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from gis_mcp import services


class Command(BaseCommand):
    help = "Exercise the local GIS MCP service layer with a representative parcel overlay call."

    def add_arguments(self, parser):
        parser.add_argument("--parcel", default="P96023", help="Parcel ID used for GIS checks.")
        parser.add_argument("--bundles", default="core", help="Comma-separated GIS bundles to query.")
        parser.add_argument("--layers", default="", help="Optional comma-separated GIS layer keys to query.")
        parser.add_argument("--json", action="store_true", help="Print the full JSON payload.")

    def handle(self, *args, **options):
        try:
            payload = {
                "rule": services.gis_answer_rule(),
                "layers": services.list_gis_layers(),
                "parcel_overlays": services.get_parcel_overlays(
                    options["parcel"],
                    bundles=options["bundles"] or None,
                    layers=options["layers"] or None,
                    include_parcel_geometry=False,
                ),
            }
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2, default=str))
            return

        overlays = payload["parcel_overlays"]["overlays"]
        ok_count = sum(1 for overlay in overlays if overlay.get("status") == "ok")
        feature_count = sum(int(overlay.get("count") or 0) for overlay in overlays)
        self.stdout.write(
            self.style.SUCCESS(
                f"GIS MCP checked {len(overlays)} layers for {payload['parcel_overlays']['parcel']}: "
                f"{ok_count} ok, {feature_count} intersecting features."
            )
        )
