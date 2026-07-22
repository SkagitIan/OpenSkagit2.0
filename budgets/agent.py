from __future__ import annotations

import logging
import os
import re
import threading
from queue import Empty, Queue
from typing import Any, Iterator

from . import services


logger = logging.getLogger(__name__)

MAX_TURNS = 24

INSTRUCTIONS = (
    "You are the OpenSkagit budget analyst: a patient county librarian who has read every published "
    "budget book and always shows the citizen the page. Answer using only the supplied OpenSkagit budget tools. "
    "Never use outside knowledge or memory for any figure -- if a tool has not returned it, you do not know it.\n\n"
    "Workflow: use search_budget_document (one jurisdiction) or search_all_budget_documents (every published "
    "jurisdiction at once) to find candidate pages, then use read_budget_pages to read the full text of the most "
    "relevant pages before summarizing or quoting them. Do not answer from a short search snippet alone if the "
    "question calls for explanation or a quote -- read the page first. Use calculate for any arithmetic on cited "
    "figures (differences, ratios, sums) instead of doing mental math, and use compare_budget_per_capita whenever "
    "the citizen is comparing jurisdictions of very different sizes.\n\n"
    "Be direct, concise, and plain-spoken -- assume no finance background. Always identify the jurisdiction, "
    "fiscal year, and whether the document is proposed, preliminary, adopted, or amended. For every numeric claim, "
    "cite the official source URL and the PDF page supplied by the tool; a quote from document text must cite its "
    "page too. Clearly distinguish all-funds and General Fund figures. Do not call revenue minus expenditure a "
    "surplus unless the source explicitly defines it that way.\n\n"
    "Make numbers meaningful, not just recited: when you give one large number, anchor it (its percent of the "
    "total using percent_of_side_total, or its amount per resident). When comparing jurisdictions of different "
    "sizes, proactively offer a per-capita comparison alongside the raw totals. When a result includes a table-like "
    "list of rows (a breakdown, a comparison, a trend), say so plainly so it can be shown as a table.\n\n"
    "If reviewed data is unavailable for a jurisdiction (for example Hamilton or Lyman currently have no located "
    "budget PDF), say so plainly and do not guess or estimate. If required context is missing, ask one short "
    "follow-up question instead of choosing a jurisdiction or year yourself."
)


def _plain_text_links(value: str) -> str:
    return re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'\1: \2', value)


def _build_tools():
    from agents import function_tool

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
        """Group reviewed budget facts by the best available source dimension, or by fund, department, category, or account. Each row includes percent_of_side_total."""
        return services.budget_get_breakdown(jurisdiction_name, fiscal_year, side, group_by, limit)

    @function_tool
    def get_budget_trend(jurisdiction_name: str, side: str = "expenditure") -> dict[str, Any]:
        """Get a reviewed annual budget trend for one jurisdiction."""
        return services.budget_get_trend(jurisdiction_name, side)

    @function_tool
    def compare_budget_jurisdictions(
        jurisdiction_names: list[str], fiscal_year: int | None = None, side: str = "expenditure"
    ) -> dict[str, Any]:
        """Compare reviewed revenue, expenditure, or fund-balance totals across jurisdictions."""
        return services.budget_compare_jurisdictions(jurisdiction_names, fiscal_year, side)

    @function_tool
    def compare_budget_per_capita(
        jurisdiction_names: list[str], fiscal_year: int | None = None, side: str = "expenditure"
    ) -> dict[str, Any]:
        """Compare reviewed totals per resident across jurisdictions of different sizes. Cites the population source and vintage for each jurisdiction; per_capita is null where population isn't on file."""
        return services.budget_compare_per_capita(jurisdiction_names, fiscal_year, side)

    @function_tool
    def search_budget_document(jurisdiction_name: str, search_terms: str, fiscal_year: int | None = None) -> dict[str, Any]:
        """Full-text search one jurisdiction's official budget PDF and return page-numbered, ranked passages. Use read_budget_pages afterward to read the full page."""
        return services.budget_search_documents(jurisdiction_name, search_terms, fiscal_year)

    @function_tool
    def search_all_budget_documents(search_terms: str, fiscal_year: int | None = None) -> dict[str, Any]:
        """Full-text search across every published jurisdiction's official budget document at once, grouped by jurisdiction. Use this for cross-document questions like 'what does Anacortes say about the water utility' when the jurisdiction isn't fixed yet, or to compare how multiple jurisdictions discuss a topic."""
        return services.budget_search_all_documents(search_terms, fiscal_year)

    @function_tool
    def read_budget_pages(jurisdiction_name: str, start_page: int, end_page: int, fiscal_year: int | None = None) -> dict[str, Any]:
        """Read the full official text of a small page range (up to 5 pages) from one jurisdiction's budget document, with the source URL. Use after search to read past a snippet before summarizing or quoting."""
        return services.budget_read_pages(jurisdiction_name, start_page, end_page, fiscal_year)

    @function_tool
    def calculate(expression: str) -> dict[str, Any]:
        """Safely evaluate a short arithmetic expression, e.g. '115485921 / 17565' or '(120-100)/120*100'. Numbers and + - * / // % ** only. Use this instead of doing mental math on cited figures."""
        return services.calculate(expression)

    return [
        list_budget_jurisdictions,
        get_budget_summary,
        get_budget_breakdown,
        get_budget_trend,
        compare_budget_jurisdictions,
        compare_budget_per_capita,
        search_budget_document,
        search_all_budget_documents,
        read_budget_pages,
        calculate,
    ]


