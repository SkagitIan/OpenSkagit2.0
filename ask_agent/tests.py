from __future__ import annotations

import inspect
import re
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from ask_agent import conversation
from ask_agent.agent import AnalysisResponse, QueryResult, _status_message, _tabulate_tool_output
from ask_agent.models import AskMessage, AskThread


# The known local tool names defined inline in ask_agent.agent.answer_question(),
# kept here as a literal list (not imported) so this test catches accidental
# renames/duplicates without needing to run the full DuckDB/Postgres-backed agent.
ASK_AGENT_LOCAL_TOOL_NAMES = {
    "get_analysis_context",
    "run_analysis_query",
    "search_parcels",
    "get_property_context",
    "get_property_summary",
    "get_gis_overlays",
    "get_census_context",
    "get_soils_context",
    "list_gis_layers",
}


class LocalToolNameListStaysInSyncTests(SimpleTestCase):
    def test_hardcoded_local_tool_names_match_build_agent_source(self):
        """Guards ASK_AGENT_LOCAL_TOOL_NAMES against silent drift: every name in the
        list must still be a real @function_tool-decorated def inside _build_agent
        (shared by both answer_question and stream_ask_turn)."""
        from ask_agent.agent import _build_agent

        source = inspect.getsource(_build_agent)
        defined = set(re.findall(r"@function_tool\s*\n\s*def (\w+)\(", source))
        self.assertEqual(defined, ASK_AGENT_LOCAL_TOOL_NAMES)


class SharedToolBuilderTests(SimpleTestCase):
    """ask_agent consolidates budgets/zoning/opportunity tools via shared builder
    functions instead of hand-duplicating @function_tool wrappers (which had already
    drifted out of sync once: ask_agent only had 6 of budgets' 10 current tools)."""

    def test_budget_tools_are_reused_not_duplicated(self):
        from budgets.agent import build_budget_tools

        names = {tool.name for tool in build_budget_tools()}
        self.assertEqual(len(names), len(build_budget_tools()))
        self.assertIn("compare_budget_per_capita", names)
        self.assertIn("read_budget_pages", names)
        self.assertIn("search_all_budget_documents", names)
        self.assertIn("calculate", names)

    def test_zoning_tools_are_exposed(self):
        from zoning_mcp.agent_tools import build_zoning_tools

        tools = build_zoning_tools()
        names = [tool.name for tool in tools]
        self.assertEqual(len(names), len(set(names)), "zoning tool names must be unique")
        self.assertIn("zoning_resolve_parcel", names)
        self.assertIn("zoning_build_feasibility", names)
        self.assertIn("zoning_compare_zones", names)

    def test_opportunity_screening_tools_are_exposed(self):
        from opportunity.agent_tools import build_opportunity_tools

        tools = build_opportunity_tools()
        names = [tool.name for tool in tools]
        self.assertEqual(
            set(names),
            {
                "screen_delinquent_tax_pressure",
                "screen_vacant_buildable_lots",
                "screen_possible_lot_splits",
                "screen_teardown_candidates",
                "screen_assemblage_opportunities",
            },
        )

    def test_consolidated_tool_set_has_no_name_collisions(self):
        """The full tool set ask_agent assembles (its own local tools plus the three
        shared builders) must not have any duplicate function-tool names -- the model
        can't disambiguate two tools with the same name."""
        from budgets.agent import build_budget_tools
        from opportunity.agent_tools import build_opportunity_tools
        from zoning_mcp.agent_tools import build_zoning_tools

        all_names = (
            list(ASK_AGENT_LOCAL_TOOL_NAMES)
            + [tool.name for tool in build_budget_tools()]
            + [tool.name for tool in build_zoning_tools()]
            + [tool.name for tool in build_opportunity_tools()]
        )
        duplicates = {name for name in all_names if all_names.count(name) > 1}
        self.assertEqual(duplicates, set(), f"duplicate tool names: {duplicates}")


