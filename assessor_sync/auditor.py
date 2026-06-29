from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup


SEARCH_URL = "https://www.skagitcounty.net/Search/Recording/default.aspx"
RESULTS_URL = "https://www.skagitcounty.net/Search/Recording/Results.aspx"
BASE_URL = "https://www.skagitcounty.net"
REQUEST_TIMEOUT = 45
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

CORE_INVESTOR_DOCUMENT_TYPES = (
    "Deed",
    "Transfer on Death Deed",
    "Real Estate Contract",
    "Deed Of Trust",
    "Mortgage",
    "Notice Of Default",
    "Notice Of Foreclosure",
    "Notice Of Trustees Sale",
    "Amended Notice Trustees Sale",
    "Discontinuance Trustees Sale",
    "Order Of Sale",
    "Certificate Of Sale",
    "Certif Of Redemption",
    "Bankruptcy",
    "Lien",
    "Amended Lien",
    "Federal Tax Lien",
    "Of Certificate Fed-tax Lien",
    "Judgment",
    "Judgement Lien",
    "Writ Of Attachment",
    "Satisfy Lien",
    "Release Federal Tax Lien",
    "Release Of Lis-pend",
    "Lease",
    "Amended Lease",
    "Assignment Of Lease",
    "Termination Of Lease",
    "Option",
    "Release Option",
    "First Right Of Refusal",
    "Assign Of Rents And Leases",
    "Assignment Of Rent",
    "Boundary line adjustment",
    "Amend Boundary Line Adjust",
    "Binding Site Plan",
    "Amend Binding Site Plan",
    "Plat",
    "Short Plat",
    "Amendment Of Plat",
    "Amendment Of Short Plat",
    "Survey",
    "Amendment Of Survey",
    "Condominium Plat",
    "Lot Certification",
    "Land Classification",
    "Approval Land Classification",
    "Change Of Land Classification",
    "Removal Land Classification",
    "Open Space Tax Agreement",
    "Terminate Open Space Agmt",
    "Rezone",
    "Easement",
    "Assign Easement",
    "Modif Of Easement",
    "Release Of Easement",
    "Water Agreement",
    "Water Right Certificate",
    "Title Elimination",
)

DOCUMENT_SIGNAL_GROUPS = {
    "transfer": {"Deed", "Transfer on Death Deed", "Real Estate Contract"},
    "financing": {"Deed Of Trust", "Mortgage"},
    "distress": {
        "Notice Of Default",
        "Notice Of Foreclosure",
        "Notice Of Trustees Sale",
        "Amended Notice Trustees Sale",
        "Discontinuance Trustees Sale",
        "Order Of Sale",
        "Certificate Of Sale",
        "Certif Of Redemption",
        "Bankruptcy",
    },
    "lien_judgment": {
        "Lien",
        "Amended Lien",
        "Federal Tax Lien",
        "Of Certificate Fed-tax Lien",
        "Judgment",
        "Judgement Lien",
        "Writ Of Attachment",
        "Satisfy Lien",
        "Release Federal Tax Lien",
        "Release Of Lis-pend",
    },
    "lease_option": {
        "Lease",
        "Amended Lease",
        "Assignment Of Lease",
        "Termination Of Lease",
        "Option",
        "Release Option",
        "First Right Of Refusal",
        "Assign Of Rents And Leases",
        "Assignment Of Rent",
    },
    "land_division": {
        "Boundary line adjustment",
        "Amend Boundary Line Adjust",
        "Binding Site Plan",
        "Amend Binding Site Plan",
        "Plat",
        "Short Plat",
        "Amendment Of Plat",
        "Amendment Of Short Plat",
        "Survey",
        "Amendment Of Survey",
        "Condominium Plat",
        "Lot Certification",
    },
    "land_status": {
        "Land Classification",
        "Approval Land Classification",
        "Change Of Land Classification",
        "Removal Land Classification",
        "Open Space Tax Agreement",
        "Terminate Open Space Agmt",
        "Rezone",
    },
    "rights_access": {
        "Easement",
        "Assign Easement",
        "Modif Of Easement",
        "Release Of Easement",
        "Water Agreement",
        "Water Right Certificate",
        "Title Elimination",
    },
}
DOCUMENT_TYPE_LOOKUP = {name.upper(): name for name in CORE_INVESTOR_DOCUMENT_TYPES}


