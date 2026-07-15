from __future__ import annotations
from graph.entities import classify_entity, cluster_entities, normalize_owner_name, normalize_mailing_address
from django.test import SimpleTestCase

class EntityResolutionTests(SimpleTestCase):
    def test_joint_owner_variants_canonicalize_together(self):
        self.assertEqual(normalize_owner_name("SMITH JOHN & JANE"), normalize_owner_name("SMITH, JOHN R & JANE M"))
    def test_classification(self):
        self.assertEqual(classify_entity("ACME LLC"), "llc")
        self.assertEqual(classify_entity("SMITH FAMILY TRUST"), "trust")
        self.assertEqual(classify_entity("CITY OF BURLINGTON"), "gov")
    def test_junk_mailing_key_is_skipped(self):
        rows = [{"owner_name": f"OWNER {i}", "parcel_number": str(i), "owner_add_1": "1 MAIN STREET", "owner_city": "BURLINGTON", "owner_state": "WA", "owner_zip": "98233"} for i in range(3)]
        result = cluster_entities(rows, mailing_threshold=2)
        self.assertEqual(result.groups, ())
        self.assertEqual(len(result.junk_mailing_keys), 1)
    def test_entity_id_is_deterministic(self):
        rows = [{"owner_name": "ACME LLC", "parcel_number": "P1"}]
        self.assertEqual(cluster_entities(rows).entities[0].entity_id, cluster_entities(rows).entities[0].entity_id)
    def test_address_is_normalized(self):
        self.assertEqual(normalize_mailing_address("1 Main Street", "", "", "Burlington", "wa", "98233"), "1 MAIN ST BURLINGTON WA 98233")