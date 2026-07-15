"""Read-only, bounded Cypher execution for internal parcel graph searches.

This module does not permit graph mutation or identity-bearing result fields
for end-user queries. It runs Kuzu in a child process so a stalled query can be
terminated on Windows as well as Unix.
"""
from __future__ import annotations
import multiprocessing as mp
import re
from queue import Empty
from pathlib import Path
from typing import Any
from graph.patterns import DEFAULT_GRAPH_ZIP

DEFAULT_CYPHER_LIMIT = 200
_FORBIDDEN = re.compile(r"\b(CREATE|MERGE|SET|DELETE|DETACH|DROP|COPY|INSTALL|LOAD|TRANSACTION|CALL)\b", re.IGNORECASE)
_FORBIDDEN_RETURN_FIELDS = re.compile(r"\b(canonical_name|entity_id|group_id|mailing_key|mailing_address|owner_name|owner)\b", re.IGNORECASE)

def _return_clause(query: str) -> str:
    match = re.search(r"\bRETURN\b(.*?)(?:\bLIMIT\b|$)", query, re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else ""

def validate_cypher(query: str, limit: int = DEFAULT_CYPHER_LIMIT, allow_internal: bool = False) -> str:
    """Validate read-only Cypher and enforce a result limit."""
    value = (query or "").strip()
    if not value or ";" in value:
        raise ValueError("Cypher must be one non-empty statement without semicolons.")
    if not re.search(r"\bMATCH\b", value, re.IGNORECASE) or not re.search(r"\bRETURN\b", value, re.IGNORECASE):
        raise ValueError("Cypher must contain MATCH and RETURN.")
    if _FORBIDDEN.search(value):
        raise ValueError("Cypher contains a mutation, DDL, import, or procedure clause.")
    if not allow_internal and _FORBIDDEN_RETURN_FIELDS.search(_return_clause(value)):
        raise ValueError("End-user graph results cannot return owner/entity/address fields.")
    bounded = max(1, min(int(limit), DEFAULT_CYPHER_LIMIT))
    limit_match = re.search(r"\bLIMIT\s+(\d+)\s*$", value, re.IGNORECASE)
    if limit_match:
        requested = int(limit_match.group(1))
        return value[:limit_match.start(1)] + str(min(requested, bounded))
    return f"{value} LIMIT {bounded}"

def _execute_worker(graph_zip: str, query: str, queue) -> None:
    try:
        from graph.patterns import _connection
        with _connection(Path(graph_zip)) as connection:
            rows = connection.execute(query).get_as_df().to_dict("records")
        queue.put((True, rows))
    except Exception as exc:  # noqa: BLE001
        queue.put((False, str(exc)))

def execute_cypher(query: str, limit: int = DEFAULT_CYPHER_LIMIT, timeout_seconds: float = 10.0, graph_zip: Path = DEFAULT_GRAPH_ZIP, allow_internal: bool = False) -> list[dict[str, Any]]:
    """Execute validated Cypher in a read-only child process with a hard timeout."""
    validated = validate_cypher(query, limit=limit, allow_internal=allow_internal)
    context = mp.get_context("spawn")
    queue = context.Queue()
    process = context.Process(target=_execute_worker, args=(str(graph_zip), validated, queue))
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(2)
        raise TimeoutError(f"Cypher exceeded {timeout_seconds:.1f}s timeout.")
    try:
        ok, payload = queue.get(timeout=1)
    except Empty as exc:
        raise RuntimeError(f"Cypher worker exited with code {process.exitcode}.") from exc
    if not ok:
        raise RuntimeError(str(payload))
    return payload