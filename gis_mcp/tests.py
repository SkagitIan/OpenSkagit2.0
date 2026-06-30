from __future__ import annotations

import json
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from gis_mcp.layers import GIS_LAYERS, GisLayerConfig
from gis_mcp import services


class GisMcpServiceTests(SimpleTestCase):
    def test_clean_parcel_accepts_prefixed_and_numeric_values(self):
        self.assertEqual(services.clean_parcel("P96023"), "P96023")
        self.assertEqual(services.clean_parcel("96023"), "P96023")

    def test_clean_parcel_rejects_invalid_values(self):
        with self.assertRaises(ValueError):
            services.clean_parcel("abc")

    def test_parse_layer_keys_deduplicates_bundles_and_layers(self):
        keys = services.parse_layer_keys(layers="zoning,uga,zoning", bundles="core")
        self.assertEqual(keys.count("zoning"), 1)
        self.assertEqual(keys.count("uga"), 1)
        self.assertIn("npdes", keys)

    def test_parse_layer_keys_rejects_unknown_bundle(self):
        with self.assertRaises(ValueError):
            services.parse_layer_keys(bundles="not_a_bundle")

    def test_existing_out_fields_uses_valid_configured_fields(self):
        layer = GisLayerConfig("test", "Test", "https://example.test/0", "A,B,C", "")
        metadata = {"fields": [{"name": "A"}, {"name": "C"}, {"name": "OBJECTID"}]}
        self.assertEqual(services.existing_out_fields(layer, metadata), "A,C")

    def test_existing_out_fields_falls_back_to_objectid(self):
        layer = GisLayerConfig("test", "Test", "https://example.test/0", "Missing", "")
        metadata = {"fields": [{"name": "OBJECTID"}]}
        self.assertEqual(services.existing_out_fields(layer, metadata), "OBJECTID")

    @patch("gis_mcp.services.requests.post")
    def test_arcgis_request_posts_query_payload(self, post):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"features": []}
        post.return_value = response
        layer = GIS_LAYERS["zoning"]

        services.arcgis_request(layer, {"where": "1=1", "returnGeometry": "false"})

        post.assert_called_once()
        _, kwargs = post.call_args
        self.assertEqual(post.call_args.args[0], f"{layer.url}/query")
        self.assertEqual(kwargs["data"]["f"], "json")
        self.assertEqual(kwargs["data"]["where"], "1=1")

    @patch("gis_mcp.services.arcgis_request")
    def test_get_parcel_gis_builds_parcel_query(self, arcgis_request):
        arcgis_request.return_value = {
            "features": [{"attributes": {"PARCELID": "P96023"}, "geometry": {"rings": []}}],
        }

        result = services.get_parcel_gis("P96023")

        self.assertEqual(result["attributes"]["PARCELID"], "P96023")
        params = arcgis_request.call_args.args[1]
        self.assertEqual(params["where"], "PARCELID = 'P96023'")
        self.assertEqual(params["outSR"], "4326")
        self.assertEqual(params["returnGeometry"], "true")

    @patch("gis_mcp.services.arcgis_request")
    @patch("gis_mcp.services.fetch_layer_metadata")
    def test_query_overlay_layer_uses_intersect_geometry(self, fetch_metadata, arcgis_request):
        fetch_metadata.return_value = {
            "name": "Zoning",
            "geometryType": "esriGeometryPolygon",
            "fields": [{"name": "OBJECTID"}, {"name": "ZONING_CODE"}],
        }
        arcgis_request.return_value = {"features": [{"attributes": {"OBJECTID": 1}}]}

        result = services.query_overlay_layer(GIS_LAYERS["zoning"], json.dumps({"rings": []}))

        self.assertEqual(result["status"], "ok")
        params = arcgis_request.call_args.args[1]
        self.assertEqual(params["geometryType"], "esriGeometryPolygon")
        self.assertEqual(params["spatialRel"], "esriSpatialRelIntersects")
        self.assertEqual(params["resultRecordCount"], "25")

    @patch("gis_mcp.services.query_overlay_layer")
    @patch("gis_mcp.services.get_parcel_gis")
    def test_get_parcel_overlays_preserves_per_layer_errors(self, get_parcel_gis, query_overlay_layer):
        get_parcel_gis.return_value = {"attributes": {"PARCELID": "P96023"}, "geometry": {"rings": []}}

        def side_effect(layer, geometry_text):
            if layer.key == "zoning":
                return {"layer": layer.key, "label": layer.label, "status": "ok", "count": 1, "features": []}
            raise RuntimeError("service unavailable")

        query_overlay_layer.side_effect = side_effect

        result = services.get_parcel_overlays("P96023", layers="zoning,uga")

        self.assertEqual([overlay["layer"] for overlay in result["overlays"]], ["zoning", "uga"])
        self.assertEqual(result["overlays"][0]["status"], "ok")
        self.assertEqual(result["overlays"][1]["status"], "query_error")
