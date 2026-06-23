import os
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings, tag
from django.urls import reverse

from . import services


class OpportunityHelperTests(SimpleTestCase):
    def test_money_formats_empty_and_numeric_values(self):
        self.assertEqual(services.money(None), "$0")
        self.assertEqual(services.money(Decimal("123456.78")), "$123,457")

    def test_acres_formats_values(self):
        self.assertEqual(services.acres(None), "unknown acres")
        self.assertEqual(services.acres("0.72"), "0.72 acres")

    def test_risk_flags_drops_empty_values(self):
        self.assertEqual(services.risk_flags("Missing zoning", None, "", "Small lot"), ["Missing zoning", "Small lot"])

    def test_land_use_classifiers(self):
        self.assertEqual(services.land_use_code("(150) MOBILE HOME PARKS"), "150")
        self.assertTrue(services.is_resource_land_use("(830) CURRENT USE FARM AND AG"))
        self.assertTrue(services.is_public_or_civic_land_use("(680) EDUCATION SERVICES (SCHOOLS)"))
        self.assertTrue(services.is_vacant_buildable_land_use("(911) UNDEVELOPED LAND INCORPORATED"))
        self.assertTrue(services.is_residential_dwelling_land_use("(111) HOUSEHOLD, SFR, INSIDE CITY"))

    def test_utility_labels_and_phrase(self):
        self.assertEqual(services.utility_labels("*SEW, PWR, WTR-P"), ["sewer", "power", "public water"])
        self.assertEqual(services.utility_labels("*SEP, PWR, WTR-W"), ["septic", "power", "well water"])
        self.assertEqual(services.utility_phrase("*SEW, PWR, WTR-P"), "sewer, power and public water indicated")
        self.assertEqual(services.utility_phrase("*SEP, PWR, WTR-W"), "septic, power and well water indicated")
        self.assertEqual(services.utility_phrase(""), "no utility signal")

    def test_zone_classifiers(self):
        self.assertTrue(services.is_natural_resource_zone("RRc-NRL", "Rural Resource - Natural Resource Lands", "NRL"))
        self.assertTrue(services.is_natural_resource_zone("Ag-NRL", "Agricultural - Natural Resource Lands", "NRL"))
        self.assertTrue(services.is_natural_resource_zone("IF-NRL", "Industrial Forest - Natural Resource Lands", "NRL"))
        self.assertTrue(services.is_natural_resource_zone("SF-NRL", "Secondary Forest - Natural Resource Lands", "NRL"))
        self.assertTrue(services.is_urban_residential_zone("LIR"))
        self.assertTrue(services.is_urban_residential_zone("MR"))
        self.assertFalse(services.is_urban_residential_zone("RUR"))
        self.assertTrue(services.is_rural_residential_zone("RUR"))

    def test_auditor_document_url_from_recording_number(self):
        self.assertEqual(
            services._auditor_url("202506270191"),
            "https://www.skagitcounty.net/AuditorRecording/Documents/RecordedDocuments/2025/06/27/202506270191.pdf",
        )

    def test_recent_document_url_only_within_90_days(self):
        recent = {"deed_date_iso": "2026-06-01", "recording_number": "202506270191"}
        old = {"deed_date_iso": "2026-02-01", "recording_number": "202506270191"}
        self.assertTrue(services._recent_document_url(recent, today=date(2026, 6, 23)))
        self.assertEqual(services._recent_document_url(old, today=date(2026, 6, 23)), "")

    def test_delinquent_years_phrase_separates_current_year_balance(self):
        self.assertEqual(
            services._delinquent_years_phrase(1, 1),
            "1 prior delinquent tax year plus current-year balance",
        )
        self.assertEqual(services._delinquent_years_phrase(0, 1), "current-year delinquent balance")


@override_settings(ROOT_URLCONF="config.urls", OPPORTUNITY_DASHBOARD_PASSWORD="letmein")
class OpportunityAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user("staff", password="pass", is_staff=True)
        self.user = User.objects.create_user("user", password="pass", is_staff=False)

    def test_anonymous_user_sees_password_gate(self):
        response = self.client.get(reverse("opportunity_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter the shared password")

    def test_wrong_password_stays_locked(self):
        response = self.client.post(reverse("opportunity_dashboard"), {"password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "That password did not work.")

    @patch("opportunity.views.tab_counts", return_value={tab.key: 0 for tab in services.TABS})
    @patch("opportunity.views.fetch_tab_rows", return_value=[])
    def test_correct_password_can_load_dashboard(self, fetch_tab_rows, tab_counts):
        response = self.client.post(reverse("opportunity_dashboard"), {"password": "letmein"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delinquent Tax Pressure")


@tag("opportunity_live")
class OpportunityLiveQueryTests(TestCase):
    databases = {"default"}

    def setUp(self):
        if os.getenv("OPPORTUNITY_LIVE_TESTS") != "1":
            self.skipTest("Set OPPORTUNITY_LIVE_TESTS=1 to run live opportunity query smoke tests.")

    def test_each_tab_returns_shared_row_shape(self):
        required = {
            "parcel_number",
            "location",
            "zoning",
            "why_it_ranks",
            "risk_flags",
            "map_url",
            "score",
        }
        for tab in services.TABS:
            rows = services.fetch_tab_rows(tab.key, {}, limit=1)
            for row in rows:
                self.assertTrue(required.issubset(row.keys()), tab.key)
