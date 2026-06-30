import os
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings, tag
from django.urls import reverse

from . import services
from .ai_search import (
    OpportunitySearchError,
    _extract_markdown_section,
    _fallback_generated_search,
    _needs_zoning_mcp_context,
    _proposed_uses_for_zoning,
    apply_prompt_result_filters,
    parse_generated_search_response,
    validate_search_sql,
)
from .models import OpportunitySearch, OpportunitySearchFeedback


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

    def test_current_use_zoning_audit_flags_residential_use_in_industrial_zoning(self):
        audit = services.current_use_zoning_audit(
            {
                "land_use": "(111) HOUSEHOLD, SFR, INSIDE CITY",
                "waza_general": "IND",
                "zone_id": "I",
                "zone_name": "Industrial Zone",
            }
        )
        self.assertEqual(audit["status"], "review")
        self.assertEqual(audit["label"], "Residential use in industrial zoning")
        self.assertIn("HOUSEHOLD, SFR, INSIDE CITY", audit["description"])
        self.assertIn("I", audit["description"])
        self.assertEqual(
            services.current_use_zoning_flags(
                {"land_use": "(111) HOUSEHOLD, SFR, INSIDE CITY", "waza_general": "IND", "zone_id": "I"}
            ),
            ["Residential use in industrial zoning"],
        )

    def test_current_use_zoning_audit_ignores_expected_combinations(self):
        residential_zone = services.current_use_zoning_audit(
            {"land_use": "(111) HOUSEHOLD, SFR, INSIDE CITY", "waza_general": "LIR", "zone_id": "R-5"}
        )
        industrial_vacant_use = services.current_use_zoning_audit(
            {"land_use": "(911) UNDEVELOPED LAND INCORPORATED", "waza_general": "IND", "zone_id": "I"}
        )
        self.assertEqual(residential_zone["status"], "")
        self.assertEqual(industrial_vacant_use["status"], "")

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

    def test_location_adds_city_without_zip_noise(self):
        self.assertEqual(services._city_label("Mount Vernon, WA 98273"), "Mount Vernon")
        self.assertEqual(services._location_label("1725 S 30TH STREET", "Mount Vernon"), "1725 S 30TH STREET, Mount Vernon")

    def test_value_history_phrase_is_compact(self):
        self.assertEqual(services._value_history_phrase(Decimal("70")), "; assessed value up 70% since 2020")
        self.assertEqual(services._value_history_phrase(Decimal("1")), "; assessed value roughly flat since 2020")

    def test_improvement_label_translates_assessor_codes(self):
        self.assertEqual(services._improvement_label("MA1.5F"), "one-and-a-half-story dwelling")
        self.assertEqual(services._improvement_label("MAIN AREA"), "main dwelling area")

    def test_sync_narrative_response_parser(self):
        parsed = services.parse_sync_narrative_response(
            '{"headline":"Fresh assessor changes","dek":"A local field note","narrative":"Several records changed overnight.",'
            '"bullets":["Sales changed","Land changed","Review before use"],'
            '"notable_signals":["Lot certification: P1 in Bow"],"trend_line":"Land division led the day",'
            '"disclaimer":"Screening only","newsletter_subject":"Skagit field note","preview_text":"Fresh signals"}'
        )
        self.assertEqual(parsed["headline"], "Fresh assessor changes")
        self.assertEqual(parsed["dek"], "A local field note")
        self.assertEqual(len(parsed["bullets"]), 3)
        self.assertEqual(parsed["notable_signals"], ["Lot certification: P1 in Bow"])

    def test_sync_narrative_fallback_is_plain_english(self):
        narrative = services.fallback_sync_narrative(
            {"files_changed": 2, "tables": {"sales": {"updated": 3, "inserted": 1, "applied_rows": 4}}}
        )
        self.assertIn("2 changed source file", narrative["narrative"])
        self.assertEqual(len(narrative["bullets"]), 3)

    def test_fresh_sale_requires_event_date_inside_window(self):
        start = date(2026, 6, 23)
        end = date(2026, 6, 30)
        self.assertTrue(services._is_fresh_sale_row({"sale_date": "2026-06-25"}, start, end))
        self.assertFalse(services._is_fresh_sale_row({"sale_date": "2024-01-03"}, start, end))
        self.assertFalse(services._is_fresh_sale_row({"sale_date": ""}, start, end))

    def test_sync_brief_fallback_ignores_stale_sales_updates(self):
        context = {
            "window": {"label": "Jun 23, 2026 to Jun 30, 2026"},
            "counts": {"fresh_recordings": 0, "fresh_sales": 0, "stale_sales_updates_ignored": 119},
            "signal_counts": {},
            "notable_signals": [],
        }
        narrative = services.fallback_sync_narrative({}, context)
        self.assertIn("No fresh investor-facing", narrative["headline"])
        self.assertIn("119 historical assessor sales update", narrative["narrative"])
        self.assertEqual(len(narrative["bullets"]), 3)

    def test_notability_ranks_land_division_over_generic_financing(self):
        land_score = services._brief_notability_score({"signal_group": "land_division", "document_type": "Lot Certification", "parcel_number": "P1"})
        financing_score = services._brief_notability_score({"signal_group": "financing", "document_type": "Deed Of Trust", "parcel_number": "P2"})
        self.assertGreater(land_score, financing_score)

    def test_latest_nonempty_sync_report_skips_empty_latest_report(self):
        empty_latest = SimpleNamespace(run=SimpleNamespace(summary={"files_changed": 0, "tables": {"sales": {"applied_rows": 0}}}))
        prior_active = SimpleNamespace(run=SimpleNamespace(summary={"files_changed": 1, "tables": {"sales": {"inserted": 2}}}))

        class FakeReportQuery:
            def __init__(self, reports):
                self.reports = reports

            def select_related(self, *_args):
                return self

            def filter(self, **_kwargs):
                return self

            def order_by(self, *_args):
                return self

            def __getitem__(self, item):
                return self.reports[item]

        class FakeReport:
            objects = FakeReportQuery([empty_latest, prior_active])

        self.assertIs(services.latest_nonempty_sync_report(FakeReport), prior_active)

    def test_ai_search_response_parser_requires_structured_json(self):
        parsed = parse_generated_search_response(
            '{"title":"Large parcels","criteria_summary":"Over 40 acres","assumptions":["screening only"],'
            '"sql":"SELECT p.parcel_number FROM skagit_parcels p WHERE p.acres > %s","params":[40]}'
        )
        self.assertEqual(parsed["title"], "Large parcels")
        self.assertEqual(parsed["params"], [40])

    def test_multiunit_prompt_has_safe_deterministic_fallback(self):
        generated = _fallback_generated_search("parcels with multi unit buildings like duplex to sixplex. no sales activity for 15 years. average quality.")
        self.assertIsNotNone(generated)
        self.assertIn("NULLIF(s.sale_date_iso, '')::date", generated.sql)
        self.assertIn("(%s || ' years')::interval", generated.sql)
        self.assertEqual(generated.params, [15])

    def test_ai_search_sql_validator_allows_safe_select(self):
        sql = "SELECT p.parcel_number FROM skagit_parcels p WHERE p.inactive_date IS NULL AND p.acres > %s"
        self.assertEqual(validate_search_sql(sql, [10]), sql)

    def test_ai_search_sql_validator_rejects_mutation(self):
        with self.assertRaises(OpportunitySearchError):
            validate_search_sql("DELETE FROM skagit_parcels WHERE parcel_number = %s", ["P1"])

    def test_ai_search_sql_validator_rejects_unapproved_table(self):
        with self.assertRaises(OpportunitySearchError):
            validate_search_sql("SELECT parcel_number FROM auth_user")

    def test_ai_search_sql_validator_checks_params(self):
        with self.assertRaises(OpportunitySearchError):
            validate_search_sql("SELECT p.parcel_number FROM skagit_parcels p WHERE p.acres > %s", [])

    def test_ai_search_home_intent_filters_nonresidential_results(self):
        rows = [
            {"parcel_number": "P1", "land_use_code": "110", "current_use": "(110) HOUSEHOLD SFR OUTSIDE CITY"},
            {"parcel_number": "P2", "land_use_code": "580", "current_use": "(580) RETAIL TRADE, EATING & DRINKING"},
            {"parcel_number": "P3", "land_use_code": "670", "current_use": "(670) GOVERNMENTAL SERVICES"},
        ]
        filtered = apply_prompt_result_filters("large homes in Conway suitable for senior community conversion", rows)
        self.assertEqual([row["parcel_number"] for row in filtered], ["P1"])

    def test_ai_search_bare_recreation_land_filters_bad_asset_classes(self):
        rows = [
            {"parcel_number": "P1", "land_use_code": "911", "current_use": "(911) UNDEVELOPED LAND", "land_use": "(911) UNDEVELOPED LAND", "acres": 1.2, "map_url": "map"},
            {"parcel_number": "P2", "land_use_code": "", "current_use": "MH LEASED PROPERTY", "land_use": "MH LEASED PROPERTY", "acres": 0, "map_url": ""},
            {"parcel_number": "P3", "land_use_code": "140", "current_use": "CONDOMINIUM COMMON AREA", "land_use": "(140) CONDOMINIUM", "acres": 0.4, "map_url": "map"},
            {"parcel_number": "P4", "land_use_code": "670", "current_use": "GOVERNMENTAL SERVICES", "land_use": "(670) GOVERNMENTAL SERVICES", "acres": 1.0, "map_url": "map"},
            {"parcel_number": "P5", "land_use_code": "110", "current_use": "(110) HOUSEHOLD SFR", "land_use": "(110) HOUSEHOLD SFR", "acres": 0.8, "map_url": "map"},
        ]
        filtered = apply_prompt_result_filters("Recreation or Small Bare Land Parcels with Utilities Under $200K Assessed Value", rows)
        self.assertEqual([row["parcel_number"] for row in filtered], ["P1"])

    def test_skill_reference_section_extractor_stops_at_next_heading(self):
        markdown = "# Root\n\n## `land_use` Mappings\nkeep this\n\n### Child\nand this\n\n## Other\nskip this"
        section = _extract_markdown_section(markdown, "`land_use` Mappings")
        self.assertIn("keep this", section)
        self.assertIn("and this", section)
        self.assertNotIn("skip this", section)

    def test_zoning_mcp_context_triggers_for_use_suitability_prompts(self):
        self.assertTrue(_needs_zoning_mcp_context("large homes suitable for senior community conversion"))
        self.assertFalse(_needs_zoning_mcp_context("vacant parcels under 200k with power"))

    def test_zoning_mcp_use_hints_preserve_senior_conversion_intent(self):
        uses = _proposed_uses_for_zoning("large homes in Conway suitable for senior community conversion")
        self.assertIn("senior housing", uses)
        self.assertIn("assisted living", uses)
        self.assertIn("single family residence", uses)


