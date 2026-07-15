from __future__ import annotations
from django.test import SimpleTestCase
from pathlib import Path
from tempfile import TemporaryDirectory
from graph.kuzu_build import GraphTables, build_kuzu_database
from graph.kuzu_build import is_vacant_buildable
class KuzuBuildTests(SimpleTestCase):
    def test_vacant_buildable_excludes_resource_and_open_space_codes(self):
        self.assertTrue(is_vacant_buildable("(911) UNDEVELOPED LAND", "LIR", "R5"))
        self.assertFalse(is_vacant_buildable("(940) OPEN SPACE", "OS", "OS"))
        self.assertFalse(is_vacant_buildable("(911) UNDEVELOPED LAND", "NRL", "R5-NRL"))
    def test_kuzu_copy_loads_fixture_nodes_and_edges(self):
        with TemporaryDirectory() as tmp:
            tables = GraphTables(
                parcels=[{"pid":"P1","acres":1.0,"land_use":"(911) LAND","zone_id":"R5","city_name":"BURLINGTON","assessed_value":1.0,"building_value":0.0,"land_value":1.0,"year_built":0,"utilities":"SEW","is_vacant_buildable":True,"delinquent_years":0}],
                entities=[{"entity_id":"E1","canonical_name":"TEST LLC","kind":"llc"}], groups=[{"group_id":"G1"}], recordings=[{"recording_number":"R1","document_type":"DEED","signal_group":"transfer","recorded_date":"2026-01-01"}],
                owns=[{"FROM":"E1","TO":"P1"}], member_of=[{"FROM":"E1","TO":"G1"}], adjacency=[], affects=[{"FROM":"R1","TO":"P1"}],
            )
            counts = build_kuzu_database(Path(tmp) / "db", tables, Path(tmp) / "csv")
            self.assertEqual(counts["parcel_nodes"], 1)
            self.assertEqual(counts["owns_edges"], 1)