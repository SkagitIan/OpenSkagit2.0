import json
import os
import unittest
from datetime import date
from decimal import Decimal
from io import StringIO
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings, tag
from django.urls import reverse

from . import services
from .ai_search import (
    OpportunitySearchError,
    _build_plan_prompt,
    _extract_markdown_section,
    _fallback_generated_search,
    _fallback_search_plan,
    _needs_zoning_mcp_context,
    _proposed_uses_for_zoning,
    _skill_reference_context,
    _skill_reference_metadata,
    apply_prompt_result_filters,
    parse_generated_search_response,
    run_ai_opportunity_search,
    validate_search_sql,
)
from .models import OpportunitySearch, OpportunitySearchFeedback
from .ai_evals import (
    EvalCaseResult,
    EvalFailure,
    EvalRunResult,
    OpportunityEvalCase,
    build_action_plan,
    evaluate_rows,
    evaluate_sql,
    load_eval_cases,
    run_eval_case,
)
from .r2_search import (
    DuckDBR2OpportunityClient,
    R2GeneratedSearch,
    R2SearchError,
    _generation_instructions,
    format_r2_result_row,
    ontology_reference_text,
    parcel_search_path,
    parquet_registry,
    parse_generated_r2_search_response,
    run_generated_r2_search,
    zoning_mcp_reference_text,
)


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

    def test_r2_response_parser_tolerates_harmless_shape_drift(self):
        parsed = parse_generated_r2_search_response(
            """{"title":"Large parcels","criteria_summary":"Over 40 acres",
            "assumptions":"screening only","params":{},
            "sql":"SELECT parcel_number FROM read_parquet('r2://openskagit/derived/parcel_search.parquet')"}"""
        )
        self.assertEqual(parsed.assumptions, ["screening only"])
        self.assertEqual(parsed.params, [])

    def test_eval_case_loader_validates_json_cases(self):
        with TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cases.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump([{"id": "case-1", "prompt": "large parcels", "row_expectations": {"min_acres": 1}}], handle)
            cases = load_eval_cases(path)
        self.assertEqual(cases[0].id, "case-1")
        self.assertEqual(cases[0].row_expectations["min_acres"], 1)

    def test_eval_case_loader_rejects_missing_required_fields(self):
        with TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cases.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump([{"id": "case-1"}], handle)
            with self.assertRaisesRegex(ValueError, "missing required"):
                load_eval_cases(path)

    def test_eval_sql_checks_known_bad_patterns(self):
        case = OpportunityEvalCase(
            id="utilities",
            prompt="lots with utilities",
            forbidden_sql_patterns=["ps\\.utilities", "(?<!\\.)\\bacres\\b\\s*>\\s*1"],
        )
        failures = evaluate_sql(
            case,
            "SELECT ps.parcel_number, ps.utilities FROM read_parquet('r2://openskagit/derived/parcel_search.parquet') ps WHERE acres > 1",
        )
        self.assertEqual([failure.code for failure in failures], ["forbidden_sql_pattern", "forbidden_sql_pattern"])

    def test_eval_rows_flags_wrong_place_and_missing_utility_evidence(self):
        case = OpportunityEvalCase(
            id="places",
            prompt="lots in sedro-woolley with utilities",
            row_expectations={"place_terms": ["sedro-woolley"], "require_utilities": True, "min_acres": 1},
        )
        failures = evaluate_rows(
            case,
            [{"parcel_number": "P1", "location": "4308 WHISTLE LAKE RD, Anacortes", "city": "Anacortes", "acres": 0.5, "utilities": ""}],
        )
        self.assertIn("row_place", [failure.code for failure in failures])
        self.assertIn("row_utilities", [failure.code for failure in failures])
        self.assertIn("row_min_acres", [failure.code for failure in failures])

    def test_eval_low_quality_uses_quality_codes_not_condition_codes(self):
        case = OpportunityEvalCase(
            id="low-quality",
            prompt="low quality dwellings",
            row_expectations={"require_low_quality_signal": True},
        )
        self.assertFalse(evaluate_rows(case, [{"parcel_number": "P1", "quality_codes": "MSL"}]))
        failures = evaluate_rows(case, [{"parcel_number": "P2", "condition_codes": "F"}])
        self.assertEqual([failure.code for failure in failures], ["row_low_quality"])

    def test_eval_rows_checks_land_use_zoning_and_value_thresholds(self):
        case = OpportunityEvalCase(
            id="commercial",
            prompt="commercial parcels in Burlington over 500k",
            row_expectations={
                "place_terms": ["burlington"],
                "expected_land_use_code_prefixes": ["5", "6"],
                "forbidden_land_use_code_prefixes": ["1"],
                "zoning_terms": ["commercial"],
                "min_assessed_value": 500000,
            },
        )
        failures = evaluate_rows(
            case,
            [
                {
                    "parcel_number": "P1",
                    "location": "Burlington",
                    "land_use": "(580) RETAIL TRADE, EATING & DRINKING",
                    "zoning": "Commercial",
                    "assessed_value": 750000,
                }
            ],
        )
        self.assertEqual(failures, [])

    def test_eval_missing_sale_can_satisfy_no_valid_sale_prompt(self):
        case = OpportunityEvalCase(
            id="no-sale",
            prompt="no valid sale in 25 years",
            row_expectations={"min_years_since_last_valid_sale": 25, "allow_missing_sale_as_old": True},
        )
        self.assertEqual(evaluate_rows(case, [{"parcel_number": "P1", "years_since_last_valid_sale": None}]), [])

    def test_eval_advanced_row_expectations(self):
        case = OpportunityEvalCase(
            id="advanced",
            prompt="older garage parcels with reasons and maps",
            row_expectations={
                "min_numeric_fields": {"total_garage_area": 1},
                "max_numeric_fields": {"primary_actual_year_built": 1980},
                "required_text_terms": ["garage"],
                "forbidden_text_terms": ["public"],
                "require_match_reasons": True,
                "require_geometry": True,
            },
        )
        row = {
            "parcel_number": "P1",
            "total_garage_area": 400,
            "primary_actual_year_built": 1950,
            "match_reasons": "garage area and older building",
            "map_url": "https://maps.example/",
        }
        self.assertEqual(evaluate_rows(case, [row]), [])

    def test_eval_quality_code_expectations_use_quality_fields(self):
        case = OpportunityEvalCase(
            id="average-quality",
            prompt="average quality homes",
            row_expectations={"expected_quality_codes": ["MSA"], "forbidden_quality_codes": ["MSL"]},
        )
        self.assertEqual(evaluate_rows(case, [{"parcel_number": "P1", "quality_codes": "MSA | MSG", "match_reasons": "MSL excluded"}]), [])
        failures = evaluate_rows(case, [{"parcel_number": "P2", "quality_codes": "MSL"}])
        self.assertIn("row_quality_code", [failure.code for failure in failures])
        self.assertIn("row_forbidden_quality_code", [failure.code for failure in failures])

    def test_r2_generation_prompt_includes_opportunity_ontology(self):
        ontology = ontology_reference_text()
        instructions = _generation_instructions()
        self.assertIn("Opportunity Search Ontology", ontology)
        self.assertIn("Opportunity search ontology:", instructions)
        self.assertIn("SFR / Single-Family Residential", instructions)
        self.assertIn("Mobile / Manufactured Homes", instructions)

    def test_r2_generation_prompt_includes_zoning_mcp_reference(self):
        zoning = zoning_mcp_reference_text()
        instructions = _generation_instructions()
        self.assertIn("Opportunity Zoning Reference", zoning)
        self.assertIn("Zoning MCP reference:", instructions)
        self.assertIn("R_1/R_5/R_7/R_15", instructions)
        self.assertIn("resource_code BETWEEN 810 AND 890 OR resource_code IN", instructions)
        self.assertIn("two-to-four-unit", instructions)

    def test_mobile_home_parks_are_not_filtered_as_individual_homes(self):
        rows = [
            {
                "parcel_number": "P1",
                "land_use": "(150) MOBILE HOME PARKS",
                "land_use_code": "150",
                "current_use": "MOBILE HOME PARKS",
            }
        ]
        self.assertEqual(apply_prompt_result_filters("Mobile home parks, not individual mobile homes.", rows), rows)

    def test_eval_forbidden_text_uses_current_parcel_context(self):
        case = OpportunityEvalCase(
            id="private-recreation",
            prompt="private recreation lots excluding churches",
            row_expectations={"forbidden_text_terms": ["church"]},
        )
        historical_church_sale = {
            "parcel_number": "P1",
            "owner": "RES RLH WEST COAST LLC",
            "land_use": "(911) UNDEVELOPED LAND INCORPORATED",
            "parcel_data": {"last_valid_sale_buyer": "SALEM LUTHERAN CHURCH"},
        }
        current_church_owner = {
            "parcel_number": "P2",
            "owner": "SALEM LUTHERAN CHURCH",
            "land_use": "(911) UNDEVELOPED LAND INCORPORATED",
        }
        self.assertEqual(evaluate_rows(case, [historical_church_sale]), [])
        self.assertEqual([failure.code for failure in evaluate_rows(case, [current_church_owner])], ["row_forbidden_text"])

    def test_eval_place_terms_only_check_current_place_fields(self):
        case = OpportunityEvalCase(
            id="sedro-place",
            prompt="Sedro parcels",
            row_expectations={
                "place_terms": ["sedro-woolley"],
                "forbidden_place_terms": ["anacortes", "burlington", "mount vernon", "la conner"],
            },
        )
        row = {
            "parcel_number": "P1",
            "location": "123 MAIN ST, Sedro-Woolley",
            "city": "Sedro-Woolley",
            "zoning": "Burlington residential reference should not count as current place",
            "parcel_data": {
                "situs_city_state_zip": "SEDRO WOOLLEY, WA 98284",
                "library_service_area": "Burlington Library District",
            },
        }
        self.assertEqual(evaluate_rows(case, [row]), [])

    def test_public_cemetery_recreation_prompt_is_not_bare_private_lot_filter(self):
        rows = [
            {
                "parcel_number": "P1",
                "land_use_code": "760",
                "current_use": "(760) CEMETERY",
                "land_use": "(760) CEMETERY",
                "map_url": "",
            }
        ]
        filtered = apply_prompt_result_filters(
            "Cemetery or church recreation/cultural use parcels, not private investment land.",
            rows,
        )
        self.assertEqual(filtered, rows)

    def test_eval_failure_includes_action_plan(self):
        case = OpportunityEvalCase(id="low-quality", prompt="low quality homes")
        generated = R2GeneratedSearch(
            short_name="Low Quality",
            title="Low quality",
            criteria_summary="Low quality homes.",
            assumptions=[],
            sql=(
                "SELECT ps.parcel_number FROM read_parquet('r2://openskagit/derived/parcel_search.parquet') ps "
                "WHERE ps.primary_building_style LIKE '%MSL%'"
            ),
            params=[],
            tool_trace=[],
        )
        result = EvalCaseResult(
            case=case,
            status="failed",
            failures=[EvalFailure("min_result_count", "Expected at least 1 rows, got 0.")],
            generated=generated,
        )
        actions = build_action_plan(result)
        self.assertIn("too narrow", actions[0])

    def test_eval_failure_identifies_incomplete_cte(self):
        case = OpportunityEvalCase(id="low-quality", prompt="low quality homes")
        generated = R2GeneratedSearch(
            short_name="Low Quality",
            title="Low quality",
            criteria_summary="Low quality homes.",
            assumptions=[],
            sql=(
                "WITH low_quality AS ("
                "SELECT parcel_number FROM read_parquet('r2://openskagit/derived/parcel_search.parquet')"
                ")"
            ),
            params=[],
            tool_trace=[],
        )
        result = EvalCaseResult(
            case=case,
            status="error",
            failures=[EvalFailure("eval_exception", 'R2SearchError: Parser Error: syntax error at or near ")"')],
            generated=generated,
        )
        actions = build_action_plan(result)
        self.assertIn("no final SELECT", actions[0])

    def test_run_eval_case_uses_mocked_generation_and_execution(self):
        case = OpportunityEvalCase(
            id="sedro",
            prompt="large homes in Sedro-Woolley",
            expected_min_result_count=1,
            row_expectations={"place_terms": ["sedro-woolley"], "require_dwelling": True},
        )

        def fake_generator(prompt, **_kwargs):
            return R2GeneratedSearch(
                short_name="Sedro Homes",
                title="Sedro homes",
                criteria_summary="Homes in Sedro-Woolley.",
                assumptions=[],
                sql="SELECT parcel_number FROM read_parquet('r2://openskagit/derived/parcel_search.parquet')",
                params=[],
                tool_trace=[],
            )

        def fake_executor(_generated, **_kwargs):
            return (
                [{"parcel_number": "P1"}],
                [
                    {
                        "parcel_number": "P1",
                        "location": "114 N REED ST, Sedro-Woolley",
                        "city": "Sedro-Woolley",
                        "land_use": "(111) HOUSEHOLD, SFR, INSIDE CITY",
                        "land_use_code": "111",
                        "current_use": "(111) HOUSEHOLD, SFR, INSIDE CITY",
                    }
                ],
                {"source": "duckdb_r2"},
            )

        result = run_eval_case(case, model="test-model", generator=fake_generator, executor=fake_executor)
        self.assertEqual(result.status, "passed")
        self.assertEqual(result.filtered_rows[0]["parcel_number"], "P1")

    @patch.dict(os.environ, {"OPPORTUNITY_EVALS_LIVE": "1", "OPENAI_API_KEY": "test", "R2_ACCOUNT_ID": "acct", "R2_ACCESS_KEY_ID": "key", "R2_SECRET_ACCESS_KEY": "secret"})
    @patch("opportunity.management.commands.run_opportunity_ai_evals.run_opportunity_ai_evals")
    def test_eval_management_command_reports_mocked_success(self, run_evals):
        case = OpportunityEvalCase(id="case-1", prompt="large parcels")
        run_evals.return_value = EvalRunResult([EvalCaseResult(case=case, status="passed", failures=[])])
        stdout = StringIO()
        call_command("run_opportunity_ai_evals", "--json", stdout=stdout)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["summary"]["passed"], 1)
        run_evals.assert_called_once()

    def test_multiunit_prompt_has_safe_deterministic_fallback(self):
        generated = _fallback_generated_search("parcels with multi unit buildings like duplex to sixplex. no sales activity for 15 years. average quality.")
        self.assertIsNotNone(generated)
        self.assertIn("NULLIF(s.sale_date_iso, '')::date", generated.sql)
        self.assertIn("(%s || ' years')::interval", generated.sql)
        self.assertEqual(generated.params, [15])

    def test_ai_search_sql_validator_allows_safe_select(self):
        sql = "SELECT parcel_number FROM read_parquet('r2://openskagit/derived/parcel_search.parquet') WHERE acres > 10"
        self.assertEqual(validate_search_sql(sql, []), sql)

    def test_ai_search_sql_validator_rejects_mutation(self):
        with self.assertRaises(OpportunitySearchError):
            validate_search_sql("DELETE FROM read_parquet('r2://openskagit/derived/parcel_search.parquet') WHERE parcel_number = 'P1'")

    def test_ai_search_sql_validator_rejects_multiple_statements(self):
        with self.assertRaises(OpportunitySearchError):
            validate_search_sql("SELECT parcel_number FROM read_parquet('r2://openskagit/derived/parcel_search.parquet'); SELECT 1")

    def test_ai_search_sql_validator_rejects_admin_and_secret_statements(self):
        with self.assertRaises(OpportunitySearchError):
            validate_search_sql("INSTALL httpfs")
        with self.assertRaises(OpportunitySearchError):
            validate_search_sql("SELECT parcel_number FROM read_parquet('r2://openskagit/derived/parcel_search.parquet') WHERE SECRET = 'x'")

    def test_ai_search_sql_validator_rejects_unapproved_parquet_path(self):
        with self.assertRaises(OpportunitySearchError):
            validate_search_sql("SELECT parcel_number FROM read_parquet('r2://openskagit/private.parquet')")

    def test_ai_search_sql_validator_rejects_arbitrary_url_or_local_path(self):
        with self.assertRaises(OpportunitySearchError):
            validate_search_sql("SELECT parcel_number FROM read_parquet('r2://openskagit/derived/parcel_search.parquet') WHERE 'https://example.com/data.parquet' <> ''")
        with self.assertRaises(OpportunitySearchError):
            validate_search_sql("SELECT parcel_number FROM read_parquet('r2://openskagit/derived/parcel_search.parquet') WHERE '/tmp/data.parquet' <> ''")

    def test_ai_search_sql_validator_rejects_params(self):
        with self.assertRaises(OpportunitySearchError):
            validate_search_sql("SELECT parcel_number FROM read_parquet('r2://openskagit/derived/parcel_search.parquet') WHERE acres > ?", [10])

    def test_ai_search_sql_validator_rejects_placeholder_without_params(self):
        with self.assertRaises(OpportunitySearchError):
            validate_search_sql("SELECT parcel_number FROM read_parquet('r2://openskagit/derived/parcel_search.parquet') WHERE acres > ?")

    def test_ai_search_sql_validator_rejects_with_without_final_select(self):
        with self.assertRaisesRegex(OpportunitySearchError, "final SELECT"):
            validate_search_sql(
                "WITH low_quality AS ("
                "SELECT parcel_number FROM read_parquet('r2://openskagit/derived/parcel_search.parquet')"
                ")"
            )

    def test_ai_search_sql_validator_rejects_unknown_alias_column(self):
        with self.assertRaisesRegex(OpportunitySearchError, "Utilities live in assessor.parquet"):
            validate_search_sql(
                "SELECT ps.parcel_number, ps.utilities "
                "FROM read_parquet('r2://openskagit/derived/parcel_search.parquet') ps "
                "WHERE ps.utilities = 'Yes'"
            )

    def test_ai_search_sql_validator_rejects_broad_city_limits_or_place(self):
        with self.assertRaisesRegex(OpportunitySearchError, "inside_city_limits"):
            validate_search_sql(
                "SELECT ps.parcel_number "
                "FROM read_parquet('r2://openskagit/derived/parcel_search.parquet') ps "
                "WHERE ps.inside_city_limits = TRUE OR ps.city_name = 'Sedro-Woolley'"
            )

    def test_ai_search_sql_validator_rejects_unsafe_land_use_cast(self):
        with self.assertRaisesRegex(OpportunitySearchError, "TRY_CAST"):
            validate_search_sql(
                "SELECT ps.parcel_number "
                "FROM read_parquet('r2://openskagit/derived/parcel_search.parquet') ps "
                "WHERE CAST(regexp_extract(COALESCE(ps.land_use, ''), '^\\\\((\\\\d+)\\\\)', 1) AS INTEGER) BETWEEN 710 AND 790"
            )

    def test_ai_search_sql_validator_allows_assessor_utilities_join(self):
        sql = (
            'SELECT ps.parcel_number AS parcel_number, a."Utilities" AS utilities '
            "FROM read_parquet('r2://openskagit/derived/parcel_search.parquet') ps "
            'JOIN read_parquet(\'r2://openskagit/assessor.parquet\') a ON ps.parcel_number = TRIM(a."Parcel Number") '
            'WHERE TRIM(COALESCE(a."Utilities", \'\')) <> \'\''
        )
        self.assertEqual(validate_search_sql(sql, []), sql)

    def test_ai_search_sql_validator_requires_parcel_number(self):
        with self.assertRaises(OpportunitySearchError):
            validate_search_sql("SELECT acres FROM read_parquet('r2://openskagit/derived/parcel_search.parquet')")

    def test_r2_schema_registry_parses_raw_and_derived_columns(self):
        registry = parquet_registry()
        self.assertIn("r2://openskagit/improvements.parquet", registry)
        self.assertIn("ParcelNumber", registry["r2://openskagit/improvements.parquet"].columns)
        self.assertIn("Parcel Number", registry["r2://openskagit/assessor.parquet"].columns)
        self.assertIn("parcel_number", registry["r2://openskagit/derived/parcel_search.parquet"].columns)

    def test_r2_sample_values_validates_path_column_and_caps_limit(self):
        class FakeConnection:
            description = [("val",), ("n",)]

            def __init__(self):
                self.sql = ""

            def execute(self, sql):
                self.sql = sql
                return self

            def fetchall(self):
                return [("AGAR", 3)]

        fake = FakeConnection()
        client = DuckDBR2OpportunityClient(con=fake)
        output = client.sample_values("r2://openskagit/improvements.parquet", "imprv_det_type_cd", limit=999)
        self.assertIn("AGAR", output)
        self.assertIn("LIMIT 50", fake.sql)
        with self.assertRaises(R2SearchError):
            client.sample_values("r2://openskagit/improvements.parquet", "not_a_column")
        with self.assertRaises(R2SearchError):
            client.sample_values("r2://openskagit/private.parquet", "parcel_number")

    def test_r2_execute_wraps_duckdb_binder_errors_for_retry(self):
        class FakeConnection:
            def execute(self, _sql):
                raise RuntimeError('Binder Error: Ambiguous reference to column name "acres"')

        client = DuckDBR2OpportunityClient(con=FakeConnection())
        with self.assertRaisesRegex(R2SearchError, "DuckDB execution failed: Binder Error"):
            client.execute("SELECT parcel_number, acres FROM read_parquet('r2://openskagit/derived/parcel_search.parquet')")

    def test_r2_result_hydration_formats_existing_ui_shape(self):
        row = format_r2_result_row(
            "P1",
            {
                "parcel_number": "P1",
                "situs_address": "1 MAIN ST",
                "situs_city_state_zip": "Mount Vernon, WA 98273",
                "owner_name": "Owner",
                "land_use": "(111) HOUSEHOLD, SFR, INSIDE CITY",
                "acres": 0.5,
                "assessed_value": 400000,
                "assessor_building_value": 250000,
                "improved_land_value": 150000,
                "zoning_code_short": "R-5",
                "zoning_label": "Residential",
                "gis_x": -122.33,
                "gis_y": 48.42,
            },
            {"parcel_number": "P1", "score": 88, "match_reasons": ["large lot", "residential use"]},
        )
        self.assertEqual(row["parcel_number"], "P1")
        self.assertEqual(row["current_use"], "HOUSEHOLD, SFR, INSIDE CITY")
        self.assertEqual(row["score"], 88)
        self.assertIn("large lot", row["signal_labels"])
        self.assertIn("maps", row["map_url"])
        self.assertEqual(row["assessed_value_fmt"], "$400,000")
        self.assertEqual(row["land_value_fmt"], "$150,000")

    def test_r2_result_hydration_flags_invalid_geometry(self):
        row = format_r2_result_row(
            "P2",
            {"parcel_number": "P2", "gis_x": 1200000, "gis_y": 500000, "land_use": "(911) UNDEVELOPED LAND"},
            {"parcel_number": "P2"},
        )
        self.assertEqual(row["location"], "n/a")
        self.assertEqual(row["map_url"], "")
        self.assertIn("No parcel geometry", row["risk_flags"])

    @tag("live")
    @unittest.skipUnless(os.environ.get("OPPORTUNITY_R2_LIVE_TESTS") == "1", "Set OPPORTUNITY_R2_LIVE_TESTS=1 to run live R2 smoke tests.")
    def test_live_r2_attached_garage_remodel_candidates_smoke(self):
        generated = R2GeneratedSearch(
            short_name="Garage Remodel",
            title="Attached-garage remodel candidates",
            criteria_summary="Live smoke query for parcels with living area and garage area.",
            assumptions=["Smoke test only; not investment advice."],
            sql=(
                "SELECT parcel_number, 75 AS score, 'garage/remodel candidate' AS match_reasons "
                f"FROM read_parquet('{parcel_search_path()}') "
                "WHERE COALESCE(total_garage_area, 0) > 0 "
                "AND COALESCE(primary_building_living_area, largest_building_living_area, 0) > 0 "
                "LIMIT 5"
            ),
            params=[],
            tool_trace=[],
        )
        raw_rows, hydrated_rows, diagnostics = run_generated_r2_search(generated, limit=5)
        self.assertLessEqual(len(raw_rows), 5)
        self.assertEqual(diagnostics["source"], "duckdb_r2")
        for row in hydrated_rows:
            self.assertIn("parcel_number", row)

    def test_ai_search_home_intent_filters_nonresidential_results(self):
        rows = [
            {"parcel_number": "P1", "land_use_code": "110", "current_use": "(110) HOUSEHOLD SFR OUTSIDE CITY", "location": "Main St, Conway", "city": "Conway"},
            {"parcel_number": "P2", "land_use_code": "580", "current_use": "(580) RETAIL TRADE, EATING & DRINKING", "location": "Main St, Conway", "city": "Conway"},
            {"parcel_number": "P3", "land_use_code": "670", "current_use": "(670) GOVERNMENTAL SERVICES", "location": "Main St, Conway", "city": "Conway"},
        ]
        filtered = apply_prompt_result_filters("large homes in Conway suitable for senior community conversion", rows)
        self.assertEqual([row["parcel_number"] for row in filtered], ["P1"])

    def test_ai_search_prompt_place_filters_nonmatching_cities(self):
        rows = [
            {
                "parcel_number": "P1",
                "land_use_code": "111",
                "current_use": "(111) HOUSEHOLD, SFR, INSIDE CITY",
                "location": "114 N REED ST, Sedro-Woolley",
                "city": "Sedro-Woolley",
            },
            {
                "parcel_number": "P2",
                "land_use_code": "111",
                "current_use": "(111) HOUSEHOLD, SFR, INSIDE CITY",
                "location": "4308 WHISTLE LAKE RD, Anacortes",
                "city": "Anacortes",
            },
        ]
        filtered = apply_prompt_result_filters(
            "Parcels located in Sedro-Woolley city or its immediate unincorporated vicinity with existing residential dwellings",
            rows,
        )
        self.assertEqual([row["parcel_number"] for row in filtered], ["P1"])

    def test_ai_search_prompt_filters_do_not_treat_skagit_county_as_place(self):
        rows = [
            {
                "parcel_number": "P1",
                "land_use_code": "510",
                "current_use": "(510) WHOLESALE/RETAIL",
                "location": "1 MAIN ST, Burlington",
                "city": "Burlington",
            }
        ]
        filtered = apply_prompt_result_filters("Commercial retail properties in Skagit County assessed over one million dollars", rows)
        self.assertEqual([row["parcel_number"] for row in filtered], ["P1"])

    def test_ai_search_prompt_filters_allow_residential_condos(self):
        rows = [
            {
                "parcel_number": "P1",
                "land_use_code": "140",
                "current_use": "(140) CONDO RESIDENTIAL",
                "location": "1 MAIN ST, Anacortes",
                "city": "Anacortes",
            }
        ]
        filtered = apply_prompt_result_filters("Residential condominium parcels in Anacortes", rows)
        self.assertEqual([row["parcel_number"] for row in filtered], ["P1"])

    def test_ai_search_prompt_filters_do_not_treat_flood_plain_exclusion_as_place(self):
        rows = [
            {
                "parcel_number": "P1",
                "land_use_code": "911",
                "current_use": "(911) UNDEVELOPED LAND INCORPORATED",
                "location": "1 MAIN ST, Mount Vernon",
                "city": "Mount Vernon",
                "acres": 1.5,
                "utilities": "",
            }
        ]
        filtered = apply_prompt_result_filters("less than 2 acre parcels with no utilities, no exemptions not in flood plain", rows)
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

    def test_skill_reference_context_loads_from_configured_repo_style_path(self):
        with TemporaryDirectory() as tmp:
            references = os.path.join(tmp, "references")
            os.makedirs(references)
            with open(os.path.join(tmp, "SKILL.md"), "w", encoding="utf-8") as handle:
                handle.write("# Skill\n\nPrefer readable labels.")
            with open(os.path.join(references, "descriptions.md"), "w", encoding="utf-8") as handle:
                handle.write("# Descriptions\n\nInvestor meaning for tired buildings.")
            with open(os.path.join(references, "codes.md"), "w", encoding="utf-8") as handle:
                handle.write("# Codes\n\n## `land_use` Mappings\n(111) means SFR.")
            with patch.dict(os.environ, {"OPENSKAGIT_POSTGIS_SKILL_DIR": tmp}):
                _skill_reference_context.cache_clear()
                context = _skill_reference_context()
                metadata = _skill_reference_metadata()
        _skill_reference_context.cache_clear()
        self.assertIn("Prefer readable labels", context)
        self.assertIn("Investor meaning for tired buildings", context)
        self.assertIn("(111) means SFR", context)
        self.assertTrue(metadata["skill_context_loaded"])
        self.assertIn("SKILL.md", metadata["skill_context_files"])
        self.assertIn("descriptions.md", metadata["skill_context_files"])

    def test_skill_reference_context_prefers_project_data_path(self):
        with TemporaryDirectory() as tmp:
            skill_dir = os.path.join(tmp, "data", "openskagit-postgis")
            references = os.path.join(skill_dir, "references")
            os.makedirs(references)
            with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as handle:
                handle.write("# OpenSkagit PostGIS\n\nProject-local skill instructions.")
            with open(os.path.join(references, "descriptions.md"), "w", encoding="utf-8") as handle:
                handle.write("# Descriptions\n\nProject-local readable descriptions.")
            with open(os.path.join(references, "codes.md"), "w", encoding="utf-8") as handle:
                handle.write("# Codes\n\n## `land_use` Mappings\nProject-local land-use mappings.")
            with patch.dict(os.environ, {"OPENSKAGIT_POSTGIS_SKILL_DIR": ""}), override_settings(BASE_DIR=tmp):
                _skill_reference_context.cache_clear()
                context = _skill_reference_context()
                metadata = _skill_reference_metadata()
        _skill_reference_context.cache_clear()
        self.assertIn("Project-local skill instructions", context)
        self.assertIn("Project-local readable descriptions", context)
        self.assertIn("Project-local land-use mappings", context)
        self.assertTrue(metadata["skill_context_loaded"])
        self.assertEqual(metadata["skill_context_source"], references)

    def test_plan_prompt_frames_real_estate_investor_intent_taxonomy(self):
        prompt = _build_plan_prompt("large homes near Mount Vernon for adult family home reuse")
        self.assertIn("real estate investors", prompt)
        self.assertIn("Allowed intent_type values", prompt)
        self.assertIn("existing_residential", prompt)
        self.assertIn("adult family home", prompt)

    def test_fallback_plan_has_structured_investor_intent(self):
        plan = _fallback_search_plan("large homes near Mount Vernon for adult family home reuse")
        self.assertEqual(plan.intent_type, "existing_residential")
        self.assertEqual(plan.asset_type, "existing dwelling")
        self.assertEqual(plan.investor_strategy, "senior_housing_or_adult_family_home_reuse")

    def test_fallback_plan_extracts_located_in_named_city(self):
        plan = _fallback_search_plan(
            "Parcels located in Sedro-Woolley city or its immediate unincorporated vicinity with existing residential dwellings"
        )
        self.assertEqual(plan.location["place"], "sedro-woolley")

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

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("opportunity.ai_search.run_generated_r2_search")
    @patch("opportunity.ai_search.generate_r2_search")
    def test_run_ai_search_saves_r2_results(self, generate_r2_search, run_generated_r2_search):
        generate_r2_search.return_value = SimpleNamespace(
            short_name="Large Lots",
            title="Large lots",
            criteria_summary="Parcels with larger acreage.",
            assumptions=["Screening only."],
            sql="SELECT parcel_number FROM read_parquet('r2://openskagit/derived/parcel_search.parquet')",
            params=[],
            tool_trace=[],
        )
        run_generated_r2_search.return_value = (
            [{"parcel_number": "P1"}],
            [
                {
                    "parcel_number": "P1",
                    "location": "1 MAIN ST, Mount Vernon",
                    "land_use_code": "111",
                    "current_use": "(111) HOUSEHOLD SFR",
                    "map_url": "map",
                    "risk_flags": [],
                    "signal_labels": ["large lot"],
                }
            ],
            {"source": "duckdb_r2"},
        )

        search = run_ai_opportunity_search(self.user, "large parcels")
        self.assertEqual(search.status, OpportunitySearch.STATUS_READY)
        self.assertEqual(search.result_count, 1)
        self.assertEqual(search.generated_sql, generate_r2_search.return_value.sql)
        self.assertEqual(search.result_diagnostics["engine"], "duckdb_r2")

    @patch.dict(os.environ, {"OPENAI_API_KEY": ""})
    def test_run_ai_search_errors_without_openai_key(self):
        search = run_ai_opportunity_search(self.user, "large parcels")
        self.assertEqual(search.status, OpportunitySearch.STATUS_ERROR)
        self.assertIn("OPENAI_API_KEY", search.error)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("opportunity.ai_search.run_generated_r2_search")
    @patch("opportunity.ai_search.generate_r2_search")
    def test_run_ai_search_surfaces_r2_execution_error(self, generate_r2_search, run_generated_r2_search):
        generate_r2_search.return_value = SimpleNamespace(
            short_name="Large Lots",
            title="Large lots",
            criteria_summary="Parcels with larger acreage.",
            assumptions=[],
            sql="SELECT parcel_number FROM read_parquet('r2://openskagit/derived/parcel_search.parquet')",
            params=[],
            tool_trace=[],
        )
        run_generated_r2_search.side_effect = R2SearchError("Missing required R2 environment variables: R2_ACCOUNT_ID")

        search = run_ai_opportunity_search(self.user, "large parcels")
        self.assertEqual(search.status, OpportunitySearch.STATUS_ERROR)
        self.assertIn("R2_ACCOUNT_ID", search.error)

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
