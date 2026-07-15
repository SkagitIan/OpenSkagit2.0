"""Build and validate the internal parcel relationship graph in Kuzu.

This module owns only Kuzu schema/load mechanics and row serialization. The
Kuzu file is internal and may contain canonical entity names; no file from
this module is a public response or frontend data source.
"""
from __future__ import annotations
import csv
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

NODE_SCHEMAS = {
    "Parcel": "pid STRING PRIMARY KEY, acres DOUBLE, land_use STRING, zone_id STRING, city_name STRING, assessed_value DOUBLE, building_value DOUBLE, land_value DOUBLE, year_built INT64, utilities STRING, is_vacant_buildable BOOLEAN, delinquent_years INT64",
    "Entity": "entity_id STRING PRIMARY KEY, canonical_name STRING, kind STRING",
    "OwnershipGroup": "group_id STRING PRIMARY KEY",
    "Recording": "recording_number STRING PRIMARY KEY, document_type STRING, signal_group STRING, recorded_date STRING",
}
REL_SCHEMAS = {
    "OWNS": "FROM Entity TO Parcel",
    "MEMBER_OF": "FROM Entity TO OwnershipGroup",
    "ADJACENT_TO": "FROM Parcel TO Parcel, shared_boundary_ft DOUBLE",
    "AFFECTS": "FROM Recording TO Parcel",
}

@dataclass(frozen=True)
class GraphTables:
    parcels: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    groups: list[dict[str, Any]]
    recordings: list[dict[str, Any]]
    owns: list[dict[str, Any]]
    member_of: list[dict[str, Any]]
    adjacency: list[dict[str, Any]]
    affects: list[dict[str, Any]]


def _csv_path(folder: Path, name: str, rows: list[dict[str, Any]]) -> Path:
    path = folder / f"{name}.csv"
    fields = list(rows[0]) if rows else {
        "Parcel": ["pid", "acres", "land_use", "zone_id", "city_name", "assessed_value", "building_value", "land_value", "year_built", "utilities", "is_vacant_buildable", "delinquent_years"],
        "Entity": ["entity_id", "canonical_name", "kind"],
        "OwnershipGroup": ["group_id"],
        "Recording": ["recording_number", "document_type", "signal_group", "recorded_date"],
    }.get(name, {"ADJACENT_TO": ["FROM", "TO", "shared_boundary_ft"], "OWNS": ["FROM", "TO"], "MEMBER_OF": ["FROM", "TO"], "AFFECTS": ["FROM", "TO"]}.get(name, ["FROM", "TO"]))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})
    return path


def write_intermediate_csvs(folder: Path, tables: GraphTables) -> dict[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    values = {
        "Parcel": tables.parcels, "Entity": tables.entities, "OwnershipGroup": tables.groups,
        "Recording": tables.recordings, "OWNS": tables.owns, "MEMBER_OF": tables.member_of,
        "ADJACENT_TO": tables.adjacency, "AFFECTS": tables.affects,
    }
    return {name: _csv_path(folder, name, rows) for name, rows in values.items()}


def _quote_path(path: Path) -> str:
    return "'" + path.as_posix().replace("'", "''") + "'"


def _count(conn, table: str, relationship: bool = False) -> int:
    query = f"MATCH ()-[r:{table}]->() RETURN count(r)" if relationship else f"MATCH (n:{table}) RETURN count(n)"
    result = conn.execute(query)
    return int(result.get_as_df().iloc[0, 0])


def build_kuzu_database(database_dir: Path, tables: GraphTables, intermediate_dir: Path) -> dict[str, int]:
    """Create a fresh Kuzu database using bulk CSV COPY operations."""
    try:
        import kuzu
    except ImportError as exc:  # pragma: no cover - deployment dependency
        raise RuntimeError("Kuzu is required; install kuzu==0.11.3") from exc
    database_dir = Path(database_dir)
    if database_dir.is_dir():
        shutil.rmtree(database_dir)
    elif database_dir.exists():
        database_dir.unlink()
    database_dir.parent.mkdir(parents=True, exist_ok=True)
    csv_paths = write_intermediate_csvs(Path(intermediate_dir), tables)
    db = kuzu.Database(str(database_dir))
    conn = kuzu.Connection(db)
    for name, schema in NODE_SCHEMAS.items():
        conn.execute(f"CREATE NODE TABLE {name}({schema})")
    for name, schema in REL_SCHEMAS.items():
        conn.execute(f"CREATE REL TABLE {name}({schema})")
    for name in ("Parcel", "Entity", "OwnershipGroup", "Recording", "OWNS", "MEMBER_OF", "ADJACENT_TO", "AFFECTS"):
        conn.execute(f"COPY {name} FROM {_quote_path(csv_paths[name])} (HEADER=true)")
    counts = {f"{name.lower()}_nodes": _count(conn, name) for name in NODE_SCHEMAS}
    counts.update({f"{name.lower()}_edges": _count(conn, name, relationship=True) for name in REL_SCHEMAS})
    smoke = conn.execute("MATCH (p:Parcel)-[:ADJACENT_TO]->(n:Parcel) RETURN count(DISTINCT p)").get_as_df().iloc[0, 0]
    counts["parcels_with_adjacency"] = int(smoke)
    expected = {
        "parcel_nodes": len(tables.parcels), "entity_nodes": len(tables.entities), "ownershipgroup_nodes": len(tables.groups), "recording_nodes": len(tables.recordings),
        "owns_edges": len(tables.owns), "member_of_edges": len(tables.member_of), "adjacent_to_edges": len(tables.adjacency), "affects_edges": len(tables.affects),
    }
    for key, source_count in expected.items():
        loaded = counts[key]
        if source_count and loaded < source_count * 0.98:
            raise RuntimeError(f"Kuzu validation failed for {key}: loaded {loaded} of {source_count}")
    return counts


def is_vacant_buildable(land_use: str | None, zone_general: str | None, zone_id: str | None) -> bool:
    """Conservative public-data classification for vacant, non-resource land."""
    value = str(land_use or "").upper()
    code = value.lstrip("(").split(")", 1)[0]
    zone = str(zone_general or "").upper()
    zid = str(zone_id or "").upper()
    return code.startswith("9") and code not in {"930", "940", "970"} and zone not in {"NRL", "PUB", "OS"} and "-NRL" not in zid