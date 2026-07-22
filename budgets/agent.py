from __future__ import annotations

import os
import re
from typing import Any

from . import services


def _plain_text_links(value: str) -> str:
    return re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'\1: \2', value)


def answer_budget_question(question: str, jurisdiction: str = "", year: int | None = None) -> str:
    if not question.strip():
        return "Enter a budget question."
    if not os.environ.get("OPENAI_API_KEY"):
        return "Budget chat is not configured. You can still use the jurisdiction and year controls above."
    try:
        from agents import Agent, Runner, function_tool
    except ImportError:
        return "Budget chat is temporarily unavailable."

    @function_tool
    def list_budget_jurisdictions() -> dict[str, Any]:
        """List budget jurisdictions and years with reviewed public data."""
        return services.budget_list_jurisdictions()

    @function_tool
    def get_budget_summary(jurisdiction_name: str, fiscal_year: int | None = None) -> dict[str, Any]:
        """Get reviewed revenue, expenditure, and fund-balance totals from the selected official budget document."""
        return services.budget_get_summary(jurisdiction_name, fiscal_year)

    @function_tool
    def get_budget_breakdown(
        jurisdiction_name: str,
        fiscal_year: int | None = None,
        side: str = "expenditure",
        group_by: str = "auto",
        limit: int = 20,
    ) -> dict[str, Any]:
        """Group reviewed budget facts by the best available source dimension, or by fund, department, category, or account."""
        return services.budget_get_breakdown(jurisdiction_name, fiscal_year, side, group_by, limit)

    @function_tool
    def get_budget_trend(jurisdiction_name: str, side: str = "expenditure") -> dict[str, Any]:
        """Get a reviewed annual budget trend for one jurisdiction."""
        return services.budget_get_trend(jurisdiction_name, side)

    @function_tool
    def compare_budget_jurisdictions(jurisdiction_names: list[str], fiscal_year: int | None = None, side: str = "expenditure") -> dict[str, Any]:
        """Compare reviewed revenue, expenditure, or fund-balance totals across jurisdictions."""
        return services.budget_compare_jurisdictions(jurisdiction_names, fiscal_year, side)
    @function_tool
    def search_budget_document(jurisdiction_name: str, search_terms: str, fiscal_year: int | None = None) -> dict[str, Any]:
        """Search the official budget PDF text and return page-numbered passages."""
        return services.budget_search_documents(jurisdiction_name, search_terms, fiscal_year)

    context = []
    if jurisdiction:
        context.append(f"Selected jurisdiction: {jurisdiction}")
    if year:
        context.append(f"Selected fiscal year: {year}")
    prompt = question if not context else f"{question}\n\nPage context:\n" + "\n".join(context)
    agent = Agent(
        name="OpenSkagit budget analyst",
        model=os.environ.get("OPENAI_MODEL", "gpt-4.1"),
        instructions=(
            "Answer citizen questions using only the supplied OpenSkagit budget tools. Be direct and concise. "
            "Always identify the jurisdiction, fiscal year, and whether the document is proposed, preliminary, adopted, or amended. "
            "For every numeric claim, cite the official source URL and the PDF page supplied by the tool. Clearly distinguish all-funds and General Fund figures. "
            "Cite the official source URL and page number when using document search. Do not call revenue minus expenditure a surplus "
            "unless the source explicitly defines it that way. If reviewed data is unavailable, say so plainly and do not guess."
        ),
        tools=[list_budget_jurisdictions, get_budget_summary, get_budget_breakdown, get_budget_trend, compare_budget_jurisdictions, search_budget_document],
    )
    try:
        result = Runner.run_sync(agent, prompt, max_turns=10)
        return _plain_text_links(str(result.final_output))
    except Exception:
        return "Budget chat is temporarily unavailable. The reviewed figures and official source links are still available above."
