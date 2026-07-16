from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests
from bs4 import BeautifulSoup
from django.db import connection

ASSESSOR_BASE = "https://www.skagitcounty.net/Search/Property/Webservice.asmx"
TIMEOUT = float(os.environ.get("ASSESSOR_MCP_TIMEOUT", 30))
USER_AGENT = "OpenSkagit research tool"

# Fields compared nightly for change detection
TRACKED_FIELDS = [
    "owner_name",
    "land_value",
    "building_value",
    "total_value",
    "taxable_value",
    "total_taxes",
    "general_taxes",
    "sale_date",
    "sale_price",
    "deed_type",
    "acres",
    "assessment_use_code",
]


def clean_parcel(value: str) -> str:
    text = (value or "").strip().upper()
    if re.fullmatch(r"\d{1,10}", text):
        text = f"P{text}"
    if not re.fullmatch(r"P\d{1,10}", text):
        raise ValueError(f"Parcel must look like P96023, got: {value!r}")
    return text


def search_parcels(query: str, limit: int = 10) -> dict[str, Any]:
    """Search the canonical PostGIS parcel store by parcel ID or situs address."""

    text = " ".join((query or "").strip().upper().split())
    if not text:
        raise ValueError("Parcel search query is required.")
    count = min(max(int(limit or 10), 1), 25)
    exact_parcel = clean_parcel(text) if re.fullmatch(r"P?\d{1,10}", text) else None
    tokens = re.findall(r"[A-Z0-9]+", text)
    if not tokens:
        raise ValueError("Parcel search query must contain letters or numbers.")
    address_sql = "upper(concat_ws(' ', p.situs_street_number, p.situs_street_name, p.situs_city_state_zip))"

    if exact_parcel:
        where_sql = "p.parcel_number = %s"
        where_params: list[Any] = [exact_parcel]
    else:
        where_sql = " AND ".join(f"{address_sql} LIKE %s" for _ in tokens)
        where_params = [f"%{token}%" for token in tokens]

    sql = f"""
        WITH matches AS (
            SELECT
                p.parcel_number,
                nullif(trim(concat_ws(' ', p.situs_street_number, p.situs_street_name)), '') AS address,
                p.situs_city_state_zip,
                p.land_use,
                p.total_market_value,
                ST_X(ST_PointOnSurface(g.geometry)) AS longitude,
                ST_Y(ST_PointOnSurface(g.geometry)) AS latitude,
                count(*) OVER () AS total_matches,
                CASE
                    WHEN p.parcel_number = %s THEN 0
                    WHEN {address_sql} = %s THEN 1
                    WHEN {address_sql} LIKE %s THEN 2
                    ELSE 3
                END AS match_rank
            FROM skagit_parcels p
            LEFT JOIN gis_skagit_parcels g ON g.parcel_id = p.parcel_number
            WHERE p.inactive_date IS NULL AND {where_sql}
        )
        SELECT parcel_number, address, situs_city_state_zip, land_use, total_market_value,
               longitude, latitude, total_matches
        FROM matches
        ORDER BY match_rank, parcel_number
        LIMIT %s
    """
    rank_params = [exact_parcel or "", text, f"{text}%"]
    with connection.cursor() as cursor:
        cursor.execute(sql, [*rank_params, *where_params, count])
        rows = cursor.fetchall()

    results = [
        {
            "parcel_id": row[0],
            "label": " — ".join(value for value in (row[1], row[2], row[0]) if value),
            "address": row[1],
            "city_state_zip": row[2],
            "land_use": row[3],
            "total_market_value": row[4],
            "longitude": float(row[5]) if row[5] is not None else None,
            "latitude": float(row[6]) if row[6] is not None else None,
        }
        for row in rows
    ]
    return {
        "query": query,
        "normalized_query": text,
        "count": len(results),
        "total_matches": int(rows[0][7]) if rows else 0,
        "results": results,
    }


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _post_fill_page(parcel_id: str, result_type: str) -> str:
    resp = requests.post(
        f"{ASSESSOR_BASE}/fillPage",
        json={"sValue": parcel_id, "ResultType": result_type},
        headers={"Content-Type": "application/json; charset=UTF-8", "User-Agent": USER_AGENT},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    html = resp.json().get("d", "")
    if not html:
        raise ValueError(f"Empty response for {parcel_id}/{result_type}")
    return html


def _post_tax_detail(parcel_id: str, year: int | str) -> str:
    resp = requests.post(
        f"{ASSESSOR_BASE}/getTaxHistoryDetail",
        json={"sValue": parcel_id, "sYear": str(year)},
        headers={"Content-Type": "application/json; charset=UTF-8", "User-Agent": USER_AGENT},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("d", "")


# ---------------------------------------------------------------------------
# BeautifulSoup helpers
# ---------------------------------------------------------------------------

def _text(el) -> str:
    if el is None:
        return ""
    return " ".join(el.get_text(separator=" ").split())


def _clean(value: str) -> str:
    return value.strip().replace("\xa0", " ").lstrip("+").strip()


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_details(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, Any] = {}

    # Parcel identification row (table with "Parcel Number" header cell)
    for tbl in soup.find_all("table"):
        header_cells = tbl.find_all("td", attrs={"bgcolor": "#E0E0E0"})
        labels = [_text(c) for c in header_cells]
        if "Parcel Number" in labels:
            data_rows = [tr for tr in tbl.find_all("tr")
                         if not tr.find("td", attrs={"bgcolor": "#E0E0E0"})]
            if data_rows:
                data_cells = data_rows[0].find_all("td")
                for i, label in enumerate(labels):
                    if i < len(data_cells):
                        result[label.lower().replace(" ", "_")] = _text(data_cells[i])
            break

    # Owner info (table with "Owner Information" header)
    for tbl in soup.find_all("table"):
        header = tbl.find("td", attrs={"bgcolor": "#E0E0E0"})
        if header and "Owner Information" in _text(header):
            rows = tbl.find_all("tr")[1:]
            lines = [_text(r) for r in rows if _text(r)]
            if lines:
                result["owner_name"] = lines[0]
                if len(lines) > 1:
                    result["owner_mailing_address"] = " ".join(lines[1:])
            break

    # Site address
    for tbl in soup.find_all("table"):
        header = tbl.find("td", attrs={"bgcolor": "#E0E0E0"})
        if header and "Site Address" in _text(header):
            rows = tbl.find_all("tr")[1:]
            lines = [
                _text(r) for r in rows
                if _text(r)
                and "Zip Code" not in _text(r)
                and "Site Address" not in _text(r)
                and "Jurisdiction" not in _text(r)
            ]
            result["site_address"] = lines[0] if lines else ""
            break

    # Zoning from jzTable
    jtbl = soup.find("table", id="jzTable")
    if jtbl:
        zoning_div = jtbl.find("div", id="zoning")
        if zoning_div:
            result["zoning"] = _text(zoning_div)

    # Legal description
    legal = soup.find("legal")
    if legal:
        result["legal_description"] = _text(legal)

    # Big summary table: "Values for * Taxes" header cells
    for tbl in soup.find_all("table"):
        direct_rows = tbl.find_all("tr", recursive=False)
        if not direct_rows:
            continue
        header_texts = [_text(td) for td in direct_rows[0].find_all("td", recursive=False)]
        if not any("Values for" in t for t in header_texts):
            continue
        if len(direct_rows) < 2:
            break
        inner_tds = direct_rows[1].find_all("td", recursive=False)

        # TD 0: assessment values (div labels + adjacent value td)
        if len(inner_tds) > 0:
            for row in inner_tds[0].find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                label = _text(cells[0])
                value = _clean(_text(cells[-1]))
                if "Building Market Value" in label:
                    result["building_value"] = value
                elif "Land Market Value" in label:
                    result["land_value"] = value
                elif "Total Market Value" in label:
                    result["total_value"] = value
                elif "Assessed Value" in label and "Taxable" not in label:
                    result["assessed_value"] = value
                elif "Taxable Value" in label and "Selling" not in label:
                    result["taxable_value"] = value

        # TD 1: sale info
        if len(inner_tds) > 1:
            for row in inner_tds[1].find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                label = _text(cells[0])
                value = _text(cells[1])
                if "Deed Type" in label:
                    result["deed_type"] = value
                elif "Sale Date" in label:
                    result["sale_date"] = value
                elif "Taxable Selling Price" in label:
                    result["sale_price"] = _clean(value)

        # TD 2+: tax summary
        for i in range(2, len(inner_tds)):
            for row in inner_tds[i].find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                label = _text(cells[0])
                value = _clean(_text(cells[-1]))
                if "General Taxes" in label:
                    result["general_taxes"] = value
                elif "Special Assessments" in label:
                    result["special_assessments"] = value
                elif "Total Taxes" in label:
                    result["total_taxes"] = value
                elif "Taxable Value" in label:
                    result["tax_year_taxable_value"] = value

        break  # processed

    # First border=1 table: Assessment Use Code + Neighborhood
    for tbl in soup.find_all("table", attrs={"border": "1"}):
        if "Assessment Use Code" in tbl.get_text():
            for row in tbl.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) >= 2:
                    label = _text(cells[0]).lstrip("*").strip()
                    value = _text(cells[1])
                    if "Assessment Use Code" in label:
                        result["assessment_use_code"] = value
                    elif label == "Neighborhood":
                        result["neighborhood"] = value
            break

    # Second border=1 table: Levy Code, School District, Acres, etc. (5-col layout)
    for tbl in soup.find_all("table", attrs={"border": "1"}):
        tbl_text = tbl.get_text()
        if "Levy Code" in tbl_text or "School District" in tbl_text:
            for row in tbl.find_all("tr"):
                cells = row.find_all("td")
                # Table has paired cols: (0,1) and (3,4) with a divider at col 2
                for li, vi in [(0, 1), (3, 4)]:
                    if li < len(cells) and vi < len(cells):
                        label = _text(cells[li]).lstrip("*").strip()
                        value = _text(cells[vi])
                        if "Levy Code" in label:
                            result["levy_code"] = value
                        elif "School District" in label:
                            result["school_district"] = value
                        elif "Fire District" in label:
                            result["fire_district"] = value
                        elif "Exemptions" in label:
                            result["exemptions"] = value
                        elif "Utilities" in label:
                            result["utilities"] = value
                        elif label == "Acres":
                            result["acres"] = value
            break

    return {k: v for k, v in result.items() if v}


def parse_history(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    history_tbl = None
    for tbl in soup.find_all("table"):
        if "Account History" in tbl.get_text() and "VALUE YEAR" in tbl.get_text():
            history_tbl = tbl
            break

    if not history_tbl:
        return {"records": [], "note": "No history data found"}

    headers: list[str] = []
    records: list[dict[str, str]] = []

    for row in history_tbl.find_all("tr"):
        if row.find("td", attrs={"bgcolor": "#006699"}):
            headers = [_text(td) for td in row.find_all("td")]
        elif headers:
            cells = row.find_all("td")
            if cells and len(cells) == len(headers):
                record = {headers[i]: _clean(_text(cells[i])) for i in range(len(headers))}
                if any(record.values()):
                    records.append(record)

    return {"columns": headers, "records": records, "count": len(records)}


def parse_sales(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    sales: list[dict[str, str]] = []
    current: dict[str, str] = {}

    for tbl in soup.find_all("table"):
        if "SALE NUMBER" not in tbl.get_text() and "Transfer History" not in tbl.get_text():
            continue
        for row in tbl.find_all("tr"):
            cells = row.find_all("td")
            if not cells:
                continue
            row_text = _text(row)
            if "SALE NUMBER" in row_text:
                if current:
                    sales.append(current)
                current = {"sale_number": row_text.replace("SALE NUMBER", "").strip()}
                continue
            # 3-col rows: label | : | value
            if len(cells) == 3:
                label = _text(cells[0])
                value = _text(cells[2])
                if label and label != ":":
                    current[label] = value
            elif len(cells) == 2:
                label = _text(cells[0])
                value = _text(cells[1])
                if label:
                    current[label] = value

    if current:
        sales.append(current)

    return {"sales": sales, "count": len(sales)}


def parse_land(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    segments: list[dict[str, str]] = []
    current: dict[str, str] = {}

    for tbl in soup.find_all("table"):
        if "LAND SEGMENT" not in tbl.get_text():
            continue
        for row in tbl.find_all("tr"):
            cells = row.find_all("td")
            if not cells:
                continue
            row_text = _text(row)
            if "LAND SEGMENT" in row_text and (row.find("td", attrs={"bgcolor": "#7799bb"}) or "SEGMENT" in row_text.upper()):
                if current:
                    segments.append(current)
                current = {"segment": row_text}
                continue
            if len(cells) == 2:
                label = _clean(_text(cells[0])).rstrip(":")
                value = _clean(_text(cells[1]))
                if label and value:
                    current[label] = value

    if current:
        segments.append(current)

    return {"segments": segments, "count": len(segments)}


def parse_improvements(html: str) -> dict[str, Any]:
    if "No Improvement information" in html:
        return {"improvements": [], "note": "No improvement records"}

    soup = BeautifulSoup(html, "html.parser")
    items: list[dict[str, str]] = []

    for tbl in soup.find_all("table"):
        tbl_text = tbl.get_text()
        if "Improvement" not in tbl_text or "Parcel" in _text(tbl.find("th") or tbl.find("tr")):
            continue
        item: dict[str, str] = {}
        for row in tbl.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) == 2:
                label = _clean(_text(cells[0])).rstrip(":")
                value = _clean(_text(cells[1]))
                if label and value:
                    item[label] = value
        if item:
            items.append(item)

    return {"improvements": items, "count": len(items)}


def parse_permits(html: str) -> dict[str, Any]:
    if "No Permit" in html or "no permit" in html.lower():
        return {"permits": [], "note": "No permit records"}

    soup = BeautifulSoup(html, "html.parser")
    permits: list[dict[str, str]] = []

    for tbl in soup.find_all("table"):
        header_row = tbl.find("tr")
        if not header_row:
            continue
        headers = [_text(th) for th in header_row.find_all(["th", "td"])]
        if not headers or "Permit" not in tbl.get_text():
            continue
        for row in tbl.find_all("tr")[1:]:
            cells = row.find_all("td")
            if cells and len(cells) == len(headers):
                permits.append({headers[i]: _text(cells[i]) for i in range(len(headers))})

    return {"permits": permits, "count": len(permits)}


def parse_tax_detail(html: str) -> dict[str, Any]:
    script_end = html.rfind("</script>")
    if script_end >= 0:
        html = html[script_end + 9:]

    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, Any] = {}

    year_span = soup.find("span", id="currentYear")
    if year_span:
        result["year"] = _text(year_span)

    # Owner info
    for tbl in soup.find_all("table"):
        th = tbl.find("th")
        if th and "Owner Information" in _text(th):
            rows = tbl.find_all("tr")[1:]
            lines = [_text(r) for r in rows if _text(r)]
            if lines:
                result["owner_name"] = lines[0]
            break

    # Installments
    installments = []
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) >= 4:
            label = _text(cells[2])
            if "Installment" in label or "DUE" in label:
                installments.append({"label": label, "amount": _clean(_text(cells[-1]))})
    if installments:
        result["installments"] = installments

    # Tax district detail table
    for tbl in soup.find_all("table"):
        th = tbl.find("th")
        if th and "Property Tax" in _text(th):
            header_row = tbl.find("tr")
            col_headers = [_text(td) for td in header_row.find_all(["th", "td"])] if header_row else []
            districts = []
            for row in tbl.find_all("tr")[1:]:
                cells = row.find_all("td")
                if cells and col_headers:
                    district = {col_headers[i]: _clean(_text(cells[i]))
                                for i in range(min(len(col_headers), len(cells)))}
                    if any(district.values()):
                        districts.append(district)
            result["tax_districts"] = districts
            break

    return result


# ---------------------------------------------------------------------------
# Snapshot helpers (used by check_watched_parcels management command)
# ---------------------------------------------------------------------------

def extract_tracked_fields(details: dict[str, Any]) -> dict[str, str]:
    return {field: str(details.get(field, "")) for field in TRACKED_FIELDS}


def diff_tracked_fields(old: dict[str, str], new: dict[str, str]) -> dict[str, dict[str, str]]:
    """Return {field: {old: ..., new: ...}} for any changed fields."""
    return {
        field: {"old": old.get(field, ""), "new": new.get(field, "")}
        for field in TRACKED_FIELDS
        if old.get(field, "") != new.get(field, "")
    }


# ---------------------------------------------------------------------------
# High-level fetchers (used by MCP tools)
# ---------------------------------------------------------------------------

def get_parcel_details(parcel_id: str) -> dict[str, Any]:
    parcel_id = clean_parcel(parcel_id)
    return {"parcel_id": parcel_id, **parse_details(_post_fill_page(parcel_id, "Details"))}


def get_parcel_history(parcel_id: str) -> dict[str, Any]:
    parcel_id = clean_parcel(parcel_id)
    return {"parcel_id": parcel_id, **parse_history(_post_fill_page(parcel_id, "History"))}


def get_parcel_sales(parcel_id: str) -> dict[str, Any]:
    parcel_id = clean_parcel(parcel_id)
    return {"parcel_id": parcel_id, **parse_sales(_post_fill_page(parcel_id, "Sales"))}


def get_parcel_land(parcel_id: str) -> dict[str, Any]:
    parcel_id = clean_parcel(parcel_id)
    return {"parcel_id": parcel_id, **parse_land(_post_fill_page(parcel_id, "Land"))}


def get_parcel_improvements(parcel_id: str) -> dict[str, Any]:
    parcel_id = clean_parcel(parcel_id)
    return {"parcel_id": parcel_id, **parse_improvements(_post_fill_page(parcel_id, "Improvements"))}


def get_parcel_permits(parcel_id: str) -> dict[str, Any]:
    parcel_id = clean_parcel(parcel_id)
    return {"parcel_id": parcel_id, **parse_permits(_post_fill_page(parcel_id, "Permits"))}


def get_parcel_tax_detail(parcel_id: str, year: int | None = None) -> dict[str, Any]:
    parcel_id = clean_parcel(parcel_id)
    if year is None:
        from datetime import date
        year = date.today().year
    html = _post_tax_detail(parcel_id, year)
    return {"parcel_id": parcel_id, "requested_year": year, **parse_tax_detail(html)}


def get_full_parcel_report(parcel_id: str) -> dict[str, Any]:
    parcel_id = clean_parcel(parcel_id)
    tasks = {
        "details": lambda: parse_details(_post_fill_page(parcel_id, "Details")),
        "history": lambda: parse_history(_post_fill_page(parcel_id, "History")),
        "sales": lambda: parse_sales(_post_fill_page(parcel_id, "Sales")),
        "land": lambda: parse_land(_post_fill_page(parcel_id, "Land")),
        "improvements": lambda: parse_improvements(_post_fill_page(parcel_id, "Improvements")),
    }
    results: dict[str, Any] = {"parcel_id": parcel_id}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fn): key for key, fn in tasks.items()}
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:
                errors[key] = str(exc)
    if errors:
        results["fetch_errors"] = errors
    return results
