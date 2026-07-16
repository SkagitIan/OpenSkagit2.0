from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from . import services


class ContextServiceTests(SimpleTestCase):
    def test_clean_parcel_normalizes_numeric_ids(self):
        self.assertEqual(services.clean_parcel("96023"), "P96023")
        with self.assertRaises(ValueError):
            services.clean_parcel("not-a-parcel")

    def test_shape_acs_preserves_counts_and_derives_rates(self):
        shaped = services._shape_acs(
            {
                "total_population": 100,
                "race_total": 100,
                "white_alone": 75,
                "households": 40,
                "poverty_universe": 80,
                "below_poverty": 8,
                "education_25_plus_total": 50,
                "bachelors_degree": 10,
                "masters_degree": 5,
                "professional_degree": 0,
                "doctorate_degree": 0,
                "housing_units": 50,
                "vacant_housing_units": 5,
                "occupied_housing_units": 45,
                "owner_occupied_units": 30,
                "renter_occupied_units": 15,
                "workers_commute_total": 20,
                "aggregate_commute_minutes": 600,
            }
        )
        self.assertEqual(shaped["demographics"]["total_population"], 100)
        self.assertEqual(shaped["demographics"]["race_ethnicity"]["white_alone_pct"], 75.0)
        self.assertEqual(shaped["socioeconomic"]["poverty_rate_pct"], 10.0)
        self.assertEqual(shaped["commute"]["mean_commute_minutes"], 30.0)

    @patch("context_mcp.services.parcel_spatial_context")
    @patch("context_mcp.services.requests.post")
    def test_soils_uses_postgis_geometry_and_shapes_nrcs_rows(self, post, spatial):
        spatial.return_value = {
            "parcel": "P96023",
            "centroid": {"longitude": -122.3, "latitude": 48.4},
            "geometry_wkt": "MULTIPOLYGON(((-122 48,-122 49,-121 49,-122 48)))",
        }
        response = MagicMock()
        response.json.return_value = {
            "Table": [
                ["mukey", "musym", "muname", "drclassdcd"],
                ["1", "A1", "Example soil", "Well drained"],
            ]
        }
        post.return_value = response

        result = services.get_soils_context("P96023")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["mapunit_count"], 1)
        self.assertEqual(result["mapunits"][0]["muname"], "Example soil")
        self.assertIn("MULTIPOLYGON", post.call_args.kwargs["data"]["QUERY"])
        self.assertIn("mu.farmlndcl", post.call_args.kwargs["data"]["QUERY"])

    @patch("context_mcp.services.requests.get")
    def test_census_reporter_fallback_maps_acs_columns(self, get):
        response = MagicMock()
        response.json.return_value = {
            "data": {
                "05000US53057": {
                    "B01003": {"estimate": {"B01003001": 131328}},
                }
            },
            "geography": {"05000US53057": {"name": "Skagit County, WA"}},
            "release": {"id": "acs2024_5yr", "name": "ACS 2024 5-year"},
        }
        get.return_value = response

        result = services._census_reporter_query(
            {
                "county": {"state": "53", "county": "057", "name": "Skagit County"},
            }
        )

        self.assertEqual(result["results"]["county"]["demographics"]["total_population"], 131328)
        self.assertEqual(result["release"]["id"], "acs2024_5yr")
