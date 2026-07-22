import json
import types
from datetime import date
from decimal import Decimal
from unittest.mock import call, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from budgets import services
from budgets.agent import (
    _classify_result,
    _plain_text_links,
    _status_message,
    _suggest_follow_ups,
    answer_budget_turn,
    stream_budget_turn,
)
from budgets.extraction import _candidate_amounts, parse_money
from budgets.models import BudgetDocument, BudgetDocumentPage, BudgetJurisdiction, BudgetLineItem
from budgets.services import budget_get_breakdown, budget_get_summary, budget_search_documents, budget_list_jurisdictions
from budgets.views import _jurisdiction_from_question


class BudgetServiceTests(TestCase):
    def setUp(self):
        self.jurisdiction, _ = BudgetJurisdiction.objects.update_or_create(
            slug="anacortes", defaults={"name": "City of Anacortes", "mcag": "0628", "kind": "city", "active": True}
        )
        self.document = BudgetDocument.objects.create(
            jurisdiction=self.jurisdiction, fiscal_year=2026, title="2026 Final Adopted Budget",
            status="adopted", version_date=date(2025, 11, 24), source_url="https://example.test/anacortes-2026.pdf",
            content_sha256="a" * 64, page_count=2, published=True, is_current=True,
            extracted_summary={"complete_breakdown_sides": ["expenditure"]},
        )
        BudgetDocumentPage.objects.create(document=self.document, page_number=1, text="The public safety budget supports police and fire staffing.")
        BudgetDocumentPage.objects.create(document=self.document, page_number=2, text="The Water Fund pays for water utility treatment and transmission mains.")
        self.jurisdiction.population = 17565
        self.jurisdiction.population_source = "U.S. Census Bureau, 2020 Decennial Census"
        self.jurisdiction.population_source_year = 2020
        self.jurisdiction.save()
        BudgetLineItem.objects.bulk_create([
            BudgetLineItem(document=self.document, page_number=1, fiscal_year=2026, side="revenue", amount_kind="adopted", account_name="Total revenue", amount=Decimal("120.00"), reviewed=True, is_total=True),
            BudgetLineItem(document=self.document, page_number=1, fiscal_year=2026, side="expenditure", amount_kind="adopted", account_name="Total expenditures", amount=Decimal("100.00"), reviewed=True, is_total=True),
            BudgetLineItem(document=self.document, page_number=1, fiscal_year=2026, side="expenditure", amount_kind="adopted", department_name="Public Safety", amount=Decimal("70.00"), reviewed=True),
            BudgetLineItem(document=self.document, page_number=2, fiscal_year=2026, side="expenditure", amount_kind="adopted", department_name="Parks", amount=Decimal("30.00"), reviewed=True),
        ])
        self.sedro_woolley = BudgetJurisdiction.objects.get(slug="sedro-woolley")
        self.sedro_woolley.population = 12299
        self.sedro_woolley.save()
        self.sedro_woolley_document = BudgetDocument.objects.create(
            jurisdiction=self.sedro_woolley, fiscal_year=2026, title="2025-2026 Biennial Budget Book",
            status="adopted", source_url="https://example.test/sedro-woolley-2026.pdf",
            content_sha256="c" * 64, page_count=1, published=True, is_current=True,
        )
        BudgetLineItem.objects.bulk_create([
            BudgetLineItem(document=self.sedro_woolley_document, page_number=1, fiscal_year=2026, side="revenue", amount_kind="adopted", account_name="Total revenue", amount=Decimal("50.00"), reviewed=True, is_total=True),
            BudgetLineItem(document=self.sedro_woolley_document, page_number=1, fiscal_year=2026, side="expenditure", amount_kind="adopted", account_name="Total expenditures", amount=Decimal("45.00"), reviewed=True, is_total=True),
        ])

    def test_summary_is_explicit_and_does_not_call_difference_surplus(self):
        result = budget_get_summary("anacortes", 2026)
        self.assertEqual(result["document"]["status"], "adopted")
        self.assertEqual(result["totals"], {"revenue": 120.0, "expenditure": 100.0, "difference": 20.0, "fund_balance": 0})
        self.assertIn("not automatically a surplus", result["warning"])

    def test_breakdown_and_page_citations(self):
        breakdown = budget_get_breakdown("City of Anacortes", 2026)
        self.assertEqual([row["name"] for row in breakdown["rows"]], ["Public Safety", "Parks"])
        self.assertEqual(breakdown["side_total"], 100.0)
        search = budget_search_documents("0628", "police staffing", 2026)
        self.assertEqual(search["matches"][0]["page"], 1)
        self.assertEqual(search["document"]["source_url"], "https://example.test/anacortes-2026.pdf")

    def test_breakdown_rows_carry_percent_of_side_total(self):
        breakdown = budget_get_breakdown("anacortes", 2026)
        rows = {row["name"]: row["percent_of_side_total"] for row in breakdown["rows"]}
        self.assertEqual(rows["Public Safety"], 70.0)
        self.assertEqual(rows["Parks"], 30.0)

    def test_search_all_documents_groups_by_jurisdiction_and_skips_unpublished(self):
        result = services.budget_search_all_documents("water utility")
        slugs = [row["jurisdiction"]["slug"] for row in result["results"]]
        self.assertEqual(slugs, ["anacortes"])
        # Sedro-Woolley has a published document (searched) but no page text (no matches).
        self.assertIn("City of Anacortes", result["jurisdictions_searched"])
        self.assertIn("City of Sedro-Woolley", result["jurisdictions_searched"])
        # Hamilton and Lyman have no published document at all, so they're never searched.
        self.assertNotIn("Town of Hamilton", result["jurisdictions_searched"])
        self.assertNotIn("Town of Lyman", result["jurisdictions_searched"])
        anacortes_result = next(row for row in result["results"] if row["jurisdiction"]["slug"] == "anacortes")
        self.assertEqual(anacortes_result["matches"][0]["page"], 2)

    def test_search_all_documents_requires_a_query(self):
        with self.assertRaises(ValueError):
            services.budget_search_all_documents("   ")

    def test_read_budget_pages_returns_full_text_and_caps_span(self):
        result = services.budget_read_pages("anacortes", 1, 2, 2026)
        self.assertEqual([page["page"] for page in result["pages"]], [1, 2])
        self.assertIn("police", result["pages"][0]["text"])
        self.assertFalse(result["capped"])

    def test_read_budget_pages_rejects_out_of_range_pages(self):
        with self.assertRaisesMessage(ValueError, "has only"):
            services.budget_read_pages("anacortes", 50, 51, 2026)

    def test_read_budget_pages_rejects_invalid_range(self):
        with self.assertRaises(ValueError):
            services.budget_read_pages("anacortes", 3, 1, 2026)

    def test_compare_per_capita_cites_population_source(self):
        result = services.budget_compare_per_capita(["anacortes", "sedro-woolley"], 2026, "expenditure")
        rows = {row["jurisdiction"]["slug"]: row for row in result["rows"]}
        self.assertAlmostEqual(rows["anacortes"]["per_capita"], round(100.0 / 17565, 2), places=2)
        self.assertAlmostEqual(rows["sedro-woolley"]["per_capita"], round(45.0 / 12299, 2), places=2)
        self.assertEqual(rows["anacortes"]["population_source"], "U.S. Census Bureau, 2020 Decennial Census")

    def test_compare_per_capita_handles_missing_population(self):
        BudgetJurisdiction.objects.filter(slug="burlington").update(population=None)
        BudgetDocument.objects.create(
            jurisdiction=BudgetJurisdiction.objects.get(slug="burlington"), fiscal_year=2026, title="Burlington budget",
            status="adopted", source_url="https://example.test/burlington-2026.pdf",
            content_sha256="f" * 64, page_count=1, published=True, is_current=True,
        )
        BudgetLineItem.objects.create(
            document=BudgetDocument.objects.get(jurisdiction__slug="burlington"), page_number=1, fiscal_year=2026,
            side="expenditure", amount_kind="adopted", amount=Decimal("10"), reviewed=True, is_total=True,
        )
        result = services.budget_compare_per_capita(["anacortes", "burlington"], 2026, "expenditure")
        row = next(row for row in result["rows"] if row["jurisdiction"]["slug"] == "burlington")
        self.assertIsNone(row["per_capita"])

    def test_calculate_evaluates_safe_arithmetic(self):
        self.assertEqual(services.calculate("100 / 4")["result"], 25.0)
        self.assertAlmostEqual(services.calculate("(120 - 100) / 120 * 100")["result"], 100 * 20 / 120)

    def test_calculate_blocks_unsafe_expressions(self):
        with self.assertRaises(ValueError):
            services.calculate("__import__('os').system('echo hi')")
        with self.assertRaises(ValueError):
            services.calculate("open('/etc/passwd').read()")
        with self.assertRaises(ValueError):
            services.calculate("1 / 0")

    def test_published_preliminary_does_not_override_adopted_default(self):
        BudgetDocument.objects.create(
            jurisdiction=self.jurisdiction, fiscal_year=2027, title="Published preliminary", status="preliminary",
            source_url="https://example.test/preliminary.pdf", content_sha256="e" * 64, published=True, is_current=True,
        )
        self.assertEqual(budget_get_summary("anacortes")["document"]["fiscal_year"], 2026)
    def test_unpublished_working_document_is_not_public_default(self):
        BudgetDocument.objects.create(
            jurisdiction=self.jurisdiction, fiscal_year=2027, title="Working draft", status="preliminary",
            source_url="https://example.test/draft.pdf", content_sha256="b" * 64, published=False, is_current=True,
        )
        self.assertEqual(budget_get_summary("anacortes")["document"]["fiscal_year"], 2026)
        row = next(row for row in budget_list_jurisdictions()["jurisdictions"] if row["slug"] == "anacortes")
        self.assertEqual(row["published_years"], [2026])

    def test_public_page_has_results_sources_and_sample_questions(self):
        response = self.client.get(reverse("budgets:home"), {"jurisdiction": "anacortes", "year": 2026})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "$120")
        self.assertContains(response, "Largest spending departments")
        self.assertContains(response, "Totals cited to")
        self.assertContains(response, "expenditure p. 1")
        self.assertContains(response, "How much is budgeted for public safety?")
        self.assertContains(response, "Official document")

    def test_publish_command_enforces_review_gate(self):
        draft = BudgetDocument.objects.create(
            jurisdiction=self.jurisdiction, fiscal_year=2027, title="Draft", status="preliminary",
            source_url="https://example.test/review.pdf", content_sha256="d" * 64, page_count=1,
        )
        BudgetDocumentPage.objects.create(document=draft, page_number=1, text="Draft budget")
        BudgetLineItem.objects.create(
            document=draft, page_number=1, fiscal_year=2027, side="other", amount_kind="unknown",
            amount=Decimal("10"), raw_data={"candidate_only": True},
        )
        with self.assertRaisesMessage(CommandError, "no reviewed total"):
            call_command("publish_budget_document", document=draft.pk)
        BudgetLineItem.objects.create(
            document=draft, page_number=1, fiscal_year=2027, side="expenditure", amount_kind="recommended",
            department_name="Public Safety", amount=Decimal("10"), reviewed=True, is_total=True,
        )
        call_command("publish_budget_document", document=draft.pk, current=True)
        draft.refresh_from_db()
        self.assertTrue(draft.published)
        self.assertTrue(draft.is_current)
    @patch("budgets.views.answer_budget_turn")
    def test_blank_chat_asks_what_the_citizen_wants_to_know(self, answer_question):
        response = self.client.post(reverse("budgets:ask"), {"question": ""})
        self.assertContains(response, "What would you like to know")
        answer_question.assert_not_called()

    @patch("budgets.views.answer_budget_turn")
    def test_chat_asks_a_follow_up_when_jurisdiction_is_missing(self, answer_question):
        response = self.client.post(reverse("budgets:ask"), {"question": "How much is budgeted for public safety?"})
        self.assertContains(response, "Which jurisdiction do you mean?")
        answer_question.assert_not_called()

    def test_question_can_name_its_jurisdiction(self):
        self.assertEqual(_jurisdiction_from_question("What does Sedro-Woolley spend?"), "sedro-woolley")
        self.assertEqual(_jurisdiction_from_question("What is Skagit spending?"), "skagit-county")
        self.assertEqual(_jurisdiction_from_question("How much is public safety?"), "")

    @patch("budgets.views.answer_budget_turn")
    def test_named_jurisdiction_uses_current_reviewed_year(self, answer_question):
        answer_question.return_value = ("Reviewed answer", "resp_test")
        self.client.post(reverse("budgets:ask"), {"question": "What does Sedro-Woolley spend?"})
        answer_question.assert_called_once_with("What does Sedro-Woolley spend?", "sedro-woolley", 2026, None)

    @patch("budgets.views.answer_budget_turn")
    def test_chat_resolves_current_budget_to_reviewed_year(self, answer_question):
        answer_question.return_value = ("Reviewed answer", "resp_test")
        self.client.post(reverse("budgets:ask"), {"jurisdiction": "anacortes", "question": "What is spent?"})
        answer_question.assert_called_once_with("What is spent?", "anacortes", 2026, None)

    @patch("budgets.views.answer_budget_turn")
    def test_follow_up_uses_previous_response_id(self, answer_question):
        answer_question.side_effect = [("First answer", "resp_one"), ("Second answer", "resp_two")]
        self.client.post(reverse("budgets:ask"), {"jurisdiction": "anacortes", "question": "What is spent?"})
        self.client.post(reverse("budgets:ask"), {"jurisdiction": "anacortes", "question": "And revenue?"})
        self.assertEqual(
            answer_question.call_args_list,
            [
                call("What is spent?", "anacortes", 2026, None),
                call("And revenue?", "anacortes", 2026, "resp_one"),
            ],
        )

    @patch.dict("os.environ", {"OPENAI_API_KEY": ""})
    def test_chat_has_clear_unconfigured_message(self):
        response = self.client.post(reverse("budgets:ask"), {"jurisdiction": "anacortes", "year": "2026", "question": "What is spent?"})
        self.assertContains(response, "Budget chat is not configured")


