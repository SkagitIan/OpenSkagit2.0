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
    return duckdb.connect(str(path or database_path()), read_only=read_only)
