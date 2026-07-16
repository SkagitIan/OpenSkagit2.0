import base64
import hashlib
import json
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth.models import AnonymousUser
from django.contrib.staticfiles import finders
from django.template.loader import get_template
from django.test import RequestFactory, SimpleTestCase

from . import views


class StaffUser:
    is_authenticated = True
    is_active = True
    is_staff = True


class NonStaffUser(StaffUser):
    is_staff = False


class BboxValidationTests(SimpleTestCase):
    def test_valid_bbox(self):
        self.assertEqual(views._parse_bbox("-122.40,48.40,-122.39,48.41"), (-122.4, 48.4, -122.39, 48.41))

    def test_rejects_missing_malformed_nonfinite_and_reversed_bbox(self):
        for bbox in (None, "1,2,3", "a,2,3,4", "nan,2,3,4", "-122,48,-123,49"):
            with self.subTest(bbox=bbox), self.assertRaises(ValueError):
                views._parse_bbox(bbox)

    def test_rejects_oversized_and_outside_bbox(self):
        for bbox in ("-122.6,48.2,-122.4,48.3", "-124,48,-123.99,48.01"):
            with self.subTest(bbox=bbox), self.assertRaises(ValueError):
                views._parse_bbox(bbox)


class FieldMapViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_page_redirects_anonymous_to_login_with_next(self):
        request = self.factory.get("/field/")
        request.user = AnonymousUser()
        response = views.field_map(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)
        self.assertIn("next=/field/", response.url)

    def test_page_redirects_nonstaff(self):
        request = self.factory.get("/field/")
        request.user = NonStaffUser()
        self.assertEqual(views.field_map(request).status_code, 302)

    @patch("field_map.views.render")
    def test_page_renders_for_staff(self, render):
        render.return_value = Mock(status_code=200)
        request = self.factory.get("/field/")
        request.user = StaffUser()
        response = views.field_map(request)
        self.assertEqual(response.status_code, 200)
        render.assert_called_once_with(request, "field_map/map.html")

    def test_api_rejects_anonymous_without_data(self):
        request = self.factory.get("/field/api/parcels/", {"bbox": "-122.4,48.4,-122.39,48.41"})
        request.user = AnonymousUser()
        response = views.parcels_geojson(request)
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("features", json.loads(response.content))
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_api_rejects_invalid_bbox_before_query(self):
        request = self.factory.get("/field/api/parcels/", {"bbox": "bad"})
        request.user = StaffUser()
        with patch("field_map.views._query_parcels") as query:
            response = views.parcels_geojson(request)
        self.assertEqual(response.status_code, 400)
        query.assert_not_called()

    @patch("field_map.views._query_parcels")
    def test_api_returns_allowlisted_geojson_fields(self, query):
        query.return_value = [{
            "parcel_number": "P123", "owner_name": "FIELD OWNER", "situs_address": "10 MAIN ST",
            "situs_city_state_zip": "BURLINGTON WA 98233", "acres": Decimal("1.250"),
            "land_use": "(110) HOUSEHOLD SFR", "geometry": {"type": "MultiPolygon", "coordinates": []},
        }]
        request = self.factory.get("/field/api/parcels/", {"bbox": "-122.4,48.4,-122.39,48.41"})
        request.user = StaffUser()
        response = views.parcels_geojson(request)
        payload = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["type"], "FeatureCollection")
        self.assertFalse(payload["truncated"])
        self.assertEqual(payload["features"][0]["properties"], {
            "parcel_number": "P123", "owner_name": "FIELD OWNER", "situs_address": "10 MAIN ST",
            "situs_city_state_zip": "BURLINGTON WA 98233", "acres": 1.25,
            "land_use": "(110) HOUSEHOLD SFR",
        })

    @patch("field_map.views._query_parcels")
    def test_api_caps_and_marks_truncated_results(self, query):
        row = {
            "parcel_number": "P1", "owner_name": None, "situs_address": None,
            "situs_city_state_zip": None, "acres": None, "land_use": None,
            "geometry": '{"type":"MultiPolygon","coordinates":[]}',
        }
        query.return_value = [row.copy() for _ in range(views.MAX_FEATURES + 1)]
        request = self.factory.get("/field/api/parcels/", {"bbox": "-122.4,48.4,-122.39,48.41"})
        request.user = StaffUser()
        payload = json.loads(views.parcels_geojson(request).content)
        self.assertTrue(payload["truncated"])
        self.assertEqual(len(payload["features"]), views.MAX_FEATURES)