@override_settings(ROOT_URLCONF="config.urls")
class OpportunityAuthTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("user", password="pass", is_staff=False)

    def test_anonymous_routes_redirect_to_parcel_book_login(self):
        targets = [
            reverse("opportunity_home"),
            reverse("opportunity_explore"),
            reverse("opportunity_watchlist"),
            reverse("opportunity_parcel_detail", args=["P12345"]),
        ]
        for target in targets:
            response = self.client.get(target)
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse("opportunity_login"), response["Location"])

    @patch("opportunity.views.dashboard_context", return_value={"tabs": services.TABS, "watchlist": [], "sync": {"metrics": [], "changes": []}})
    def test_logged_in_user_can_load_dashboard(self, dashboard_context):
        self.client.login(username="user", password="pass")
        response = self.client.get(reverse("opportunity_home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "What's Hot Right Now")

    @patch("opportunity.views.tab_counts", return_value={tab.key: "" for tab in services.TABS})
    @patch("opportunity.views.fetch_tab_rows", return_value=[])
    def test_logged_in_user_can_load_explore(self, fetch_tab_rows, tab_counts):
        self.client.login(username="user", password="pass")
        response = self.client.get(reverse("opportunity_explore"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Explore parcel signals")

    @patch("opportunity.views.parcel_detail", return_value=None)
    def test_unknown_parcel_returns_404(self, parcel_detail):
        self.client.login(username="user", password="pass")
        response = self.client.get(reverse("opportunity_parcel_detail", args=["P404"]))
        self.assertEqual(response.status_code, 404)


@override_settings(ROOT_URLCONF="config.urls")
class OpportunityWatchlistTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("user", password="pass")
        self.other = User.objects.create_user("other", password="pass")

    def test_save_is_idempotent(self):
        self.client.login(username="user", password="pass")
        url = reverse("opportunity_save")
        self.client.post(url, {"parcel_number": "P100387", "source_tab": "delinquent-tax-pressure"})
        self.client.post(url, {"parcel_number": "P100387", "source_tab": "delinquent-tax-pressure"})
        from .models import OpportunitySavedParcel

        self.assertEqual(OpportunitySavedParcel.objects.filter(user=self.user, parcel_number="P100387").count(), 1)

    def test_unsave_removes_only_current_user_row(self):
        from .models import OpportunitySavedParcel

        OpportunitySavedParcel.objects.create(user=self.user, parcel_number="P100387")
        OpportunitySavedParcel.objects.create(user=self.other, parcel_number="P100387")
        self.client.login(username="user", password="pass")
        self.client.post(reverse("opportunity_save"), {"parcel_number": "P100387", "action": "unsave"})
        self.assertFalse(OpportunitySavedParcel.objects.filter(user=self.user, parcel_number="P100387").exists())
        self.assertTrue(OpportunitySavedParcel.objects.filter(user=self.other, parcel_number="P100387").exists())

    @patch("opportunity.views.watchlist_rows", return_value=[])
    def test_users_can_load_only_their_watchlist_page(self, watchlist_rows):
        self.client.login(username="user", password="pass")
        response = self.client.get(reverse("opportunity_watchlist"))
        self.assertEqual(response.status_code, 200)
        watchlist_rows.assert_called_once_with(self.user)


@override_settings(ROOT_URLCONF="config.urls")
class OpportunityAISearchTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("user", password="pass")
        self.other = User.objects.create_user("other", password="pass")

    def test_ai_search_page_loads_for_logged_in_user(self):
        self.client.login(username="user", password="pass")
        response = self.client.get(reverse("opportunity_ai_search"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Search opportunities in plain English")

    def test_ai_search_page_lists_unsaved_pending_searches(self):
        OpportunitySearch.objects.create(
            user=self.user,
            prompt="large homes in Conway",
            status=OpportunitySearch.STATUS_DRAFT,
        )
        self.client.login(username="user", password="pass")
        response = self.client.get(reverse("opportunity_ai_search"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "large homes in Conway")
        self.assertContains(response, "Finding parcels")

    @patch("opportunity.views.start_ai_opportunity_search")
    def test_ai_search_post_redirects_to_pending_result(self, start_ai_opportunity_search):
        search = OpportunitySearch.objects.create(
            user=self.user,
            prompt="large parcels",
            title="Large parcels",
            status=OpportunitySearch.STATUS_DRAFT,
        )
        start_ai_opportunity_search.return_value = search
        self.client.login(username="user", password="pass")
        response = self.client.post(reverse("opportunity_ai_search"), {"prompt": "large parcels"})
        self.assertRedirects(response, reverse("opportunity_detail", args=[search.pk]))
        start_ai_opportunity_search.assert_called_once_with(self.user, "large parcels")

    def test_ai_search_detail_shows_pending_state(self):
        search = OpportunitySearch.objects.create(
            user=self.user,
            prompt="large parcels",
            title="Large parcels",
            status=OpportunitySearch.STATUS_DRAFT,
        )
        self.client.login(username="user", password="pass")
        response = self.client.get(reverse("opportunity_detail", args=[search.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Finding target parcels")
        self.assertNotContains(response, "No parcels matched this AI search.")

    def test_ai_search_detail_is_private_to_owner(self):
        search = OpportunitySearch.objects.create(
            user=self.user,
            prompt="large parcels",
            title="Large parcels",
            status=OpportunitySearch.STATUS_READY,
            result_rows=[],
        )
        self.client.login(username="other", password="pass")
        response = self.client.get(reverse("opportunity_detail", args=[search.pk]))
        self.assertEqual(response.status_code, 404)

    def test_user_can_save_ai_search(self):
        search = OpportunitySearch.objects.create(user=self.user, prompt="large parcels")
        self.client.login(username="user", password="pass")
        response = self.client.post(reverse("opportunity_ai_search_save", args=[search.pk]))
        self.assertRedirects(response, reverse("opportunity_detail", args=[search.pk]))
        search.refresh_from_db()
        self.assertIsNotNone(search.saved_at)

    def test_user_can_leave_search_feedback(self):
        search = OpportunitySearch.objects.create(user=self.user, prompt="large parcels")
        self.client.login(username="user", password="pass")
        response = self.client.post(
            reverse("opportunity_ai_search_feedback", args=[search.pk]),
            {"rating": "bad", "reason_code": "too_broad", "comment": "Lots of noise"},
        )
        self.assertRedirects(response, reverse("opportunity_detail", args=[search.pk]))
        feedback = OpportunitySearchFeedback.objects.get(search=search, user=self.user)
        self.assertEqual(feedback.rating, "bad")
        self.assertEqual(feedback.reason_code, "too_broad")


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
            "current_use",
            "risk_flags",
            "map_url",
            "signal_labels",
        }
        for tab in services.TABS:
            rows = services.fetch_tab_rows(tab.key, {}, limit=1)
            for row in rows:
                self.assertTrue(required.issubset(row.keys()), tab.key)