class BudgetAgentHelperTests(TestCase):
    def test_status_message_fills_in_arguments(self):
        message = _status_message("search_budget_document", {"jurisdiction_name": "Anacortes", "search_terms": "water"})
        self.assertEqual(message, "Searching the Anacortes budget for “water”…")

    def test_status_message_falls_back_when_arguments_are_missing(self):
        message = _status_message("get_budget_summary", {})
        self.assertEqual(message, "Pulling reviewed totals for")

    def test_status_message_falls_back_for_unknown_tool(self):
        self.assertEqual(_status_message("some_future_tool", {}), "Working on it…")

    def test_classify_result_maps_known_tools(self):
        self.assertEqual(_classify_result("get_budget_breakdown", {}), "breakdown")
        self.assertEqual(_classify_result("compare_budget_per_capita", {}), "per_capita")

    def test_classify_result_falls_back_to_shape(self):
        self.assertEqual(_classify_result("some_future_tool", {"rows": []}), "generic")
        self.assertIsNone(_classify_result("calculate", {"result": 1}))

    def test_suggest_follow_ups_uses_kind_specific_suggestions(self):
        suggestions = _suggest_follow_ups({"kind": "per_capita"})
        self.assertIn("Show the raw totals instead", suggestions)

    def test_suggest_follow_ups_defaults_without_structured_result(self):
        suggestions = _suggest_follow_ups(None)
        self.assertEqual(suggestions[0], "What are the largest spending categories?")

    def test_build_budget_tools_is_public_for_reuse_by_other_agents(self):
        # ask_agent imports this directly instead of hand-duplicating tool wrappers.
        from budgets.agent import build_budget_tools

        names = {tool.name for tool in build_budget_tools()}
        self.assertEqual(len(names), 10)
        self.assertIn("read_budget_pages", names)


