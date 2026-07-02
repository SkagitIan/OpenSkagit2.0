"""DuckDB/R2 query helpers for ParcelBook AI."""

from __future__ import annotations

import os
from typing import Any

from .sql_safety import DEFAULT_PARQUET_PATH, validate_and_limit_sql

DEFAULT_CAVEATS = [
    "Assessed value is not market value.",
    "Zoning fields in parcel_search are discovery signals, not final legal zoning determinations.",
    "Missing geometry or address means the source data is incomplete for that parcel, not that the parcel is invalid.",
]


def parcel_search_path() -> str:
    return os.environ.get("PARCEL_SEARCH_PARQUET_PATH", DEFAULT_PARQUET_PATH)


def get_duckdb_connection():
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    account_id = os.environ.get("R2_ACCOUNT_ID")
    key_id = os.environ.get("R2_ACCESS_KEY_ID")
    secret = os.environ.get("R2_SECRET_ACCESS_KEY")
    if account_id and key_id and secret:
        con.execute(
            """
            CREATE OR REPLACE SECRET r2_secret (
                TYPE R2,
                KEY_ID ?,
                SECRET ?,
                ACCOUNT_ID ?
            )
            """,
            [key_id, secret, account_id],
        )
    return con


def get_parcel_schema() -> list[dict[str, Any]]:
    con = get_duckdb_connection()
    rows = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{parcel_search_path()}')").fetchall()
    return [{"name": row[0], "type": row[1], "null": row[2]} for row in rows]


def execute_parcel_sql(sql: str, limit: int = 100) -> dict[str, Any]:
    safe_sql = validate_and_limit_sql(sql, limit=limit)
    con = get_duckdb_connection()
    cursor = con.execute(safe_sql)
    columns = [d[0] for d in cursor.description or []]
    rows = [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]
    return {"sql": safe_sql, "row_count": len(rows), "rows": rows, "caveats": list(DEFAULT_CAVEATS)}
