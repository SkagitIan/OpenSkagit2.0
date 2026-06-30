from __future__ import annotations

import os

import django
from mcp.server.fastmcp import FastMCP

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from . import services  # noqa: E402

mcp = FastMCP("OpenSkagit Zoning MCP")
AGENT_RULE = "Do not answer zoning questions from memory. Use structured zoning tools first; if no structured rule exists, search the source code and cite the source."


@mcp.tool()
def zoning_answer_rule() -> dict:
    return {"rule": AGENT_RULE, "flow": "parcel -> jurisdiction -> zone -> overlays -> proposed use -> standards -> source citation"}


@mcp.tool()
def resolve_parcel(parcel_id: str | None = None, address: str | None = None) -> dict:
    return services.resolve_parcel(parcel_id=parcel_id, address=address)


@mcp.tool()
def get_zone_profile(jurisdiction: str, zone_code: str) -> dict:
    return services.get_zone_profile(jurisdiction, zone_code)


@mcp.tool()
def lookup_use_status(jurisdiction: str, zone_code: str, proposed_use: str) -> dict:
    return services.lookup_use_status(jurisdiction, zone_code, proposed_use)


@mcp.tool()
def list_allowed_uses(jurisdiction: str, zone_code: str, status_filter: list[str] | None = None) -> dict:
    return services.list_allowed_uses(jurisdiction, zone_code, status_filter)


@mcp.tool()
def search_zoning_code(jurisdiction: str, query: str, limit: int = 8) -> dict:
    return services.search_zoning_code(jurisdiction, query, limit)


@mcp.tool()
def get_development_standards(jurisdiction: str, zone_code: str) -> dict:
    return services.get_development_standards(jurisdiction, zone_code)


@mcp.tool()
def get_overlays_and_constraints(parcel_id: str) -> dict:
    return services.get_overlays_and_constraints(parcel_id)


@mcp.tool()
def build_parcel_feasibility_report(parcel_id: str, proposed_use: str) -> dict:
    return services.build_parcel_feasibility_report(parcel_id, proposed_use)


@mcp.tool()
def compare_zones_for_use(proposed_use: str, jurisdictions: list[str] | None = None) -> dict:
    return services.compare_zones_for_use(proposed_use, jurisdictions)


if __name__ == "__main__":
    mcp.run()
