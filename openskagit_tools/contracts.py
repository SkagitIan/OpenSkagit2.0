from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

CONTRACT_VERSION = "1.0"
FreshnessStatus = Literal["fresh", "stale", "unknown"]


@dataclass(frozen=True)
class ToolContract:
    name: str
    domain: str
    description: str
    source_ids: tuple[str, ...]
    read_only: bool = True
    contract_version: str = CONTRACT_VERSION


def result_envelope(
    data: Any,
    *,
    contract: ToolContract,
    warnings: list[str] | None = None,
    errors: list[dict[str, Any]] | None = None,
    as_of: str | None = None,
    freshness_status: FreshnessStatus = "unknown",
) -> dict[str, Any]:
    """Return the common read-only tool result shape.

    ``retrieved_at`` records when OpenSkagit assembled the response. It must not be
    treated as the source data's effective date, so freshness remains ``unknown``
    unless a service supplies a real ``as_of`` value.
    """
    retrieved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "data": data,
        "sources": [
            {"source_id": source_id, "retrieved_at": retrieved_at}
            for source_id in contract.source_ids
        ],
        "freshness": {"as_of": as_of, "status": freshness_status},
        "warnings": list(warnings or []),
        "errors": list(errors or []),
    }