class StreamingHelperTests(SimpleTestCase):
    def test_status_message_fills_in_known_tool_arguments(self):
        message = _status_message("search_parcels", {"q": "123 Main St"})
        self.assertEqual(message, "Searching parcels for “123 Main St”…")

    def test_status_message_falls_back_to_prefix_when_argument_missing(self):
        message = _status_message("get_property_context", {})
        self.assertEqual(message, "Pulling the full property report for parcel")

    def test_status_message_falls_back_to_generic_for_unknown_tool(self):
        self.assertEqual(_status_message("some_unlisted_tool", {}), "Working on it…")

    def test_status_message_reuses_budget_tool_status_verbs(self):
        message = _status_message("search_all_budget_documents", {"search_terms": "public safety"})
        self.assertIn("public safety", message)

    def test_tabulate_tool_output_reads_rows_key(self):
        result = _tabulate_tool_output({"rows": [{"parcel": "P1", "score": 5}, {"parcel": "P2", "score": 3}]})
        self.assertEqual(result.columns, ["parcel", "score"])
        self.assertEqual(len(result.rows), 2)

    def test_tabulate_tool_output_reads_results_key(self):
        result = _tabulate_tool_output({"query": "main st", "results": [{"parcel_id": "P1"}]})
        self.assertEqual(result.columns, ["parcel_id"])

    def test_tabulate_tool_output_returns_none_for_non_tabular_data(self):
        self.assertIsNone(_tabulate_tool_output({"parcel": "P1", "property": {"nested": True}}))
        self.assertIsNone(_tabulate_tool_output({"rows": []}))


class ConversationHelperTests(TestCase):
    def test_create_thread_titles_from_first_prompt(self):
        thread = conversation.create_thread("What are the largest parcels in Anacortes?")
        self.assertEqual(thread.title, "What are the largest parcels in Anacortes?")
        self.assertEqual(thread.last_response_id, "")

    def test_get_thread_returns_none_for_unknown_or_malformed_id(self):
        self.assertIsNone(conversation.get_thread(str(uuid.uuid4())))
        self.assertIsNone(conversation.get_thread("not-a-uuid"))
        self.assertIsNone(conversation.get_thread(None))

    def test_append_user_message_persists_role_and_content(self):
        thread = conversation.create_thread("hello")
        message = conversation.append_user_message(thread, "hello")
        self.assertEqual(message.role, AskMessage.Role.USER)
        self.assertEqual(message.content, "hello")

    def test_append_assistant_message_updates_thread_response_id(self):
        thread = conversation.create_thread("hello")
        analysis = AnalysisResponse(answer="Hi there", response_id="resp_123")
        conversation.append_assistant_message(thread, analysis)
        thread.refresh_from_db()
        self.assertEqual(thread.last_response_id, "resp_123")

    def test_append_assistant_message_leaves_response_id_untouched_on_failure(self):
        thread = conversation.create_thread("hello")
        conversation.append_assistant_message(thread, AnalysisResponse(answer="ok", response_id="resp_1"))
        # A later failed turn returns no response_id; the thread should keep the last good one.
        conversation.append_assistant_message(thread, AnalysisResponse(answer="Analysis failed", response_id=None))
        thread.refresh_from_db()
        self.assertEqual(thread.last_response_id, "resp_1")

    def test_append_assistant_message_serializes_decimal_and_date_rows(self):
        import datetime

        thread = conversation.create_thread("hello")
        result = QueryResult(
            columns=["acres", "sold_on"],
            rows=[{"acres": Decimal("1.25"), "sold_on": datetime.date(2026, 1, 1)}],
        )
        message = conversation.append_assistant_message(thread, AnalysisResponse(answer="ok", result=result))
        message.refresh_from_db()
        self.assertEqual(message.structured_result["rows"][0]["acres"], "1.25")
        self.assertIn("2026-01-01", message.structured_result["rows"][0]["sold_on"])


class AskThreadViewTests(TestCase):
    @patch("ask_agent.agent.answer_question")
    def test_posting_without_a_thread_creates_one_and_redirects(self, answer_question):
        answer_question.return_value = AnalysisResponse(answer="There are 12 parcels.", response_id="resp_1")
        response = self.client.post(reverse("ask"), {"prompt": "How many parcels in Anacortes?"})

        self.assertEqual(AskThread.objects.count(), 1)
        thread = AskThread.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("ask_thread", args=[thread.id]))
        self.assertEqual(thread.last_response_id, "resp_1")
        self.assertEqual(list(thread.messages.values_list("role", "content")), [
            ("user", "How many parcels in Anacortes?"),
            ("assistant", "There are 12 parcels."),
        ])
        answer_question.assert_called_once_with("How many parcels in Anacortes?", None)

    def test_getting_an_unknown_thread_404s(self):
        response = self.client.get(reverse("ask_thread", args=[uuid.uuid4()]))
        self.assertEqual(response.status_code, 404)

    def test_getting_a_thread_renders_its_history(self):
        thread = conversation.create_thread("What about Burlington?")
        conversation.append_user_message(thread, "What about Burlington?")
        conversation.append_assistant_message(thread, AnalysisResponse(answer="Burlington has 900 parcels."))

        response = self.client.get(reverse("ask_thread", args=[thread.id]))
        self.assertContains(response, "What about Burlington?")
        self.assertContains(response, "Burlington has 900 parcels.")

    @patch("ask_agent.agent.answer_question")
    def test_posting_to_an_existing_thread_continues_it_with_previous_response_id(self, answer_question):
        thread = conversation.create_thread("first question")
        conversation.append_assistant_message(thread, AnalysisResponse(answer="first answer", response_id="resp_1"))
        answer_question.return_value = AnalysisResponse(answer="second answer", response_id="resp_2")

        response = self.client.post(reverse("ask_thread", args=[thread.id]), {"prompt": "a follow-up"})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("ask_thread", args=[thread.id]))
        answer_question.assert_called_once_with("a follow-up", "resp_1")
        self.assertEqual(AskThread.objects.count(), 1)
        thread.refresh_from_db()
        self.assertEqual(thread.last_response_id, "resp_2")

    @patch("ask_agent.agent.answer_question")
    def test_blank_post_does_not_create_a_thread(self, answer_question):
        response = self.client.post(reverse("ask"), {"prompt": ""})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a question.")
        self.assertEqual(AskThread.objects.count(), 0)
        answer_question.assert_not_called()


