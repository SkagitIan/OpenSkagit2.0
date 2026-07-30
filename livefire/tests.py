from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from .models import DayAssumption, MenuItem, QuoteRequest, Snapshot, VendorQuote
from .services import calculate, create_base_scenario, snapshot_data


class ForecastTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("planner", password="secret")
        self.scenario = create_base_scenario(self.user)

    def test_base_values_and_decimal_formula(self):
        result = calculate(self.scenario)
        self.assertEqual(result["receipt"], Decimal("20.30"))
        self.assertEqual(result["daily"][0]["customers"], Decimal("1000.00"))
        self.assertEqual(result["daily"][0]["revenue"], Decimal("20300.00"))
        self.assertEqual(result["entree_mix"], Decimal("1.00"))
        self.assertIsInstance(result["totals"]["profit"], Decimal)

    def test_capacity_warning_and_day_specific_assumptions(self):
        saturday = self.scenario.days.get(day="sat")
        saturday.traffic = 20000; saturday.max_transactions_per_hour = 100; saturday.save()
        row = next(row for row in calculate(self.scenario)["daily"] if row["day"] == "Saturday")
        self.assertEqual(row["customers"], Decimal("2000.00"))
        self.assertTrue(row["capacity_warning"])

    def test_entree_mix_warning(self):
        MenuItem.objects.filter(scenario=self.scenario, category="entree").first().delete()
        self.assertTrue(calculate(self.scenario)["entree_mix_warning"])


class BoundaryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("owner", password="secret")
        self.other = get_user_model().objects.create_user("other", password="secret")
        self.scenario = create_base_scenario(self.user)

    def test_dashboard_requires_authentication(self):
        response = self.client.get(reverse("livefire:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_scenario_ownership_is_enforced(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse("livefire:scenario_archive", args=[self.scenario.pk]))
        self.assertEqual(response.status_code, 404)

    def test_vendor_token_needs_no_account_and_reveals_no_forecast(self):
        request = QuoteRequest.objects.create(owner=self.user, item_name="Salmon", vendor_name="Fish Co")
        response = self.client.get(reverse("livefire:vendor_quote", args=[request.token]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "profit")
        response = self.client.post(reverse("livefire:vendor_quote", args=[request.token]), {"price": "100", "package_size": "10", "minimum_order": "2", "delivery_fee": "20", "available": "on"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(request.quotes.count(), 1)
        self.assertEqual(request.quotes.get().unit_cost, Decimal("11"))

    def test_quote_comparison_is_private(self):
        request = QuoteRequest.objects.create(owner=self.user, item_name="Wood", vendor_name="Wood Co")
        VendorQuote.objects.create(request=request, price=10, package_size=2)
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse("livefire:quotes")), "Wood Co")

    def test_snapshot_is_immutable_and_public(self):
        snapshot = Snapshot.objects.create(scenario=self.scenario, title="April plan", visible_sections=["forecast"], data=snapshot_data(self.scenario))
        original = snapshot.data["totals"]["revenue"]
        self.scenario.menu_items.update(price=Decimal("99"))
        response = self.client.get(reverse("livefire:shared", args=[snapshot.token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, original)
        snapshot.refresh_from_db(); self.assertEqual(snapshot.data["totals"]["revenue"], original)
