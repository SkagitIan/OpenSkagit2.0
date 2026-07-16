from __future__ import annotations

import json
import os
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

DEFAULT_BASE_URL = "https://skagit-parcels.ian-larsen-1976.workers.dev"

FIELD_MAP = {
    "assessed_value": ("assessed_value", "Assessed Value"),
    "total_market_value": ("market_value", "Total Market Value"),
    "building_value": ("improvement_value", "Building Value"),
    "acres": ("acres", "Acres"),
    "sale_date": ("sale_date", "Sale Date"),
    "sale_price": ("sale_price", "Sale Price"),
    "tax_year": ("tax_year", "Tax Year"),
}


def _embedded_assessor(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    for field, value in payload.items():
        if not isinstance(value, str) or not value.lstrip().startswith("{"):
            continue
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            continue
        assessor = decoded.get("assessor") if isinstance(decoded, dict) else None
        if isinstance(assessor, dict):
            return assessor, field
    return None, None


def _comparable(value: Any, *, date_value: bool = False) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if date_value:
        match = re.match(r"\d{4}-\d{2}-\d{2}", text)
        return match.group(0) if match else text
    cleaned = text.replace(",", "").replace("$", "")
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        return text.upper()
    return format(number.normalize(), "f")


class Command(BaseCommand):
    help = "Compare a deterministic, read-only D1 parcel sample with canonical PostGIS without logging parcel payloads."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", default=os.environ.get("LEGACY_D1_BASE_URL", DEFAULT_BASE_URL))
        parser.add_argument("--sample-size", type=int, default=25)
        parser.add_argument("--timeout", type=float, default=20)

    def handle(self, *args, **options):
        sample_size = options["sample_size"]
        if not 1 <= sample_size <= 500:
            raise CommandError("--sample-size must be between 1 and 500")
        base_url = str(options["base_url"]).rstrip("/")
        timeout = options["timeout"]

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT count(*) FILTER (WHERE inactive_date IS NULL), count(*)
                FROM skagit_parcels
                """
            )
            postgis_active, postgis_total = cursor.fetchone()
            cursor.execute(
                """
                SELECT parcel_number, assessed_value, total_market_value, building_value,
                       acres, sale_date, sale_price, tax_year
                FROM skagit_parcels
                WHERE inactive_date IS NULL
                ORDER BY md5(parcel_number)
                LIMIT %s
                """,
                [sample_size],
            )
            columns = [column[0] for column in cursor.description]
            samples = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]

        session = requests.Session()
        health = session.get(f"{base_url}/health", timeout=timeout)
        health.raise_for_status()
        d1_count = health.json().get("parcel_count")

        comparisons = {field: {"comparable": 0, "matches": 0, "mismatches": 0} for field in FIELD_MAP}
        missing = 0
        failures = 0
        normalized_core_complete = 0
        embedded_records = 0
        embedded_fields: Counter[str] = Counter()
        received = 0

        for sample in samples:
            try:
                response = session.get(f"{base_url}/parcel/{sample['parcel_number']}", timeout=timeout)
                if response.status_code == 404:
                    missing += 1
                    continue
                response.raise_for_status()
                payload = response.json()
            except (requests.RequestException, ValueError):
                failures += 1
                continue
            received += 1
            if all(payload.get(field) is not None for field in ("assessed_value", "acres", "latitude", "longitude")):
                normalized_core_complete += 1
            embedded, embedded_field = _embedded_assessor(payload)
            if embedded:
                embedded_records += 1
                embedded_fields[embedded_field or "unknown"] += 1

            for field, (direct_key, embedded_key) in FIELD_MAP.items():
                d1_value = payload.get(direct_key)
                if d1_value is None and embedded:
                    d1_value = embedded.get(embedded_key)
                left = _comparable(sample.get(field), date_value=field == "sale_date")
                right = _comparable(d1_value, date_value=field == "sale_date")
                if left is None or right is None:
                    continue
                comparisons[field]["comparable"] += 1
                comparisons[field]["matches" if left == right else "mismatches"] += 1

        result = {
            "source": base_url,
            "counts": {
                "d1": d1_count,
                "postgis_active": postgis_active,
                "postgis_total": postgis_total,
                "d1_minus_postgis_active": d1_count - postgis_active if isinstance(d1_count, int) else None,
                "d1_minus_postgis_total": d1_count - postgis_total if isinstance(d1_count, int) else None,
            },
            "sample": {
                "requested": sample_size,
                "received": received,
                "missing_in_d1": missing,
                "request_failures": failures,
                "normalized_core_complete": normalized_core_complete,
                "embedded_assessor_records": embedded_records,
                "embedded_assessor_fields": dict(embedded_fields),
            },
            "field_comparisons": comparisons,
            "safe_to_delete": False,
            "next_gate": "Export D1/R2, classify count and field mismatches, then establish 30 days of zero traffic.",
        }
        self.stdout.write(json.dumps(result, indent=2, default=str))
