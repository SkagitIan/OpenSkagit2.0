from __future__ import annotations

import json
import re
import urllib.request
from datetime import date
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup
from django.utils import timezone


FILL_PAGE_URL = "https://www.skagitcounty.net/Search/Property/Webservice.asmx/fillPage"
TAX_HISTORY_URL = "https://www.skagitcounty.net/Search/Property/Webservice.asmx/getTaxHistoryDetail"

MONTHS = {
    "JANUARY": 1,
    "FEBRUARY": 2,
    "MARCH": 3,
    "APRIL": 4,
    "MAY": 5,
    "JUNE": 6,
    "JULY": 7,
    "AUGUST": 8,
    "SEPTEMBER": 9,
    "OCTOBER": 10,
    "NOVEMBER": 11,
    "DECEMBER": 12,
}

LEAD_ORDER = {
    "unknown": 0,
    "clear": 1,
    "watch": 2,
    "one_late": 3,
    "behind": 4,
    "serious": 5,
    "severe": 6,
}


def parse_money(value: str | None) -> Decimal | None:
    if value is None:
        return None
    cleaned = value.replace("$", "").replace(",", "").strip()
    if cleaned in {"", ".", ".00"}:
        return Decimal("0.00")
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def money_as_string(value: Decimal | None) -> str | None:
    return str(value.quantize(Decimal("0.01"))) if value is not None else None


def post_json(url: str, body: dict[str, str], timeout: int = 20) -> str:
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


def statement_request(parcel_number: str, tax_year: int, current_year: int | None = None) -> tuple[str, dict[str, str]]:
    current_year = current_year or timezone.localdate().year
    if tax_year >= current_year:
        return FILL_PAGE_URL, {"sValue": parcel_number, "ResultType": "Taxes"}
    return TAX_HISTORY_URL, {"sValue": parcel_number, "sYear": str(tax_year)}


def value_after_label(text: str, label: str) -> Decimal | None:
    pattern = rf"{re.escape(label)}\s*:?\s*(\$?[0-9,]*\.?[0-9]+|\$\.\d{{0,2}}|\$\.00)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return parse_money(match.group(1)) if match else None


def parse_due_date(tax_year: int, due_by: str) -> date | None:
    match = re.search(r"([A-Z]+)\s+(\d{1,2})", due_by.upper())
    if not match:
        return None
    month = MONTHS.get(match.group(1))
    if not month:
        return None
    return date(tax_year, month, int(match.group(2)))


def classify_statement(parsed: dict, today: date | None = None) -> dict:
    today = today or timezone.localdate()
    total_due = parse_money(parsed.get("total_due"))
    amount_paid = parse_money(parsed.get("amount_paid"))
    tax_year = parsed.get("tax_year")

    status = "unknown"
    if total_due is not None:
        status = "paid" if total_due == 0 else "unpaid"
    if total_due and total_due > 0 and amount_paid and amount_paid > 0:
        status = "partially_paid"

    unpaid_count = 0
    delinquent_count = 0
    delinquent_dates = []
    enriched_installments = []
    for item in parsed.get("installments", []):
        amount = parse_money(item.get("amount"))
        due_date = parse_due_date(int(item["tax_year"]), item.get("due_by", ""))
        is_unpaid = bool(amount and amount > 0 and not item.get("paid"))
        is_delinquent = bool(is_unpaid and due_date and due_date < today)
        if is_unpaid:
            unpaid_count += 1
        if is_delinquent:
            delinquent_count += 1
            delinquent_dates.append(due_date)
        enriched_installments.append(
            {
                **item,
                "amount": money_as_string(amount),
                "due_date": due_date.isoformat() if due_date else None,
                "is_unpaid": is_unpaid,
                "is_delinquent": is_delinquent,
            }
        )

    if total_due and total_due > 0 and tax_year and int(tax_year) < today.year and delinquent_count == 0:
        delinquent_count = 1

    lead_level = "unknown"
    if total_due is not None:
        lead_level = "clear" if total_due == 0 else "watch"
    if total_due and total_due > 0:
        if delinquent_count <= 1:
            lead_level = "one_late"
        if delinquent_count >= 2:
            lead_level = "behind"
        if delinquent_count >= 2 and (
            total_due >= Decimal("1000.00") or int(tax_year or today.year) <= today.year - 2
        ):
            lead_level = "serious"
        if delinquent_count >= 2 and (
            total_due >= Decimal("5000.00") or int(tax_year or today.year) <= today.year - 3
        ):
            lead_level = "severe"

    return {
        "status": status,
        "lead_level": lead_level,
        "unpaid_installment_count": unpaid_count,
        "delinquent_installment_count": delinquent_count,
        "oldest_due_date": min(delinquent_dates).isoformat() if delinquent_dates else None,
        "installments": enriched_installments,
    }


def parse_statement(html: str, source_url: str, today: date | None = None) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    year_match = re.search(r"\b(20\d{2})\s+Real Estate Tax Statement\b", text)
    parcel_match = re.search(r"Parcel ID:\s*([A-Z0-9-]+)", text)
    xref_match = re.search(r"Xref ID:\s*([0-9-]+)", text)
    levy_match = re.search(r"Levy Code:\s*([0-9A-Z-]+)", text)

    installments = []
    for match in re.finditer(
        r"(20\d{2})\s+(First|Second)\s+Installment\s+DUE by\s+([^:]+):\s*"
        r"(?:(PAID):\s*)?(\$?[0-9,]*\.?[0-9]+|\$\.\d{0,2}|\$\.00)",
        text,
        flags=re.IGNORECASE,
    ):
        amount = parse_money(match.group(5))
        installments.append(
            {
                "tax_year": int(match.group(1)),
                "installment": match.group(2).lower(),
                "due_by": match.group(3).strip(),
                "paid": bool(match.group(4)),
                "amount": money_as_string(amount),
            }
        )

    tax_year = int(year_match.group(1)) if year_match else None
    parsed = {
        "parcel_number": parcel_match.group(1) if parcel_match else None,
        "tax_account_number": xref_match.group(1) if xref_match else None,
        "tax_year": tax_year,
        "levy_code": levy_match.group(1) if levy_match else None,
        "general_tax": money_as_string(value_after_label(text, "General Tax")),
        "special_assessments_fees": money_as_string(value_after_label(text, "Special Assessment/Fees")),
        "total_due": money_as_string(value_after_label(text, f"{tax_year} Total Due")) if tax_year else None,
        "amount_paid": money_as_string(value_after_label(text, f"{tax_year} Amount Paid")) if tax_year else None,
        "installments": installments,
        "source_url": source_url,
        "source_fetched_at": timezone.now().isoformat(),
    }
    parsed.update(classify_statement(parsed, today=today))
    return parsed


def fetch_statement(parcel_number: str, tax_year: int, timeout: int = 20, current_year: int | None = None) -> dict:
    source_url, body = statement_request(parcel_number, tax_year, current_year=current_year)
    html = post_json(source_url, body, timeout=timeout)
    if not html:
        raise ValueError("County endpoint returned no statement HTML.")
    parsed = parse_statement(html, source_url)
    if not parsed.get("parcel_number"):
        raise ValueError("Tax statement did not include a parcel number.")
    return parsed


def lead_rank(level: str | None) -> int:
    return LEAD_ORDER.get(level or "unknown", 0)
