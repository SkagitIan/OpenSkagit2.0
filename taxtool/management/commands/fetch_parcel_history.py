"""
Management command: fetch_parcel_history

Fetches multi-year assessed-value and tax history for every active parcel
from the public Skagit County property search webservice and stores it in
skagit_parcel_history / skagit_parcel_history_status.

Resumable: parcels already marked 'ok' or 'no_data' are skipped on rerun.

Usage:
    python manage.py fetch_parcel_history
    python manage.py fetch_parcel_history --limit 50 --delay 0.1
    python manage.py fetch_parcel_history --retry-errors
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.db import connection

API_URL = "https://www.skagitcounty.net/search/propertym/Webservice.asmx/fillPage"

CREATE_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS skagit_parcel_history (
    parcel_number TEXT NOT NULL,
    tax_year INTEGER NOT NULL,
    value_year INTEGER,
    building_value NUMERIC,
    land_value NUMERIC,
    total_value NUMERIC,
    tax_amount NUMERIC,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (parcel_number, tax_year)
)
"""

CREATE_STATUS_TABLE = """
CREATE TABLE IF NOT EXISTS skagit_parcel_history_status (
    parcel_number TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def parse_money(text):
    text = text.replace("$", "").replace(",", "").strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_year(text):
    text = text.strip()
    return int(text) if text.isdigit() else None


def fetch_history_html(parcel_number, timeout=15):
    body = json.dumps({"sValue": parcel_number, "ResultType": "history"}).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("d", "")


def parse_assessed_values(html):
    """
    Returns a list of dicts (tax_year, value_year, building_value, land_value,
    total_value, tax_amount) from the "Assessed Values" table, or [] if the
    parcel has no history on file.
    """
    soup = BeautifulSoup(html, "html.parser")
    header = soup.find("h3", string=lambda s: s and "Assessed Values" in s)
    if not header:
        return []
    table = header.find_next("table")
    if not table:
        return []

    rows = []
    for tr in table.find_all("tr"):
        if tr.find_parent("thead"):
            continue
        tds = tr.find_all("td")
        if len(tds) < 6:
            continue
        tax_year = parse_year(tds[0].get_text())
        if tax_year is None:
            continue
        rows.append({
            "tax_year": tax_year,
            "value_year": parse_year(tds[1].get_text()),
            "building_value": parse_money(tds[2].get_text()),
            "land_value": parse_money(tds[3].get_text()),
            "total_value": parse_money(tds[4].get_text()),
            "tax_amount": parse_money(tds[5].get_text()),
        })
    return rows


class Command(BaseCommand):
    help = "Fetch per-parcel assessed-value/tax history from the Skagit County property search API."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None,
                             help="Only process the first N pending parcels (for testing).")
        parser.add_argument("--delay", type=float, default=0.3,
                             help="Seconds to sleep between requests.")
        parser.add_argument("--retry-errors", action="store_true",
                             help="Re-attempt parcels previously marked 'error'.")

    def handle(self, *args, **options):
        limit = options["limit"]
        delay = options["delay"]
        retry_errors = options["retry_errors"]

        with connection.cursor() as cursor:
            cursor.execute(CREATE_HISTORY_TABLE)
            cursor.execute(CREATE_STATUS_TABLE)

        statuses_to_skip = ["ok", "no_data"] if not retry_errors else ["ok", "no_data", "error"]
        placeholders = ", ".join(["%s"] * len(statuses_to_skip))
        query = f"""
            SELECT p.parcel_number
            FROM skagit_parcels p
            WHERE p.inactive_date IS NULL
              AND p.parcel_number NOT IN (
                  SELECT parcel_number FROM skagit_parcel_history_status
                  WHERE status IN ({placeholders})
              )
            ORDER BY p.parcel_number
        """
        with connection.cursor() as cursor:
            cursor.execute(query, statuses_to_skip)
            pending = [row[0] for row in cursor.fetchall()]

        if limit:
            pending = pending[:limit]

        total = len(pending)
        self.stdout.write(f"{total} parcels to fetch")

        ok = no_data = errors = 0

        for i, parcel_number in enumerate(pending, 1):
            try:
                html = fetch_history_html(parcel_number)
                rows = parse_assessed_values(html)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                self._mark_status(parcel_number, "error")
                errors += 1
                self.stdout.write(f"[{i}/{total}] {parcel_number} ERROR: {e}")
                time.sleep(delay)
                continue

            if not rows:
                self._mark_status(parcel_number, "no_data")
                no_data += 1
            else:
                self._save_history(parcel_number, rows)
                self._mark_status(parcel_number, "ok")
                ok += 1

            if i % 200 == 0 or i == total:
                self.stdout.write(f"[{i}/{total}] ok={ok} no_data={no_data} errors={errors}")

            time.sleep(delay)

        self.stdout.write(self.style.SUCCESS(
            f"Done. ok={ok} no_data={no_data} errors={errors} (of {total} processed)"
        ))

    def _save_history(self, parcel_number, rows):
        with connection.cursor() as cursor:
            for r in rows:
                cursor.execute(
                    """
                    INSERT INTO skagit_parcel_history
                        (parcel_number, tax_year, value_year, building_value, land_value, total_value, tax_amount, fetched_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (parcel_number, tax_year) DO UPDATE SET
                        value_year = EXCLUDED.value_year,
                        building_value = EXCLUDED.building_value,
                        land_value = EXCLUDED.land_value,
                        total_value = EXCLUDED.total_value,
                        tax_amount = EXCLUDED.tax_amount,
                        fetched_at = now()
                    """,
                    [
                        parcel_number,
                        r["tax_year"],
                        r["value_year"],
                        r["building_value"],
                        r["land_value"],
                        r["total_value"],
                        r["tax_amount"],
                    ],
                )

    def _mark_status(self, parcel_number, status):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO skagit_parcel_history_status (parcel_number, status, fetched_at)
                VALUES (%s, %s, now())
                ON CONFLICT (parcel_number) DO UPDATE SET
                    status = EXCLUDED.status,
                    fetched_at = now()
                """,
                [parcel_number, status],
            )
