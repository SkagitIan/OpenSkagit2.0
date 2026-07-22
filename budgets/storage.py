from __future__ import annotations

import re
import uuid

from django.core.files.storage import storages


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def budget_pdf_storage():
    """Resolve the dedicated budget archive without changing other file storage."""
    return storages["budget_pdfs"]


def budget_pdf_upload_to(instance, _filename: str) -> str:
    """Create a stable, non-user-controlled object key for an imported PDF."""
    digest = (instance.content_sha256 or "").strip().lower()
    if not _SHA256_RE.fullmatch(digest):
        digest = uuid.uuid4().hex
    jurisdiction = instance.jurisdiction.slug
    status = instance.status
    return f"budgets/{jurisdiction}/{instance.fiscal_year}/{status}/{digest}.pdf"
