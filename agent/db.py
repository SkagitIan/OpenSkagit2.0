import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Optional

import httpx


DB_PATH = os.environ.get("D1_LOCAL_PATH", "catalog/local.db")
D1_ACCOUNT_ID = os.environ.get("D1_ACCOUNT_ID", "")
D1_DATABASE_ID = os.environ.get("D1_DATABASE_ID", "")
D1_API_TOKEN = os.environ.get("D1_API_TOKEN", "")
D1_API_BASE = os.environ.get("D1_API_BASE", "https://api.cloudflare.com/client/v4")


def using_d1() -> bool:
    return bool(D1_ACCOUNT_ID and D1_DATABASE_ID and D1_API_TOKEN)


def connect() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def execute(sql: str, params: Iterable[Any] = ()) -> dict:
    if using_d1():
        return _execute_d1(sql, list(params))
    with connect() as conn:
        cursor = conn.execute(sql, tuple(params))
        return {"rowcount": cursor.rowcount, "lastrowid": cursor.lastrowid}


def executemany(sql: str, rows: Iterable[Iterable[Any]]) -> None:
    if using_d1():
        for row in rows:
            _execute_d1(sql, list(row))
        return
    with connect() as conn:
        conn.executemany(sql, [tuple(row) for row in rows])


def executescript(sql: str) -> None:
    if using_d1():
        for statement in _split_sql_script(sql):
            if statement:
                execute(statement)
        return
    with connect() as conn:
        conn.executescript(sql)


def fetchone(sql: str, params: Iterable[Any] = ()) -> Optional[dict]:
    rows = fetchall(sql, params)
    return rows[0] if rows else None


def fetchall(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    if using_d1():
        response = _execute_d1(sql, list(params))
        result = (response.get("result") or [{}])[0]
        results = result.get("results") or {}
        columns = results.get("columns") or []
        rows = results.get("rows") or []
        return [dict(zip(columns, row)) for row in rows]
    with connect() as conn:
        return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]


def ensure_local_seeded() -> None:
    if using_d1() or Path(DB_PATH).exists():
        return
    try:
        from catalog.seeds.seed import seed_local

        seed_local()
    except Exception:
        pass


def _execute_d1(sql: str, params: list[Any] | None = None) -> dict:
    url = f"{D1_API_BASE.rstrip('/')}/accounts/{D1_ACCOUNT_ID}/d1/database/{D1_DATABASE_ID}/raw"
    payload: dict[str, Any] = {"sql": sql}
    if params is not None:
        payload["params"] = params
    with httpx.Client(timeout=20.0) as client:
        response = client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {D1_API_TOKEN}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
    data = response.json()
    if not data.get("success", False):
        messages = data.get("errors") or data.get("messages") or []
        detail = "; ".join(item.get("message", str(item)) for item in messages) or "D1 query failed"
        raise RuntimeError(detail)
    return data


def _split_sql_script(sql: str) -> list[str]:
    statements = []
    current = []
    in_string: str | None = None
    for char in sql:
        current.append(char)
        if char in {"'", '"'}:
            in_string = None if in_string == char else char if in_string is None else in_string
        if char == ";" and in_string is None:
            statement = "".join(current).strip().rstrip(";").strip()
            if statement:
                statements.append(statement)
            current = []
    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements
