from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.conf import settings
from pypdf import PdfReader


MAX_PDF_BYTES = settings.BUDGET_MAX_PDF_MB * 1024 * 1024
MAX_CANDIDATE_ABS_AMOUNT = Decimal("1000000000000")
MONEY_RE = re.compile(r"(?P<label>[^\n]{3,160}?)\s+(?P<amount>\(?-?\$?[\d,]+(?:\.\d{2})?\)?)\s*$")


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str


@dataclass(frozen=True)
class CandidateAmount:
    page_number: int
    label: str
    amount: Decimal
    raw_line: str


def extract_pdf(pdf_bytes: bytes) -> tuple[str, list[ExtractedPage], list[CandidateAmount], list[str]]:
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("The supplied file is not a PDF.")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError(f"PDF exceeds the {MAX_PDF_BYTES // (1024 * 1024)} MB import limit.")

    digest = hashlib.sha256(pdf_bytes).hexdigest()
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages: list[ExtractedPage] = []
    candidates: list[CandidateAmount] = []
    warnings: list[str] = []

    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if not text.strip():
            warnings.append(f"Page {number} has no extractable text and may require OCR.")
        pages.append(ExtractedPage(page_number=number, text=text))
        candidates.extend(_candidate_amounts(number, text))
    return digest, pages, candidates, warnings


def _candidate_amounts(page_number: int, text: str) -> list[CandidateAmount]:
    rows: list[CandidateAmount] = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        match = MONEY_RE.search(line)
        if not match:
            continue
        label = match.group("label").strip(" .:-")
        if not label or label.lower() in {"page", "total"}:
            continue
        try:
            amount = parse_money(match.group("amount"))
        except InvalidOperation:
            continue
        if abs(amount) > MAX_CANDIDATE_ABS_AMOUNT:
            continue
        rows.append(CandidateAmount(page_number, label, amount, raw_line))
    return rows


def parse_money(value: str) -> Decimal:
    normalized = value.strip().replace("$", "").replace(",", "")
    if normalized.startswith("(") and normalized.endswith(")"):
        normalized = f"-{normalized[1:-1]}"
    return Decimal(normalized)
