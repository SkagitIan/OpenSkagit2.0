"""
Management command: process_taxshift_signups

Continuously watches for new TaxShiftSignup rows, resolves their free-text
address_or_parcel into a canonical parcel_number, and captures a baseline
snapshot (live assessor Details page + already-ingested auditor recordings)
for each one.

This is the safety-net path: the tax_signup view already fires this same
work immediately in a background thread on signup (see views.py), so most
rows are resolved within seconds. This command exists to catch the rare
case that slips through (e.g. the web worker process was mid-restart when
a signup came in), and to send the verification email for any row whose
email hasn't gone out yet.

Because it's a safety net for an occasional, low-volume form rather than
a constant workload, production runs it with --once on a Railway Cron
Schedule (see railway.taxshift-signups.json — every 5 minutes) instead of
as an always-on service. The continuous-loop mode below is kept for local
development convenience.

Usage:
    python manage.py process_taxshift_signups --once   # production (cron)
    python manage.py process_taxshift_signups           # local dev loop
    python manage.py process_taxshift_signups --poll-seconds 30
"""
from __future__ import annotations

import logging
import os
import time

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Resolve pending TaxShiftSignup rows, capture a baseline snapshot, and send verification emails."

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
                self.stdout.write(f"Processed {processed} signup(s).")
                return
            if processed == 0:
                time.sleep(poll_seconds)

    def _process_pending(self) -> int:
        from taxtool.models import TaxShiftSignup
        from taxtool.notifications import send_verification_email
        from taxtool.snapshot import resolve_and_snapshot

        count = 0

        pending = TaxShiftSignup.objects.filter(resolution_status=TaxShiftSignup.RESOLUTION_PENDING)
        for signup in pending.iterator():
            try:
                resolve_and_snapshot(signup, stdout=self.stdout)
            except Exception as exc:
                logger.error("Error processing signup %s: %s", signup.email, exc)
                self.stdout.write(f"  ERROR {signup.email}: {exc}")
            count += 1

        # Catch any signup whose verification email didn't go out yet (e.g. the
        # immediate background thread in the view died before sending it).
        unsent = TaxShiftSignup.objects.filter(
            is_active=True, verification_email_sent_at__isnull=True
        ).exclude(resolution_status=TaxShiftSignup.RESOLUTION_PENDING)
        for signup in unsent.iterator():
            try:
                send_verification_email(signup)
                self.stdout.write(f"  {signup.email}: verification email sent.")
            except Exception as exc:
                logger.error("Error sending verification email to %s: %s", signup.email, exc)
                self.stdout.write(f"  ERROR sending to {signup.email}: {exc}")
            count += 1

        return count
