import os
from functools import lru_cache
from typing import Optional

import yaml


REGISTRY_PATH = os.environ.get("TOOL_REGISTRY_PATH", "catalog/tools/tool_registry.yaml")


@lru_cache(maxsize=1)
def load_registry() -> dict:
    """Load and cache the tool registry. Call reload_registry() to bust cache."""
    with open(REGISTRY_PATH, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {"tools": []}


def reload_registry() -> None:
    """Bust the cache. Call after registry file changes in development."""
    load_registry.cache_clear()


def get_tool(tool_id: str) -> Optional[dict]:
    """Return a tool definition by ID, or None if not found."""
    registry = load_registry()
    for tool in registry.get("tools", []):
        if tool["id"] == tool_id:
            return tool
    return None


def find_tools_by_trigger(question: str) -> list[dict]:
    """Return all tools whose trigger keywords appear in the question."""
    question_lower = question.lower()
    registry = load_registry()
    matches = []
    for tool in registry.get("tools", []):
        for trigger in tool.get("triggers", []):
            if trigger.lower() in question_lower:
                matches.append(tool)
                break
    return matches


def list_tools() -> list[dict]:
    """Return all registered tools."""
    return load_registry().get("tools", [])