class _FakeToolCallItem:
    def __init__(self, name, arguments):
        self.raw_item = types.SimpleNamespace(name=name, arguments=arguments)

    @property
    def tool_name(self):
        return self.raw_item.name


class _FakeToolOutputItem:
    def __init__(self, output):
        self.output = output


class _FakeStreamEvent:
    def __init__(self, name, item):
        self.type = "run_item_stream_event"
        self.name = name
        self.item = item


class _FakeStreamedResult:
    def __init__(self, events, final_output, last_response_id="resp_123"):
        self._events = events
        self.final_output = final_output
        self.last_response_id = last_response_id

    async def _events_gen(self):
        for event in self._events:
            yield event

    def stream_events(self):
        return self._events_gen()


class BudgetAgentStreamTests(TestCase):
    @patch.dict("os.environ", {"OPENAI_API_KEY": ""})
    def test_stream_returns_single_final_event_when_unconfigured(self):
        events = list(stream_budget_turn("What is spent?", "anacortes", 2026))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "final")
        self.assertIn("not configured", events[0]["answer"])

    def test_stream_yields_blank_question_message_without_calling_the_model(self):
        events = list(stream_budget_turn("   ", "anacortes", 2026))
        self.assertEqual(events, [{"type": "final", "answer": "Enter a budget question.", "response_id": None}])

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("agents.Runner.run_streamed")
    def test_stream_emits_status_then_final_with_structured_result(self, run_streamed):
        fake_events = [
            _FakeStreamEvent("tool_called", _FakeToolCallItem("get_budget_breakdown", json.dumps({"jurisdiction_name": "anacortes"}))),
            _FakeStreamEvent("tool_output", _FakeToolOutputItem({"rows": [{"name": "Water Fund", "amount": 26121215}], "group_by": "fund", "side": "expenditure"})),
        ]
        run_streamed.return_value = _FakeStreamedResult(fake_events, "Anacortes budgets $26.1M for its Water Fund.")
        events = list(stream_budget_turn("How much for the water fund?", "anacortes", 2026))
        types_seen = [event["type"] for event in events]
        self.assertEqual(types_seen, ["status", "final"])
        self.assertIn("Breaking down", events[0]["message"])
        final = events[-1]
        self.assertEqual(final["answer"], "Anacortes budgets $26.1M for its Water Fund.")
        self.assertEqual(final["response_id"], "resp_123")
        self.assertEqual(final["structured_result"]["kind"], "breakdown")
        self.assertIn("Show that as a table", final["suggestions"])

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("agents.Runner.run_streamed")
    def test_stream_logs_and_degrades_gracefully_on_failure(self, run_streamed):
        run_streamed.side_effect = RuntimeError("boom")
        with self.assertLogs("budgets.agent", level="ERROR"):
            events = list(stream_budget_turn("What is spent?", "anacortes", 2026))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "final")
        self.assertIn("temporarily unavailable", events[0]["answer"])
        self.assertIsNone(events[0]["response_id"])

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("agents.Runner.run_sync")
    def test_answer_budget_turn_logs_the_real_error_server_side(self, run_sync):
        run_sync.side_effect = RuntimeError("upstream exploded")
        with self.assertLogs("budgets.agent", level="ERROR") as logs:
            answer, response_id = answer_budget_turn("What is spent?", "anacortes", 2026)
        self.assertIn("temporarily unavailable", answer)
        self.assertIsNone(response_id)
        self.assertTrue(any("upstream exploded" in message for message in logs.output))


