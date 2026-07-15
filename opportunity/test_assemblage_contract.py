from __future__ import annotations
from django.test import SimpleTestCase
from opportunity import services
from graph.patterns import _safe_detail

class AssemblageContractTests(SimpleTestCase):
    def test_existing_assemblage_formatter_contract_remains_stable(self):
        row = {
            "parcel_number": "P1", "owner_name": "INTERNAL OWNER", "address": "1 MAIN ST", "city": "BURLINGTON",
            "acres": 1.0, "land_use": "(911) LAND", "land_use_code": "911", "zone_id": "R5", "zone_name": "Residential",
            "waza_general": "LIR", "waza_specific": "", "reference_url": "", "assessed_value": 1000,
            "building_value": 0, "impr_land_value": 1000, "unimpr_land_value": 0, "lat": 48.4, "lng": -122.3,
            "cluster_count": 1, "cluster_acres": 1.0, "vacant_like_count": 1, "neighbor_zone_count": 1,
            "delinquent_neighbors": 0,
        }
        item = services._format_assemblage(row)
        for field in ("parcel_number", "location", "owner", "acres_fmt", "zoning", "assessed_value_fmt", "score", "why_it_ranks", "risk_flags"):
            self.assertIn(field, item)

    def test_graph_pattern_detail_allowlist_rejects_identity_fields(self):
        with self.assertRaises(ValueError):
            _safe_detail({"cluster_count": 2, "owner_name": "LEAK"})
        with self.assertRaises(ValueError):
            _safe_detail({"entity_id": "ent_secret"})