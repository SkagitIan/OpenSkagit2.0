from __future__ import annotations

import os
from pathlib import Path

import duckdb


def database_path() -> Path:
    from django.conf import settings

    value = os.environ.get(
        "OPENSKAGIT_DATABASE",
        getattr(settings, "OPENSKAGIT_DATABASE", "instance/openskagit.duckdb"),
    )
    path = Path(value)
    if not path.is_absolute():
        path = Path(settings.BASE_DIR) / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def connect(path: Path | None = None, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """
    Returns a DuckDB connection.

    If DATABASE_URL is set, DuckDB attaches Railway Postgres by default and
    exposes every table unqualified (no schema prefix needed in SQL). Set
    DUCKDB_USE_POSTGRES=false only when intentionally using a local .duckdb file.
    """
    pg_url = os.environ.get("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)
    use_pg = _use_postgres_by_default(pg_url)

    if pg_url and use_pg:
        conn = duckdb.connect()
        conn.execute("INSTALL postgres; LOAD postgres")
        conn.execute(f"ATTACH '{_escape_duckdb_string(pg_url)}' AS pg (TYPE POSTGRES, READ_ONLY)")
        # Create unqualified views so agent SQL needs no 'pg.' prefix
        _expose_postgres_tables(conn)
        return conn

    return duckdb.connect(str(path or database_path()), read_only=read_only)


def _use_postgres_by_default(pg_url: str) -> bool:
    configured = os.environ.get("DUCKDB_USE_POSTGRES")
    if configured is not None:
        return configured.lower() in ("1", "true", "yes", "on")
    return bool(pg_url)


def _escape_duckdb_string(value: str) -> str:
    return value.replace("'", "''")


def _expose_postgres_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Create local DuckDB views that alias every Postgres table without a prefix."""
    try:
        tables = conn.execute(
            """
            SELECT table_schema, table_name
            FROM pg.information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
              AND table_type IN ('BASE TABLE', 'VIEW')
            ORDER BY table_schema, table_name
            """
        ).fetchall()
    except duckdb.Error:
        return
    for schema_name, table_name in tables:
        try:
            conn.execute(
                f'CREATE OR REPLACE VIEW "{table_name}" AS '
                f'SELECT * FROM pg."{schema_name}"."{table_name}"'
            )
        except duckdb.Error:
            pass
