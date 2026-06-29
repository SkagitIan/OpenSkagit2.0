from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from zoning_mcp import services


class Command(BaseCommand):
    help = "Exercise the local zoning MCP service layer with representative calls."

    def add_arguments(self, parser):
        parser.add_argument("--parcel", default="", help="Optional parcel ID to resolve and inspect.")
        parser.add_argument("--jurisdiction", default="skagit_county")
        parser.add_argument("--zone", default="RC")
        parser.add_argument("--use", default="restaurant")
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        payload = {
            "zone_profile": services.get_zone_profile(options["jurisdiction"], options["zone"]),
            "use_status": services.lookup_use_status(options["jurisdiction"], options["zone"], options["use"]),
            "allowed_uses": services.list_allowed_uses(options["jurisdiction"], options["zone"], ["P", "AD", "HE", "CUP"]),
            "compare_zones": services.compare_zones_for_use(options["use"], [options["jurisdiction"]]),
        }
        if options["parcel"]:
            payload["parcel"] = services.resolve_parcel(parcel_id=options["parcel"])
            payload["overlays"] = services.get_overlays_and_constraints(options["parcel"])
        if options["json"]:
            self.stdout.write(json.dumps(payload, indent=2, default=str))
            return
        status = payload["use_status"]
        self.stdout.write(f"{options['use']} in {options['jurisdiction']} {options['zone']}: {status['status']} ({status['status_label']})")
        self.stdout.write(f"matched use: {status['matched_use']} from {status['source_table']}")
        self.stdout.write(f"allowed/reviewable uses found: {len(payload['allowed_uses']['allowed_uses'])}")
