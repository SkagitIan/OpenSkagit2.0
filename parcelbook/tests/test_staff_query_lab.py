from types import SimpleNamespace

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase

from parcelbook.views import staff_query_lab


class StaffQueryLabTests(SimpleTestCase):
    def test_staff_query_lab_requires_login(self):
        request = RequestFactory().get("/staff/parcelbook/queries/")
        request.user = AnonymousUser()
        response = staff_query_lab(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_staff_can_generate_sql_without_running_r2_query(self):
        request = RequestFactory().post(
            "/staff/parcelbook/queries/",
            {"query": "Find possible ADU candidates in Mount Vernon.", "mode": "plan"},
        )
        request.user = SimpleNamespace(is_active=True, is_staff=True)
        response = staff_query_lab(request)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Generated plan", html)
        self.assertIn("read_parquet(&#x27;r2://openskagit/derived/parcel_search.parquet&#x27;)", html)
