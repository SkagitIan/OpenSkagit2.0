from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import services

mcp = FastMCP("OpenSkagit Assessor MCP")

AGENT_RULE = (
    "Use assessor tools for live Skagit County property data. "
    "Do not answer assessment questions from memory — always query the live API. "
    "Data reflects county records and may lag real-world changes by one assessment cycle."
)


@mcp.tool()
def assessor_answer_rule() -> dict:
    return {
        "rule": AGENT_RULE,
        "flow": "parcel_id → details → [history|sales|land|improvements|permits|tax_detail]",
        "parcel_format": "P followed by digits, e.g. P45283",
        "note": "get_full_parcel_report fetches all sections in parallel for a comprehensive view.",
    }


@mcp.tool()
def get_parcel_details(parcel_id: str) -> dict:
    """Owner, address, assessed values, sale summary, tax totals, zoning, acres."""
    return services.get_parcel_details(parcel_id)


@mcp.tool()
def get_parcel_history(parcel_id: str) -> dict:
    """Year-over-year assessment history: building, land market, assessed, and tax values."""
    return services.get_parcel_history(parcel_id)


@mcp.tool()
def get_parcel_sales(parcel_id: str) -> dict:
    """Full transfer/sale history: deed type, sale date, price, buyer, seller, auditor file."""
    return services.get_parcel_sales(parcel_id)


@mcp.tool()
def get_parcel_land(parcel_id: str) -> dict:
    """Land segment breakdown: size, appraisal method, description, market value per segment."""
    return services.get_parcel_land(parcel_id)


@mcp.tool()
def get_parcel_improvements(parcel_id: str) -> dict:
    """Building/improvement details: style, year built, living area, garage, bedrooms, etc."""
    return services.get_parcel_improvements(parcel_id)


@mcp.tool()
def get_parcel_permits(parcel_id: str) -> dict:
    """Building permit history for the parcel."""
    return services.get_parcel_permits(parcel_id)


@mcp.tool()
def get_parcel_tax_detail(parcel_id: str, year: int | None = None) -> dict:
    """Detailed tax statement by district: levy rates, amounts, installment amounts. Defaults to current year."""
    return services.get_parcel_tax_detail(parcel_id, year)


@mcp.tool()
def get_full_parcel_report(parcel_id: str) -> dict:
    """Comprehensive parcel report: details, history, sales, land, and improvements in one call."""
    return services.get_full_parcel_report(parcel_id)


if __name__ == "__main__":
    mcp.run()
