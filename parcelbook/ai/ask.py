"""Public ParcelBook natural-language query API."""

from __future__ import annotations

import logging
from typing import Any

from parcelbook.data.duckdb_r2 import DuckDBR2Client
from parcelbook.data.schema_guide import schema_guide

from .parcel_query_planner import plan_parcel_query
from .result_explainer import explain_rows, standard_caveats
from .sql_safety import validate_select_sql

logger = logging.getLogger(__name__)


def ask_parcels(user_query: str, *, client: DuckDBR2Client | None = None, limit: int = 25) -> dict[str, Any]:
    plan = plan_parcel_query(user_query, schema_text=schema_guide())
    safe_sql = validate_select_sql(plan.sql, limit=limit)
    logger.info("ParcelBook query plan: %s", plan.plan)
    logger.info("ParcelBook SQL: %s", safe_sql)
    client = client or DuckDBR2Client()
    rows = client.query_records(safe_sql)
    return {
        "query": user_query,
        "intent": plan.intent,
        "plan": plan.plan,
        "sql": safe_sql,
        "row_count": len(rows),
        "results": explain_rows(user_query, rows, caveats=plan.caveats),
        "caveats": standard_caveats(plan.caveats),
    }
