"""DuckDB helpers for resolving parcels from the R2 parcel_search parquet layer."""

from __future__ import annotations

import os
import re
from typing import Any

from .seed_data import JURISDICTIONS
from .services import normalize_jurisdiction, normalize_zone_code

DEFAULT_PARCEL_SEARCH_PARQUET_PATH = "r2://openskagit/derived/parcel_search.parquet"
PARCEL_SEARCH_SOURCE = "OpenSkagit parcel_search.parquet via DuckDB/R2"

_SELECT_COLUMNS = """
    parcel_number,
    situs_address,
    situs_city_state_zip,
    city_name,
    inside_city_limits,
    zoning_code_short,
    zoning_label,
    has_geometry,
    has_situs_address,
    acres,
    land_use,
    assessed_value,
    primary_building_living_area,
    total_living_area,
    improvement_building_count,
    primary_actual_year_built,
    years_since_last_valid_sale
"""


def get_duckdb_connection():
    """Create an in-memory DuckDB connection configured for Cloudflare R2."""
    import duckdb

    conn = duckdb.connect(database=":memory:")
    conn.execute("INSTALL httpfs")
    conn.execute("LOAD httpfs")

    account_id = os.environ.get("R2_ACCOUNT_ID", "").strip()
    access_key_id = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
    secret_access_key = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
    os.environ.get("R2_BUCKET", "openskagit").strip() or "openskagit"

    if account_id and access_key_id and secret_access_key:
        endpoint = f"{account_id}.r2.cloudflarestorage.com"
        conn.execute(
            f"""
            CREATE OR REPLACE SECRET openskagit_r2 (
                TYPE S3,
                KEY_ID {_duckdb_string(access_key_id)},
                SECRET {_duckdb_string(secret_access_key)},
                REGION 'auto',
                ENDPOINT {_duckdb_string(endpoint)},
                URL_STYLE 'path'
            )
            """
        )
    return conn


def resolve_parcel_from_parquet(parcel_id: str | None = None, address: str | None = None) -> dict[str, Any]:
    """Resolve a parcel by parcel number or address from parcel_search.parquet."""
    if not parcel_id and not address:
        raise ValueError("Provide parcel_id or address.")

    path = _parcel_search_path()
    conn = get_duckdb_connection()
    try:
        params: list[Any] = [path]
        where = "TRUE"
        order_by = "parcel_number"
        if parcel_id:
            where = "upper(parcel_number) = upper(?)"
            params.append(parcel_id.strip())
        else:
            terms = _address_terms(address or "")
            if not terms:
                return _not_found(parcel_id, address)
            for term in terms:
                where += " AND concat_ws(' ', situs_address, situs_city_state_zip) ILIKE ?"
                params.append(f"%{term}%")
            order_by = "has_situs_address DESC, parcel_number"

        rows = conn.execute(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM read_parquet(?)
            WHERE {where}
            ORDER BY {order_by}
            LIMIT 5
            """,
            params,
        ).fetchall()
        columns = [column[0] for column in conn.description]
        records = [dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()

    if not records:
        return _not_found(parcel_id, address)
    return _parcel_result(records, ambiguous=bool(address and not parcel_id and len(records) > 1))


def get_parcel_from_parquet(parcel_number: str) -> dict[str, Any] | None:
    """Return the raw parcel_search record for a parcel number, if present."""
    result = resolve_parcel_from_parquet(parcel_id=parcel_number)
    if not result.get("found"):
        return None
    candidates = result.get("candidates") or []
    return candidates[0] if candidates else None


def normalize_parcel_search_jurisdiction(city_name: str | None, inside_city_limits: Any = None) -> str:
    if inside_city_limits is False or not city_name:
        return "skagit_county"
    mapped = {
        "mount_vernon": "mount_vernon",
        "burlington": "burlington",
        "sedro_woolley": "sedro_woolley",
        "anacortes": "anacortes",
        "concrete": "concrete",
        "la_conner": "la_conner",
    }
    return mapped.get(normalize_jurisdiction(city_name), "skagit_county")


def _duckdb_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _parcel_search_path() -> str:
    bucket = os.environ.get("R2_BUCKET", "openskagit").strip() or "openskagit"
    return os.environ.get("PARCEL_SEARCH_PARQUET_PATH", f"r2://{bucket}/derived/parcel_search.parquet")


def _address_terms(address: str) -> list[str]:
    return [term for term in re.findall(r"[A-Za-z0-9]+", address) if len(term) >= 2][:6]


def _not_found(parcel_id: str | None, address: str | None) -> dict[str, Any]:
    return {"found": False, "query": {"parcel_id": parcel_id, "address": address}, "source": PARCEL_SEARCH_SOURCE}


def _parcel_result(records: list[dict[str, Any]], ambiguous: bool) -> dict[str, Any]:
    row = records[0]
    jurisdiction = normalize_parcel_search_jurisdiction(row.get("city_name"), row.get("inside_city_limits"))
    notes = []
    if ambiguous:
        notes.append("Multiple parcel candidates matched this address; ask the user to disambiguate before feasibility analysis.")
    if row.get("has_geometry") is False:
        notes.append("Parcel search record is missing geometry; this is a data gap, not proof the parcel has no geometry.")
    if row.get("has_situs_address") is False:
        notes.append("Parcel search record is missing situs address fields; this is a data gap, not proof the parcel has no address.")
    if row.get("zoning_code_short"):
        notes.append("zoning_code_short is a parcel data signal and should be verified against source zoning code.")

    address = " ".join(str(value).strip() for value in [row.get("situs_address"), row.get("situs_city_state_zip")] if value)
    return {
        "found": True,
        "ambiguous": ambiguous,
        "parcel_id": row.get("parcel_number"),
        "address": address,
        "jurisdiction": jurisdiction,
        "jurisdiction_label": JURISDICTIONS.get(jurisdiction, {}).get("display_name", jurisdiction.replace("_", " ").title()),
        "zoning_code": normalize_zone_code(row.get("zoning_code_short")),
        "zoning_name": row.get("zoning_label") or "",
        "inside_city_limits": bool(row.get("inside_city_limits")),
        "inside_uga": None,
        "percent_of_parcel": None,
        "source": PARCEL_SEARCH_SOURCE,
        "source_url": "",
        "candidates": records,
        "notes": " ".join(notes),
    }
