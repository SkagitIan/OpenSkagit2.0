from __future__ import annotations
from unittest.mock import patch
from django.test import SimpleTestCase
from graph.cypher_tool import validate_cypher
from opportunity.ai_search import GeneratedSearch, _fallback_search_plan, _run_generated_search

class CypherToolTests(SimpleTestCase):
    def test_validator_injects_and_caps_limit(self):
        self.assertTrue(validate_cypher("MATCH (p:Parcel) RETURN p.pid", limit=50).endswith("LIMIT 50"))
        self.assertTrue(validate_cypher("MATCH (p:Parcel) RETURN p.pid LIMIT 999", limit=50).endswith("LIMIT 50"))
    def test_validator_rejects_mutations_and_identity_returns(self):
        for query in ("MATCH (p:Parcel) CREATE (x:Parcel {pid: 'X'}) RETURN p.pid", "MATCH (e:Entity) RETURN e.entity_id", "RETURN 1"):
            with self.assertRaises(ValueError):
                validate_cypher(query)
    def test_graph_and_sql_targets_use_separate_execution_paths(self):
        graph_generated = GeneratedSearch("Graph", "Graph", "", [], "MATCH (p:Parcel) RETURN p.pid AS parcel_number", [], "cypher")
        with patch("graph.cypher_tool.execute_cypher", return_value=[{"parcel_number": "P1"}]) as graph_execute, patch("opportunity.ai_search.hydrate_result_rows", side_effect=lambda rows: rows):
            rows = _run_generated_search("adjacent parcels", graph_generated)
        self.assertEqual(rows[0]["parcel_number"], "P1")
        graph_execute.assert_called_once()
        self.assertEqual(_fallback_search_plan("adjacent vacant lots").execution_target, "graph")
        self.assertEqual(_fallback_search_plan("vacant lots over 2 acres in Burlington").execution_target, "sql")