class AskStreamViewTests(TestCase):
    def _events(self, response):
        raw = b"".join(response.streaming_content).decode("utf-8")
        events = []
        for block in raw.split("\n\n"):
            if not block.strip():
                continue
            lines = block.splitlines()
            name = next((line[len("event: "):] for line in lines if line.startswith("event: ")), None)
            data = next((line[len("data: "):] for line in lines if line.startswith("data: ")), None)
            events.append((name, data))
        return events

    @patch("ask_agent.agent.stream_ask_turn")
    def test_stream_creates_a_thread_and_emits_its_id_before_the_answer(self, stream_ask_turn):
        stream_ask_turn.return_value = iter([
            {"type": "status", "message": "Running the analysis query…", "tool": "run_analysis_query"},
            {"type": "final", "answer": "There are 12 parcels.", "response_id": "resp_1", "sql": "", "result": None},
        ])
        response = self.client.get(reverse("ask_stream"), {"prompt": "How many parcels?"})
        events = self._events(response)
        event_names = [name for name, _data in events]

        self.assertEqual(event_names[0], "thread")
        self.assertIn("status", event_names)
        self.assertIn("answer", event_names)
        self.assertIn("done", event_names)
        # Real per-tool status text, not one of the old canned thinking/querying/summarizing strings.
        status_data = events[event_names.index("status")][1]
        self.assertIn("Running the analysis query", status_data)
        thread = AskThread.objects.get()
        self.assertIn(str(thread.id), events[0][1])
        self.assertEqual(thread.last_response_id, "resp_1")

    @patch("ask_agent.agent.stream_ask_turn")
    def test_stream_reuses_an_existing_thread_id(self, stream_ask_turn):
        thread = conversation.create_thread("first question")
        stream_ask_turn.return_value = iter([
            {"type": "final", "answer": "answer two", "response_id": "resp_2", "sql": "", "result": None},
        ])

        response = self.client.get(reverse("ask_stream"), {"prompt": "follow up", "thread": str(thread.id)})
        # StreamingHttpResponse is lazy: the generator (and its DB writes) only runs once
        # something actually iterates streaming_content, which _events() does below.
        events = self._events(response)

        self.assertIn(str(thread.id), events[0][1])
        self.assertEqual(AskThread.objects.count(), 1)
        self.assertEqual(thread.messages.count(), 2)  # follow-up user message + assistant answer
        stream_ask_turn.assert_called_once_with("follow up", None)

    @patch("ask_agent.agent.stream_ask_turn")
    def test_stream_persists_structured_result_from_final_event(self, stream_ask_turn):
        stream_ask_turn.return_value = iter([
            {
                "type": "final",
                "answer": "Here are the matches.",
                "response_id": "resp_3",
                "sql": "",
                "result": {"columns": ["parcel_id", "address"], "rows": [{"parcel_id": "P1", "address": "1 Main St"}]},
            },
        ])
        response = self.client.get(reverse("ask_stream"), {"prompt": "find parcels on Main St"})
        self._events(response)

        message = AskMessage.objects.get(role=AskMessage.Role.ASSISTANT)
        self.assertEqual(message.structured_result["columns"], ["parcel_id", "address"])
        self.assertEqual(message.structured_result["rows"][0]["parcel_id"], "P1")

    def test_stream_blank_prompt_does_not_touch_the_database(self):
        response = self.client.get(reverse("ask_stream"), {"prompt": ""})
        events = self._events(response)
        self.assertEqual([name for name, _ in events], ["answer", "done"])
        self.assertEqual(AskThread.objects.count(), 0)
