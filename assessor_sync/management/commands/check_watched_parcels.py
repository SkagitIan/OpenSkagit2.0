"""
Nightly live check: ping Skagit Assessor API for each unique watched parcel
and queue a notification for each watching user if anything changed.

Deduplication: each parcel is fetched exactly once regardless of how many
users are watching it.  Only stores a snapshot if data has changed.
"""
from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Check watched parcels against the live Skagit Assessor API and queue change notifications."

    def handle(self, *args, **options):
        from assessor_sync.models import LiveCheckRun, ParcelLiveSnapshot
        from assessor_mcp import services as assessor
        from opportunity.models import (
            OpportunitySavedParcel,
            ParcelWatchNotification,
            UserNotificationPreference,
        )

        run = LiveCheckRun.objects.create(started_at=timezone.now(), status=LiveCheckRun.STATUS_RUNNING)
        self.stdout.write(f"LiveCheckRun #{run.pk} started.")

        # Build parcel → [user] map for all watched parcels
        parcel_to_users: dict[str, list] = {}
        for item in OpportunitySavedParcel.objects.select_related("user").all():
            parcel_to_users.setdefault(item.parcel_number, []).append(item.user)

        # User IDs with watchlist notifications enabled
        watchlist_user_ids = set(
            UserNotificationPreference.objects.filter(notify_watchlist=True)
            .values_list("user_id", flat=True)
        )

        parcels = list(parcel_to_users.keys())
        self.stdout.write(
            f"Checking {len(parcels)} unique parcel(s) for "
            f"{sum(len(v) for v in parcel_to_users.values())} watch(es)."
        )

        checked = changed = errors = notifications_queued = 0

        for parcel_number in parcels:
            try:
                details_html = assessor._post_fill_page(parcel_number, "Details")
                details = assessor.parse_details(details_html)
                live_fields = assessor.extract_tracked_fields(details)

                snapshot, created = ParcelLiveSnapshot.objects.get_or_create(
                    parcel_number=parcel_number,
                    defaults={
                        "tracked_fields": live_fields,
                        "last_checked_at": timezone.now(),
                        "last_changed_at": timezone.now(),
                    },
                )

                if created:
                    # First time — record baseline, no notification
                    checked += 1
                    self.stdout.write(f"  {parcel_number}: baseline snapshot stored.")
                    continue

                diff = assessor.diff_tracked_fields(snapshot.tracked_fields, live_fields)
                snapshot.last_checked_at = timezone.now()

                if not diff:
                    snapshot.save(update_fields=["last_checked_at"])
                    checked += 1
                    continue

                # Something changed
                self.stdout.write(f"  {parcel_number}: {len(diff)} field(s) changed — generating summary.")
                ai_summary = _generate_ai_summary(parcel_number, diff, details)

                snapshot.tracked_fields = live_fields
                snapshot.last_changed_at = timezone.now()
                snapshot.save(update_fields=["tracked_fields", "last_checked_at", "last_changed_at"])

                payload = {
                    "source": "live_check",
                    "change_type": "update",
                    "changed_fields": {
                        k: f"{v['old'] or '(none)'} → {v['new'] or '(none)'}"
                        for k, v in diff.items()
                    },
                    "ai_summary": ai_summary,
                }

                for user in parcel_to_users[parcel_number]:
                    if user.pk not in watchlist_user_ids:
                        continue
                    _, was_created = ParcelWatchNotification.objects.get_or_create(
                        user=user,
                        parcel_number=parcel_number,
                        trigger_type=ParcelWatchNotification.TRIGGER_ASSESSOR,
                        run_id=run.pk,
                        defaults={"payload": payload},
                    )
                    if was_created:
                        notifications_queued += 1

                changed += 1
                checked += 1

            except Exception as exc:
                errors += 1
                logger.error("Error checking parcel %s: %s", parcel_number, exc)
                self.stdout.write(f"  ERROR {parcel_number}: {exc}")

        run.finished_at = timezone.now()
        run.status = LiveCheckRun.STATUS_SUCCESS if errors == 0 else LiveCheckRun.STATUS_PARTIAL
        run.summary = {
            "parcels_checked": checked,
            "parcels_changed": changed,
            "errors": errors,
            "notifications_queued": notifications_queued,
        }
        run.save()
        self.stdout.write(
            f"Done. Checked={checked}, changed={changed}, "
            f"notifications_queued={notifications_queued}, errors={errors}."
        )


def _generate_ai_summary(parcel_number: str, diff: dict, details: dict) -> str:
    """Call OpenAI to produce a plain-English change summary. Returns '' on failure."""
    try:
        from openai import OpenAI

        owner = details.get("owner_name", "")
        address = details.get("site_address", "")
        context = f"Parcel {parcel_number}"
        if address:
            context += f" at {address}"
        if owner:
            context += f" (owner: {owner})"

        changes_text = "; ".join(
            f"{field.replace('_', ' ')} changed from "
            f"{v['old'] or 'none'} to {v['new'] or 'none'}"
            for field, v in diff.items()
        )

        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write brief, factual property change notifications for Skagit County parcel records. "
                        "Under 40 words. Be specific about what changed and by how much. No disclaimers."
                    ),
                },
                {"role": "user", "content": f"{context}: {changes_text}"},
            ],
            max_tokens=80,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("AI summary failed for %s: %s", parcel_number, exc)
        return ""
