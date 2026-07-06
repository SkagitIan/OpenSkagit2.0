"""
Management command: process_taxshift_signups

Continuously watches for new TaxShiftSignup rows, resolves their free-text
address_or_parcel into a canonical parcel_number, and captures a baseline
snapshot (live assessor Details page + already-ingested auditor recordings)
for each one. This is the "background job" that runs after signup — it's a
long-running worker (see tax_delinquency/slow_check_tax_statements for the
same shape), not a one-shot cron job, so new signups get processed promptly.

Usage:
    python manage.py process_taxshift_signups
    python manage.py process_taxshift_signups --once
    python manage.py process_taxshift_signups --poll-seconds 30
"""
from __future__ import annotations

import logging
import os
import re
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Resolve pending TaxShiftSignup rows and capture a baseline parcel snapshot for each."

    def add_arguments(self, parser):
        parser.add_argument(
            "--poll-seconds",
            type=float,
            default=float(os.getenv("TAXSHIFT_SIGNUP_POLL_SECONDS", "15")),
            help="Seconds to sleep between polling cycles.",
        )
        parser.add_argument("--once", action="store_true", help="Process pending signups once and exit.")

    def handle(self, *args, **options):
        poll_seconds = options["poll_seconds"]
        while True:
            processed = self._process_pending()
            if options["once"]:
                self.stdout.write(f"Processed {processed} pending signup(s).")
                return
            if processed == 0:
                time.sleep(poll_seconds)

    def _process_pending(self) -> int:
        from taxtool.models import TaxShiftSignup

        pending = TaxShiftSignup.objects.filter(resolution_status=TaxShiftSignup.RESOLUTION_PENDING)
        count = 0
        for signup in pending.iterator():
            try:
                self._resolve_and_snapshot(signup)
            except Exception as exc:
                logger.error("Error processing signup %s: %s", signup.email, exc)
                self.stdout.write(f"  ERROR {signup.email}: {exc}")
            count += 1
        return count

    def _resolve_and_snapshot(self, signup) -> None:
        from taxtool.models import TaxShiftSignup
        from taxtool.queries import get_parcel, search_parcels

        query = signup.address_or_parcel.strip()
        if not query:
            signup.resolution_status = TaxShiftSignup.RESOLUTION_UNRESOLVED
            signup.save(update_fields=["resolution_status", "updated_at"])
            return

        parcel_number = self._resolve_parcel_number(query, get_parcel, search_parcels)
        if parcel_number is None:
            signup.resolution_status = TaxShiftSignup.RESOLUTION_UNRESOLVED
            signup.save(update_fields=["resolution_status", "updated_at"])
            self.stdout.write(f"  {signup.email}: no match for {query!r}.")
            return
        if parcel_number == "":
            signup.resolution_status = TaxShiftSignup.RESOLUTION_AMBIGUOUS
            signup.save(update_fields=["resolution_status", "updated_at"])
            self.stdout.write(f"  {signup.email}: ambiguous match for {query!r}.")
            return

        recorded_docs = self._capture_snapshot(parcel_number)

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
        self.stdout.write(f"  {signup.email}: resolved to {parcel_number}, snapshot captured.")

    def _resolve_parcel_number(self, query: str, get_parcel, search_parcels) -> str | None:
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

    def _capture_snapshot(self, parcel_number: str) -> list[dict]:
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
