from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests
from django.db import connection

USER_AGENT = "OpenSkagit research tool"
DEFAULT_TIMEOUT_SECONDS = 25
DEFAULT_ACS_YEAR = "2024"

ACS_VARIABLES = {
    "B01003_001E": "total_population",
    "B01002_001E": "median_age",
    "B11001_001E": "households",
    "B19013_001E": "median_household_income",
    "B17001_001E": "poverty_universe",
    "B17001_002E": "below_poverty",
    "B25001_001E": "housing_units",
    "B25002_002E": "occupied_housing_units",
    "B25002_003E": "vacant_housing_units",
    "B25003_002E": "owner_occupied_units",
    "B25003_003E": "renter_occupied_units",
    "B25077_001E": "median_owner_occupied_home_value",
    "B25064_001E": "median_gross_rent",
    "B15003_001E": "education_25_plus_total",
    "B15003_022E": "bachelors_degree",
    "B15003_023E": "masters_degree",
    "B15003_024E": "professional_degree",
    "B15003_025E": "doctorate_degree",
    "B08012_001E": "workers_commute_total",
    "B08013_001E": "aggregate_commute_minutes",
    "B02001_001E": "race_total",
    "B02001_002E": "white_alone",
    "B02001_003E": "black_alone",
    "B02001_004E": "american_indian_alaska_native_alone",
    "B02001_005E": "asian_alone",
    "B02001_006E": "native_hawaiian_pacific_islander_alone",
    "B02001_007E": "some_other_race_alone",
    "B02001_008E": "two_or_more_races",
    "B03003_003E": "hispanic_or_latino",
    "B25034_001E": "year_built_total",
    "B25034_002E": "built_2020_or_later",
    "B25034_003E": "built_2010_to_2019",
    "B25034_004E": "built_2000_to_2009",
    "B25034_005E": "built_1990_to_1999",
    "B25034_006E": "built_1980_to_1989",
    "B25034_007E": "built_1970_to_1979",
    "B25034_008E": "built_1960_to_1969",
    "B25034_009E": "built_1950_to_1959",
    "B25034_010E": "built_1940_to_1949",
    "B25034_011E": "built_1939_or_earlier",
}


def clean_parcel(value: str | None) -> str:
    parcel = (value or "").strip().upper()
    if re.fullmatch(r"\d{1,10}", parcel):
        parcel = f"P{parcel}"
    if not re.fullmatch(r"P\d{1,10}", parcel):
        raise ValueError("Parcel must look like P96023.")
    return parcel


