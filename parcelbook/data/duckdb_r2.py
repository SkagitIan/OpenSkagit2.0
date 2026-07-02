"""DuckDB helpers for querying ParcelBook parquet files in Cloudflare R2."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import duckdb


DEFAULT_BUCKET = "openskagit"
PARCEL_SEARCH_KEY = "derived/parcel_search.parquet"


@dataclass
class DuckDBR2Client:
    bucket: str | None = None
    account_id: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None
    con: duckdb.DuckDBPyConnection | None = None

    def __post_init__(self) -> None:
        self.bucket = self.bucket or os.environ.get("R2_BUCKET", DEFAULT_BUCKET)
        self.account_id = self.account_id or os.environ.get("R2_ACCOUNT_ID")
        self.access_key_id = self.access_key_id or os.environ.get("R2_ACCESS_KEY_ID")
        self.secret_access_key = self.secret_access_key or os.environ.get("R2_SECRET_ACCESS_KEY")
        self.con = self.con or duckdb.connect()

    @property
    def parcel_search_path(self) -> str:
        return f"r2://{self.bucket}/{PARCEL_SEARCH_KEY}"

    def connect(self, *, spatial: bool = False) -> duckdb.DuckDBPyConnection:
        self._require_credentials()
        self.con.execute("INSTALL httpfs")
        self.con.execute("LOAD httpfs")
        if spatial:
            self.con.execute("INSTALL spatial")
            self.con.execute("LOAD spatial")
        self.con.execute(
            f"""
            CREATE OR REPLACE SECRET r2_secret (
                TYPE R2,
                KEY_ID '{self._sql_string(self.access_key_id)}',
                SECRET '{self._sql_string(self.secret_access_key)}',
                ACCOUNT_ID '{self._sql_string(self.account_id)}'
            )
            """
        )
        return self.con

    def query_df(self, sql: str):
        self.connect()
        return self.con.execute(sql).df()

    def query_records(self, sql: str) -> list[dict[str, Any]]:
        df = self.query_df(sql)
        return df.where(df.notna(), None).to_dict(orient="records")

    def inspect_parcel_search_schema(self):
        self.connect()
        return self.con.execute(f"DESCRIBE SELECT * FROM read_parquet('{self.parcel_search_path}')").df()

    def _require_credentials(self) -> None:
        missing = [
            name
            for name, value in {
                "R2_ACCOUNT_ID": self.account_id,
                "R2_ACCESS_KEY_ID": self.access_key_id,
                "R2_SECRET_ACCESS_KEY": self.secret_access_key,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(f"Missing required R2 environment variables: {', '.join(missing)}")

    @staticmethod
    def _sql_string(value: str) -> str:
        return value.replace("'", "''")
