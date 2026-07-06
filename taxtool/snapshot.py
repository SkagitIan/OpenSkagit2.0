"""
Shared parcel-resolution + baseline-snapshot logic for TaxShiftSignup.

Used by both the process_taxshift_signups worker (catches anything missed)
and the tax_signup view's immediate background thread (the common,
fast path — see views.py).
"""
from __future__ import annotations

import logging
import re
from typing import IO

from django.utils import timezone

logger = logging.getLogger(__name__)


def resolve_and_snapshot(signup, stdout: IO | None = None) -> bool:
    """Resolve signup.address_or_parcel to a parcel_number and capture a
    baseline snapshot. Returns True if resolution succeeded."""
    from .models import TaxShiftSignup
    from .queries import get_parcel, search_parcels

    query = signup.address_or_parcel.strip()
    if not query:
        signup.resolution_status = TaxShiftSignup.RESOLUTION_UNRESOLVED
        signup.save(update_fields=["resolution_status", "updated_at"])
        return False

    parcel_number = _resolve_parcel_number(query, get_parcel, search_parcels)
    if parcel_number is None:
        signup.resolution_status = TaxShiftSignup.RESOLUTION_UNRESOLVED
        signup.save(update_fields=["resolution_status", "updated_at"])
        _log(stdout, f"  {signup.email}: no match for {query!r}.")
        return False
    if parcel_number == "":
        signup.resolution_status = TaxShiftSignup.RESOLUTION_AMBIGUOUS
        signup.save(update_fields=["resolution_status", "updated_at"])
        _log(stdout, f"  {signup.email}: ambiguous match for {query!r}.")
        return False

    recorded_docs = _capture_snapshot(parcel_number)

    signup.parcel_number = parcel_number
    signup.resolution_status = TaxShiftSignup.RESOLUTION_RESOLVED
    signup.recorded_docs_snapshot = recorded_docs
    signup.snapshot_captured_at = timezone.now()
    signup.save(
        update_fields=[
            "parcel_number",
            "resolution_status",
            "recorded_docs_snapshot",
            "snapshot_captured_at",
            "updated_at",
        ]
    )
    _log(stdout, f"  {signup.email}: resolved to {parcel_number}, snapshot captured.")
    return True


def _resolve_parcel_number(query: str, get_parcel, search_parcels) -> str | None:
    """Return a parcel_number, '' for ambiguous, or None for no match."""
    # The parcel-detail signup form (taxtool/_bill.html) pre-fills a hidden
    # "<address> / Parcel <parcel_number>" value — that suffix is authoritative,
    # so prefer it over fuzzy-matching the whole string.
    tagged = re.search(r"/\s*Parcel\s+(\S+)\s*$", query, re.I)
    if tagged:
        exact = get_parcel(tagged.group(1).upper())
        if exact:
            return exact["parcel_number"]

    exact = get_parcel(query.upper())
    if exact:
        return exact["parcel_number"]

    matches = search_parcels(query)
    if len(matches) == 1:
        return matches[0]["parcel_number"]
    if len(matches) == 0:
        return None
    return ""


def _capture_snapshot(parcel_number: str) -> list[dict]:
    from assessor_mcp import services as assessor
    from assessor_sync.models import AuditorRecording, ParcelLiveSnapshot

    details_html = assessor._post_fill_page(parcel_number, "Details")
    details = assessor.parse_details(details_html)
    live_fields = assessor.extract_tracked_fields(details)

    ParcelLiveSnapshot.objects.update_or_create(
        parcel_number=parcel_number,
        defaults={"tracked_fields": live_fields, "last_checked_at": timezone.now()},
    )

    recordings = AuditorRecording.objects.filter(parcel_number=parcel_number).order_by("-recorded_date")[:20]
    return [
        {
            "recording_number": r.recording_number,
            "recorded_date": r.recorded_date.isoformat() if r.recorded_date else "",
            "document_type": r.document_type,
            "grantor": r.grantor,
            "grantee": r.grantee,
            "pdf_url": r.pdf_url,
        }
        for r in recordings
    ]


def _log(stdout: IO | None, message: str) -> None:
    if stdout:
        stdout.write(message)
    else:
        logger.info(message)