def _build_prompt(question: str, jurisdiction: str, year: int | None) -> str:
    context = []
    if jurisdiction:
        context.append(f"Selected jurisdiction: {jurisdiction}")
    if year:
        context.append(f"Selected fiscal year: {year}")
    return question if not context else f"{question}\n\nPage context:\n" + "\n".join(context)


def _build_agent():
    from agents import Agent

    return Agent(
        name="OpenSkagit budget analyst",
        model=os.environ.get("OPENAI_MODEL", "gpt-4.1"),
        instructions=INSTRUCTIONS,
        tools=_build_tools(),
    )


def answer_budget_question(question: str, jurisdiction: str = "", year: int | None = None) -> str:
    answer, _ = answer_budget_turn(question, jurisdiction, year)
    return answer


def answer_budget_turn(
    question: str,
    jurisdiction: str = "",
    year: int | None = None,
    previous_response_id: str | None = None,
) -> tuple[str, str | None]:
    if not question.strip():
        return "Enter a budget question.", None
    if not os.environ.get("OPENAI_API_KEY"):
        return "Budget chat is not configured. You can still use the jurisdiction and year controls above.", None
    try:
        from agents import Runner
    except ImportError:
        logger.warning("Budget chat unavailable: the 'agents' package is not installed.")
        return "Budget chat is temporarily unavailable.", None

    prompt = _build_prompt(question, jurisdiction, year)
    agent = _build_agent()
    try:
        result = Runner.run_sync(
            agent,
            prompt,
            max_turns=MAX_TURNS,
            previous_response_id=previous_response_id,
            auto_previous_response_id=True,
        )
        return _plain_text_links(str(result.final_output)), result.last_response_id
    except Exception:
        logger.exception("Budget agent run failed for question=%r jurisdiction=%r year=%r", question, jurisdiction, year)
        return "Budget chat is temporarily unavailable. The reviewed figures and official source links are still available above.", None


_RESULT_KIND_BY_TOOL = {
    "get_budget_breakdown": "breakdown",
    "get_budget_trend": "trend",
    "compare_budget_jurisdictions": "comparison",
    "compare_budget_per_capita": "per_capita",
    "search_budget_document": "search",
    "search_all_budget_documents": "search_all",
    "read_budget_pages": "pages",
}


def _classify_result(tool_name: str, data: dict[str, Any]) -> str | None:
    if tool_name in _RESULT_KIND_BY_TOOL:
        return _RESULT_KIND_BY_TOOL[tool_name]
    if "rows" in data or "matches" in data or "results" in data or "pages" in data:
        return "generic"
    return None


_STATUS_VERBS = {
    "list_budget_jurisdictions": "Checking which jurisdictions have reviewed budgets…",
    "get_budget_summary": "Pulling reviewed totals for {jurisdiction_name}…",
    "get_budget_breakdown": "Breaking down {jurisdiction_name}'s budget…",
    "get_budget_trend": "Looking at {jurisdiction_name}'s budget trend…",
    "compare_budget_jurisdictions": "Comparing jurisdictions…",
    "compare_budget_per_capita": "Comparing jurisdictions per resident…",
    "search_budget_document": "Searching the {jurisdiction_name} budget for “{search_terms}”…",
    "search_all_budget_documents": "Searching every budget for “{search_terms}”…",
    "read_budget_pages": "Reading {jurisdiction_name} pages {start_page}–{end_page}…",
    "calculate": "Calculating…",
}


def _status_message(tool_name: str, arguments: dict[str, Any]) -> str:
    template = _STATUS_VERBS.get(tool_name, "Working on it…")
    try:
        return template.format(**arguments)
    except (KeyError, IndexError):
        return template.split("{")[0].strip() or "Working on it…"


