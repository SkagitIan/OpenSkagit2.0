import json
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth.models import AnonymousUser
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
