"""OpenAI Agents SDK integration for ParcelBook parcel search."""

from __future__ import annotations

from agents import Agent, function_tool

from .duckdb_tools import execute_parcel_sql
from .output_models import ParcelAgentAnswer
from .schema_guide import get_parcel_search_semantic_guide
from .zoning_router import detect_zoning_need, get_zoning_mcp_servers


@function_tool
def get_schema_guide() -> str:
    return get_parcel_search_semantic_guide()


@function_tool
def run_parcel_sql(sql: str, limit: int = 100) -> dict:
    return execute_parcel_sql(sql, limit=limit)


@function_tool
def detect_zoning_need_tool(user_query: str) -> dict:
    return detect_zoning_need(user_query)


INSTRUCTIONS = """
You are the OpenSkagit / ParcelBook Parcel Search Agent.
Always read the schema guide before writing SQL.
Convert natural-language parcel requests into safe DuckDB SQL.
Use only fields described by the schema guide.
Use run_parcel_sql to execute SQL; never pretend to have queried data.
Prefer ranked opportunity results over raw filtering when user asks for opportunities.
Use primary_building_living_area for normal house-size reasoning.
Use total_living_area only for multi-building or total-built-area reasoning.
Do not treat assessed_value as market value.
Do not treat zoning_code_short or zoning_label as legal feasibility.
When zoning/buildability/allowed-use issues matter, use zoning_mcp if enabled.
If zoning_mcp is unavailable, return parcel results but include a caveat that zoning was not checked.
Separate parcel-data match from zoning interpretation.
Return structured ParcelAgentAnswer output.
""".strip()


def build_parcel_search_agent() -> Agent:
    return Agent(
        name="OpenSkagit ParcelBook Parcel Search Agent",
        instructions=INSTRUCTIONS,
        tools=[get_schema_guide, run_parcel_sql, detect_zoning_need_tool],
        mcp_servers=get_zoning_mcp_servers(),
        output_type=ParcelAgentAnswer,
    )


parcel_search_agent = build_parcel_search_agent()