_SUGGESTIONS_BY_KIND = {
    "breakdown": [
        "Show that as a table",
        "What about per resident?",
        "Compare that to another jurisdiction",
    ],
    "comparison": [
        "Show that per resident",
        "Which is largest, and is that a lot for its size?",
        "Break one of those down by fund",
    ],
    "per_capita": [
        "Show the raw totals instead",
        "Compare a different fund or side",
        "Which jurisdiction is the outlier, and why?",
    ],
    "trend": [
        "What changed the most year to year?",
        "Compare this trend to another jurisdiction",
    ],
    "search": [
        "Read that full page",
        "Summarize that in plain language",
    ],
    "search_all": [
        "Read the most relevant page",
        "Compare how two of those jurisdictions handle it",
    ],
    "pages": [
        "Summarize this in plain language",
        "What page is that on?",
    ],
}
_DEFAULT_SUGGESTIONS = [
    "What are the largest spending categories?",
    "Compare this to a similar-sized jurisdiction",
    "Show me that as a table",
]


def _suggest_follow_ups(structured_result: dict[str, Any] | None) -> list[str]:
    kind = (structured_result or {}).get("kind")
    return list(_SUGGESTIONS_BY_KIND.get(kind, _DEFAULT_SUGGESTIONS))


def stream_budget_turn(
    question: str,
    jurisdiction: str = "",
    year: int | None = None,
    previous_response_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield status/tool/final events for a budget question, for a streaming (SSE) view.

    Bridges the openai-agents SDK's async streaming Runner to a plain synchronous
    generator via a background thread and a queue, so a sync Django/WSGI view can
    consume it chunk by chunk without needing an ASGI stack.
    """
    if not question.strip():
        yield {"type": "final", "answer": "Enter a budget question.", "response_id": None}
        return
    if not os.environ.get("OPENAI_API_KEY"):
        yield {
            "type": "final",
            "answer": "Budget chat is not configured. You can still use the jurisdiction and year controls above.",
            "response_id": None,
        }
        return
    try:
        from agents import Runner
    except ImportError:
        logger.warning("Budget chat unavailable: the 'agents' package is not installed.")
        yield {"type": "final", "answer": "Budget chat is temporarily unavailable.", "response_id": None}
        return

    import asyncio
    import json

    prompt = _build_prompt(question, jurisdiction, year)
    agent = _build_agent()
    queue: Queue = Queue()
    SENTINEL = object()

    def _run() -> None:
        async def _consume() -> None:
            try:
                result = Runner.run_streamed(
                    agent,
                    prompt,
                    max_turns=MAX_TURNS,
                    previous_response_id=previous_response_id,
                    auto_previous_response_id=True,
                )
                last_tool_result: dict[str, Any] | None = None
                last_tool_name = ""
                async for event in result.stream_events():
                    if event.type != "run_item_stream_event":
                        continue
                    if event.name == "tool_called":
                        item = event.item
                        tool_name = getattr(item, "tool_name", None) or "tool"
                        last_tool_name = tool_name
                        raw_arguments = getattr(item.raw_item, "arguments", None) if not isinstance(item.raw_item, dict) else item.raw_item.get("arguments")
                        try:
                            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else (raw_arguments or {})
                        except (TypeError, ValueError):
                            arguments = {}
                        queue.put({"type": "status", "message": _status_message(tool_name, arguments), "tool": tool_name})
                    elif event.name == "tool_output":
                        output = getattr(event.item, "output", None)
                        if isinstance(output, dict):
                            kind = _classify_result(last_tool_name, output)
                            if kind:
                                last_tool_result = {"tool": last_tool_name, "kind": kind, "data": output}
                queue.put({
                    "type": "final",
                    "answer": _plain_text_links(str(result.final_output)),
                    "response_id": result.last_response_id,
                    "structured_result": last_tool_result,
                    "suggestions": _suggest_follow_ups(last_tool_result),
                })
            except Exception:
                logger.exception(
                    "Budget agent streamed run failed for question=%r jurisdiction=%r year=%r",
                    question, jurisdiction, year,
                )
                queue.put({
                    "type": "final",
                    "answer": "Budget chat is temporarily unavailable. The reviewed figures and official source links are still available above.",
                    "response_id": None,
                })
            finally:
                queue.put(SENTINEL)

        asyncio.run(_consume())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    while True:
        try:
            item = queue.get(timeout=15)
        except Empty:
            yield {"type": "heartbeat"}
            continue
        if item is SENTINEL:
            break
        yield item
    thread.join(timeout=5)
