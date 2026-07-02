"""Safety checks for LLM-generated DuckDB SQL."""

from __future__ import annotations

import re

ALLOWED_SOURCE = "read_parquet('r2://openskagit/derived/parcel_search.parquet')"
FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|copy|create|alter|attach|install|load|pragma|secret|detach|call|export|import)\b", re.I)


def validate_select_sql(sql: str, *, limit: int = 50) -> str:
    cleaned = sql.strip().rstrip(";")
    if not re.match(r"^\s*(with\b[\s\S]+?\bselect\b|select\b)", cleaned, re.I):
        raise ValueError("Only SELECT queries are allowed.")
    if FORBIDDEN.search(cleaned):
        raise ValueError("SQL contains a forbidden statement or keyword.")
    normalized = re.sub(r"\s+", " ", cleaned.lower())
    if ALLOWED_SOURCE.lower() not in normalized:
        raise ValueError(f"SQL must read only from {ALLOWED_SOURCE}.")
    if "read_parquet" in normalized.replace(ALLOWED_SOURCE.lower(), ""):
        raise ValueError("SQL may reference only the allowed parcel_search parquet source.")
    if not re.search(r"\blimit\s+\d+\s*$", cleaned, re.I):
        cleaned = f"{cleaned}\nLIMIT {int(limit)}"
    return cleaned + ";"