def timeout_seconds() -> float:
    return float(os.environ.get("CONTEXT_MCP_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))


def acs_year() -> str:
    year = os.environ.get("CENSUS_ACS_YEAR", DEFAULT_ACS_YEAR).strip()
    if not re.fullmatch(r"20\d{2}", year):
        raise ValueError("CENSUS_ACS_YEAR must be a four-digit year.")
    return year


def census_api_key() -> str:
    return os.environ.get("CENSUS_API_KEY", "").strip()


def parcel_spatial_context(parcel_id: str) -> dict[str, Any]:
    parcel = clean_parcel(parcel_id)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                ST_X(ST_PointOnSurface(g.geometry)) AS longitude,
                ST_Y(ST_PointOnSurface(g.geometry)) AS latitude,
                ST_AsText(ST_Force2D(g.geometry)) AS geometry_wkt
            FROM gis_skagit_parcels g
            WHERE g.parcel_id = %s
              AND g.geometry IS NOT NULL
            LIMIT 1
            """,
            [parcel],
        )
        row = cursor.fetchone()
    if not row:
        raise ValueError(f"No PostGIS parcel geometry found for {parcel}")
    return {
        "parcel": parcel,
        "centroid": {"longitude": float(row[0]), "latitude": float(row[1])},
        "geometry_wkt": row[2],
    }


def _headers() -> dict[str, str]:
    return {"accept": "application/json", "user-agent": USER_AGENT}


def _first_geography(geographies: dict[str, Any], names: list[str]) -> dict[str, Any] | None:
    for name in names:
        rows = geographies.get(name) or []
        if rows:
            return rows[0]
    return None


def _normalize_geography(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    return {
        "name": item.get("NAME") or item.get("BASENAME"),
        "geoid": item.get("GEOID") or item.get("GEOIDFQ"),
        "state": item.get("STATE"),
        "county": item.get("COUNTY"),
        "tract": item.get("TRACT"),
        "block": item.get("BLOCK"),
        "place": item.get("PLACE"),
        "zcta": item.get("ZCTA5") or item.get("ZCTA"),
        "county_subdivision": item.get("COUSUB"),
    }


def _match_census_geographies(longitude: float, latitude: float) -> dict[str, Any]:
    response = requests.get(
        "https://geocoding.geo.census.gov/geocoder/geographies/coordinates",
        params={
            "x": longitude,
            "y": latitude,
            "benchmark": "Public_AR_Current",
            "vintage": "Current_Current",
            "format": "json",
        },
        headers=_headers(),
        timeout=timeout_seconds(),
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(f"Census geocoder error: {payload['errors']}")
    geographies = payload.get("result", {}).get("geographies", {})
    block = _normalize_geography(_first_geography(geographies, ["2020 Census Blocks", "Census Blocks"]))
    block_group = _normalize_geography(
        _first_geography(geographies, ["2020 Census Block Groups", "Census Block Groups", "Block Groups"])
    )
    if not block_group and block and all(block.get(key) for key in ("state", "county", "tract", "block")):
        group = str(block["block"])[0]
        block_group = {
            "name": f"{block['tract']} Block Group {group}",
            "geoid": f"{block['state']}{block['county']}{block['tract']}{group}",
            "state": block["state"],
            "county": block["county"],
            "tract": block["tract"],
            "block": group,
            "place": None,
            "zcta": None,
            "county_subdivision": None,
        }
    return {
        "block": block,
        "block_group": block_group,
        "tract": _normalize_geography(_first_geography(geographies, ["Census Tracts"])),
        "place": _normalize_geography(_first_geography(geographies, ["Incorporated Places", "Places"])),
        "county_subdivision": _normalize_geography(_first_geography(geographies, ["County Subdivisions"])),
        "county": _normalize_geography(_first_geography(geographies, ["Counties"])),
        "zcta": _normalize_geography(
            _first_geography(geographies, ["2020 ZIP Code Tabulation Areas", "ZIP Code Tabulation Areas"])
        ),
    }


def _number(value: Any) -> int | float | None:
    if value in (None, "", "-666666666", "-999999999"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _pct(part: int | float | None, total: int | float | None) -> float | None:
    return round((part / total) * 100, 1) if part is not None and total else None


def _shape_acs(raw: dict[str, int | float | None]) -> dict[str, Any]:
    college = sum(raw.get(key) or 0 for key in ("bachelors_degree", "masters_degree", "professional_degree", "doctorate_degree"))
    return {
        "demographics": {
            "total_population": raw.get("total_population"),
            "median_age": raw.get("median_age"),
            "race_ethnicity": {
                "white_alone_pct": _pct(raw.get("white_alone"), raw.get("race_total")),
                "black_alone_pct": _pct(raw.get("black_alone"), raw.get("race_total")),
                "american_indian_alaska_native_alone_pct": _pct(raw.get("american_indian_alaska_native_alone"), raw.get("race_total")),
                "asian_alone_pct": _pct(raw.get("asian_alone"), raw.get("race_total")),
                "native_hawaiian_pacific_islander_alone_pct": _pct(raw.get("native_hawaiian_pacific_islander_alone"), raw.get("race_total")),
                "some_other_race_alone_pct": _pct(raw.get("some_other_race_alone"), raw.get("race_total")),
                "two_or_more_races_pct": _pct(raw.get("two_or_more_races"), raw.get("race_total")),
                "hispanic_or_latino_pct": _pct(raw.get("hispanic_or_latino"), raw.get("race_total")),
            },
        },
        "socioeconomic": {
            "households": raw.get("households"),
            "median_household_income": raw.get("median_household_income"),
            "poverty_rate_pct": _pct(raw.get("below_poverty"), raw.get("poverty_universe")),
            "bachelors_or_higher_pct": _pct(college, raw.get("education_25_plus_total")),
        },
        "housing": {
            "housing_units": raw.get("housing_units"),
            "occupied_housing_units": raw.get("occupied_housing_units"),
            "vacancy_rate_pct": _pct(raw.get("vacant_housing_units"), raw.get("housing_units")),
            "owner_occupied_pct": _pct(raw.get("owner_occupied_units"), raw.get("occupied_housing_units")),
            "renter_occupied_pct": _pct(raw.get("renter_occupied_units"), raw.get("occupied_housing_units")),
            "median_owner_occupied_home_value": raw.get("median_owner_occupied_home_value"),
            "median_gross_rent": raw.get("median_gross_rent"),
            "year_built": {key: raw.get(key) for key in raw if key == "year_built_total" or key.startswith("built_")},
        },
        "commute": {
            "workers": raw.get("workers_commute_total"),
            "mean_commute_minutes": round(raw["aggregate_commute_minutes"] / raw["workers_commute_total"], 1)
            if raw.get("aggregate_commute_minutes") is not None and raw.get("workers_commute_total")
            else None,
        },
        "raw": raw,
    }


def _acs_query(geography: dict[str, Any] | None, level: str) -> dict[str, Any] | None:
    if not geography or not geography.get("state"):
        return None
    params: dict[str, str] = {"get": ",".join(["NAME", *ACS_VARIABLES]), "key": census_api_key()}
    state = geography["state"]
    if level == "block_group":
        if not all(geography.get(key) for key in ("county", "tract", "geoid")):
            return None
        params.update({"for": f"block group:{str(geography['geoid'])[-1]}", "in": f"state:{state} county:{geography['county']} tract:{geography['tract']}"})
    elif level == "tract":
        if not geography.get("county") or not geography.get("tract"):
            return None
        params.update({"for": f"tract:{geography['tract']}", "in": f"state:{state} county:{geography['county']}"})
    elif level == "place":
        if not geography.get("place"):
            return None
        params.update({"for": f"place:{geography['place']}", "in": f"state:{state}"})
    else:
        if not geography.get("county"):
            return None
        params.update({"for": f"county:{geography['county']}", "in": f"state:{state}"})

    response = requests.get(
        f"https://api.census.gov/data/{acs_year()}/acs/acs5",
        params=params,
        headers=_headers(),
        timeout=timeout_seconds(),
    )
    response.raise_for_status()
    table = response.json()
    if not isinstance(table, list) or len(table) < 2:
        raise RuntimeError(f"ACS {level} returned no data")
    headers, values = table[0], table[1]
    raw = {
        label: _number(values[headers.index(variable)]) if variable in headers else None
        for variable, label in ACS_VARIABLES.items()
    }
    return {
        "name": values[headers.index("NAME")] if "NAME" in headers else geography.get("name"),
        "geography": geography,
        **_shape_acs(raw),
    }


def _reporter_geoid(geography: dict[str, Any] | None, level: str) -> str | None:
    if not geography:
        return None
    if level == "block_group" and geography.get("geoid"):
        return f"15000US{geography['geoid']}"
    if level == "tract" and all(geography.get(key) for key in ("state", "county", "tract")):
        return f"14000US{geography['state']}{geography['county']}{geography['tract']}"
    if level == "place" and geography.get("state") and geography.get("place"):
        return f"16000US{geography['state']}{geography['place']}"
    if level == "county" and geography.get("state") and geography.get("county"):
        return f"05000US{geography['state']}{geography['county']}"
    return None


def _reporter_column(variable: str) -> tuple[str, str]:
    table, column = variable.split("_", 1)
    return table, f"{table}{column.removesuffix('E')}"


def _census_reporter_query(levels: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    geoids = {level: _reporter_geoid(geography, level) for level, geography in levels.items()}
    requested_geoids = [geoid for geoid in geoids.values() if geoid]
    if not requested_geoids:
        return {"results": {level: None for level in levels}, "errors": {}, "release": None}
    tables = sorted({variable.split("_", 1)[0] for variable in ACS_VARIABLES})
    # Census Reporter rejects large table combinations even when the URL is short;
    # three tables per request remains within its current public API limit.
    table_chunks = [tables[index : index + 3] for index in range(0, len(tables), 3)]

    def fetch_chunk(job: tuple[str, list[str]]) -> list[dict[str, Any]]:
        geoid, chunk = job

        def request_tables(requested_tables: list[str]) -> dict[str, Any] | None:
            response = requests.get(
                f"https://api.censusreporter.org/1.0/data/show/acs{acs_year()}_5yr",
                params={"table_ids": ",".join(requested_tables), "geo_ids": geoid},
                headers=_headers(),
                timeout=timeout_seconds(),
            )
            if response.status_code == 400:
                return None
            response.raise_for_status()
            return response.json()

        payload = request_tables(chunk)
        if payload is not None:
            return [payload]
        # Some ACS tables are unavailable at block-group level. Retry the
        # small chunk one table at a time and retain every supported table.
        return [payload for table in chunk if (payload := request_tables([table])) is not None]

    payloads: list[dict[str, Any]] = []
    jobs = [(geoid, chunk) for geoid in requested_geoids for chunk in table_chunks]
    with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as executor:
        for job_payloads in executor.map(fetch_chunk, jobs):
            payloads.extend(job_payloads)
    data: dict[str, dict[str, Any]] = {}
    geography_names: dict[str, dict[str, Any]] = {}
    release = None
    for payload in payloads:
        for geoid, tables_for_geoid in payload.get("data", {}).items():
            data.setdefault(geoid, {}).update(tables_for_geoid)
        geography_names.update(payload.get("geography", {}))
        release = release or payload.get("release")
    results: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for level, geography in levels.items():
        geoid = geoids[level]
        if not geoid:
            results[level] = None
            continue
        record = data.get(geoid)
        if not record:
            results[level] = None
            errors[level] = f"Census Reporter returned no ACS record for {geoid}"
            continue
        raw: dict[str, int | float | None] = {}
        for variable, label in ACS_VARIABLES.items():
            table, column = _reporter_column(variable)
            raw[label] = _number(record.get(table, {}).get("estimate", {}).get(column))
        results[level] = {
            "name": geography_names.get(geoid, {}).get("name") or (geography or {}).get("name"),
            "geography": geography,
            **_shape_acs(raw),
        }
    return {"results": results, "errors": errors, "release": release}


def get_census_context(parcel_id: str) -> dict[str, Any]:
    spatial = parcel_spatial_context(parcel_id)
    centroid = spatial["centroid"]
    try:
        matched = _match_census_geographies(centroid["longitude"], centroid["latitude"])
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        return {"status": "error", "parcel": spatial["parcel"], "centroid": centroid, "stage": "geography", "error": str(exc)}

    levels = {
        "block_group": matched.get("block_group"),
        "tract": matched.get("tract"),
        "place": matched.get("place"),
        "county": matched.get("county"),
    }
    release = None
    if census_api_key():
        results: dict[str, Any] = {}
        errors: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {level: executor.submit(_acs_query, geography, level) for level, geography in levels.items()}
            for level, future in futures.items():
                try:
                    results[level] = future.result()
                except (requests.RequestException, ValueError, RuntimeError) as exc:
                    results[level] = None
                    errors[level] = str(exc)
        source = f"US Census ACS {acs_year()} 5-year detailed tables"
        source_urls = [
            "https://geocoding.geo.census.gov/geocoder/",
            f"https://api.census.gov/data/{acs_year()}/acs/acs5",
        ]
    else:
        try:
            fallback = _census_reporter_query(levels)
            results = fallback["results"]
            errors = fallback["errors"]
            release = fallback["release"]
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            results = {level: None for level in levels}
            errors = {"census_reporter": str(exc)}
        source = "Census Reporter API mirror of US Census ACS 5-year estimates"
        source_urls = [
            "https://geocoding.geo.census.gov/geocoder/",
            "https://api.censusreporter.org/",
        ]

    return {
        "status": "partial" if errors else "ok",
        "parcel": spatial["parcel"],
        "source": source,
        "source_urls": source_urls,
        "release": release,
        "note": "Census statistics are matched by a point on the parcel surface to Census geographies; they are area-level estimates, not parcel-level measurements.",
        "centroid": centroid,
        "matched_geographies": matched,
        "acs": results,
        "errors": errors,
    }


def _parse_nrcs_table(payload: Any) -> list[dict[str, Any]]:
    table = payload.get("Table") or payload.get("Table1") if isinstance(payload, dict) else payload
    if not isinstance(table, list) or not table:
        return []
    if not isinstance(table[0], list):
        return table
    headers = [str(value) for value in table[0]]
    return [dict(zip(headers, row, strict=False)) for row in table[1:] if isinstance(row, list)]


def get_soils_context(parcel_id: str) -> dict[str, Any]:
    spatial = parcel_spatial_context(parcel_id)
    escaped_wkt = str(spatial["geometry_wkt"]).replace("'", "''")
    query = f"""
        SELECT DISTINCT
          mu.mukey,
          mu.musym,
          mu.muname,
          mu.mukind,
          ma.drclassdcd,
          ma.flodfreqdcd,
          ma.niccdcd,
          mu.farmlndcl,
          ma.hydgrpdcd
        FROM mapunit mu
        LEFT JOIN muaggatt ma ON mu.mukey = ma.mukey
        WHERE mu.mukey IN (
          SELECT mukey FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('{escaped_wkt}')
        )
        ORDER BY mu.musym
    """
    try:
        response = requests.post(
            "https://sdmdataaccess.nrcs.usda.gov/Tabular/post.rest",
            data={"SERVICE": "query", "REQUEST": "query", "FORMAT": "JSON+COLUMNNAME", "QUERY": query},
            headers={**_headers(), "content-type": "application/x-www-form-urlencoded"},
            timeout=timeout_seconds(),
        )
        response.raise_for_status()
        mapunits = _parse_nrcs_table(response.json())
    except (requests.RequestException, ValueError) as exc:
        return {
            "status": "error",
            "parcel": spatial["parcel"],
            "source": "NRCS Soil Data Access SSURGO",
            "source_url": "https://sdmdataaccess.nrcs.usda.gov/",
            "error": str(exc),
        }
    return {
        "status": "ok",
        "parcel": spatial["parcel"],
        "source": "NRCS Soil Data Access SSURGO",
        "source_url": "https://sdmdataaccess.nrcs.usda.gov/",
        "note": "Soil map units are intersected with the PostGIS parcel polygon using NRCS SDA. Map-unit attributes may not represent every point on the parcel.",
        "mapunit_count": len(mapunits),
        "mapunits": mapunits,
    }