class ParcelQueryTests(SimpleTestCase):
    @patch("field_map.views.connection")
    def test_query_is_parameterized_and_uses_spatial_indexes(self, db):
        cursor = db.cursor.return_value.__enter__.return_value
        cursor.description = [(name,) for name in (
            "parcel_number", "owner_name", "situs_address", "situs_city_state_zip", "acres", "land_use", "geometry",
        )]
        cursor.fetchall.return_value = []
        bbox = (-122.4, 48.4, -122.39, 48.41)
        views._query_parcels(bbox)
        sql, params = cursor.execute.call_args.args
        self.assertIn("g.geometry && v.geometry", sql)
        self.assertIn("ST_Intersects(g.geometry, v.geometry)", sql)
        self.assertIn("p.inactive_date IS NULL", sql)
        self.assertEqual(params, [*bbox, views.MAX_FEATURES + 1])


class PwaAssetTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_manifest_is_installable_and_scoped_to_field_map(self):
        response = views.web_manifest(self.factory.get("/field/manifest.webmanifest"))
        payload = json.loads(response.content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/manifest+json")
        self.assertEqual(payload["start_url"], "/field/")
        self.assertEqual(payload["scope"], "/field/")
        self.assertEqual(payload["display"], "standalone")
        self.assertEqual(payload["icons"][0]["type"], "image/svg+xml")

    def test_service_worker_has_field_scope_and_does_not_cache_private_api(self):
        response = views.service_worker(self.factory.get("/field/service-worker.js"))
        script = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/javascript")
        self.assertEqual(response["Service-Worker-Allowed"], "/field/")
        self.assertEqual(response["Cache-Control"], "no-cache")
        self.assertIn('url.pathname.startsWith("/field/api/")', script)
        self.assertIn("/static/field_map/vendor/leaflet/leaflet.css", script)
        self.assertNotIn("basemaps.cartocdn.com", script)
        self.assertNotIn("basemap.nationalmap.gov", script)

    def test_template_uses_only_self_hosted_leaflet(self):
        source = get_template("field_map/map.html").template.source
        self.assertIn("field_map/vendor/leaflet/leaflet.css", source)
        self.assertIn("field_map/vendor/leaflet/leaflet.js", source)
        self.assertIn("field_map:manifest", source)
        self.assertNotIn("unpkg.com/leaflet", source)
        self.assertNotIn("integrity=", source)

    def test_leaflet_assets_and_pwa_icon_are_discoverable(self):
        for asset in (
            "field_map/vendor/leaflet/leaflet.css",
            "field_map/vendor/leaflet/leaflet.js",
            "field_map/vendor/leaflet/images/layers.png",
            "field_map/icons/field-map-icon.svg",
        ):
            with self.subTest(asset=asset):
                self.assertIsNotNone(finders.find(asset))

    def test_parcel_click_does_not_bubble_to_map_close_handler(self):
        path = finders.find("field_map/field_map.js")
        with open(path, "r", encoding="utf-8") as asset:
            script = asset.read()
        self.assertIn("bubblingMouseEvents:false", script)
        self.assertIn('map.on("click",resetSelection)', script)
        self.assertNotIn("stopPropagation(event.originalEvent)", script)

    def test_leaflet_css_matches_official_1_9_4_checksum(self):
        path = finders.find("field_map/vendor/leaflet/leaflet.css")
        with open(path, "rb") as asset:
            digest = base64.b64encode(hashlib.sha256(asset.read()).digest()).decode()
        self.assertEqual(digest, "p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=")
