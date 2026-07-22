from __future__ import annotations

import inspect
import re

from django.test import SimpleTestCase


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
    def test_hardcoded_local_tool_names_match_answer_question_source(self):
        """Guards ASK_AGENT_LOCAL_TOOL_NAMES against silent drift: every name in the
        list must still be a real @function_tool-decorated def inside answer_question."""
        from ask_agent.agent import answer_question

        source = inspect.getsource(answer_question)
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
