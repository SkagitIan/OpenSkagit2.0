"""Prompts for ParcelBook natural-language parcel search."""

from __future__ import annotations

from pathlib import Path

from parcelbook.data.schema_guide import schema_guide

def planner_skill_text() -> str:
    return (Path(__file__).with_name("SKILL.md")).read_text()


PLANNER_SYSTEM_PROMPT = """You are ParcelBook's parcel-query planner for Skagit County, Washington.
Turn a user's natural-language request into safe DuckDB SQL over the parcel_search parquet.
Return JSON with keys: intent, plan, sql, caveats.
Rules:
- Use only known columns from the schema guide.
- Use only read_parquet('r2://openskagit/derived/parcel_search.parquet').
- Produce SELECT-only SQL with a LIMIT.
- Add a ranking score when the query asks for opportunities or candidates.
- Treat missing geometry/address as data flags, not errors, unless the user requires map/address results.
- Prefer primary_building_living_area for house-size filters.
- Do not make legal zoning claims; zoning fields are planning signals requiring verification.
"""


def planner_user_prompt(user_query: str, schema_text: str | None = None) -> str:
    return f"""ParcelBook planner skill:
{planner_skill_text()}

Schema guide:
{schema_text or schema_guide()}

User query: {user_query}

Return compact JSON only."""
