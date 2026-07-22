from datetime import date
from decimal import Decimal
from unittest.mock import call, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from budgets.agent import _plain_text_links
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
        )
        BudgetDocumentPage.objects.create(document=self.document, page_number=1, text="The public safety budget supports police and fire staffing.")
        BudgetLineItem.objects.bulk_create([
            BudgetLineItem(document=self.document, page_number=1, fiscal_year=2026, side="revenue", amount_kind="adopted", account_name="Total revenue", amount=Decimal("120.00"), reviewed=True, is_total=True),
            BudgetLineItem(document=self.document, page_number=1, fiscal_year=2026, side="expenditure", amount_kind="adopted", account_name="Total expenditures", amount=Decimal("100.00"), reviewed=True, is_total=True),
            BudgetLineItem(document=self.document, page_number=1, fiscal_year=2026, side="expenditure", amount_kind="adopted", department_name="Public Safety", amount=Decimal("70.00"), reviewed=True),
            BudgetLineItem(document=self.document, page_number=2, fiscal_year=2026, side="expenditure", amount_kind="adopted", department_name="Parks", amount=Decimal("30.00"), reviewed=True),
        ])

    def test_summary_is_explicit_and_does_not_call_difference_surplus(self):
        result = budget_get_summary("anacortes", 2026)
        self.assertEqual(result["document"]["status"], "adopted")
        self.assertEqual(result["totals"], {"revenue": 120.0, "expenditure": 100.0, "difference": 20.0, "fund_balance": 0})
        self.assertIn("not automatically a surplus", result["warning"])

    def test_breakdown_and_page_citations(self):
        breakdown = budget_get_breakdown("City of Anacortes", 2026)
        self.assertEqual([row["name"] for row in breakdown["rows"]], ["Public Safety", "Parks"])
        search = budget_search_documents("0628", "police staffing", 2026)
        self.assertEqual(search["matches"][0]["page"], 1)
        self.assertEqual(search["document"]["source_url"], "https://example.test/anacortes-2026.pdf")

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


class BudgetExtractionTests(TestCase):
    def test_markdown_source_link_is_rendered_as_safe_plain_url(self):
        answer = '[Burlington budget, page 43 (PDF)](https://example.test/budget.pdf)'
        self.assertEqual(_plain_text_links(answer), 'Burlington budget, page 43 (PDF): https://example.test/budget.pdf')

    def test_money_parser(self):
        self.assertEqual(parse_money("$1,234.50"), Decimal("1234.50"))
        self.assertEqual(parse_money("(250)"), Decimal("-250"))

    def test_implausibly_large_candidate_is_ignored(self):
        self.assertEqual(_candidate_amounts(1, "Malformed total 123456789012345678901"), [])
