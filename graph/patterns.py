"""Read-only graph pattern queries and public-safe pattern serialization.

This module does not access Postgres or expose entity names, owner names,
entity IDs, mailing keys, or addresses. It reads the internal Kuzu artifact and
returns only parcel IDs plus aggregate pattern evidence.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
import tempfile
import zipfile
from typing import Any, Iterator

from django.conf import settings

DEFAULT_GRAPH_ZIP = Path(settings.BASE_DIR) / "data" / "processed" / "skagit_graph.kuzu.zip"
PUBLIC_DETAIL_KEYS = {"cluster_count", "cluster_acres", "vacant_like_count", "neighbor_zone_count", "delinquent_neighbors", "built_neighbor_count", "signal_label", "years_without_recording"}
FORBIDDEN_DETAIL_KEYS = {"owner", "owner_name", "canonical_name", "entity_id", "group_id", "mailing_key", "mailing_address", "address"}

@contextmanager
def _connection(graph_zip: Path = DEFAULT_GRAPH_ZIP) -> Iterator[Any]:
    try:
        import kuzu
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Kuzu is required; install kuzu==0.11.3") from exc
    graph_zip = Path(graph_zip)
    if not graph_zip.exists():
        raise FileNotFoundError(f"Kuzu graph artifact not found: {graph_zip}")
    with tempfile.TemporaryDirectory(prefix="openskagit_graph_") as folder:
        with zipfile.ZipFile(graph_zip) as archive:
            archive.extractall(folder)
        database_path = next(Path(folder).rglob("skagit_graph.kuzu"), None)
        if database_path is None:
            raise RuntimeError("Kuzu graph archive does not contain skagit_graph.kuzu")
        database = kuzu.Database(str(database_path), read_only=True)
        connection = kuzu.Connection(database)
        try:
            yield connection
        finally:
            close = getattr(connection, "close", None)
            if close:
                close()
            close = getattr(database, "close", None)
            if close:
                close()


def _rows(connection: Any, query: str) -> list[dict[str, Any]]:
    return connection.execute(query).get_as_df().to_dict("records")


def _safe_detail(detail: dict[str, Any]) -> dict[str, Any]:
    """Allow only aggregate vocabulary intended for opportunity serving."""
    for key in detail:
        lowered = key.lower()
        if key in FORBIDDEN_DETAIL_KEYS or any(token in lowered for token in ("owner", "entity", "mailing", "address")):
            raise ValueError(f"Forbidden graph detail key: {key}")
    return {key: value for key, value in detail.items() if key in PUBLIC_DETAIL_KEYS}


def _pattern_rows(connection: Any, query: str) -> list[dict[str, Any]]:
    results = []
    for row in _rows(connection, query):
        detail = _safe_detail({key: row[key] for key in row if key not in {"parcel_number", "score"} and key in PUBLIC_DETAIL_KEYS})
        results.append({"parcel_number": str(row["parcel_number"]), "score": float(row.get("score") or 0), "detail": detail})
    return results


def assemblage_candidates(graph_zip: Path = DEFAULT_GRAPH_ZIP) -> list[dict[str, Any]]:
    """Find adjacent parcels sharing an entity or internal ownership group."""
    query = """
        MATCH (p:Parcel)-[:ADJACENT_TO]-(n:Parcel)
        MATCH (e1:Entity)-[:OWNS]->(p)
        MATCH (e2:Entity)-[:OWNS]->(n)
        WHERE e1.entity_id = e2.entity_id
           OR EXISTS { MATCH (e1)-[:MEMBER_OF]->(g:OwnershipGroup)<-[:MEMBER_OF]-(e2) }
        WITH p, n
        RETURN p.pid AS parcel_number,
               count(DISTINCT n.pid) AS cluster_count,
               sum(DISTINCT n.acres) AS cluster_acres,
               sum(DISTINCT CASE WHEN n.building_value <= 10000 THEN 1 ELSE 0 END) AS vacant_like_count,
               count(DISTINCT n.zone_id) AS neighbor_zone_count,
               sum(DISTINCT CASE WHEN n.delinquent_years > 0 THEN 1 ELSE 0 END) AS delinquent_neighbors,
               count(DISTINCT n.pid) * 50 + sum(DISTINCT n.acres) * 20
                 + sum(DISTINCT CASE WHEN n.delinquent_years > 0 THEN 30 ELSE 0 END)
                 + sum(DISTINCT CASE WHEN n.building_value <= 10000 THEN 10 ELSE 0 END)
                 + CASE WHEN count(DISTINCT n.zone_id) = 1 THEN 25 ELSE 0 END AS score
        ORDER BY score DESC
    """
    with _connection(graph_zip) as connection:
        return _pattern_rows(connection, query)


def infill_candidates(graph_zip: Path = DEFAULT_GRAPH_ZIP) -> list[dict[str, Any]]:
    """Find vacant-buildable parcels with at least three built neighbors."""
    query = """
        MATCH (p:Parcel)-[:ADJACENT_TO]-(n:Parcel)
        WHERE p.is_vacant_buildable AND n.building_value > 50000
        WITH p, count(DISTINCT n.pid) AS built_neighbor_count
        WHERE built_neighbor_count >= 3
        RETURN p.pid AS parcel_number, built_neighbor_count,
               built_neighbor_count * 25 AS score
        ORDER BY score DESC
    """
    with _connection(graph_zip) as connection:
        return _pattern_rows(connection, query)


def estate_signal_candidates(graph_zip: Path = DEFAULT_GRAPH_ZIP, years: int = 5) -> list[dict[str, Any]]:
    """Find single-parcel entities near recent transfer signals without exposing identity."""
    cutoff = (date.today() - timedelta(days=365 * years)).isoformat()
    query = f"""
        MATCH (e:Entity)-[:OWNS]->(p:Parcel)
        WHERE NOT EXISTS {{ MATCH (e)-[:OWNS]->(other:Parcel) WHERE other.pid <> p.pid }}
          AND NOT EXISTS {{ MATCH (r:Recording)-[:AFFECTS]->(p) WHERE r.recorded_date >= '{cutoff}' }}
        MATCH (p)-[:ADJACENT_TO]-(neighbor:Parcel)<-[:AFFECTS]-(recent:Recording)
        WHERE recent.signal_group IN ['fresh_sale', 'transfer', 'sale']
          AND recent.recorded_date >= '{cutoff}'
        RETURN p.pid AS parcel_number, '{years}' AS years_without_recording,
               40 AS score
        ORDER BY score DESC
    """
    with _connection(graph_zip) as connection:
        return _pattern_rows(connection, query)


def all_pattern_results(graph_zip: Path = DEFAULT_GRAPH_ZIP) -> dict[str, list[dict[str, Any]]]:
    return {"assemblage": assemblage_candidates(graph_zip), "infill": infill_candidates(graph_zip), "estate_signal": estate_signal_candidates(graph_zip)}