@dataclass(frozen=True)
class AuditorRecording:
    recording_number: str
    recorded_date: date | None
    document_type: str
    signal_group: str
    grantor: str
    grantee: str
    filer: str
    comment: str
    legal: str
    parcel_number: str
    parcel_text: str
    assessor_url: str
    pdf_url: str
    reference_url: str
    raw_row: dict[str, Any]

    def compact_dict(self) -> dict[str, Any]:
        return {
            "recording_number": self.recording_number,
            "recorded_date": self.recorded_date.isoformat() if self.recorded_date else "",
            "document_type": self.document_type,
            "signal_group": self.signal_group,
            "grantor": self.grantor,
            "grantee": self.grantee,
            "parcel_number": self.parcel_number,
            "pdf_url": self.pdf_url,
        }


def signal_group_for(document_type: str) -> str:
    document_type = _canonical_document_type(document_type)
    for group, names in DOCUMENT_SIGNAL_GROUPS.items():
        if document_type in names:
            return group
    return "other"


def build_search_payload(search_page_html: str, document_type: str, start_date: date, end_date: date) -> dict[str, str]:
    soup = BeautifulSoup(search_page_html, "html.parser")
    payload: dict[str, str] = {}
    for field in soup.find_all(["input", "select"]):
        name = field.get("name")
        if not name:
            continue
        if field.name == "select":
            payload[name] = ""
        elif field.get("type") != "image":
            payload[name] = field.get("value", "")

    payload.update(
        {
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "ctl00$content$ddlDocumentType": document_type,
            "ctl00$content$txtStartDate": _format_county_date(start_date),
            "ctl00$content$txtEndDate": _format_county_date(end_date),
            "ctl00$content$ddlSortBy": "DateRecorded",
            "ctl00$content$ddlSortOrder": "ASC",
            "ctl00$content$btnSearchRecording": "Search",
            "hiddenInputToUpdateATBuffer_CommonToolkitScripts": "1",
        }
    )
    return payload


def build_next_payload(results_page_html: str) -> dict[str, str]:
    soup = BeautifulSoup(results_page_html, "html.parser")
    payload = {}
    for field in soup.find_all(["input", "select"]):
        name = field.get("name")
        if not name:
            continue
        if field.name == "select":
            selected = field.find("option", selected=True)
            payload[name] = selected.get("value", "") if selected else ""
        elif field.get("type") != "image":
            payload[name] = field.get("value", "")
    payload["ctl00$content$btnNextTop"] = "Next >>"
    payload.pop("ctl00$content$btnSearchRecording", None)
    return payload


def parse_recordings(html: str) -> list[AuditorRecording]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[AuditorRecording] = []
    for tr in soup.select("table.resultTable tbody tr"):
        cells = tr.find_all("td")
        if len(cells) < 10:
            continue
        file_number, recorded_date, document_type = _parse_file_cell(_cell_text(cells[3]))
        if not file_number:
            continue

        assessor_url = ""
        pdf_url = ""
        reference_url = ""
        for link in tr.find_all("a"):
            href = link.get("href")
            if not href:
                continue
            absolute = urljoin(BASE_URL, href)
            lower = absolute.lower()
            if "search/property" in lower:
                assessor_url = absolute
            elif lower.endswith(".pdf"):
                pdf_url = absolute
            elif "references.aspx" in lower:
                reference_url = absolute

        parcel_text = _cell_text(cells[9])
        parcel_number = _parcel_from_assessor_url(assessor_url) or _parcel_from_text(parcel_text)
        raw_row = {
            "file_cell": _cell_text(cells[3]),
            "grantor": _cell_text(cells[4]),
            "grantee": _cell_text(cells[5]),
            "filer": _cell_text(cells[6]),
            "comment": _cell_text(cells[7]),
            "legal": _cell_text(cells[8]),
            "parcel": parcel_text,
            "links": [urljoin(BASE_URL, link.get("href")) for link in tr.find_all("a") if link.get("href")],
        }
        rows.append(
            AuditorRecording(
                recording_number=file_number,
                recorded_date=recorded_date,
                document_type=document_type,
                signal_group=signal_group_for(document_type),
                grantor=_cell_text(cells[4]),
                grantee=_cell_text(cells[5]),
                filer=_cell_text(cells[6]),
                comment=_empty_dash(_cell_text(cells[7])),
                legal=_cell_text(cells[8]),
                parcel_number=parcel_number,
                parcel_text=parcel_text,
                assessor_url=assessor_url,
                pdf_url=pdf_url,
                reference_url=reference_url,
                raw_row=raw_row,
            )
        )
    return rows


