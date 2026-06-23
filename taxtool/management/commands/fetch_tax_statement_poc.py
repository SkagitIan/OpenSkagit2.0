from __future__ import annotations

import json
import re
import urllib.request
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


FILL_PAGE_URL = "https://www.skagitcounty.net/Search/Property/Webservice.asmx/fillPage"
TAX_HISTORY_URL = "https://www.skagitcounty.net/Search/Property/Webservice.asmx/getTaxHistoryDetail"


def parse_money(value: str) -> str | None:
    cleaned = value.replace("$", "").replace(",", "").strip()
    if cleaned in {"", "."}:
        return "0.00"
    try:
        return str(Decimal(cleaned).quantize(Decimal("0.01")))
    except InvalidOperation:
        return None


def post_json(url: str, body: dict[str, str], timeout: int) -> str:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("d", "")


def value_after_label(text: str, label: str) -> str | None:
    pattern = rf"{re.escape(label)}\s*:?\s*(\$?[0-9,]*\.?[0-9]+|\$\.\d{{0,2}}|\$\.00)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return parse_money(match.group(1)) if match else None


def parse_statement(html: str, source_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    year_match = re.search(r"\b(20\d{2})\s+Real Estate Tax Statement\b", text)
    parcel_match = re.search(r"Parcel ID:\s*([A-Z0-9-]+)", text)
    xref_match = re.search(r"Xref ID:\s*([0-9-]+)", text)

    installments = []
    for match in re.finditer(
        r"(20\d{2})\s+(First|Second)\s+Installment\s+DUE by\s+([^:]+):\s*"
        r"(?:(PAID):\s*)?(\$?[0-9,]*\.?[0-9]+|\$\.\d{0,2}|\$\.00)",
        text,
        flags=re.IGNORECASE,
    ):
        installments.append(
            {
                "tax_year": int(match.group(1)),
                "installment": match.group(2).lower(),
                "due_by": match.group(3).strip(),
                "paid": bool(match.group(4)),
                "amount": parse_money(match.group(5)),
            }
        )

    tax_year = int(year_match.group(1)) if year_match else None
    total_due = value_after_label(text, f"{tax_year} Total Due") if tax_year else None
    amount_paid = value_after_label(text, f"{tax_year} Amount Paid") if tax_year else None

    status = "unknown"
    if total_due is not None:
        status = "paid" if Decimal(total_due) == 0 else "unpaid"
    if total_due is not None and amount_paid not in {None, "0.00"} and Decimal(total_due) > 0:
        status = "partially_paid"

    return {
        "parcel_number": parcel_match.group(1) if parcel_match else None,
        "tax_account_number": xref_match.group(1) if xref_match else None,
        "tax_year": tax_year,
        "levy_code": re.search(r"Levy Code:\s*([0-9A-Z-]+)", text).group(1)
        if re.search(r"Levy Code:\s*([0-9A-Z-]+)", text)
        else None,
        "general_tax": value_after_label(text, "General Tax"),
        "special_assessments_fees": value_after_label(text, "Special Assessment/Fees"),
        "total_due": total_due,
        "amount_paid": amount_paid,
        "status": status,
        "installments": installments,
        "source_url": source_url,
        "source_fetched_at": timezone.now().isoformat(),
    }


class Command(BaseCommand):
    help = "Fetch and parse one public Skagit County tax statement as a delinquent-tax PoC."

    def add_arguments(self, parser):
        parser.add_argument("parcel_number", help="Parcel number, for example P45283.")
        parser.add_argument("--year", type=int, default=None, help="Prior/current statement year to fetch.")
        parser.add_argument("--timeout", type=int, default=15)

    def handle(self, *args, **options):
        parcel_number = options["parcel_number"].strip().upper()
        year = options["year"]
        timeout = options["timeout"]

        if year:
            url = TAX_HISTORY_URL
            body = {"sValue": parcel_number, "sYear": str(year)}
        else:
            url = FILL_PAGE_URL
            body = {"sValue": parcel_number, "ResultType": "Taxes"}

        try:
            html = post_json(url, body, timeout)
        except Exception as exc:
            raise CommandError(f"Could not fetch tax statement: {exc}") from exc

        if not html:
            raise CommandError("County endpoint returned no statement HTML.")

        parsed = parse_statement(html, url)
        self.stdout.write(json.dumps(parsed, indent=2, sort_keys=True))
