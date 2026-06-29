from __future__ import annotations

from django.core.management.base import BaseCommand

from zoning_mcp.models import Jurisdiction, Zone, ZoningUseRule
from zoning_mcp.seed_data import JURISDICTIONS, SEED_RULES, ZONE_NAMES


class Command(BaseCommand):
    help = "Load structured zoning seed data into the zoning_mcp tables."

    def handle(self, *args, **options):
        jurisdictions = {}
        for key, data in JURISDICTIONS.items():
            jurisdiction, _ = Jurisdiction.objects.update_or_create(
                key=key,
                defaults={
                    "display_name": data["display_name"],
                    "code_source": data["code_source"],
                    "zoning_title": data["zoning_title"],
                    "source_url": data["source_url"],
                    "extraction_status": data["extraction_status"],
                },
            )
            jurisdictions[key] = jurisdiction

        zones = {}
        for jurisdiction_key, zone_map in ZONE_NAMES.items():
            jurisdiction = jurisdictions[jurisdiction_key]
            for zone_code, zone_name in zone_map.items():
                zone, _ = Zone.objects.update_or_create(
                    jurisdiction=jurisdiction,
                    zone_code=zone_code,
                    defaults={"zone_name": zone_name},
                )
                zones[(jurisdiction_key, zone_code)] = zone

        rule_count = 0
        for seed_rule in SEED_RULES:
            jurisdiction = jurisdictions[seed_rule.jurisdiction]
            for zone_code, status in seed_rule.zones.items():
                zone = zones[(seed_rule.jurisdiction, zone_code)]
                ZoningUseRule.objects.update_or_create(
                    jurisdiction=jurisdiction,
                    zone=zone,
                    normalized_use_key=seed_rule.normalized_use_key,
                    source_table=seed_rule.source_table,
                    defaults={
                        "use_category": seed_rule.use_category,
                        "use_name": seed_rule.use_name,
                        "local_status": status,
                        "normalized_status": status,
                        "source_url": seed_rule.source_url,
                        "notes": seed_rule.notes,
                    },
                )
                rule_count += 1

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(jurisdictions)} jurisdictions and {rule_count} zoning use rules."))
