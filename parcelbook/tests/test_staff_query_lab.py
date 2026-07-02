from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase

from parcelbook.views import staff_query_lab
from parcelbook_ai.output_models import ParcelAgentAnswer, ParcelResult


class StaffQueryLabTests(SimpleTestCase):
    def test_staff_query_lab_requires_login(self):
        request = RequestFactory().get("/staff/parcelbook/queries/")
        request.user = AnonymousUser()
        response = staff_query_lab(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_staff_can_preview_route_without_running_query(self):
        request = RequestFactory().get(
            "/staff/parcelbook/queries/",
            {"query": "Find ADU candidates in Mount Vernon.", "limit": "5"},
        )
        request.user = SimpleNamespace(is_active=True, is_staff=True)
        response = staff_query_lab(request)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Detected routing", html)
        self.assertIn("parcel_first", html)
        self.assertIn("Ask ParcelBook AI", html)

    def test_staff_can_run_mocked_parcelbook_ai(self):
        request = RequestFactory().post(
            "/staff/parcelbook/queries/",
            {"query": "Find older houses on big lots", "limit": "3"},
        )
        request.user = SimpleNamespace(is_active=True, is_staff=True)

        def fake_ask(query, limit=25):
            self.assertEqual(query, "Find older houses on big lots")
            self.assertEqual(limit, 3)
            return ParcelAgentAnswer(
                interpreted_intent="older big-lot homes",
                mode="none",
                sql_used="SELECT * FROM read_parquet('r2://openskagit/derived/parcel_search.parquet') LIMIT 3;",
                row_count=1,
                results=[
                    ParcelResult(
                        parcel_number="P1",
                        address="1 Main St",
                        owner_name="Owner",
                        parcel_data={"acres": 1.2},
                        parcel_match_reason="Older home on a larger lot.",
                        caveats=["Assessed value is not market value."],
                    )
                ],
                general_caveats=["Assessed value is not market value."],
            )

        from unittest.mock import patch

        with patch("parcelbook.views.ask_parcels", fake_ask):
            response = staff_query_lab(request)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Agent answer", html)
        self.assertIn("P1", html)
        self.assertIn("Older home on a larger lot.", html)
