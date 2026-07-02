"""Deterministic zoning-need router for ParcelBook AI."""

from __future__ import annotations

import logging
import os
import shlex

logger = logging.getLogger(__name__)

ZONING_KEYWORDS = [
    "zoning", "allowed", "permitted", "prohibited", "conditional", "cup", "feasibility",
    "build", "convert", "adu", "accessory dwelling", "duplex", "triplex", "fourplex",
    "middle housing", "multifamily", "subdivision", "short plat", "density", "setback",
    "setbacks", "height", "lot coverage", "parking", "restaurant", "storage",
    "contractor yard", "mobile home park", "campground", "rv park",
]


def normalize_proposed_use(user_query: str) -> str | None:
    q = user_query.lower()
    if "adu" in q or "accessory dwelling" in q:
        return "accessory dwelling unit"
    if "restaurant" in q:
        return "restaurant"
    for phrase in ["contractor yard", "mobile home park", "campground", "rv park", "duplex", "triplex", "fourplex", "multifamily", "storage"]:
        if phrase in q:
            return phrase
    return None


def detect_zoning_need(user_query: str) -> dict:
    q = user_query.lower()
    proposed_use = normalize_proposed_use(user_query)
    hits = [kw for kw in ZONING_KEYWORDS if kw in q]
    if not hits:
        return {"needs_zoning": False, "mode": "none", "reason": "No zoning/buildability keywords detected.", "proposed_use": None, "zoning_questions": []}

    starts_zoning_only = q.strip().startswith(("which zones", "what zones", "where is", "is ", "are ")) and "parcel" not in q
    zoning_first = "find parcels" in q and ("zones where" in q or "where" in q and ("allowed" in q or "permitted" in q))
    mode = "zoning_only" if starts_zoning_only else "zoning_first" if zoning_first else "parcel_first"
    return {
        "needs_zoning": True,
        "mode": mode,
        "reason": f"Detected zoning/buildability terms: {', '.join(hits)}.",
        "proposed_use": proposed_use,
        "zoning_questions": [f"Check zoning rules for {proposed_use or 'the proposed use/buildability issue'}"],
    }


def get_zoning_mcp_servers() -> list:
    if os.environ.get("ZONING_MCP_ENABLED", "false").lower() not in {"1", "true", "yes", "on"}:
        return []
    try:
        from agents.mcp import MCPServerStdio, MCPServerStreamableHttp
        transport = os.environ.get("ZONING_MCP_TRANSPORT", "stdio").lower()
        if transport == "http":
            url = os.environ.get("ZONING_MCP_URL")
            return [MCPServerStreamableHttp(params={"url": url})] if url else []
        command = os.environ.get("ZONING_MCP_COMMAND", "python manage.py check_zoning_mcp")
        parts = shlex.split(command)
        return [MCPServerStdio(params={"command": parts[0], "args": parts[1:]})]
    except Exception as exc:
        logger.warning("Zoning MCP configuration failed; continuing without MCP: %s", exc)
        return []
