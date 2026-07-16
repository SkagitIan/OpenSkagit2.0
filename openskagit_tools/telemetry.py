from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Any, Callable

from asgiref.sync import sync_to_async

from .models import McpToolCall

logger = logging.getLogger(__name__)


def _outcome(result: Any) -> str:
    if not isinstance(result, dict):
        return "success"
    if result.get("errors"):
        return "error"
    data = result.get("data")
    if isinstance(data, dict) and data.get("status") == "partial":
        return "partial"
    return "success"


def instrument_tool(handler: Callable[..., Any], *, tool_name: str, caller_class: str) -> Callable[..., Any]:
    """Record aggregate-use evidence without arguments, tokens, or response data."""

    def invoke_and_record(*args, **kwargs):
        started = time.perf_counter()
        result = None
        error_class = ""
        outcome = "error"
        try:
            result = handler(*args, **kwargs)
            outcome = _outcome(result)
            return result
        except Exception as exc:
            error_class = type(exc).__name__
            raise
        finally:
            freshness = result.get("freshness", {}) if isinstance(result, dict) else {}
            try:
                McpToolCall.objects.create(
                    tool_name=tool_name,
                    caller_class=caller_class,
                    outcome=outcome,
                    duration_ms=max(0, round((time.perf_counter() - started) * 1000)),
                    freshness_status=str(freshness.get("status") or "unknown")[:20],
                    freshness_as_of=str(freshness.get("as_of") or "")[:80],
                    error_class=error_class,
                )
            except Exception:
                logger.exception("Unable to record MCP tool telemetry for %s", tool_name)

    @wraps(handler)
    async def wrapped(*args, **kwargs):
        # FastMCP executes async callables on the event loop. Move the complete
        # Django-backed tool invocation, including telemetry, to a sync thread.
        return await sync_to_async(invoke_and_record, thread_sensitive=True)(*args, **kwargs)

    return wrapped
