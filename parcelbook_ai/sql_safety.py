"""Mandatory SQL safety layer for agent-generated DuckDB SQL."""

from __future__ import annotations

import os
import re

DEFAULT_PARQUET_PATH = "r2://openskagit/derived/parcel_search.parquet"
FORBIDDEN = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|COPY|EXPORT|ATTACH|INSTALL|LOAD|SECRET|PRAGMA|CALL|SET|DETACH|TRUNCATE)\b", re.I)
LIMIT_RE = re.compile(r"\bLIMIT\s+(\d+)\b", re.I)
READ_PARQUET_RE = re.compile(r"read_parquet\s*\(\s*(['\"])(.*?)\1\s*\)", re.I)
URL_OR_PATH_RE = re.compile(r"(['\"])((?:https?://|file:|/|\.\.?/)[^'\"]+)\1", re.I)


def _allowed_paths() -> set[str]:
    return {DEFAULT_PARQUET_PATH, os.environ.get("PARCEL_SEARCH_PARQUET_PATH", DEFAULT_PARQUET_PATH)}


def _strip_terminal_semicolon(sql: str) -> str:
    stripped = sql.strip()
    if ";" not in stripped:
        return stripped
    if stripped.endswith(";") and stripped.count(";") == 1:
        return stripped[:-1].strip()
    raise ValueError("Multiple statements or non-terminal semicolons are not allowed.")


def validate_and_limit_sql(sql: str, limit: int = 100) -> str:
    cleaned = _strip_terminal_semicolon(sql)
    if not re.match(r"^\s*(SELECT\b|WITH\b[\s\S]+?\bSELECT\b)", cleaned, re.I):
        raise ValueError("Only SELECT queries or WITH ... SELECT queries are allowed.")
    if FORBIDDEN.search(cleaned):
        raise ValueError("SQL contains a forbidden destructive/admin keyword.")

    parquet_refs = READ_PARQUET_RE.findall(cleaned)
    if not parquet_refs:
        raise ValueError("SQL must reference read_parquet for parcel_search.parquet.")
    allowed = _allowed_paths()
    for _, path in parquet_refs:
        if path not in allowed:
            raise ValueError("SQL may reference only the configured parcel_search.parquet R2 path.")
    if len(parquet_refs) != len(READ_PARQUET_RE.findall(cleaned)):
        raise ValueError("Malformed read_parquet reference.")
    for _, value in URL_OR_PATH_RE.findall(cleaned):
        if value not in allowed:
            raise ValueError("Arbitrary local paths and HTTP URLs are not allowed.")

    max_limit = int(limit)
    match = None
    for match in LIMIT_RE.finditer(cleaned):
        pass
    if match is None:
        cleaned = f"{cleaned}\nLIMIT {max_limit}"
    elif int(match.group(1)) > max_limit:
        cleaned = cleaned[: match.start(1)] + str(max_limit) + cleaned[match.end(1) :]
    return cleaned + ";"
