from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from zoning_mcp.duckdb_parcel_search import normalize_parcel_search_jurisdiction, resolve_parcel_from_parquet
from zoning_mcp.parcel_search_semantics import get_parcel_search_semantic_guide
from zoning_mcp import services


@override_settings(DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}})
class ParcelSearchDuckDBTests(SimpleTestCase):
    def test_normalize_jurisdiction_city_mapping(self):
        self.assertEqual(normalize_parcel_search_jurisdiction("MOUNT VERNON", True), "mount_vernon")
        self.assertEqual(normalize_parcel_search_jurisdiction("BURLINGTON", True), "burlington")
        self.assertEqual(normalize_parcel_search_jurisdiction("SEDRO-WOOLLEY", True), "sedro_woolley")
        self.assertEqual(normalize_parcel_search_jurisdiction("ANACORTES", True), "anacortes")
        self.assertEqual(normalize_parcel_search_jurisdiction("CONCRETE", True), "concrete")
        self.assertEqual(normalize_parcel_search_jurisdiction("LA CONNER", True), "la_conner")
        self.assertEqual(normalize_parcel_search_jurisdiction("MOUNT VERNON", False), "skagit_county")
        self.assertEqual(normalize_parcel_search_jurisdiction(None, True), "skagit_county")

    @patch("zoning_mcp.duckdb_parcel_search.get_duckdb_connection")
    def test_resolve_parcel_from_parquet_uses_parameterized_query(self, mock_connection):
        cursor = MagicMock()
        row = (
            "P123", "1 Main St", "Mount Vernon WA", "MOUNT VERNON", True,
            "R-1", "Residential", False, False, 1.25, "Residential", 250000,
            1200, 1500, 1, 1990, 4,
        )
        cursor.execute.return_value = cursor
        cursor.fetchall.return_value = [row]
        cursor.description = [(name,) for name in [
            "parcel_number", "situs_address", "situs_city_state_zip", "city_name", "inside_city_limits",
            "zoning_code_short", "zoning_label", "has_geometry", "has_situs_address", "acres", "land_use",
            "assessed_value", "primary_building_living_area", "total_living_area", "improvement_building_count",
            "primary_actual_year_built", "years_since_last_valid_sale",
        ]]
        mock_connection.return_value = cursor

        result = resolve_parcel_from_parquet(parcel_id="P123'; DROP TABLE parcels; --")

        sql, params = cursor.execute.call_args.args
        self.assertIn("read_parquet(?)", sql)
        self.assertIn("upper(parcel_number) = upper(?)", sql)
        self.assertEqual(params[1], "P123'; DROP TABLE parcels; --")
        self.assertTrue(result["found"])
        self.assertEqual(result["jurisdiction"], "mount_vernon")
        self.assertIn("missing geometry", result["notes"])

    @patch("zoning_mcp.services._resolve_parcel_from_database")
    @patch("zoning_mcp.duckdb_parcel_search.resolve_parcel_from_parquet", side_effect=RuntimeError("r2 unavailable"))
    def test_services_resolve_parcel_falls_back_when_duckdb_fails(self, _mock_duckdb, mock_database):
        mock_database.return_value = {"found": True, "parcel_id": "P123", "source": "db"}

        result = services.resolve_parcel(parcel_id="P123")

        self.assertEqual(result["source"], "db")
        mock_database.assert_called_once_with(parcel_id="P123", address=None)

    @patch("zoning_mcp.services.get_overlays_and_constraints", return_value={"notes": []})
    @patch("zoning_mcp.services.get_development_standards", return_value={"source_matches": []})
    @patch("zoning_mcp.services.lookup_use_status", return_value={"status": "P", "matched_use": "ADU"})
    @patch("zoning_mcp.services.get_zone_profile", return_value={"source_url": "", "zone_name": "Residential"})
    @patch("zoning_mcp.services.resolve_parcel")
    def test_build_parcel_feasibility_report_includes_existing_keys_plus_caveats(self, mock_resolve, *_mocks):
        mock_resolve.return_value = {
            "found": True,
            "ambiguous": False,
            "parcel_id": "P123",
            "jurisdiction": "mount_vernon",
            "jurisdiction_label": "Mount Vernon",
            "zoning_code": "R-1",
            "zoning_name": "Residential",
            "notes": "zoning_code_short is a parcel data signal.",
        }

        report = services.build_parcel_feasibility_report("P123", "ADU")

        for key in ["parcel", "zone_profile", "use_status", "development_standards", "overlays", "citations", "caveats"]:
            self.assertIn(key, report)
        self.assertTrue(report["caveats"])
        self.assertTrue(any("Assessed value is not market value" in caveat for caveat in report["caveats"]))

    def test_parcel_search_semantics_returns_useful_guide(self):
        guide = get_parcel_search_semantic_guide()
        self.assertIn("parcel_search.parquet", guide)
        self.assertIn("primary_building_living_area", guide)
        self.assertIn("not legal zoning authority", guide)
        self.assertGreater(len(guide), 200)