class BudgetCompareViewTests(TestCase):
    def setUp(self):
        self.anacortes, _ = BudgetJurisdiction.objects.update_or_create(
            slug="anacortes", defaults={"name": "City of Anacortes", "mcag": "0628", "kind": "city", "active": True, "population": 17565}
        )
        self.mount_vernon = BudgetJurisdiction.objects.get(slug="mount-vernon")
        self.mount_vernon.population = 35509
        self.mount_vernon.save()
        for jurisdiction, amount in ((self.anacortes, "100"), (self.mount_vernon, "300")):
            document = BudgetDocument.objects.create(
                jurisdiction=jurisdiction, fiscal_year=2026, title="Budget", status="adopted",
                source_url=f"https://example.test/{jurisdiction.slug}.pdf", content_sha256=jurisdiction.slug.ljust(64, "0"),
                page_count=1, published=True, is_current=True,
            )
            BudgetLineItem.objects.create(
                document=document, page_number=1, fiscal_year=2026, side="expenditure", amount_kind="adopted",
                amount=Decimal(amount), reviewed=True, is_total=True,
            )

    def test_compare_page_without_selection_still_renders(self):
        response = self.client.get(reverse("budgets:compare"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Compare jurisdictions side by side")

    def test_compare_page_shows_per_capita_and_citations(self):
        response = self.client.get(reverse("budgets:compare"), {"jurisdictions": "anacortes,mount-vernon", "side": "expenditure"})
        self.assertContains(response, "City of Anacortes")
        self.assertContains(response, "City of Mount Vernon")
        self.assertContains(response, "17,565")
        self.assertContains(response, "example.test/anacortes.pdf#page=1")

    def test_compare_page_accepts_repeated_checkbox_params(self):
        # The <form> renders one checkbox per jurisdiction, all named "jurisdictions",
        # so a real submission sends repeated query params, not one comma-joined value.
        response = self.client.get(reverse("budgets:compare"), {"jurisdictions": ["anacortes", "mount-vernon"], "side": "expenditure"})
        self.assertContains(response, "City of Anacortes")
        self.assertContains(response, "City of Mount Vernon")


class BudgetAskStreamViewTests(TestCase):
    def setUp(self):
        self.jurisdiction, _ = BudgetJurisdiction.objects.update_or_create(
            slug="anacortes", defaults={"name": "City of Anacortes", "mcag": "0628", "kind": "city", "active": True}
        )
        self.document = BudgetDocument.objects.create(
            jurisdiction=self.jurisdiction, fiscal_year=2026, title="Budget", status="adopted",
            source_url="https://example.test/anacortes.pdf", content_sha256="a" * 64, page_count=1,
            published=True, is_current=True,
        )
        BudgetLineItem.objects.create(
            document=self.document, page_number=1, fiscal_year=2026, side="expenditure", amount_kind="adopted",
            amount=Decimal("100"), reviewed=True, is_total=True,
        )

    def _events(self, response):
        raw = b"".join(response.streaming_content).decode("utf-8")
        return [json.loads(chunk[len("data: "):]) for chunk in raw.split("\n\n") if chunk.startswith("data: ")]

    def test_stream_endpoint_rejects_get(self):
        response = self.client.get(reverse("budgets:ask_stream"))
        self.assertEqual(response.status_code, 405)

    def test_stream_endpoint_blank_question(self):
        response = self.client.post(reverse("budgets:ask_stream"), {"question": ""})
        events = self._events(response)
        self.assertEqual(events, [{"type": "final", "answer": "What would you like to know about the budget?", "response_id": None}])

    def test_stream_endpoint_unknown_jurisdiction(self):
        response = self.client.post(reverse("budgets:ask_stream"), {"question": "How much is budgeted for public safety?"})
        events = self._events(response)
        self.assertEqual(events[-1]["answer"], "Which jurisdiction do you mean? Choose one above, then ask again.")

    @patch.dict("os.environ", {"OPENAI_API_KEY": ""})
    def test_stream_endpoint_emits_context_then_unconfigured_message(self):
        response = self.client.post(reverse("budgets:ask_stream"), {"question": "What is spent?", "jurisdiction": "anacortes"})
        events = self._events(response)
        self.assertEqual(events[0], {"type": "context", "jurisdiction": "anacortes", "year": 2026})
        self.assertIn("not configured", events[-1]["answer"])


class BudgetExtractionTests(TestCase):
    def test_markdown_source_link_is_rendered_as_safe_plain_url(self):
        answer = '[Burlington budget, page 43 (PDF)](https://example.test/budget.pdf)'
        self.assertEqual(_plain_text_links(answer), 'Burlington budget, page 43 (PDF): https://example.test/budget.pdf')

    def test_money_parser(self):
        self.assertEqual(parse_money("$1,234.50"), Decimal("1234.50"))
        self.assertEqual(parse_money("(250)"), Decimal("-250"))

    def test_implausibly_large_candidate_is_ignored(self):
        self.assertEqual(_candidate_amounts(1, "Malformed total 123456789012345678901"), [])