def has_next_page(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    button = soup.find("input", {"name": "ctl00$content$btnNextTop"})
    if not button:
        button = soup.find("input", {"name": "ctl00$content$btnNextBottom"})
    if not button:
        return False
    disabled = button.get("disabled") or button.has_attr("disabled")
    css_class = " ".join(button.get("class", []))
    return not disabled and "aspNetDisabled" not in css_class


def result_count(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    match = re.search(r"The search returned\s+([\d,]+)\s+records?", text, re.I)
    return int(match.group(1).replace(",", "")) if match else 0


class AuditorRecordingClient:
    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def search(
        self,
        document_type: str,
        start_date: date,
        end_date: date,
        max_pages: int = 25,
    ) -> tuple[list[AuditorRecording], dict[str, Any]]:
        search_response = self.session.get(SEARCH_URL, timeout=REQUEST_TIMEOUT)
        search_response.raise_for_status()
        payload = build_search_payload(search_response.text, document_type, start_date, end_date)

        records: list[AuditorRecording] = []
        pages = 0
        capped = False
        next_payload: dict[str, str] | None = payload
        total_count = 0
        while next_payload is not None and pages < max_pages:
            response = self.session.post(
                RESULTS_URL,
                data=next_payload,
                headers={"Origin": BASE_URL, "Referer": SEARCH_URL},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            pages += 1
            total_count = result_count(response.text) or total_count
            records.extend(parse_recordings(response.text))
            if has_next_page(response.text):
                next_payload = build_next_payload(response.text)
            else:
                next_payload = None
        if next_payload is not None:
            capped = True

        return records, {"pages": pages, "result_count": total_count or len(records), "capped": capped}


def _format_county_date(value: date) -> str:
    return f"{value.month}/{value.day}/{value.year}"


def _cell_text(cell) -> str:
    return _normalize_space(cell.get_text(" ", strip=True))


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _empty_dash(value: str) -> str:
    return "" if value.strip() == "-" else value


def _parse_file_cell(value: str) -> tuple[str, date | None, str]:
    match = re.match(r"(?P<number>\d{12})\s+(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+(?P<type>.+)", value)
    if not match:
        return "", None, value
    return (
        match.group("number"),
        _parse_county_date(match.group("date")),
        _canonical_document_type(match.group("type")),
    )


def _canonical_document_type(value: str) -> str:
    normalized = _normalize_space(value).upper()
    return DOCUMENT_TYPE_LOOKUP.get(normalized, _normalize_space(value).title())


def _parse_county_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None


def _parcel_from_assessor_url(value: str) -> str:
    if not value:
        return ""
    params = parse_qs(urlparse(value).query)
    parcel = (params.get("id") or [""])[0]
    return parcel.upper() if re.fullmatch(r"P\d+", parcel or "", re.I) else ""


def _parcel_from_text(value: str) -> str:
    match = re.search(r"\bP\d+\b", value or "", re.I)
    return match.group(0).upper() if match else ""
